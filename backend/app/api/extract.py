# app/api/extract.py
"""Unified extraction endpoint with smart cache-aware routing

This endpoint intelligently handles both cache hits and misses:
- Cache HIT → Returns result immediately (200 OK)
- Cache MISS → Returns job_id for async processing (202 Accepted)
"""
from datetime import datetime
import time
import os
import tempfile
import uuid
import json
import asyncio

from fastapi import APIRouter, Request, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse

from app.api.dependencies import (
    rate_limiter, get_client_ip, document_processor, cache,
    analytics, extraction_pipeline, extraction_repository
)
from app.api.jobs import JobProgressTracker
from app.auth import get_current_user
from app.db_models_users import User, UsageLog
from app.models import ExtractedData
from app.utils.file_utils import save_raw_text, save_parsed_result, save_raw_llm_response, make_file_label
from app.utils.normalization import _normalize_llm_output
from app.services.mock_responses import get_mock_cim_response
from app.services.risk_detector import detect_red_flags
from app.config import settings
from app.utils.logging import logger
from app.database import get_db
from app.db_models import JobState, Extraction

# Parser system imports
from app.services.parsers import ParserFactory
from app.utils.pdf_utils import detect_pdf_type

router = APIRouter()


async def process_document_async(
    job_id: str,
    extraction_id: str,
    file_content: bytes,
    filename: str,
    client_ip: str,
    user_id: str
):
    """Background task to process document and update job state"""
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
            progress_tracker
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
            from app.db_models_users import User
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


@router.post("/api/extract")
async def extract_document(
    file: UploadFile = File(...),
    request: Request = None,
    user: User = Depends(get_current_user)
):
    """
    Unified extraction endpoint with smart cache-aware routing.

    **Requires authentication** - User must provide valid Clerk session token.

    Returns:
        - 200 OK: Cache hit, result included immediately
        - 202 Accepted: Cache miss, returns job_id for async processing
        - 401 Unauthorized: Missing or invalid authentication
        - 403 Forbidden: Page limit exceeded
        - 429 Rate Limited: Rate limit exceeded
        - 500 Error: Unexpected error

    Examples:
        Cache HIT:
        {
            "success": true,
            "data": { ... },
            "metadata": { ... },
            "from_cache": true
        }

        Cache MISS:
        {
            "success": true,
            "job_id": "550e8400-e29b-41d4-a716-446655440000",
            "extraction_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
            "from_cache": false,
            "stream_url": "/api/jobs/550e8400-e29b-41d4-a716-446655440000/stream",
            "result_url": "/api/extractions/7c9e6679-7425-40de-944b-e07fc1f90ae7"
        }
    """
    # Mock mode bypass
    if settings.mock_mode:
        logger.info("Mock mode enabled - returning test data")
        mock_response = get_mock_cim_response()
        return {
            "success": True,
            "data": mock_response["data"],
            "metadata": mock_response["metadata"],
            "from_cache": False
        }

    request_id = str(uuid.uuid4())
    file_label = make_file_label(file.filename, request_id)
    start_time = time.time()
    client_ip = get_client_ip(request)

    logger.info("Extraction request received", extra={
        "request_id": request_id,
        "file_name": file_label,
        "client_ip": client_ip,
        "user_id": user.id,
        "user_tier": user.tier
    })

    try:
        # Read file content
        content = await file.read()

        # ============================================
        # STEP 1: Check page limit (admin users have unlimited)
        # ============================================
        if user.tier != "admin" and user.pages_limit > 0:
            if user.pages_this_month >= user.pages_limit:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "page_limit_exceeded",
                        "message": f"Monthly page limit reached ({user.pages_limit} pages). Please upgrade your plan.",
                        "pages_used": user.pages_this_month,
                        "pages_limit": user.pages_limit
                    }
                )

        logger.info(f"User page usage: {user.pages_this_month}/{user.pages_limit}", extra={
            "request_id": request_id,
            "user_id": user.id
        })

        # ============================================
        # STEP 2: Check cache FIRST (highest priority)
        # ============================================
        cached_result = cache.get(content)

        if cached_result:
            logger.info("Cache HIT - returning immediately", extra={"request_id": request_id})

            _, remaining = rate_limiter.check_limit(client_ip)

            analytics.track_event(
                "cache_hit",
                client_ip=client_ip,
                filename=file.filename,
                file_size=len(content)
            )

            # Apply normalization and red flags to cached data
            try:
                normalized_cached = _normalize_llm_output(cached_result)
                extracted_data_obj = ExtractedData(**normalized_cached.get("data", {}))
                red_flags = detect_red_flags(extracted_data_obj)
                if "data" not in normalized_cached:
                    normalized_cached["data"] = {}
                normalized_cached["data"]["red_flags"] = red_flags
            except Exception as e:
                logger.warning(f"Failed to process cached data: {e}")
                normalized_cached = cached_result
                if "data" not in normalized_cached:
                    normalized_cached["data"] = {}
                normalized_cached["data"]["red_flags"] = []

            # Return 200 OK with full result (sync behavior)
            return {
                "success": True,
                "data": normalized_cached.get("data", cached_result["data"]),
                "metadata": {
                    "request_id": request_id,
                    "filename": file.filename,
                    "pages": cached_result["metadata"]["pages"],
                    "characters_extracted": cached_result["metadata"]["characters_extracted"],
                    "processing_time_seconds": time.time() - start_time,
                    "timestamp": datetime.now().isoformat()
                },
                "from_cache": True
            }

        # ============================================
        # STEP 2: Cache MISS - Check rate limit
        # ============================================
        logger.info("Cache MISS - creating async job", extra={"request_id": request_id})

        is_allowed, remaining = rate_limiter.check_limit(client_ip)

        if not is_allowed:
            reset_time = rate_limiter.get_reset_time(client_ip)
            hours_until_reset = (reset_time - datetime.now()).total_seconds() / 3600

            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"Rate limit exceeded. Resets in {hours_until_reset:.1f} hours.",
                    "reset_in_hours": round(hours_until_reset, 1)
                }
            )

        # Validate file
        document_processor.validate_file(file.filename, content)

        analytics.track_event(
            "upload_start",
            client_ip=client_ip,
            filename=file.filename,
            file_size=len(content)
        )

        # ============================================
        # STEP 3: Create extraction + job records
        # ============================================
        db = next(get_db())
        try:
            extraction = Extraction(
                id=request_id,
                user_id=user.id,
                user_tier=user.tier,
                filename=file.filename,
                file_size_bytes=len(content),
                page_count=0,  # Will be updated after parsing
                status="processing"
            )
            db.add(extraction)
            db.commit()

            # Create job state
            job_id = str(uuid.uuid4())
            job_state = JobState(
                id=job_id,
                extraction_id=request_id,
                status="queued",
                current_stage="queued",
                progress_percent=0,
                message="Queued for processing..."
            )
            db.add(job_state)
            db.commit()

            logger.info(f"Created job {job_id} for extraction {request_id}", extra={"job_id": job_id})

        finally:
            db.close()

        # Record upload for rate limiting
        rate_limiter.record_upload(client_ip)

        # ============================================
        # STEP 4: Start background processing with asyncio
        # ============================================
        # Use asyncio.create_task() for true fire-and-forget background execution
        asyncio.create_task(
            process_document_async(
                job_id,
                request_id,
                content,
                file.filename,
                client_ip,
                user.id
            )
        )

        # ============================================
        # STEP 5: Return 202 Accepted with job_id (async behavior)
        # ============================================
        return JSONResponse(
            status_code=202,  # Accepted - processing asynchronously
            content={
                "success": True,
                "job_id": job_id,
                "extraction_id": request_id,
                "message": "Document queued for processing",
                "from_cache": False,
                "stream_url": f"/api/jobs/{job_id}/stream",
                "status_url": f"/api/jobs/{job_id}/status",
                "result_url": f"/api/extractions/{request_id}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error", extra={"request_id": request_id, "error": str(e)})
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred. Request ID: {request_id}"
        )


