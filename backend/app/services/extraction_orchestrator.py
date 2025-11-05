"""Document extraction orchestration service

This module contains the background processing workflows for document extraction
and retry operations. It orchestrates the flow between parsing, pipeline processing,
and database updates.

Separated from the API layer to keep endpoints thin and business logic testable.
"""
import os
import tempfile
import uuid
import asyncio
from datetime import datetime

from app.api.dependencies import (
    extraction_pipeline, extraction_repository, cache
)
from app.services.job_tracker import JobProgressTracker
from app.db_models_users import User, UsageLog
from app.models import ExtractedData
from app.utils.file_utils import save_raw_text, save_parsed_result, save_raw_llm_response
from app.utils.normalization import _normalize_llm_output
from app.services.risk_detector import detect_red_flags
from app.services.parsers import ParserFactory
from app.utils.pdf_utils import detect_pdf_type
from app.config import settings
from app.utils.logging import logger
from app.database import get_db


async def process_document_async(
    job_id: str,
    extraction_id: str,
    file_content: bytes,
    filename: str,
    client_ip: str,
    user_id: str,
    context: str = None
):
    """Background task to process document and update job state

    Args:
        job_id: Unique job identifier for progress tracking
        extraction_id: Unique extraction identifier
        file_content: PDF file bytes
        filename: Original filename
        client_ip: Client IP address (unused, kept for compatibility)
        user_id: Clerk user ID
        context: Optional user-provided context to guide extraction
    """
    # CRITICAL: Small delay to allow SSE connection to establish
    # Browser may delay sending SSE GET request until POST completes
    await asyncio.sleep(0.3)  # 300ms delay

    db = next(get_db())
    progress_tracker = JobProgressTracker(db, job_id)

    try:
        # Update: Starting parsing
        progress_tracker.update_progress(
            status="parsing",
            current_stage="parsing",
            progress_percent=5,
            message=f"Parsing {filename}..."
        )

        # Save PDF to temporary file
        temp_pdf_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pdf', delete=False) as temp_file:
                temp_pdf_path = temp_file.name
                temp_file.write(file_content)

            logger.info(f"Saved PDF to temp file: {temp_pdf_path}", extra={"job_id": job_id})

            # Detect PDF type
            pdf_type = detect_pdf_type(temp_pdf_path)
            logger.info(f"PDF type detected: {pdf_type}", extra={"job_id": job_id})

            progress_tracker.update_progress(
                progress_percent=10,
                message=f"Detected {pdf_type} PDF, initializing parser..."
            )

            # Get user tier
            user_tier = settings.force_user_tier if settings.force_user_tier else "free"

            # Check if supported
            if not ParserFactory.is_supported(user_tier, pdf_type):
                upgrade_message = ParserFactory.get_upgrade_message(user_tier, pdf_type)
                progress_tracker.mark_error(
                    error_stage="parsing",
                    error_message=upgrade_message,
                    error_type="upgrade_required",
                    is_retryable=False
                )
                extraction_repository.mark_failed(extraction_id, upgrade_message)
                return

            # Get parser
            parser = ParserFactory.get_parser(user_tier, pdf_type)
            if not parser:
                error_msg = "Failed to initialize document parser"
                progress_tracker.mark_error(
                    error_stage="parsing",
                    error_message=error_msg,
                    error_type="parser_error",
                    is_retryable=True
                )
                extraction_repository.mark_failed(extraction_id, error_msg)
                return

            logger.info(f"Using parser: {parser.name}", extra={"job_id": job_id})

            # Parse document (await parser's own async implementation)
            parser_output = await parser.parse(temp_pdf_path, pdf_type)
            text = parser_output.text
            page_count = parser_output.page_count

            logger.info(f"Parser completed: {len(text)} chars from {page_count} pages", extra={"job_id": job_id})

            # Update extraction metadata
            extraction_repository.update_extraction(
                extraction_id=extraction_id,
                page_count=page_count,
                pdf_type=pdf_type,
                parser_used=parser_output.parser_name,
                processing_time_ms=parser_output.processing_time_ms,
                cost_usd=parser_output.cost_usd
            )

            # Store parser output
            extraction_repository.create_parser_output(
                extraction_id=extraction_id,
                parser_name=parser_output.parser_name,
                parser_version=parser_output.parser_version,
                pdf_type=pdf_type,
                raw_output={"text": text[:10000]},
                raw_output_length=len(text),
                processing_time_ms=parser_output.processing_time_ms,
                cost_usd=parser_output.cost_usd
            )

            progress_tracker.update_progress(
                progress_percent=15,
                message=f"Parsed {page_count} pages successfully",
                parsing_completed=True
            )
            # Yield control so SSE poll loop can run
            await asyncio.sleep(0)

        finally:
            # Clean up temp file
            if temp_pdf_path and os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)
                logger.info(f"Removed temporary PDF file", extra={"job_id": job_id})

        save_raw_text(extraction_id, text, filename)

        # Run extraction pipeline with progress tracking
        pipeline_result = await extraction_pipeline.process(
            parser_output,
            extraction_id,
            filename,
            progress_tracker,
            context=context
        )
        extracted_data = pipeline_result.extracted_data

        save_raw_llm_response(extraction_id, extracted_data, filename)

        # Normalize LLM output
        try:
            normalized_payload = _normalize_llm_output(extracted_data)
        except Exception as e:
            logger.exception("Normalization failed", extra={"job_id": job_id, "error": str(e)})
            normalized_payload = extracted_data

        # Run red flag detection
        try:
            extracted_data_obj = ExtractedData(**normalized_payload.get("data", {}))
            red_flags = detect_red_flags(extracted_data_obj)

            if "data" not in normalized_payload:
                normalized_payload["data"] = {}
            normalized_payload["data"]["red_flags"] = red_flags

            logger.info(f"Red flag detection complete: {len(red_flags)} flags", extra={"job_id": job_id})
        except Exception as e:
            logger.warning(f"Red flag detection failed: {e}", extra={"job_id": job_id})
            if "data" not in normalized_payload:
                normalized_payload["data"] = {}
            normalized_payload["data"]["red_flags"] = []

        # Save result
        save_parsed_result(extraction_id, normalized_payload, filename)

        # Update extraction as completed
        extraction_repository.mark_completed(extraction_id)

        # Mark job as completed
        progress_tracker.mark_completed()

        # ============================================
        # Update user usage tracking
        # ============================================
        try:
            user = db.query(User).filter(User.id == user_id).first()

            if user:
                # Update user page counts
                user.pages_this_month += page_count
                user.total_pages_processed += page_count

                # Create usage log entry
                usage_log = UsageLog(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    extraction_id=extraction_id,
                    pages_processed=page_count,
                    operation_type="extraction",
                    cost_usd=pipeline_result.total_cost_usd if hasattr(pipeline_result, 'total_cost_usd') else 0.0
                )
                db.add(usage_log)
                db.commit()

                logger.info(f"Updated user usage: {user.pages_this_month}/{user.pages_limit} pages", extra={
                    "job_id": job_id,
                    "user_id": user_id,
                    "pages_added": page_count
                })
        except Exception as e:
            logger.warning(f"Failed to update user usage: {e}", extra={"job_id": job_id})
            # Don't fail the extraction if usage tracking fails

        # Cache result
        response_data = {
            **normalized_payload,
            "metadata": {
                "request_id": extraction_id,
                "filename": filename,
                "pages": page_count,
                "characters_extracted": len(text),
            }
        }
        cache.set(file_content, response_data)

        logger.info("Document processing completed successfully", extra={"job_id": job_id})

    except Exception as e:
        logger.exception("Document processing failed", extra={"job_id": job_id, "error": str(e)})

        # Determine error type
        error_type = "unknown_error"
        error_stage = "unknown"
        is_retryable = True

        if "API" in str(e) or "Anthropic" in str(e):
            error_type = "llm_error"
            error_stage = "extracting"
        elif "parse" in str(e).lower():
            error_type = "parsing_error"
            error_stage = "parsing"
        elif "chunk" in str(e).lower():
            error_type = "chunking_error"
            error_stage = "chunking"

        progress_tracker.mark_error(
            error_stage=error_stage,
            error_message=str(e)[:1000],
            error_type=error_type,
            is_retryable=is_retryable
        )

        extraction_repository.mark_failed(extraction_id, str(e)[:500])

    finally:
        db.close()


