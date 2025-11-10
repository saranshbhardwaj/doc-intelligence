# backend/app/services/tasks/extraction.py
"""Celery tasks for Extraction Mode pipeline.

Pipeline: Parse → Chunk → Summarize → Extract

Shared tasks (also used by Chat Mode):
- parse_document_task: Parse PDF to text
- chunk_document_task: Chunk text into sections

Extraction-specific tasks:
- summarize_context_task: Summarize narrative chunks
- extract_structured_task: Extract structured data with expensive LLM
"""
from __future__ import annotations
import asyncio
import uuid
from typing import Dict, Any

from celery import shared_task, chain

from app.config import settings
from app.database import get_db
from app.services.parsers import ParserFactory
from app.services.chunkers import ChunkerFactory
from app.services.llm_client import LLMClient
from app.services.job_tracker import JobProgressTracker
from app.utils.pdf_utils import detect_pdf_type
from app.utils.file_utils import (
    save_raw_text,
    save_chunks,
    save_summaries,
    save_combined_context,
    save_raw_llm_response,
    save_parsed_result,
)
from app.utils.normalization import _normalize_llm_output
from app.services.risk_detector import detect_red_flags
from app.models import ExtractedData
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.user_repository import UserRepository
from app.utils.logging import logger


def _get_db_session():
    return next(get_db())


def _load_file_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


_DEF_LLMC = lambda: LLMClient(
    api_key=settings.anthropic_api_key,
    model=settings.llm_model,
    max_tokens=settings.llm_max_tokens,
    max_input_chars=settings.llm_max_input_chars,
    timeout_seconds=settings.llm_timeout_seconds,
)


# ============================================================================
# SHARED TASKS (used by both Extraction and Chat pipelines)
# ============================================================================


