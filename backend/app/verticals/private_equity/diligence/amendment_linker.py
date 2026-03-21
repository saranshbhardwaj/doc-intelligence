"""Amendment parent-document matching for PE diligence.

For each document classified as 'amendment', identifies which document in the
data room it amends using LLM reasoning over the room document list.

LLM call strategy: 1 serial + N-1 parallel with Anthropic prompt caching.
  - Call 1 (awaited):       system_prompt[room_doc_list] + user_prompt[amendment_1]
                            → cache MISS → cache WRITE → result_1
  - Calls 2..N (gathered):  system_prompt[room_doc_list] + user_prompt[amendment_K]
                            → cache HIT (same system prompt)
  Wall clock ≈ time(call_1) + time(longest parallel call)
"""
from __future__ import annotations

import asyncio
import json
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.config import settings
from app.core.llm.llm_client import LLMClient
from app.core.llm.structured_runner import StructuredLLMRunner
from app.utils.logging import logger


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class AmendmentLinkCandidate(BaseModel):
    amendment_document_id: str
    parent_document_id: Optional[str] = None  # null when no match found
    amendment_type: Optional[Literal["modifies", "supersedes", "supplements", "references"]] = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_quote: str = ""   # sentence in the amendment referencing the parent
    rationale: str = ""
    reason: Optional[str] = None  # populated when parent_document_id is null


class AmendmentLinkBatch(BaseModel):
    links: List[AmendmentLinkCandidate] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Linker
# ---------------------------------------------------------------------------

# Keywords used to filter room doc list when > max_room_docs
_CONTRACT_KEYWORDS = (
    "agreement", "contract", "msa", "spa", "nda", "lsa", "mou", "lease",
    "license", "service", "purchase", "loan", "indenture", "covenant",
)