@router.get("/api/extractions/{extraction_id}")
async def get_extraction_result(extraction_id: str):
    """
    Fetch the final extraction result after job completes.

    Called by frontend after receiving 'complete' event from SSE stream.

    Returns the full extracted data with metadata.
    """
    db = next(get_db())

    try:
        # Check if extraction exists
        extraction = db.query(Extraction).filter(Extraction.id == extraction_id).first()

        if not extraction:
            raise HTTPException(
                status_code=404,
                detail=f"Extraction {extraction_id} not found"
            )

        # Check status
        if extraction.status == "processing":
            # Still processing - check job state for details
            job = db.query(JobState).filter(JobState.extraction_id == extraction_id).first()

            return JSONResponse(
                status_code=202,  # Accepted (still processing)
                content={
                    "success": False,
                    "status": "processing",
                    "message": job.message if job else "Extraction still in progress",
                    "progress": job.progress_percent if job else 0,
                    "job_id": job.id if job else None
                }
            )

        if extraction.status == "failed":
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "extraction_failed",
                    "message": extraction.error_message or "Extraction failed",
                    "extraction_id": extraction_id
                }
            )

        # Status is "completed" - load result from saved file
        parsed_dir = settings.parsed_dir

        # Find the result file (search by extraction_id prefix)
        result_files = list(parsed_dir.glob(f"*_{extraction_id[:8]}.json"))

        if not result_files:
            raise HTTPException(
                status_code=404,
                detail=f"Extraction result file not found for {extraction_id}"
            )

        # Load the result
        result_file = result_files[0]
        with open(result_file, 'r', encoding='utf-8') as f:
            result_data = json.load(f)

        logger.info(f"Retrieved extraction result for {extraction_id}", extra={
            "extraction_id": extraction_id
        })

        return {
            "success": True,
            "data": result_data.get("data", {}),
            "metadata": {
                "extraction_id": extraction_id,
                "filename": extraction.filename,
                "pages": extraction.page_count,
                "processing_time_ms": extraction.processing_time_ms,
                "cost_usd": extraction.cost_usd,
                "parser_used": extraction.parser_used,
                "created_at": extraction.created_at.isoformat() if extraction.created_at else None,
                "completed_at": extraction.completed_at.isoformat() if extraction.completed_at else None
            },
            "from_cache": extraction.from_cache or False
        }

    finally:
        db.close()