async def retry_document_async(
    job_id: str,
    extraction_id: str,
    resume_stage: str,
    resume_data_path: str
):
    """Retry LLM extraction from saved combined context

    Currently only supports retrying from the extraction stage (most common failure).
    This avoids re-running expensive parsing, chunking, and summarization.

    Args:
        job_id: Job ID to track progress
        extraction_id: Original extraction ID
        resume_stage: Stage to resume from (always "extracting" for now)
        resume_data_path: Path to saved combined context file
    """
    await asyncio.sleep(0.3)  # Small delay for SSE connection

    db = next(get_db())
    progress_tracker = JobProgressTracker(db, job_id)

    try:
        # Load extraction record
        extraction = extraction_repository.get_by_id(extraction_id)
        if not extraction:
            progress_tracker.mark_error(
                error_stage="retry",
                error_message="Original extraction not found",
                error_type="not_found",
                is_retryable=False
            )
            return

        filename = extraction.filename
        context = extraction.context

        logger.info(f"Retrying extraction from {resume_stage} stage", extra={
            "job_id": job_id,
            "extraction_id": extraction_id,
            "resume_stage": resume_stage
        })

        progress_tracker.update_progress(
            status="resuming",
            current_stage=f"resuming_{resume_stage}",
            progress_percent=5,
            message=f"Resuming from {resume_stage} stage..."
        )
        await asyncio.sleep(0)

        # Load combined context and call expensive LLM
        logger.info(f"Loading combined context from {resume_data_path}", extra={"job_id": job_id})

        try:
            # Load the saved combined context (plain text file)
            with open(resume_data_path, 'r', encoding='utf-8') as f:
                combined_context = f.read()

            if not combined_context or not combined_context.strip():
                raise ValueError("Combined context file is empty")

            logger.info(f"Loaded combined context: {len(combined_context)} chars", extra={"job_id": job_id})

            progress_tracker.update_progress(
                status="extracting",
                current_stage="extracting",
                progress_percent=70,
                message="Retrying structured data extraction..."
            )
            await asyncio.sleep(0)

            # Call expensive LLM with cached combined context
            logger.info("Calling expensive LLM (retry)", extra={"job_id": job_id})
            extracted_data = await extraction_pipeline.llm_client.extract_structured_data(
                combined_context,
                context
            )

            progress_tracker.update_progress(
                progress_percent=90,
                message="Finalizing extraction results...",
                extracting_completed=True
            )
            await asyncio.sleep(0)

        except FileNotFoundError:
            logger.error(f"Cached data file not found: {resume_data_path}", extra={"job_id": job_id})
            raise Exception(f"Cached intermediate data not found. Cannot retry from {resume_stage} stage.")
        except Exception as e:
            logger.error(f"Failed to load cached data: {e}", extra={"job_id": job_id})
            raise

        # Continue with common post-processing steps
        save_raw_llm_response(extraction_id, extracted_data, filename)

        # Normalize LLM output
        try:
            normalized_payload = _normalize_llm_output(extracted_data)
        except Exception as e:
            logger.exception("Normalization failed", extra={"job_id": job_id, "error": str(e)})
            normalized_payload = extracted_data

        # Run red flag detection
        try:
            extracted_data_obj = ExtractedData(**normalized_payload.get("data", {}))
            red_flags = detect_red_flags(extracted_data_obj)

            if "data" not in normalized_payload:
                normalized_payload["data"] = {}
            normalized_payload["data"]["red_flags"] = red_flags

            logger.info(f"Red flag detection complete: {len(red_flags)} flags", extra={"job_id": job_id})
        except Exception as e:
            logger.warning(f"Red flag detection failed: {e}", extra={"job_id": job_id})
            if "data" not in normalized_payload:
                normalized_payload["data"] = {}
            normalized_payload["data"]["red_flags"] = []

        # Save result
        save_parsed_result(extraction_id, normalized_payload, filename)

        # Update extraction as completed
        extraction_repository.mark_completed(extraction_id)

        # Mark job as completed
        progress_tracker.mark_completed()

        # NOTE: We don't update user usage on retry since pages were already counted
        # in the original upload attempt

        logger.info("Retry completed successfully", extra={"job_id": job_id})

    except Exception as e:
        logger.exception("Retry failed", extra={"job_id": job_id, "error": str(e)})

        # Determine error type
        error_type = "unknown_error"
        error_stage = "retry"
        is_retryable = True

        if "API" in str(e) or "Anthropic" in str(e):
            error_type = "llm_error"
            error_stage = "extracting"
        elif "not found" in str(e).lower() or "FileNotFoundError" in str(e):
            error_type = "cache_miss"
            is_retryable = False

        progress_tracker.mark_error(
            error_stage=error_stage,
            error_message=str(e)[:1000],
            error_type=error_type,
            is_retryable=is_retryable
        )

        extraction_repository.mark_failed(extraction_id, str(e)[:500])

    finally:
        db.close()
