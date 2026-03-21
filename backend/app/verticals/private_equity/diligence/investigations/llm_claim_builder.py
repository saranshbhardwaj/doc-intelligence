"""LLM-augmented claim builder for diligence investigations.

Runs after the deterministic regex claim builder to catch clauses that
regex cannot match (paraphrased language, unusual legal phrasing, etc.).

Design:
    - Single Responsibility: only extracts claim candidates from chunks via LLM.
      Does NOT handle merging, persistence, or adjudication.
    - Anchor gate: every LLM claim must reference a valid chunk_id from the
      input set.  Claims without anchors are rejected with an audit event.
    - Trust boundary: LLM claims always get ``verification_status: "needs_review"``
      regardless of confidence.  They expand recall, never auto-accept.
    - Prompt caching: system prompt uses ``cache_control: ephemeral`` (5-min TTL,
      ~10x cheaper on repeated calls within the same investigation run).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Literal, Optional, Sequence, Set

from pydantic import BaseModel, Field

from app.config import settings
from app.core.llm.llm_client import LLMClient
from app.core.llm.structured_runner import StructuredLLMRunner
from app.utils.logging import logger


# ---------------------------------------------------------------------------
# Pydantic schema for structured LLM output
# ---------------------------------------------------------------------------

class LLMClaimCandidate(BaseModel):
    """A single claim candidate extracted by the LLM."""
    chunk_id: str = Field(..., description="The chunk_id from the input that contains the evidence")
    claim_key: str = Field(..., description="Claim identifier matching the investigation template")
    claim_text: str = Field(..., max_length=500, description="One-sentence claim statement")
    stance: Literal["supported", "contradicted", "inconclusive"] = Field(
        ..., description="Whether the evidence supports, contradicts, or is inconclusive for the claim"
    )
    evidence_quote: str = Field(..., max_length=600, description="Verbatim quote from the chunk")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in this extraction")
    rationale: Optional[str] = Field(
        default=None, max_length=300,
        description="Brief explanation for why this clause is relevant",
    )


class LLMClaimBatch(BaseModel):
    """Batch of claim candidates from one LLM call."""
    claims: List[LLMClaimCandidate] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# System prompt (cached via Anthropic ephemeral cache)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEMPLATE = """\
You are a PE diligence analyst reviewing document chunks from a virtual data room.

INVESTIGATION: {investigation_title}
QUESTION: {investigation_question}

ALLOWED CLAIM KEYS (only use these):
{claim_keys_block}

TASK:
Review each chunk below. If a chunk contains language relevant to the investigation
question — even if the phrasing is unusual, paraphrased, or uses legal synonyms —
extract a claim candidate.

RULES:
1. chunk_id MUST exactly match one of the input chunk IDs.
2. evidence_quote MUST be a verbatim substring from the chunk text (do not paraphrase).
3. Only extract claims for language that is genuinely relevant to the investigation.
4. If a chunk contains no relevant language, do not force a claim.
5. Be conservative with confidence: use 0.7+ only for clear, explicit clauses.
6. For indirect or implied language, use confidence 0.4-0.6.
7. If you are uncertain whether language is relevant, still extract it with low
   confidence — false positives are reviewed, false negatives are missed forever.

