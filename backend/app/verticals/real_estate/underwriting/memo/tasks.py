"""Celery task: generate an IC credit memo from a completed underwriting run."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from celery import shared_task

from app.database import SessionLocal
from app.repositories.re_memo_repository import ReMemoRepository
from app.repositories.re_underwriting_repo import UnderwritingRunRepository
from app.services.job_tracker import JobProgressTracker
from app.core.storage.cloudflare_r2 import get_r2_storage
from app.utils.costs import compute_llm_cost
from app.utils.metrics import (
    LLM_CACHE_HITS,
    LLM_CACHE_MISSES,
    LLM_COST_USD,
    LLM_REQUESTS_TOTAL,
    LLM_TOKEN_USAGE,
)

from .adapters import AnthropicMemoLLM, RagRetriever
from .data_assembler import build_memo_context
from .docx_renderer import render_memo_docx
from .filenames import build_memo_filename
from .narrator import narrate_all_sections, collect_section_warnings

logger = logging.getLogger(__name__)

_MEMO_OP_TYPE = "credit_memo"


def _record_memo_llm_metrics(usage: dict) -> None:
    """Mirror TemplateFillRun's Prometheus pattern for the credit memo flow."""
    model = usage.get("model") or "unknown"
    input_tokens = usage.get("input_tokens", 0) or 0
    output_tokens = usage.get("output_tokens", 0) or 0
    cache_creation = usage.get("cache_creation_input_tokens", 0) or 0
    cache_read = usage.get("cache_read_input_tokens", 0) or 0
    calls = usage.get("calls", 0) or 0
    try:
        for _ in range(calls):
            LLM_REQUESTS_TOTAL.labels(model=model, operation_type=_MEMO_OP_TYPE).inc()
        if input_tokens:
            LLM_TOKEN_USAGE.labels(model=model, token_type="input", operation_type=_MEMO_OP_TYPE).inc(input_tokens)
        if output_tokens:
            LLM_TOKEN_USAGE.labels(model=model, token_type="output", operation_type=_MEMO_OP_TYPE).inc(output_tokens)
        if cache_creation:
            LLM_TOKEN_USAGE.labels(model=model, token_type="cache_write", operation_type=_MEMO_OP_TYPE).inc(cache_creation)
        if cache_read:
            LLM_TOKEN_USAGE.labels(model=model, token_type="cache_read", operation_type=_MEMO_OP_TYPE).inc(cache_read)
            LLM_CACHE_HITS.labels(operation_type=_MEMO_OP_TYPE).inc()
        else:
            LLM_CACHE_MISSES.labels(operation_type=_MEMO_OP_TYPE).inc()
        cost = compute_llm_cost(model, input_tokens, output_tokens)
        if cost:
            LLM_COST_USD.labels(model=model, operation_type=_MEMO_OP_TYPE).inc(cost)
    except Exception:
        logger.exception("Failed to record memo LLM metrics")


