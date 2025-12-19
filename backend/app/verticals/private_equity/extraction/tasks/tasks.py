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
from app.verticals.private_equity.extraction.llm_service import ExtractionLLMService
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
    model=settings.cheap_llm_model,
    max_tokens=settings.cheap_llm_max_tokens,
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

        # Check per-document page limit for full extraction (scalability limit)
        if payload.get("mode") != "chat" and parser_output.page_count > settings.max_pages_per_extraction:
            error_msg = (
                f"Document too large for full extraction ({parser_output.page_count} pages, "
                f"limit: {settings.max_pages_per_extraction}). "
                "Please use workflow mode for large documents."
            )
            tracker.mark_error(
                error_stage="parsing",
                error_message=error_msg,
                error_type="document_too_large",
                is_retryable=False
            )
            repo.mark_failed(extraction_id, error_msg)
            logger.warning(
                f"Document exceeds extraction page limit: {parser_output.page_count} > {settings.max_pages_per_extraction}",
                extra={"extraction_id": extraction_id, "page_count": parser_output.page_count}
            )
            return {
                "status": "failed",
                "error": "document_too_large",
                "message": error_msg,
                "extraction_id": extraction_id,
                "page_count": parser_output.page_count,
                "max_pages": settings.max_pages_per_extraction
            }

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
        
        raw_output = {
            "text": parser_output.text[:400],
            "page_count": parser_output.page_count,
            "parser_name": parser_output.parser_name,
            "parser_version": parser_output.parser_version,
            "processing_time_ms": parser_output.processing_time_ms,
            "cost_usd": parser_output.cost_usd,
            "metadata": parser_output.metadata,
}       
        repo.create_parser_output(
            extraction_id=extraction_id,
            parser_name=parser_output.parser_name,
            parser_version=parser_output.parser_version,
            pdf_type=pdf_type,
            raw_output=raw_output,
            raw_output_length=len(parser_output.text),
            processing_time_ms=parser_output.processing_time_ms,
            cost_usd=parser_output.cost_usd
        )

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

    # Initialize core LLM client and extraction service
    llm_client = _DEF_LLMC()
    extraction_service = ExtractionLLMService(llm_client)

    try:
        chunks = payload.get("chunks", [])
        # Ensure each chunk has a metadata dict to avoid KeyError
        for ch in chunks:
            if "metadata" not in ch:
                ch["metadata"] = {}
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
            batch_summaries = asyncio.run(extraction_service.summarize_chunks_batch(batch_data))
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
        tracker.update_progress(progress_percent=50, message="Narrative summaries complete")

        # Keep full table chunks (don't extract metrics - preserves all information)
        table_chunks = [c for c in chunks if c.get("metadata", {}).get("has_tables")]

        if table_chunks:
            logger.info(f"Including {len(table_chunks)} full table chunks in extraction", extra={
                "extraction_id": extraction_id,
                "table_chunks": len(table_chunks)
            })
            tracker.update_progress(progress_percent=55, message=f"Including {len(table_chunks)} full table chunks")

        # Build combined context with narrative summaries + full tables
        combined_sections = []

        if summaries:
            combined_sections.append("=== DOCUMENT SUMMARIES (Narrative) ===\n")
            for idx, c in enumerate(narrative_chunks):
                pg = (c.get("metadata") or {}).get("page_number")
                summary = summaries[idx] if idx < len(summaries) else (c.get("narrative_text") or "")
                combined_sections.append(f"[Page {pg}]\n{summary}\n")

        if table_chunks:
            combined_sections.append("\n=== TABLES (Full Content) ===\n")
            for c in table_chunks:
                pg = (c.get("metadata") or {}).get("page_number")
                table_text = c.get("text", "")
                combined_sections.append(f"[Page {pg}]\n{table_text}\n")

        combined_text = "\n".join(combined_sections)

        original_chars = sum(len(c["text"]) for c in chunks)
        metadata = {
            "original_chars": original_chars,
            "combined_chars": len(combined_text),
            "narrative_chunks": len(narrative_chunks),
            "table_chunks": len(table_chunks),
            "narrative_summaries": len(summaries),
        }
        combined_path = save_combined_context(extraction_id, combined_text, metadata, filename)

        tracker.update_progress(progress_percent=65, message="Context combined", details={"combined_chars": metadata["combined_chars"]})

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
        user_repo = UserRepository()
        user = user_repo.get_user(user_id)
        if not user:
            tracker.mark_error(error_stage="extracting", error_message="User not found", error_type="user_error", is_retryable=False)
            repo.mark_failed(extraction_id, "User not found")
            return {"status": "failed", "error": "User not found", "extraction_id": extraction_id}

        # Re-query extraction within THIS task's session to avoid detached instance issues
        from app.db_models import Extraction as ExtractionModel
        extraction = db.query(ExtractionModel).filter(ExtractionModel.id == extraction_id).first()

        # --- EXTRACTION LOGIC ---
        tracker.update_progress(status="extracting", current_stage="extracting", progress_percent=70, message="Extracting structured data this can take a while...")
        combined_text = payload["combined_context"]

        # Use caching for CIM extraction (system prompt is 100% static)
        # This provides ~90% cost savings on calls 2-N with the same system prompt
        from app.verticals.private_equity.extraction.prompts import CIM_EXTRACTION_SYSTEM_PROMPT, create_extraction_prompt

        # Build user message with context formatting
        user_message = create_extraction_prompt(combined_text, context)

        extracted_data = asyncio.run(
            llm_client.extract_structured_data(
                text=user_message,  # Formatted user message (with optional context)
                system_prompt=CIM_EXTRACTION_SYSTEM_PROMPT,  # Static system prompt (cached)
                use_cache=True  # ✅ Enable caching!
            )
        )

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
                pages_to_add=0,
                update_monthly=True
            )

            if success:
                # Create usage log entry
                usage_log = UsageLog(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    extraction_id=extraction_id,
                    pages_processed=0,
                    operation_type="extraction",
                    cost_usd=extraction.cost_usd if extraction and extraction.cost_usd else 0.0,
                )
                db.add(usage_log)
                db.commit()
                logger.debug(f"Updated user usage: 0 pages", extra={
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

        # Preserve full payload context for downstream store task (needs job_id, etc.)
        return {
            **payload,
            "status": "completed",
            "extraction_id": extraction_id,
            "normalized_result": normalized_payload,
        }
    except Exception as e:
        tracker.mark_error(error_stage="extracting", error_message=str(e), error_type="llm_error", is_retryable=True)
        repo.mark_failed(extraction_id, str(e)[:500])
        raise
    finally:
        db.close()


# ============================================================================
# PIPELINE ENTRY POINT
# ============================================================================


@shared_task(bind=True)
def store_extraction_result_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Store extraction result to R2 (large) or inline DB (small).

    Final task in extraction pipeline.Uses artifacts.py for storage.

    Input payload:
        - extraction_id: Extraction ID
        - normalized_result: Final extraction result (after normalization)
        - job_id: Job ID for progress tracking
        - total_cost_usd: Total processing cost

    Output: Publishes complete event via Redis
    """
    extraction_id = payload["extraction_id"]
    job_id = payload.get("job_id")
    if not job_id:
        # Fallback lookup to avoid hard failure if prior task dropped job_id
        try:
            from app.repositories.job_repository import JobRepository
            jr = JobRepository()
            # Try common accessor names
            job = None
            for accessor in ("get_job_by_extraction_id", "get_job_for_extraction", "get_job"):
                if hasattr(jr, accessor):
                    try:
                        job = getattr(jr, accessor)(extraction_id)
                    except Exception:
                        job = None
                    if job:
                        break
            if job:
                job_id = getattr(job, "id", None)
                logger.warning(
                    "Recovered missing job_id in store_extraction_result_task via repository lookup",
                    extra={"extraction_id": extraction_id, "job_id": job_id}
                )
        except Exception:
            logger.warning(
                "Unable to recover missing job_id in store_extraction_result_task; continuing without progress tracking",
                extra={"extraction_id": extraction_id}
            )
    result_data = payload.get("normalized_result", payload.get("data", {}))
    total_cost_usd = payload.get("total_cost_usd", 0.0)

    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id) if job_id else None
    extraction_repo = ExtractionRepository()

    try:
        # Import extraction artifact service
        from app.services.artifacts import persist_extraction_artifact

        if tracker:
            tracker.update_progress(
                progress_percent=95,
                message="Storing extraction result..."
            )

        # Persist extraction artifact (R2 if large, inline if small)
        artifact_pointer = persist_extraction_artifact(extraction_id, result_data)

        # Update extraction record
        success = extraction_repo.update_extraction_artifact(
            extraction_id=extraction_id,
            artifact=artifact_pointer,
            status="completed",
            total_cost_usd=total_cost_usd
        )

        if not success:
            raise Exception("Failed to update extraction record with artifact")

        if tracker:
            tracker.mark_completed()

        logger.info(
            "Extraction result stored successfully",
            extra={"extraction_id": extraction_id, "artifact_backend": artifact_pointer.get("backend", "inline")}
        )

        return {
            **payload,
            "artifact": artifact_pointer,
            "status": "completed"
        }

    except Exception as e:
        error_msg = f"Failed to store extraction result: {str(e)}"
        logger.exception(error_msg, extra={"extraction_id": extraction_id})

        extraction_repo.mark_extraction_failed(extraction_id, error_msg)
        if tracker:
            tracker.mark_error(
                error_stage="storing",
                error_message=error_msg,
                error_type="storage_error",
                is_retryable=True
            )

        return {
            **payload,
            "status": "failed",
            "error": error_msg
        }


@shared_task(bind=True)
def start_extraction_from_chunks_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Start extraction from existing DocumentChunks (for library documents).

    Skips parse/chunk steps and loads chunks from DocumentChunk table.

    Input payload:
        - job_id: Job ID
        - extraction_id: Extraction ID
        - document_id: Document ID
        - user_id: User ID
        - context: Optional extraction context

    Pipeline: Load Chunks → Summarize → Extract → Store
    """
    job_id = payload["job_id"]
    extraction_id = payload["extraction_id"]
    document_id = payload["document_id"]
    user_id = payload.get("user_id")
    context = payload.get("context")
    filename = payload.get("filename", "document")

    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id)

    try:
        tracker.update_progress(
            status="running",
            current_stage="loading_chunks",
            progress_percent=10,
            message="Loading document chunks..."
        )

        # Load chunks from DocumentChunk table
        from app.db_models_chat import DocumentChunk
        chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).order_by(DocumentChunk.chunk_index).all()

        if not chunks:
            raise Exception("No chunks found for document - document may not be indexed yet")

        tracker.update_progress(
            progress_percent=30,
            message=f"Loaded {len(chunks)} chunks from document"
        )

        # Normalize chunk representation to match output of chunk_document_task
        chunk_data = []
        for c in chunks:
            table_count = getattr(c, "table_count", 0) or 0
            has_tables = bool(table_count) or bool(getattr(c, "is_tabular", False))
            metadata = {
                "page_number": getattr(c, "page_number", None),
                "table_count": table_count,
                "has_tables": has_tables,
            }
            narrative_text = getattr(c, "narrative_text", None) or (c.text[:400] if getattr(c, "text", None) else None)
            tables = getattr(c, "tables", []) or []
            chunk_id = f"{document_id}-{getattr(c, 'chunk_index', '0')}"
            chunk_data.append({
                "chunk_id": chunk_id,
                "text": c.text,
                "narrative_text": narrative_text,
                "tables": tables,
                "metadata": metadata,
            })

        # Update payload with chunks and metadata
        payload_with_chunks = {
            **payload,
            "chunks": chunk_data,
            "filename": filename,
            "mode": "extraction"
        }

        # Chain: Summarize → Extract → Store
        task_chain = chain(
            summarize_context_task.s(payload_with_chunks),
            extract_structured_task.s(),
            store_extraction_result_task.s()
        )

        result = task_chain.apply_async()

        logger.info(
            "Extraction from chunks started",
            extra={"job_id": job_id, "document_id": document_id, "chunks_count": len(chunks)}
        )

        return {
            **payload_with_chunks,
            "task_id": result.id
        }

    except Exception as e:
        error_msg = f"Failed to start extraction from chunks: {str(e)}"
        logger.exception(error_msg, extra={"extraction_id": extraction_id, "document_id": document_id})

        extraction_repo = ExtractionRepository()
        extraction_repo.mark_extraction_failed(extraction_id, error_msg)

        tracker.mark_error(
            error_stage="loading_chunks",
            error_message=error_msg,
            error_type="chunk_load_error",
            is_retryable=True
        )

        return {
            **payload,
            "status": "failed",
            "error": error_msg
        }


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

    Pipeline: Parse → Chunk → Summarize → Extract → Store
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
        store_extraction_result_task.s()  # Added final storage step
    )
    result = task_chain.apply_async()
    logger.info("Extraction pipeline started", extra={"job_id": job_id, "task_id": result.id})
    return result.id


def start_extraction_from_chunks_chain(
    job_id: str,
    extraction_id: str,
    document_id: str,
    user_id: str,
    filename: str,
    context: str | None
):
    """
    Start extraction pipeline from existing chunks (library documents).

    Pipeline: Load Chunks → Summarize → Extract → Store
    """
    payload = {
        "job_id": job_id,
        "extraction_id": extraction_id,
        "document_id": document_id,
        "user_id": user_id,
        "filename": filename,
        "context": context,
        "mode": "extraction",
    }

    # This triggers the start_extraction_from_chunks_task
    result = start_extraction_from_chunks_task.apply_async(args=[payload])

    logger.info(
        "Extraction from chunks pipeline started",
        extra={"job_id": job_id, "document_id": document_id, "task_id": result.id, "user_id": user_id}
    )
    return result.id