@shared_task(bind=True)
def parse_document_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse PDF document to text.

    SHARED by both Extraction and Chat Mode pipelines.

    Input payload:
        - file_path: Path to uploaded PDF
        - filename: Original filename
        - job_id: JobState ID for progress tracking
        - user_id: User ID
        - extraction_id: Extraction ID (for Extract mode) or document_id (for Chat mode)

    Output payload:
        - All input fields
        - pdf_type: "digital" or "scanned"
        - parser_output: Parser output with text and metadata
    """
    job_id = payload["job_id"]
    extraction_id = payload["extraction_id"]
    file_path = payload["file_path"]
    filename = payload["filename"]
    user_id = payload["user_id"]
    context = payload.get("context")

    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id)
    repo = ExtractionRepository()

    from app.db_models_users import User
    from PyPDF2 import PdfReader

    try:
        # --- ENFORCE USER PAGE LIMITS AT PIPELINE START ---
        user_repo = UserRepository()
        user = user_repo.get_user(user_id)
        if not user:
            tracker.mark_error(error_stage="parsing", error_message="User not found", error_type="user_error", is_retryable=False)
            repo.mark_failed(extraction_id, "User not found")
            return {"status": "failed", "error": "User not found", "extraction_id": extraction_id}

        # Edge case: Ensure user has valid tier and limits
        if not user.tier:
            logger.warning(f"User {user_id} has no tier set, defaulting to 'free'", extra={"user_id": user_id})
            user.tier = "free"

        # Use PyPDF2 to get page count before parsing
        try:
            reader = PdfReader(file_path)
            pre_parse_page_count = len(reader.pages)

            # Edge case: Check for zero or negative page count
            if pre_parse_page_count <= 0:
                raise ValueError(f"Invalid page count: {pre_parse_page_count}")

        except Exception as pdf_err:
            tracker.mark_error(error_stage="parsing", error_message=f"PDF page count error: {pdf_err}", error_type="pdf_error", is_retryable=False)
            repo.mark_failed(extraction_id, f"PDF page count error: {pdf_err}")
            return {"status": "failed", "error": f"PDF page count error: {pdf_err}", "extraction_id": extraction_id}

        default_limit = getattr(settings, "default_pages_limit", 100)
        pages_limit = user.pages_limit if user.pages_limit is not None else default_limit

        # Edge case: Ensure page limit is positive
        if pages_limit <= 0:
            logger.warning(f"User {user_id} has invalid page limit {pages_limit}, using default", extra={"user_id": user_id})
            pages_limit = default_limit

        # Edge case: Check for page limit exceeded BEFORE processing
        if user.tier == "free" and user.total_pages_processed + pre_parse_page_count > pages_limit:
            error_msg = f"Free tier page limit exceeded (limit: {pages_limit}, requested: {pre_parse_page_count})"
            tracker.mark_error(
                error_stage="parsing",
                error_message=error_msg,
                error_type="limit_error",
                is_retryable=False
            )
            repo.mark_failed(extraction_id, error_msg)
            return {"status": "failed", "error": "Free tier page limit exceeded", "extraction_id": extraction_id}
        elif user.tier != "free" and user.pages_this_month + pre_parse_page_count > pages_limit:
            error_msg = f"Monthly page limit exceeded (limit: {pages_limit}, requested: {pre_parse_page_count})"
            tracker.mark_error(
                error_stage="parsing",
                error_message=error_msg,
                error_type="limit_error",
                is_retryable=False
            )
            repo.mark_failed(extraction_id, error_msg)
            return {"status": "failed", "error": "Monthly page limit exceeded", "extraction_id": extraction_id}

        # --- CONTINUE WITH PARSING ---
        tracker.update_progress(status="parsing", current_stage="parsing", progress_percent=5, message="Parsing document...")
        pdf_type = detect_pdf_type(file_path)
        tracker.update_progress(progress_percent=8, message=f"Detected {pdf_type} PDF")

        parser = ParserFactory.get_parser(settings.force_user_tier or "free", pdf_type)
        if not parser:
            raise ValueError("No parser available for detected PDF type")

        # Run async parser in sync Celery task using asyncio.run
        parser_output = asyncio.run(parser.parse(file_path, pdf_type))
        text = parser_output.text

        # Update extraction metadata (for Extract mode only, skip for Chat mode)
        if "extraction_id" in payload and payload.get("mode") != "chat":
            repo.update_extraction(
                extraction_id,
                page_count=parser_output.page_count,
                pdf_type=pdf_type,
                parser_used=parser_output.parser_name,
                processing_time_ms=parser_output.processing_time_ms,
                cost_usd=parser_output.cost_usd,
            )

        # Save raw text for debugging
        save_raw_text(extraction_id, text, filename)

        tracker.update_progress(progress_percent=15, message="Parsing complete", parsing_completed=True)

        return {
            **payload,
            "pdf_type": pdf_type,
            "parser_output": {
                "text": text,
                "page_count": parser_output.page_count,
                "parser_name": parser_output.parser_name,
                "parser_version": parser_output.parser_version,
                "processing_time_ms": parser_output.processing_time_ms,
                "cost_usd": parser_output.cost_usd,
                "metadata": parser_output.metadata,
            },
        }
    except Exception as e:
        tracker.mark_error(error_stage="parsing", error_message=str(e), error_type="parsing_error", is_retryable=False)
        repo.mark_failed(extraction_id, str(e)[:500])
        raise
    finally:
        db.close()


@shared_task(bind=True)
def chunk_document_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chunk document text into sections.

    SHARED by both Extraction and Chat Mode pipelines.

    Input payload:
        - parser_output: Output from parse_document_task
        - All other fields from parse_document_task

    Output payload:
        - All input fields
        - chunks: List of chunk dicts with text and metadata
        - chunking_strategy: Chunking strategy used
    """
    job_id = payload["job_id"]
    extraction_id = payload["extraction_id"]
    filename = payload["filename"]

    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id)
    repo = ExtractionRepository()

    try:
        tracker.update_progress(status="chunking", current_stage="chunking", progress_percent=20, message="Chunking document...")
        po = payload["parser_output"]

        # Minimal ParserOutput reconstruction
        from app.services.parsers.base import ParserOutput
        parser_output = ParserOutput(
            text=po["text"],
            page_count=po["page_count"],
            parser_name=po["parser_name"],
            parser_version=po["parser_version"],
            processing_time_ms=po["processing_time_ms"],
            cost_usd=po["cost_usd"],
            pdf_type=payload.get("pdf_type"),
            metadata=po["metadata"],
        )

        chunker = ChunkerFactory.get_chunker(parser_output.parser_name)
        if not chunker:
            tracker.update_progress(progress_percent=25, message="No chunker available - skipping chunking", chunking_completed=True)
            return {**payload, "chunking_skipped": True}

        chunking_output = chunker.chunk(parser_output)

        chunks_path = save_chunks(
            extraction_id,
            {
                "strategy": chunking_output.strategy.value,
                "total_chunks": chunking_output.total_chunks,
                "metadata": chunking_output.metadata,
                "chunks": [
                    {
                        "chunk_id": c.chunk_id,
                        "text": c.text[:500],
                        "metadata": c.metadata,
                        "narrative_text_preview": (c.narrative_text or "")[:400],
                    }
                    for c in chunking_output.chunks
                ],
            },
            filename,
        )

        tracker.update_progress(progress_percent=30, message="Chunking complete", chunking_completed=True)

        return {
            **payload,
            "chunks": [
                {
                    "chunk_id": c.chunk_id,
                    "text": c.text,
                    "narrative_text": c.narrative_text,
                    "tables": c.tables,
                    "metadata": c.metadata,
                }
                for c in chunking_output.chunks
            ],
            "chunking_strategy": chunking_output.strategy.value,
            "chunks_path": chunks_path,
        }
    except Exception as e:
        tracker.mark_error(error_stage="chunking", error_message=str(e), error_type="chunking_error", is_retryable=True)
        try:
            repo.mark_failed(extraction_id, str(e)[:500])
        except Exception:
            pass
        raise
    finally:
        db.close()