def _compute_memo_cost(usage: dict) -> float | None:
    try:
        return compute_llm_cost(
            usage.get("model") or "unknown",
            usage.get("input_tokens", 0) or 0,
            usage.get("output_tokens", 0) or 0,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Indirection points so integration tests can patch the heavy collaborators.
# ---------------------------------------------------------------------------

def _get_db_session():
    return SessionLocal()


def _get_llm():
    return AnthropicMemoLLM()


def _get_retriever(db):
    return RagRetriever(db)


def _store_in_r2(key: str, data: bytes, content_type: str) -> str:
    storage = get_r2_storage()
    return storage.store_bytes(key=key, data=data, content_type=content_type)


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

@shared_task(name="generate_credit_memo", queue="critical", bind=True)
def generate_credit_memo_task(self, memo_id: str, run_id: str, user_id: str) -> dict[str, Any]:
    """Generate an IC credit memo DOCX from a completed underwriting run.

    Args:
        memo_id: ID of the ``UnderwritingMemo`` row (already created by the API).
        run_id: ID of the source ``UnderwritingRun``.
        user_id: Owning user — used for security-scoped DB fetches and the R2 key path.

    Returns:
        ``{"memo_id": ..., "status": "complete", "r2_key": ...}`` on success.

    Raises:
        RuntimeError: Re-raised after marking the memo as failed so the Celery
            result backend records a failure.
    """
    db = _get_db_session()
    repo = ReMemoRepository(db)
    run_repo = UnderwritingRunRepository(db)
    tracker = JobProgressTracker(db, self.request.id)

    repo.update_status(memo_id, "generating", job_id=self.request.id)

    try:
        tracker.update_progress(
            status="generating",
            current_stage="loading",
            progress_percent=5,
            message="Pulling deal data…",
        )

        run = run_repo.get(run_id, user_id)
        memo = repo.get(memo_id, user_id)

        if run is None or memo is None:
            raise RuntimeError("Memo or run not found")
        if not run.result_artifact:
            raise RuntimeError(
                "Run has no result_artifact — underwriting must be complete before generating a memo"
            )

        tracker.update_progress(
            status="generating",
            current_stage="assembling",
            progress_percent=10,
            message="Reviewing financials and verdict…",
        )
        ctx = build_memo_context(run, memo)

        tracker.update_progress(
            status="generating",
            current_stage="drafting",
            progress_percent=15,
            message="Drafting memo sections…",
        )
        llm = _get_llm()
        retriever = _get_retriever(db)
        narrate_t0 = time.time()
        sections = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=retriever))
        narrate_duration_s = time.time() - narrate_t0

        for warning in collect_section_warnings(sections):
            repo.append_warning(memo_id, warning)

        # Record LLM usage — Prometheus metrics + DB persistence.
        try:
            usage = llm.get_usage_totals() if hasattr(llm, "get_usage_totals") else None
        except Exception:
            usage = None
        if usage:
            _record_memo_llm_metrics(usage)
            cost_usd = _compute_memo_cost(usage)
            memo_metadata = {
                "llm": {
                    "model": usage.get("model"),
                    "calls": usage.get("calls", 0),
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
                    "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
                    "cost_usd": cost_usd,
                },
                "narration_duration_s": round(narrate_duration_s, 2),
            }
            repo.set_metadata(memo_id, memo_metadata)
            logger.info(
                "Credit memo LLM usage: model=%s calls=%d input=%d output=%d "
                "cache_create=%d cache_read=%d cost=$%.4f duration=%.2fs",
                usage.get("model"),
                usage.get("calls", 0),
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
                usage.get("cache_creation_input_tokens", 0),
                usage.get("cache_read_input_tokens", 0),
                cost_usd or 0.0,
                narrate_duration_s,
            )

        tracker.update_progress(
            status="generating",
            current_stage="rendering",
            progress_percent=75,
            message="Composing the memo…",
        )
        docx_bytes = render_memo_docx(ctx, sections)

        tracker.update_progress(
            status="generating",
            current_stage="uploading",
            progress_percent=90,
            message="Preparing download…",
        )
        memo_filename = build_memo_filename(
            (memo.cover_data or {}).get("deal_name") or ctx.deal_name,
            memo.version,
        )
        r2_key = f"re-underwriting-memos/{user_id}/{run_id}/{memo_filename}"
        _store_in_r2(
            r2_key,
            docx_bytes,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        repo.mark_complete(memo_id, r2_key=r2_key, file_size_bytes=len(docx_bytes))
        tracker.mark_completed()

        logger.info(
            "Credit memo generated: memo_id=%s run_id=%s r2_key=%s bytes=%d",
            memo_id,
            run_id,
            r2_key,
            len(docx_bytes),
        )
        return {"memo_id": memo_id, "status": "complete", "r2_key": r2_key}

    except Exception as e:
        logger.exception("Memo generation failed for memo_id=%s: %s", memo_id, e)
        repo.mark_failed(memo_id, error_message=str(e))
        tracker.mark_error(
            error_stage="memo_generation",
            error_message=str(e),
            error_type="memo_generation_failed",
            is_retryable=False,
            internal_error=str(e),
        )
        raise

    finally:
        db.close()
