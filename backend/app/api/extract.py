# app/api/extract.py
"""Unified extraction endpoint with smart cache-aware routing

This endpoint intelligently handles both cache hits and misses:
- Cache HIT → Returns result immediately (200 OK)
- Cache MISS → Returns job_id for async processing (202 Accepted)
"""
from datetime import datetime
import time
import uuid
import json
import asyncio
import hashlib
import os

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import JSONResponse

from app.api.dependencies import (
    get_client_ip, document_processor, cache, analytics
)
from app.auth import get_current_user
from app.db_models_users import User
from app.models import ExtractedData
from app.utils.file_utils import make_file_label
from app.utils.normalization import _normalize_llm_output
from app.services.mock_responses import get_mock_cim_response
from app.services.risk_detector import detect_red_flags
from app.config import settings
from app.utils.logging import logger
from app.repositories.job_repository import JobRepository
from app.repositories.extraction_repository import ExtractionRepository

# Orchestration service
from app.services.async_pipeline.extraction_orchestrator import process_document_async
from app.services.tasks import start_extraction_chain

router = APIRouter()


@router.post("/api/extract")
async def extract_document(
    file: UploadFile = File(...),
    context: str = Form(None),
    request: Request = None,
    user: User = Depends(get_current_user)
):
    """
    Unified extraction endpoint with smart cache-aware routing.

    **Requires authentication** - User must provide valid Clerk session token.

    Args:
        file: PDF file to extract
        context: Optional user-provided context to guide extraction (max 500 chars)
        request: FastAPI request object
        user: Authenticated user from Clerk

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

        # Calculate content hash for duplicate detection
        content_hash = hashlib.sha256(content).hexdigest()

        # ============================================
        # STEP 1: Check if user already has this exact document (by content hash)
        # ============================================
        extraction_repo = ExtractionRepository()
        existing_extraction = extraction_repo.check_duplicate_extraction(
            user_id=user.id,
            content_hash=content_hash
        )

        if existing_extraction:
            logger.info("Duplicate document detected - returning existing extraction", extra={
                "request_id": request_id,
                "existing_extraction_id": existing_extraction.id,
                "user_id": user.id
            })

            # Load existing result from parsed_dir
            result_files = list(settings.parsed_dir.glob(f"*_{existing_extraction.id[:8]}.json"))

            if result_files:
                with open(result_files[0], 'r', encoding='utf-8') as f:
                    result_data = json.load(f)

                return {
                    "success": True,
                    "data": result_data.get("data", {}),
                    "metadata": {
                        "extraction_id": existing_extraction.id,
                        "request_id": request_id,
                        "filename": existing_extraction.filename,
                        "pages": existing_extraction.page_count,
                        "characters_extracted": result_data.get("metadata", {}).get("characters_extracted", 0),
                        "processing_time_seconds": time.time() - start_time,
                        "timestamp": datetime.now().isoformat(),
                        "original_created_at": existing_extraction.created_at.isoformat() if existing_extraction.created_at else None
                    },
                    "from_cache": False,
                    "from_history": True,
                    "message": "This document was already processed"
                }
            else:
                # Extraction record exists but file is missing - treat as cache miss
                logger.warning("Extraction exists but result file missing", extra={
                    "extraction_id": existing_extraction.id
                })

        # ============================================
        # STEP 2: Check page limit (admin users have unlimited)
        # ============================================
        if user.tier != "admin" and user.pages_limit > 0:
            # For free tier: Check total pages processed (one-time limit)
            # For paid tiers: Check monthly pages (recurring limit)
            if user.tier == "free":
                # Free tier gets 100 pages ONE TIME total
                if user.total_pages_processed >= user.pages_limit:
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "error": "page_limit_exceeded",
                            "message": f"Free tier limit reached ({user.pages_limit} pages total). Please upgrade to continue.",
                            "pages_used": user.total_pages_processed,
                            "pages_limit": user.pages_limit,
                            "tier": user.tier
                        }
                    )
            else:
                # Paid tiers have monthly limits
                if user.pages_this_month >= user.pages_limit:
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "error": "page_limit_exceeded",
                            "message": f"Monthly page limit reached ({user.pages_limit} pages). Your limit resets next month.",
                            "pages_used": user.pages_this_month,
                            "pages_limit": user.pages_limit,
                            "tier": user.tier
                        }
                    )

        # Log usage
        if user.tier == "free":
            logger.info(f"User page usage (total): {user.total_pages_processed}/{user.pages_limit}", extra={
                "request_id": request_id,
                "user_id": user.id
            })
        else:
            logger.info(f"User page usage (monthly): {user.pages_this_month}/{user.pages_limit}", extra={
                "request_id": request_id,
                "user_id": user.id
            })

        # ============================================
        # STEP 3: Check cache (global cache across all users)
        # ============================================
        cached_result = cache.get(content)

        if cached_result:
            logger.info("Cache HIT - creating extraction record and returning result", extra={
                "request_id": request_id,
                "user_id": user.id
            })

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

            # Create extraction record in database so it appears in user's history
            # Validate and truncate context if provided
            if context:
                context = context.strip()[:500]

            extraction = extraction_repo.create_extraction_record(
                extraction_id=request_id,
                user_id=user.id,
                user_tier=user.tier,
                filename=file.filename,
                file_size_bytes=len(content),
                content_hash=content_hash,
                status="completed",
                page_count=cached_result["metadata"]["pages"],
                from_cache=True,
                context=context
            )

            if extraction:
                # Save parsed result to disk so dashboard can load it
                try:
                    from app.utils.file_utils import save_parsed_result
                    save_parsed_result(request_id, normalized_cached, file.filename)

                    logger.info("Cache hit extraction saved to database and disk", extra={
                        "request_id": request_id,
                        "user_id": user.id
                    })
                except Exception as e:
                    logger.error(f"Failed to save cache hit result to disk: {e}", extra={
                        "request_id": request_id
                    }, exc_info=True)
            else:
                logger.error("Failed to save cache hit extraction to database", extra={
                    "request_id": request_id,
                    "user_id": user.id
                })

            # Return 200 OK with full result (sync behavior)
            return {
                "success": True,
                "data": normalized_cached.get("data", cached_result["data"]),
                "metadata": {
                    "extraction_id": request_id,
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
        # STEP 4: Cache MISS - Check rate limit
        # ============================================
        logger.info("Cache MISS - creating async job", extra={"request_id": request_id})

        # Validate file
        document_processor.validate_file(file.filename, content)

        analytics.track_event(
            "upload_start",
            client_ip=client_ip,
            filename=file.filename,
            file_size=len(content)
        )

        # ============================================
        # STEP 5: Create extraction + job records
        # ============================================
        # Validate and truncate context if provided
        if context:
            context = context.strip()[:500]  # Max 500 chars

        extraction = extraction_repo.create_extraction_record(
            extraction_id=request_id,
            user_id=user.id,
            user_tier=user.tier,
            filename=file.filename,
            file_size_bytes=len(content),
            content_hash=content_hash,
            status="processing",
            page_count=0,  # Will be updated after parsing
            from_cache=False,
            context=context
        )

        if not extraction:
            raise HTTPException(status_code=500, detail="Failed to create extraction record")

        # Create job state
        job_id = str(uuid.uuid4())
        job_repo = JobRepository()
        job_state = job_repo.create_job(
            extraction_id=request_id,
            status="queued",
            current_stage="queued",
            progress_percent=0,
            message="Queued for processing...",
            job_id=job_id
        )

        if not job_state:
            raise HTTPException(status_code=500, detail="Failed to create job tracking record")

        logger.info(f"Created job {job_id} for extraction {request_id}", extra={"job_id": job_id})

        # ============================================
        # STEP 6: Start background processing (Celery or asyncio)
        if settings.use_celery:
            # Persist uploaded file to a shared volume path so worker container can access
            # Use /shared_uploads (ensure this directory is a bind/volume mount in docker-compose)
            shared_root = os.getenv("SHARED_UPLOAD_ROOT", "/shared_uploads")
            try:
                os.makedirs(shared_root, exist_ok=True)
            except Exception:
                # Fallback to system temp if shared dir cannot be created
                import tempfile
                shared_root = tempfile.gettempdir()

            safe_filename = file.filename.replace("/", "_").replace("\\", "_")
            temp_path = os.path.join(shared_root, f"{request_id}_{safe_filename}")
            with open(temp_path, "wb") as f_out:
                f_out.write(content)
            logger.info("Saved uploaded file for Celery processing", extra={"job_id": job_id, "path": temp_path})
            start_extraction_chain(temp_path, file.filename, job_id, request_id, user.id, context)
        else:
            asyncio.create_task(
                process_document_async(
                    job_id,
                    request_id,
                    content,
                    file.filename,
                    client_ip,
                    user.id,
                    context
                )
            )

        # ============================================
        # STEP 7: Return 202 Accepted with job_id (async behavior)
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
    extraction_repo = ExtractionRepository()
    job_repo = JobRepository()

    # Check if extraction exists
    extraction = extraction_repo.get_extraction(extraction_id)

    if not extraction:
        raise HTTPException(
            status_code=404,
            detail=f"Extraction {extraction_id} not found"
        )

    # Check status
    if extraction.status == "processing":
        # Still processing - check job state for details
        job = job_repo.get_job_by_extraction_id(extraction_id)

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
