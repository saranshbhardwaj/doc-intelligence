"""LLM-backed structured clause extraction for PE diligence (stage 4b).

Flow:
  1. Receive regex pre-filter hits (List[dict] from _extract_clause_hits)
  2. Group by clause_type → look up relevant playbooks
  3. For each playbook, assemble candidate chunks + fill prompt template
  4. Call LLM via StructuredLLMRunner → get structured JSON per clause
  5. Return List[dict] ready to be stored in pe_diligence_clauses

Key design decisions:
  - System prompt = playbook template (static, cache-eligible)
  - User content = candidate chunk text (varies per doc)
  - Uses asyncio.gather for concurrent playbook calls (capped)
  - Falls back gracefully on any LLM error (logs + continues)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.config import settings
from app.core.llm.llm_client import LLMClient
from app.core.llm.structured_runner import StructuredLLMRunner
from app.core.rag.hybrid_retriever import HybridRetriever
from app.core.rag.reranker import get_reranker
from app.utils.logging import logger


# ─── Pydantic schema for LLM output ─────────────────────────────────────────


class ExtractedClause(BaseModel):
    clause_type: str
    extracted_fields: Dict[str, Any] = Field(default_factory=dict)
    raw_quote: Optional[str] = None
    interpretation: Optional[str] = None
    confidence: Optional[float] = None


class ExtractedClauseBatch(BaseModel):
    clauses: List[ExtractedClause] = Field(default_factory=list)


# ─── Helper ──────────────────────────────────────────────────────────────────

# Mapping from clause_type to natural-language query terms for hybrid search
_CLAUSE_TYPE_PHRASES = {
    "representations_warranties": "representations and warranties",
    "indemnification_cap": "indemnification cap limitation of liability",
    "material_adverse_change": "material adverse change MAC MAE",
    "closing_conditions": "conditions to closing condition precedent",
    "purchase_price_adjustment": "purchase price adjustment working capital true-up",
    "earnout_mechanics": "earnout contingent consideration earn-out",
    "basket_deductible": "basket deductible threshold",
    "survival_period": "survival period representations warranties",
    "change_of_control": "change of control consent acquisition",
    "assignment_consent": "assignment consent transfer restriction",
    "novation": "novation assignment of rights",
    "drag_along": "drag along tag along",
    "tag_along": "tag along drag along",
    "customer_contract": "master service agreement customer agreement",
    "revenue_share": "revenue share revenue sharing",
    "exclusivity": "exclusivity exclusive sole source",
    "mfn_pricing": "most favored nation MFN pricing",
    "termination": "termination for convenience termination rights",
    "leverage_ratio": "leverage ratio net debt EBITDA covenant",
    "interest_coverage": "interest coverage FCCR DSCR times interest earned",
    "event_of_default": "event of default cross default acceleration",
    "prepayment": "prepayment penalty make whole call premium",
    "ip_assignment": "IP assignment work for hire intellectual property",
    "license_terms": "license licensing royalty",
    "non_compete": "non compete non-compete",
    "non_solicit": "non solicit non-solicit",
    "employment_term": "employment agreement employment term",
    "severance": "severance separation package",
    "equity_vesting": "vesting equity stock option RSU profits interest",
}


def _playbook_query(playbook: dict) -> str:
    """Build a natural-language query from playbook clause types."""
    clause_types = playbook.get("clause_types") or []
    phrases = [
        _CLAUSE_TYPE_PHRASES.get(ct, ct.replace("_", " "))
        for ct in clause_types
    ]
    return " ".join(phrases)


def _build_candidate_text(hits: List[dict], max_chunks: int) -> str:
    """Format candidate hits into a numbered text block for the LLM prompt."""
    lines = []
    seen_chunks: set[str] = set()
    count = 0
    for hit in hits:
        ev = hit.get("evidence", {})
        chunk_id = ev.get("source_chunk_id") or ""
        quote = ev.get("quote", "").strip()
        if not quote:
            continue
        # Deduplicate by chunk_id
        if chunk_id and chunk_id in seen_chunks:
            continue
        if chunk_id:
            seen_chunks.add(chunk_id)

        doc_id = ev.get("source_document_id", "")
        page = ev.get("source_page_number") or "?"
        lines.append(
            f"[Excerpt {count + 1}] (doc:{doc_id[:8]}... page:{page})\n{quote}"
        )
        count += 1
        if count >= max_chunks:
            break
    return "\n\n---\n\n".join(lines)


def _build_system_prompt(playbook: dict) -> str:
    """Build the LLM system prompt from a playbook record.

    Returns structured JSON instruction wrapping the playbook's prompt_template.
    """
    template = playbook.get("prompt_template") or ""
    output_schema = playbook.get("output_schema") or {}
    schema_str = json.dumps(output_schema, indent=2)
    return (
        f"{template}\n\n"
        "Return your answer as a JSON object with a 'clauses' key containing an array. "
        "Each element must match this JSON Schema:\n"
        f"{schema_str}\n"
        "Only include clauses you found in the excerpts. "
        "If no relevant clauses are found, return {\"clauses\": []}."
    )


# ─── Main extractor class ────────────────────────────────────────────────────


class LLMClauseExtractor:
    """Structured LLM clause extractor using playbook prompts."""

    def __init__(self, runner: StructuredLLMRunner | None = None):
        if runner is None:
            llm_client = LLMClient(
                api_key=settings.anthropic_api_key,
                model=settings.synthesis_llm_model,
                max_tokens=settings.synthesis_llm_max_tokens,
                max_input_chars=settings.llm_max_input_chars,
                timeout_seconds=settings.synthesis_llm_timeout_seconds,
            )
            runner = StructuredLLMRunner(llm_client)
        self.runner = runner
        self.min_confidence = settings.pe_diligence_llm_clause_min_confidence
        self.max_chunks_per_type = settings.pe_diligence_llm_clause_max_chunks_per_type

    async def _extract_for_playbook(
        self,
        playbook: dict,
        hits_by_type: Dict[str, List[dict]],
        db: Session,
        document_ids: List[str],
        room_id: str,
        run_id: str,
    ) -> List[dict]:
        """Run one playbook against its candidate hits + augmented hybrid search results. Returns clause dicts."""
        clause_types: List[str] = playbook.get("clause_types") or []
        relevant_hits: List[dict] = []
        for ct in clause_types:
            relevant_hits.extend(hits_by_type.get(ct, []))

        # Augment with hybrid retrieval: find semantically similar chunks the regex missed
        hybrid_chunks_added = 0
        try:
            retriever = HybridRetriever(db)
            playbook_query = _playbook_query(playbook)
            hybrid_results = retriever.retrieve(
                query=playbook_query,
                document_ids=document_ids,
                top_k=self.max_chunks_per_type * 3,  # Fetch more, will rerank and cap later
            )

            # Track which chunks we already have from regex
            seen_chunk_ids = {h.get("evidence", {}).get("source_chunk_id") for h in relevant_hits if h.get("evidence")}

            # Merge hybrid results (avoid duplicates)
            for hybrid_chunk in hybrid_results:
                chunk_id = str(hybrid_chunk.get("id", ""))
                if chunk_id and chunk_id not in seen_chunk_ids:
                    seen_chunk_ids.add(chunk_id)
                    # Wrap hybrid chunk to match clause_hit structure
                    relevant_hits.append({
                        "clause_type": clause_types[0] if clause_types else "unknown",
                        "evidence": {
                            "source_chunk_id": chunk_id,
                            "source_document_id": str(hybrid_chunk.get("document_id", "")),
                            "source_page_number": hybrid_chunk.get("page_number"),
                            "quote": (hybrid_chunk.get("text") or "")[:1000],
                        },
                        "_from_hybrid": True,
                    })
                    hybrid_chunks_added += 1
        except Exception as hybrid_exc:
            logger.warning(
                "Hybrid retrieval failed for playbook; continuing with regex hits only",
                extra={
                    "playbook_slug": playbook.get("slug"),
                    "room_id": room_id,
                    "error": str(hybrid_exc)[:200],
                },
            )

        if not relevant_hits:
            return []

        # Rerank all hits if we have more than max_chunks_per_type
        if len(relevant_hits) > self.max_chunks_per_type:
            try:
                reranker = get_reranker()
                if reranker:
                    playbook_query = _playbook_query(playbook)
                    # Extract quotes for reranking
                    quotes = [
                        (h.get("evidence", {}).get("quote", "") or "")[:500]
                        for h in relevant_hits
                    ]
                    if quotes:
                        scores = reranker.predict(
                            [(playbook_query, quote) for quote in quotes]
                        )
                        # Sort by score descending
                        ranked = sorted(
                            zip(scores, relevant_hits),
                            key=lambda x: -x[0]
                        )
                        relevant_hits = [h for _, h in ranked[:self.max_chunks_per_type]]
                    else:
                        relevant_hits = relevant_hits[:self.max_chunks_per_type]
                else:
                    relevant_hits = relevant_hits[:self.max_chunks_per_type]
            except Exception as rerank_exc:
                logger.warning(
                    "Reranking failed for playbook; using unsorted order",
                    extra={
                        "playbook_slug": playbook.get("slug"),
                        "room_id": room_id,
                        "error": str(rerank_exc)[:200],
                    },
                )
                relevant_hits = relevant_hits[:self.max_chunks_per_type]

        # Build the candidate text and prompt
        candidate_text = _build_candidate_text(relevant_hits, self.max_chunks_per_type)
        if not candidate_text.strip():
            return []

        # Log chunk source breakdown
        regex_hits = [h for h in relevant_hits if not h.get("_from_hybrid")]
        hybrid_hits = [h for h in relevant_hits if h.get("_from_hybrid")]
        logger.debug(
            "Playbook clause extraction chunk sources",
            extra={
                "playbook_slug": playbook.get("slug"),
                "room_id": room_id,
                "regex_hits": len(regex_hits),
                "hybrid_hits": len(hybrid_hits),
                "total_chunks": len(relevant_hits),
            },
        )

        # Fill {candidate_chunks} placeholder if present
        system_prompt = _build_system_prompt(playbook)
        user_content = f"Extract clauses from the following excerpts:\n\n{candidate_text}"

        try:
            result = await self.runner.run_structured(
                user_content=user_content,
                system_prompt=system_prompt,
                pydantic_model=ExtractedClauseBatch,
                use_cache=False,
            )
        except Exception as exc:
            logger.warning(
                "LLM clause extraction failed for playbook",
                extra={
                    "playbook_slug": playbook.get("slug"),
                    "room_id": room_id,
                    "run_id": run_id,
                    "error": str(exc)[:300],
                },
            )
            return []

        raw_clauses = result.get("data", {}).get("clauses", [])
        out: List[dict] = []
        for raw in raw_clauses:
            if not isinstance(raw, dict):
                continue
            clause_type = raw.get("clause_type", "")
            confidence = raw.get("confidence")
            if confidence is not None and float(confidence) < self.min_confidence:
                continue

            # Find the best matching evidence hit for source attribution
            matching_hits = hits_by_type.get(clause_type, relevant_hits)
            primary_hit = matching_hits[0]["evidence"] if matching_hits else {}

            # Extract fields minus the top-level keys we promote
            extracted_fields = {
                k: v for k, v in raw.items()
                if k not in {"clause_type", "raw_quote", "interpretation", "confidence"}
            }

            out.append(
                {
                    "room_id": room_id,
                    "analysis_run_id": run_id,
                    "source_document_id": primary_hit.get("source_document_id"),
                    "source_chunk_id": primary_hit.get("source_chunk_id"),
                    "source_page_number": primary_hit.get("source_page_number"),
                    "clause_type": clause_type,
                    "playbook_id": playbook.get("slug"),
                    "extracted_fields": extracted_fields,
                    "raw_quote": (raw.get("raw_quote") or "")[:2000],
                    "interpretation": raw.get("interpretation"),
                    "confidence": confidence,
                    "engine": "llm_v1",
                }
            )
        return out

    async def extract_all(
        self,
        *,
        clause_hits: List[dict],
        playbooks: List[dict],
        db: Session,
        document_ids: List[str],
        room_id: str,
        run_id: str,
    ) -> List[dict]:
        """Run all applicable playbooks against clause hits + hybrid retrieval concurrently.

        Args:
            clause_hits: regex hits from _extract_clause_hits
            playbooks: list of playbook dicts (from DB or SYSTEM_PLAYBOOKS)
            db: SQLAlchemy session for HybridRetriever
            document_ids: list of document IDs in the room (for scoping hybrid retrieval)
            room_id, run_id: for logging + output rows

        Returns:
            Flat list of clause dicts ready for repo.save_clauses()
        """
        if not clause_hits or not playbooks:
            return []

        # Index hits by clause_type for fast lookup
        hits_by_type: Dict[str, List[dict]] = {}
        for hit in clause_hits:
            ct = hit.get("clause_type", "")
            hits_by_type.setdefault(ct, []).append(hit)

        # Run each playbook concurrently
        tasks = [
            self._extract_for_playbook(pb, hits_by_type, db, document_ids, room_id, run_id)
            for pb in playbooks
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_clauses: List[dict] = []
        for res in results:
            if isinstance(res, Exception):
                logger.warning(
                    "LLM clause extraction playbook task raised",
                    extra={"room_id": room_id, "error": str(res)[:300]},
                )
                continue
            all_clauses.extend(res)

        logger.info(
            "LLM clause extraction complete",
            extra={
                "room_id": room_id,
                "run_id": run_id,
                "playbooks_run": len(playbooks),
                "clauses_extracted": len(all_clauses),
            },
        )
        return all_clauses