Return an empty claims list if no chunks contain relevant language.\
"""

# Claim keys allowed per investigation type.
_CLAIM_KEYS_BY_TYPE: Dict[str, List[str]] = {
    "change_of_control_exposure": [
        "contracts_require_consent_on_coc",
        "termination_penalty_exposure_on_coc",
        "no_explicit_coc_risk_detected",
        "coverage_insufficient_needs_legal_review",
    ],
}


def _get_allowed_claim_keys(investigation_type: str) -> List[str]:
    """Return allowed claim keys for an investigation type."""
    return _CLAIM_KEYS_BY_TYPE.get(investigation_type, [])


def _build_system_prompt(
    *,
    investigation_type: str,
    investigation_title: str,
    investigation_question: str,
) -> str:
    """Build the system prompt for LLM claim extraction."""
    claim_keys = _get_allowed_claim_keys(investigation_type)
    claim_keys_block = "\n".join(f"  - {key}" for key in claim_keys) if claim_keys else "  (none defined)"
    return _SYSTEM_PROMPT_TEMPLATE.format(
        investigation_title=investigation_title,
        investigation_question=investigation_question or "N/A",
        claim_keys_block=claim_keys_block,
    )


def _build_user_content(chunks: Sequence[dict], max_chars: int = 80_000) -> str:
    """Serialize chunks as JSON for the LLM user message.

    Truncates individual chunk text if the total would exceed max_chars,
    ensuring every chunk gets at least some representation.
    """
    items = []
    total_chars = 0
    per_chunk_budget = max(500, max_chars // max(len(chunks), 1))

    for chunk in chunks:
        text = str(chunk.get("text") or "")
        if len(text) > per_chunk_budget:
            text = text[:per_chunk_budget] + "... [truncated]"
        items.append({
            "chunk_id": str(chunk.get("id") or ""),
            "document_id": str(chunk.get("document_id") or ""),
            "page_number": chunk.get("page_number"),
            "text": text,
        })
        total_chars += len(text)
        if total_chars >= max_chars:
            break

    return json.dumps({"chunks": items}, ensure_ascii=False)


def _cache_key(chunk_ids: Sequence[str], investigation_type: str) -> str:
    """Deterministic cache key for LLM results."""
    payload = f"{investigation_type}|{'|'.join(sorted(chunk_ids))}"
    return f"pe_inv_llm_claims:{hashlib.sha256(payload.encode()).hexdigest()[:24]}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class LLMClaimBuilder:
    """Extracts claim candidates from chunks using LLM structured output.

    Usage::

        builder = LLMClaimBuilder()
        candidates, rejected = await builder.augment_claims(
            chunks=unmatched_chunks,
            investigation_type="change_of_control_exposure",
            investigation_title="Change-of-Control Exposure",
            investigation_question="Do contracts create CoC risk?",
        )
    """

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

    async def augment_claims(
        self,
        *,
        chunks: Sequence[dict],
        investigation_type: str,
        investigation_title: str,
        investigation_question: str,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Extract LLM claim candidates from chunks.

        Args:
            chunks: Chunks that produced NO regex hits (unmatched evidence).
            investigation_type: Template type key.
            investigation_title: Human-readable title.
            investigation_question: The investigation question.

        Returns:
            (accepted_claims, rejected_claims) where each claim is a dict
            ready for merging into the investigation claim set.

        Accepted claims always have:
            - source_workers: ["llm"]
            - verification_status: "needs_review"
        """
        if not chunks:
            return [], []

        valid_chunk_ids: Set[str] = {
            str(c.get("id") or "") for c in chunks if c.get("id")
        }
        allowed_claim_keys = set(_get_allowed_claim_keys(investigation_type))

        system_prompt = _build_system_prompt(
            investigation_type=investigation_type,
            investigation_title=investigation_title,
            investigation_question=investigation_question,
        )
        user_content = _build_user_content(chunks)

        try:
            result = await self.runner.run_structured(
                user_content=user_content,
                system_prompt=system_prompt,
                pydantic_model=LLMClaimBatch,
                use_cache=True,  # Prompt caching enabled
            )
        except Exception as exc:
            logger.warning(
                "LLM claim augmentation failed; falling back to regex-only claims",
                extra={
                    "investigation_type": investigation_type,
                    "chunk_count": len(chunks),
                    "error": str(exc)[:500],
                },
            )
            return [], []

        raw_claims = result.get("data", {}).get("claims", [])

        accepted: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        # Dedup: keep highest confidence per claim_key
        best_by_key: Dict[str, Dict[str, Any]] = {}
        evidence_by_key: Dict[str, List[dict]] = {}

        for candidate in raw_claims:
            chunk_id = candidate.get("chunk_id", "")
            claim_key = candidate.get("claim_key", "")
            confidence = float(candidate.get("confidence") or 0.0)

            # Anchor gate: chunk_id must exist in input
            if chunk_id not in valid_chunk_ids:
                rejected.append({
                    "reason": "invalid_chunk_id",
                    "chunk_id": chunk_id,
                    "claim_key": claim_key,
                    "confidence": confidence,
                })
                continue

            # Claim key gate: must be an allowed key
            if allowed_claim_keys and claim_key not in allowed_claim_keys:
                rejected.append({
                    "reason": "invalid_claim_key",
                    "chunk_id": chunk_id,
                    "claim_key": claim_key,
                    "confidence": confidence,
                })
                continue

            # Find the source chunk for evidence metadata
            source_chunk = next(
                (c for c in chunks if str(c.get("id") or "") == chunk_id),
                {},
            )

            evidence = {
                "source_document_id": source_chunk.get("document_id"),
                "source_chunk_id": chunk_id,
                "source_page_number": source_chunk.get("page_number"),
                "char_start": None,
                "char_end": None,
                "quote": str(candidate.get("evidence_quote") or "")[:900],
                "confidence": confidence,
                "metadata_json": {
                    "signal": "llm_extraction",
                    "label": candidate.get("rationale") or "LLM-detected clause",
                    "negation_detected": False,
                    "bbox": (
                        source_chunk.get("bbox")
                        if isinstance(source_chunk.get("bbox"), dict) else None
                    ),
                    "source_page_range": source_chunk.get("page_range") or [],
                },
            }

            # Track best per claim_key; collect all evidence
            prev = best_by_key.get(claim_key)
            if prev is None or confidence > float(prev.get("confidence") or 0.0):
                best_by_key[claim_key] = {
                    "claim_key": claim_key,
                    "claim_text": str(candidate.get("claim_text") or ""),
                    "stance": candidate.get("stance") or "inconclusive",
                    "severity": "medium",
                    "verification_status": "needs_review",  # ALWAYS
                    "confidence": confidence,
                    "source_workers": ["llm"],
                    "metadata_json": {
                        "version": "llm_claims_v1",
                        "decision_reason_codes": ["llm_extracted"],
                        "rationale": candidate.get("rationale"),
                    },
                }
            evidence_by_key.setdefault(claim_key, []).append(evidence)

        # Build final accepted list with evidence attached
        for claim_key, claim in best_by_key.items():
            claim["_evidence"] = evidence_by_key.get(claim_key, [])[:5]
            accepted.append(claim)

        logger.info(
            "LLM claim augmentation completed",
            extra={
                "investigation_type": investigation_type,
                "chunks_sent": len(chunks),
                "raw_candidates": len(raw_claims),
                "accepted": len(accepted),
                "rejected": len(rejected),
            },
        )
        return accepted, rejected


