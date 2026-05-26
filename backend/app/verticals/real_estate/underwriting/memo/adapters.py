"""Thin adapters between the narrator and the real Anthropic SDK + RAG service.

Kept in their own module so the narrator can be unit-tested against fakes without
pulling in the heavy ``LLMClient`` or RAG dependencies.

Design notes
------------
- ``AnthropicMemoLLM`` wraps ``client.messages.parse`` (structured-output path).
  The anthropic SDK version pinned in requirements.txt (>=0.77.0) exposes
  ``messages.parse`` on the *sync* client and uses ``asyncio.to_thread`` to run it
  in a thread pool — matching how the rest of this codebase calls the SDK
  (see ``llm_client.py::extract_structured_data_with_schema``).

- ``RagRetriever`` delegates to ``HybridRetriever`` directly (the same component
  used by ``WorkflowRetriever``) rather than going through the full ``RAGService``,
  which is a chat-flow orchestrator and has no document-scoped retrieval method.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from anthropic import Anthropic
from httpx import Timeout
from sqlalchemy.orm import Session

from app.config import settings
from app.core.rag.hybrid_retriever import HybridRetriever
from app.core.rag.retrieval_query import RetrievalQuery
from .schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class AnthropicMemoLLM:
    """Wraps ``client.messages.parse`` to match the narrator's ``llm.parse(...)`` shape.

    Uses the synchronous ``Anthropic`` client dispatched via ``asyncio.to_thread``,
    consistent with how ``LLMClient.extract_structured_data_with_schema`` works.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 120.0,
    ):
        timeout = Timeout(
            timeout=timeout_seconds,
            read=timeout_seconds,
            write=10.0,
            connect=5.0,
        )
        self._client = Anthropic(
            api_key=api_key or settings.anthropic_api_key,
            timeout=timeout,
        )
        # Use the synthesis model (Haiku 4.5) — memo narration is structured-prose
        # synthesis from already-extracted data, same shape as workflow synthesis.
        # Override to settings.llm_model (Sonnet) here if quality is insufficient.
        self.model = model or settings.synthesis_llm_model

        # Per-instance usage accumulator. The Celery task reads these after all
        # narrator calls finish to record Prometheus metrics + persist to DB.
        self._usage_total: dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "calls": 0,
        }

    def get_usage_totals(self) -> dict:
        """Return cumulative token usage across all parse() calls on this instance.

        Shape: {input_tokens, output_tokens, cache_creation_input_tokens,
                cache_read_input_tokens, calls, model}.
        """
        return {**self._usage_total, "model": self.model}

    async def parse(
        self,
        system: str,
        messages: list[dict[str, Any]],
        output_format: type,
        max_tokens: int,
    ) -> Any:
        """Call ``messages.parse`` and return the validated Pydantic instance.

        Also accumulates per-call ``usage`` into ``self._usage_total`` so the
        task can record totals after all narration completes.
        """
        response = await asyncio.to_thread(
            self._client.messages.parse,
            model=self.model,
            system=system,
            messages=messages,
            output_format=output_format,
            max_tokens=max_tokens,
            temperature=0.0,
        )

        # Accumulate usage before returning (even if parsed_output is None and we
        # raise — the cost was incurred).
        usage = getattr(response, "usage", None)
        if usage is not None:
            self._usage_total["calls"] += 1
            self._usage_total["input_tokens"] += getattr(usage, "input_tokens", 0) or 0
            self._usage_total["output_tokens"] += getattr(usage, "output_tokens", 0) or 0
            self._usage_total["cache_creation_input_tokens"] += (
                getattr(usage, "cache_creation_input_tokens", 0) or 0
            )
            self._usage_total["cache_read_input_tokens"] += (
                getattr(usage, "cache_read_input_tokens", 0) or 0
            )

        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            stop_reason = getattr(response, "stop_reason", None)
            raise RuntimeError(
                f"LLM returned no parsed_output for memo section; "
                f"stop_reason={stop_reason!r}, model={self.model!r}"
            )
        return parsed


class RagRetriever:
    """Wraps ``HybridRetriever`` to return ``RetrievedChunk`` objects scoped to one run.

    ``HybridRetriever`` is the same retrieval component used by ``WorkflowRetriever``
    — it runs hybrid (semantic + BM25) search filtered to a list of document IDs.
    The caller (narrator) passes a ``section_key`` only for observability logging.
    """

    def __init__(self, db: Session):
        self._db = db
        self._hybrid = HybridRetriever(db)
        # Cache result of has_any_chunks per memo run so the second RAG section
        # (market_overview) doesn't repeat the COUNT query.
        self._chunks_present_cache: dict[tuple, bool] = {}

    def _has_any_chunks(self, document_ids: list[str]) -> bool:
        """Cheap pre-check: do any of these documents have indexed chunks?

        Avoids paying for an embedding call on a query that will return zero
        results. Cached per RagRetriever instance.
        """
        key = tuple(sorted(document_ids))
        if key in self._chunks_present_cache:
            return self._chunks_present_cache[key]
        try:
            from app.db_models_chat import DocumentChunk
            from sqlalchemy import select, func
            stmt = select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.document_id.in_(document_ids)
            ).limit(1)
            count = int(self._db.execute(stmt).scalar() or 0)
            result = count > 0
        except Exception:
            logger.exception("has_any_chunks check failed; assuming no chunks")
            result = False
        self._chunks_present_cache[key] = result
        return result

    def retrieve(
        self,
        *,
        query: str,
        document_ids: list[str],
        top_n: int,
        section_key: str,
    ) -> list[RetrievedChunk]:
        """Run hybrid retrieval for *query* restricted to *document_ids*.

        Args:
            query: The retrieval query string.
            document_ids: Documents to search (the memo's source docs).
            top_n: Maximum number of chunks to return after retrieval.
            section_key: Used only for diagnostic logging.

        Returns:
            A list of ``RetrievedChunk`` instances (empty on error or no docs).
        """
        if not document_ids:
            return []

        # Short-circuit when no chunks exist for these docs — saves the embedding
        # round-trip on every RAG section when the OM isn't indexed.
        if not self._has_any_chunks(document_ids):
            logger.info(
                "Skipping RAG for memo section %s — no indexed chunks for docs %s",
                section_key,
                document_ids,
            )
            return []

        rq = RetrievalQuery.from_text(query)

        try:
            hits = self._hybrid.retrieve(
                rq=rq,
                collection_id=None,
                top_k=top_n,
                document_ids=document_ids,
            )
        except Exception:
            logger.exception(
                "RAG retrieval failed for memo section %s", section_key
            )
            return []

        chunks: list[RetrievedChunk] = []
        for h in hits:
            doc_id = h.get("document_id") or ""
            page = h.get("page_number") or 1
            text = h.get("text") or ""
            if not doc_id or not text:
                continue
            chunks.append(RetrievedChunk(doc_id=doc_id, page=int(page), text=text))

        logger.debug(
            "RagRetriever: section=%s query=%r doc_ids=%d hits=%d",
            section_key,
            query[:60],
            len(document_ids),
            len(chunks),
        )
        return chunks