# ============================================================================
# EXTRACTION-SPECIFIC TASKS
# ============================================================================


@shared_task(bind=True)
def summarize_context_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Summarize narrative chunks and build combined context for extraction.

    EXTRACTION MODE ONLY (not used in Chat Mode).
    """
    job_id = payload["job_id"]
    extraction_id = payload["extraction_id"]
    filename = payload["filename"]

    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id)
    repo = ExtractionRepository()
    llm_client = _DEF_LLMC()

    try:
        chunks = payload.get("chunks", [])
        narrative_chunks = [c for c in chunks if c.get("narrative_text")]
        tracker.update_progress(status="summarizing", current_stage="summarizing", progress_percent=40, message="Summarizing sections...")

        summaries = []
        batch_size = settings.chunk_batch_size
        for i in range(0, len(narrative_chunks), batch_size):
            batch = narrative_chunks[i : i + batch_size]
            batch_data = [
                {"page": c["metadata"].get("page_number"), "text": c.get("narrative_text") or ""}
                for c in batch
            ]
            batch_summaries = asyncio.run(llm_client.summarize_chunks_batch(batch_data))
            summaries.extend(batch_summaries)

        summaries_path = save_summaries(
            extraction_id,
            {
                "model": settings.cheap_llm_model,
                "total_summaries": len(summaries),
                "batch_size": batch_size,
                "summaries": summaries,
            },
            filename,
        )
        tracker.update_progress(progress_percent=60, message="Summaries complete", summarizing_completed=True)

        # Build combined context
        table_chunks = [c for c in chunks if c["metadata"].get("has_tables")]

        combined_sections = []
        if summaries:
            combined_sections.append("=== DOCUMENT SUMMARIES (Narrative) ===\n")
            for idx, c in enumerate(narrative_chunks):
                pg = c["metadata"].get("page_number")
                summary = summaries[idx] if idx < len(summaries) else (c.get("narrative_text") or "")
                combined_sections.append(f"[Page {pg}]\n{summary}\n")
        if table_chunks:
            combined_sections.append("\n=== FINANCIAL TABLES (Complete Data) ===\n")
            for c in table_chunks:
                pg = c["metadata"].get("page_number")
                tc = c["metadata"].get("table_count")
                combined_sections.append(f"[Page {pg} - Contains {tc} table(s)]\n{c['text']}\n")
        combined_text = "\n".join(combined_sections)

        original_chars = sum(len(c["text"]) for c in chunks)
        compression_ratio = (1 - len(combined_text) / original_chars) * 100 if original_chars else 0
        metadata = {
            "original_chars": original_chars,
            "compressed_chars": len(combined_text),
            "compression_ratio": f"{compression_ratio:.1f}%",
            "narrative_chunks": len(narrative_chunks),
            "table_chunks": len(table_chunks),
            "narrative_summaries": len(summaries),
        }
        combined_path = save_combined_context(extraction_id, combined_text, metadata, filename)

        tracker.update_progress(progress_percent=65, message="Context combined", details={"compression_ratio": metadata["compression_ratio"]})

        return {**payload, "combined_context_path": combined_path, "combined_context": combined_text}
    except Exception as e:
        tracker.mark_error(error_stage="summarizing", error_message=str(e), error_type="summarizing_error", is_retryable=True)
        try:
            repo.mark_failed(extraction_id, str(e)[:500])
        except Exception:
            pass
        raise
    finally:
        db.close()


@shared_task(bind=True)
def extract_structured_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract structured data using expensive LLM.

    EXTRACTION MODE ONLY (not used in Chat Mode).
    """
    job_id = payload["job_id"]
    extraction_id = payload["extraction_id"]
    filename = payload["filename"]
    context = payload.get("context")
    user_id = payload.get("user_id")

    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id)
    repo = ExtractionRepository()
    llm_client = _DEF_LLMC()

    from app.db_models_users import User, UsageLog
    from sqlalchemy.exc import SQLAlchemyError

    try:
        # --- ENFORCE USER PAGE LIMITS ---
        user_repo = UserRepository()
        user = user_repo.get_user(user_id)
        if not user:
            tracker.mark_error(error_stage="extracting", error_message="User not found", error_type="user_error", is_retryable=False)
            repo.mark_failed(extraction_id, "User not found")
            return {"status": "failed", "error": "User not found", "extraction_id": extraction_id}

        extraction = repo.get_extraction(extraction_id)
        page_count = extraction.page_count if extraction and extraction.page_count else 0
        pages_limit = user.pages_limit if user.pages_limit is not None else 100

        if user.tier == "free":
            if user.total_pages_processed + page_count > pages_limit:
                tracker.mark_error(error_stage="extracting", error_message="Free tier page limit exceeded", error_type="limit_error", is_retryable=False)
                repo.mark_failed(extraction_id, "Free tier page limit exceeded")
                return {"status": "failed", "error": "Free tier page limit exceeded", "extraction_id": extraction_id}
        else:
            if user.pages_this_month + page_count > pages_limit:
                tracker.mark_error(error_stage="extracting", error_message="Monthly page limit exceeded", error_type="limit_error", is_retryable=False)
                repo.mark_failed(extraction_id, "Monthly page limit exceeded")
                return {"status": "failed", "error": "Monthly page limit exceeded", "extraction_id": extraction_id}

        # --- EXTRACTION LOGIC ---
        tracker.update_progress(status="extracting", current_stage="extracting", progress_percent=70, message="Extracting structured data...")
        combined_text = payload["combined_context"]
        extracted_data = asyncio.run(llm_client.extract_structured_data(combined_text, context))

        tracker.update_progress(progress_percent=90, message="Finalizing extraction...", extracting_completed=True)

        save_raw_llm_response(extraction_id, extracted_data, filename)
        try:
            normalized_payload = _normalize_llm_output(extracted_data)
        except Exception:
            normalized_payload = extracted_data

        # Red flag detection
        try:
            extracted_data_obj = ExtractedData(**normalized_payload.get("data", {}))
            red_flags = detect_red_flags(extracted_data_obj)
            if "data" not in normalized_payload:
                normalized_payload["data"] = {}
            normalized_payload["data"]["red_flags"] = red_flags
        except Exception:
            if "data" not in normalized_payload:
                normalized_payload["data"] = {}
            normalized_payload["data"]["red_flags"] = []

        save_parsed_result(extraction_id, normalized_payload, filename)
        repo.mark_completed(extraction_id)
        tracker.mark_completed()

        # --- UPDATE USAGE AND LOG ---
        try:
            # Use UserRepository for consistent data access
            user_repo_usage = UserRepository()
            success = user_repo_usage.update_page_usage(
                user_id=user_id,
                pages_to_add=page_count,
                update_monthly=True
            )

            if success:
                # Create usage log entry
                usage_log = UsageLog(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    extraction_id=extraction_id,
                    pages_processed=page_count,
                    operation_type="extraction",
                    cost_usd=extraction.cost_usd if extraction and extraction.cost_usd else 0.0,
                )
                db.add(usage_log)
                db.commit()
                logger.debug(f"Updated user usage: {page_count} pages", extra={
                    "user_id": user_id,
                    "extraction_id": extraction_id
                })
            else:
                logger.warning(f"Failed to update user page usage via repository", extra={
                    "user_id": user_id,
                    "extraction_id": extraction_id
                })
        except SQLAlchemyError as e:
            logger.error(f"Failed to update usage or log: {e}", extra={
                "user_id": user_id,
                "extraction_id": extraction_id
            })
            db.rollback()

        # Cache result
        try:
            from app.api.dependencies import cache
            response_data = {
                **normalized_payload,
                "metadata": {
                    "request_id": extraction_id,
                    "filename": filename,
                },
            }
            cache.set(_load_file_bytes(payload["file_path"]), response_data)
        except Exception:
            pass

        return {"status": "completed", "extraction_id": extraction_id}
    except Exception as e:
        tracker.mark_error(error_stage="extracting", error_message=str(e), error_type="llm_error", is_retryable=True)
        repo.mark_failed(extraction_id, str(e)[:500])
        raise
    finally:
        db.close()


# ============================================================================
# PIPELINE ENTRY POINT
# ============================================================================


def start_extraction_chain(
    file_path: str,
    filename: str,
    job_id: str,
    extraction_id: str,
    user_id: str,
    context: str | None
):
    """
    Start the extraction pipeline chain.

    Pipeline: Parse → Chunk → Summarize → Extract
    """
    payload = {
        "file_path": file_path,
        "filename": filename,
        "job_id": job_id,
        "extraction_id": extraction_id,
        "user_id": user_id,
        "context": context,
        "mode": "extraction",  # Mark as extraction mode
    }
    task_chain = chain(
        parse_document_task.s(payload),
        chunk_document_task.s(),
        summarize_context_task.s(),
        extract_structured_task.s(),
    )
    result = task_chain.apply_async()
    logger.info("Extraction pipeline started", extra={"job_id": job_id, "task_id": result.id})
    return result.id