def merge_llm_claims_into(
    *,
    regex_claims: List[dict],
    regex_evidence: Dict[str, List[dict]],
    llm_claims: List[dict],
) -> tuple[List[dict], Dict[str, List[dict]]]:
    """Merge LLM claims into the regex claim set.

    Rules:
        - Regex claim wins if same claim_key exists (regex is higher trust).
        - LLM evidence is appended to existing claim's evidence if key matches.
        - New LLM claim keys (not in regex set) are added as new claims.

    Returns:
        (merged_claims, merged_evidence) — same structure as
        build_change_of_control_claims output.
    """
    merged_claims = list(regex_claims)
    merged_evidence = {k: list(v) for k, v in regex_evidence.items()}
    existing_keys = {c["claim_key"] for c in merged_claims}

    for llm_claim in llm_claims:
        claim_key = llm_claim["claim_key"]
        llm_ev = llm_claim.pop("_evidence", [])

        if claim_key in existing_keys:
            # Regex claim exists — append LLM evidence but don't override claim.
            merged_evidence.setdefault(claim_key, []).extend(llm_ev)
            # Tag the existing claim that LLM also found evidence.
            for c in merged_claims:
                if c["claim_key"] == claim_key:
                    meta = dict(c.get("metadata_json") or {})
                    workers = list(c.get("source_workers") or ["rule"])
                    if "llm" not in workers:
                        workers.append("llm")
                    meta["llm_augmented"] = True
                    c["metadata_json"] = meta
                    c["source_workers"] = workers
                    break
        else:
            # New claim key from LLM — add as new claim.
            merged_claims.append(llm_claim)
            merged_evidence[claim_key] = llm_ev
            existing_keys.add(claim_key)

    return merged_claims, merged_evidence