class PEDiligenceAmendmentLinker:
    """Link amendment documents to their parent documents in the data room.

    Follows the same dependency-injection pattern as PEDiligenceClassificationAdapter.
    Pass a custom StructuredLLMRunner in tests to avoid real LLM calls.
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def link_amendments(
        self,
        amendments: List[dict],   # [{document_id, filename, text (first N chars)}]
        room_documents: List[dict],  # [{document_id, filename}] — all docs in room
    ) -> Dict[str, AmendmentLinkCandidate]:
        """Return {amendment_doc_id: AmendmentLinkCandidate} for each amendment."""
        if not amendments:
            return {}

        system_prompt = self._build_system_prompt(room_documents)
        room_doc_ids = {doc["document_id"] for doc in room_documents}

        if not amendments:
            return {}

        # Serial first call to prime Anthropic cache for the system prompt.
        first = amendments[0]
        result: Dict[str, AmendmentLinkCandidate] = {}
        result[first["document_id"]] = await self._link_one(
            amendment=first,
            system_prompt=system_prompt,
            room_doc_ids=room_doc_ids,
        )

        # Parallel calls for remaining amendments (cache hits).
        if len(amendments) > 1:
            sem = asyncio.Semaphore(settings.pe_diligence_amendment_linking_concurrency)

            async def _guarded(amendment: dict) -> tuple[str, AmendmentLinkCandidate]:
                async with sem:
                    candidate = await self._link_one(
                        amendment=amendment,
                        system_prompt=system_prompt,
                        room_doc_ids=room_doc_ids,
                    )
                return amendment["document_id"], candidate

            tasks = [_guarded(a) for a in amendments[1:]]
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            for outcome in outcomes:
                if isinstance(outcome, BaseException):
                    logger.warning(
                        "Amendment linking parallel call failed",
                        extra={"error": str(outcome)[:300]},
                    )
                    continue
                doc_id, candidate = outcome
                result[doc_id] = candidate

        logger.info(
            "Amendment linking completed",
            extra={
                "total_amendments": len(amendments),
                "linked": sum(1 for c in result.values() if c.parent_document_id),
                "unlinked": sum(1 for c in result.values() if not c.parent_document_id),
            },
        )
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_system_prompt(self, room_documents: List[dict]) -> str:
        max_docs = settings.pe_diligence_amendment_linking_max_room_docs
        docs = room_documents

        if len(docs) > max_docs:
            # Keep only contract-like docs + amendments to stay within context limits
            filtered = [
                d for d in docs
                if any(kw in (d.get("filename") or "").lower() for kw in _CONTRACT_KEYWORDS)
            ]
            if len(filtered) < len(docs):
                logger.warning(
                    "Room doc list truncated for amendment linking system prompt",
                    extra={"total": len(docs), "kept": len(filtered), "max": max_docs},
                )
            docs = filtered[:max_docs]

        doc_list = "\n".join(
            f'- document_id="{d["document_id"]}" filename="{d.get("filename", "")}"'
            for d in docs
        )

        return (
            "You are a legal document analyst specializing in PE/M&A transactions. "
            "Your task: given an amendment document, identify which document in the data room it amends.\n\n"
            "DATA ROOM DOCUMENTS:\n"
            f"{doc_list}\n\n"
            "INSTRUCTIONS:\n"
            "1. Read the amendment text and identify any reference to the parent agreement.\n"
            "2. Match it to a document_id from the data room list above.\n"
            "3. If the document is an 'Amended and Restated' version, use amendment_type='supersedes'.\n"
            "   If it modifies specific clauses, use 'modifies'. "
            "   If it adds obligations, use 'supplements'. "
            "   If it only references (no substantive change), use 'references'.\n"
            "4. Quote the exact sentence(s) referencing the parent in evidence_quote.\n"
            "5. If you cannot determine the parent document with confidence, "
            "   set parent_document_id=null and reason='no_parent_matched'.\n"
            "6. Set confidence between 0.0 and 1.0.\n"
            "Return a JSON object matching the AmendmentLinkBatch schema."
        )

    async def _link_one(
        self,
        *,
        amendment: dict,
        system_prompt: str,
        room_doc_ids: set[str],
    ) -> AmendmentLinkCandidate:
        doc_id = amendment["document_id"]
        filename = amendment.get("filename", "")
        text = (amendment.get("text") or "")[:settings.pe_diligence_amendment_linking_input_chars]

        user_content = json.dumps(
            {
                "amendment_document_id": doc_id,
                "filename": filename,
                "text_excerpt": text,
            },
            ensure_ascii=False,
        )

        try:
            raw = await self.runner.run_structured(
                user_content=user_content,
                system_prompt=system_prompt,
                pydantic_model=AmendmentLinkBatch,
                use_cache=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Amendment LLM call failed",
                extra={"document_id": doc_id, "error": str(exc)[:300]},
            )
            return AmendmentLinkCandidate(
                amendment_document_id=doc_id,
                parent_document_id=None,
                confidence=0.0,
                reason="llm_error",
            )

        links: list = raw.get("data", {}).get("links", [])
        candidate_dict = next(
            (lnk for lnk in links if lnk.get("amendment_document_id") == doc_id),
            links[0] if links else None,
        )

        if not candidate_dict:
            return AmendmentLinkCandidate(
                amendment_document_id=doc_id,
                parent_document_id=None,
                confidence=0.0,
                reason="no_parent_matched",
            )

        # Ensure amendment_document_id is set correctly
        candidate_dict["amendment_document_id"] = doc_id

        # Anchor gate: parent must exist in the room
        parent_id = candidate_dict.get("parent_document_id")
        if parent_id and parent_id not in room_doc_ids:
            logger.warning(
                "Amendment parent not in room doc list; rejecting link",
                extra={"amendment_doc_id": doc_id, "returned_parent_id": parent_id},
            )
            candidate_dict["parent_document_id"] = None
            candidate_dict["reason"] = "parent_not_in_room"
            candidate_dict["confidence"] = 0.0

        try:
            candidate = AmendmentLinkCandidate(**candidate_dict)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Amendment link candidate schema validation failed",
                extra={"document_id": doc_id, "error": str(exc)[:300]},
            )
            return AmendmentLinkCandidate(
                amendment_document_id=doc_id,
                parent_document_id=None,
                confidence=0.0,
                reason="schema_error",
            )

        # Confidence gate: low-confidence links are flagged for review
        # (stored but surfaced to reviewer; doesn't block the link)
        if candidate.parent_document_id and candidate.confidence < 0.6:
            logger.info(
                "Low-confidence amendment link — reviewer should verify",
                extra={"document_id": doc_id, "confidence": candidate.confidence},
            )

        return candidate
