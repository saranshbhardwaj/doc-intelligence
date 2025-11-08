# app/api/jobs.py
"""Real-time job progress tracking with Server-Sent Events (SSE)"""
import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
import httpx

from app.database import get_db
from app.db_models import JobState, Extraction
from app.db_models_users import User
from app.utils.logging import logger
from app.auth import get_current_user
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions
from app.config import settings

# Import job progress tracker (separate module to avoid circular imports)
from app.services.job_tracker import JobProgressTracker
from app.services.pubsub import safe_subscribe

# Import retry function from orchestrator service
from app.services.async_pipeline.extraction_orchestrator import retry_document_async

router = APIRouter()

# Initialize Clerk client for token verification
clerk = Clerk(bearer_auth=settings.clerk_secret_key)


@router.get("/api/jobs/{job_id}/stream")
async def stream_job_progress(job_id: str, token: Optional[str] = Query(None)):
    """
    Server-Sent Events endpoint for real-time job progress updates

    NOTE: EventSource doesn't support custom headers, so auth token must be passed as query parameter.

    Returns SSE stream with events:
    - progress: { status, stage, percent, message, details }
    - error: { stage, message, type, retryable }
    - complete: { message }
    """

    # Verify authentication via token query parameter
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    try:
        # Convert token to httpx request for Clerk SDK authentication
        # EventSource doesn't support custom headers, so we receive token as query param
        # but Clerk expects it in the Authorization header
        logger.info(f"[SSE] Verifying token for job {job_id}...", extra={"job_id": job_id})

        httpx_request = httpx.Request(
            method="GET",
            url=f"http://localhost/api/jobs/{job_id}/stream",  # URL doesn't matter for token verification
            headers={"Authorization": f"Bearer {token}"}
        )

        # Authenticate the request with Clerk
        # Empty options accepts session tokens by default (not OAuth tokens)
        request_state = clerk.authenticate_request(
            httpx_request,
            AuthenticateRequestOptions()
        )

        if not request_state.is_signed_in:
            logger.error(f"[SSE] User is not signed in for job {job_id}", extra={"job_id": job_id})
            raise HTTPException(status_code=401, detail="Not signed in")

        # Extract user_id from the token payload ('sub' field in JWT)
        user_id = request_state.payload.get('sub') if request_state.payload else None

        if not user_id:
            logger.error(f"[SSE] Could not extract user_id from token for job {job_id}", extra={"job_id": job_id})
            raise HTTPException(status_code=401, detail="Could not extract user_id from token")

        logger.info(f"[SSE] Authenticated user {user_id} for job {job_id}", extra={"job_id": job_id, "user_id": user_id})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SSE] Invalid token for job {job_id}: {e}", extra={"job_id": job_id})
        raise HTTPException(status_code=401, detail=f"Invalid authentication token: {str(e)}")

    # Verify user owns this job
    db = next(get_db())
    try:
        job = db.query(JobState).filter(JobState.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        # Get the extraction to check user ownership
        extraction = db.query(Extraction).filter(Extraction.id == job.extraction_id).first()
        if not extraction:
            raise HTTPException(status_code=404, detail=f"Extraction not found for job {job_id}")

        # Verify user owns this extraction
        if extraction.user_id != user_id:
            logger.warning(f"[SSE] User {user_id} attempted to access job {job_id} owned by {extraction.user_id}",
                         extra={"job_id": job_id, "user_id": user_id, "owner_id": extraction.user_id})
            raise HTTPException(status_code=403, detail="You don't have permission to access this job")

        logger.info(f"[SSE] User {user_id} authorized to stream job {job_id}", extra={"job_id": job_id})
    finally:
        db.close()

    async def event_generator():
        """Async generator bridging Redis pub/sub to SSE.

        Defensive behaviors:
          - Sends initial snapshot from DB (atomic ownership check already done)
          - Falls back to lightweight periodic keepalive comments
          - Auto-terminates on complete/error/end events
          - Timeout guard
        """
        logger.info(f"[SSE] ★★★ PubSub stream STARTED for job {job_id} ★★★", extra={"job_id": job_id})

        end_sent = False  # Track if we've sent end event

        # Initial DB snapshot (single query) for immediate feedback
        db = next(get_db())
        try:
            job = db.query(JobState).filter(JobState.id == job_id).first()
            if not job:
                yield ServerSentEvent(data=json.dumps({'message': 'Job not found'}), event="error")
                yield ServerSentEvent(data=json.dumps({'reason': 'not_found', 'job_id': job_id}), event="end")
                return

            if job.status == "completed":
                yield ServerSentEvent(data=json.dumps({
                    'message': job.message or 'Extraction completed successfully',
                    'extraction_id': job.extraction_id
                }), event="complete")
                yield ServerSentEvent(data=json.dumps({'reason': 'completed', 'job_id': job_id}), event="end")
                return
            if job.status == "failed":
                yield ServerSentEvent(data=json.dumps({
                    'stage': job.error_stage,
                    'message': job.error_message,
                    'type': job.error_type,
                    'retryable': job.is_retryable
                }), event="error")
                yield ServerSentEvent(data=json.dumps({'reason': 'failed', 'job_id': job_id}), event="end")
                return

            # In-progress initial event
            yield ServerSentEvent(data=json.dumps({
                'status': job.status,
                'current_stage': job.current_stage,
                'progress_percent': job.progress_percent,
                'message': job.message,
                'details': job.details or {}
            }), event="progress")
        finally:
            db.close()

        pubsub = safe_subscribe(job_id)
        max_duration = 800  # seconds
        elapsed = 0
        keepalive_interval = 8  # seconds for keepalive comment
        last_keepalive = 0
        loop = asyncio.get_event_loop()

        try:
            while elapsed < max_duration:
                # Non-blocking attempt to get message every second
                message = pubsub.get_message(timeout=1.0)
                if message and message.get('type') == 'message':
                    try:
                        data = json.loads(message['data'])
                        event_type = data.get('event')
                        payload = data.get('payload', {})
                        if event_type:
                            yield ServerSentEvent(data=json.dumps(payload), event=event_type)
                            if event_type in ("complete", "error"):
                                # Send end event after complete/error
                                yield ServerSentEvent(
                                    data=json.dumps({'reason': event_type, 'job_id': job_id}), 
                                    event="end"
                                )
                                end_sent = True
                                break
                            elif event_type == "end":
                                end_sent = True
                                break
                    except Exception as e:
                        logger.warning("[SSE] Malformed pubsub message", extra={"job_id": job_id, "error": str(e)})
                else:
                    # Keepalive comment throttled
                    if (elapsed - last_keepalive) >= keepalive_interval:
                        yield ": keepalive\n\n"
                        last_keepalive = elapsed

                await asyncio.sleep(1)
                elapsed += 1
            
            # Ensure we always send end event
            if not end_sent:
                if elapsed >= max_duration:
                    yield ServerSentEvent(
                        data=json.dumps({'message': 'Job timeout', 'type': 'timeout'}), 
                        event="error"
                    )
                yield ServerSentEvent(
                    data=json.dumps({'reason': 'timeout' if elapsed >= max_duration else 'normal', 'job_id': job_id}), 
                    event="end"
                )

        except Exception as e:
            logger.exception(f"PubSub SSE stream error for job {job_id}", extra={"error": str(e)})
            if not end_sent:
                yield ServerSentEvent(
                    data=json.dumps({'message': 'Stream error', 'type': 'stream_error'}), 
                    event="error"
                )
                yield ServerSentEvent(
                    data=json.dumps({'reason': 'stream_error', 'job_id': job_id}), 
                    event="end"
                )
        finally:
            logger.info(f"[SSE] ★★★ PubSub stream ENDED for job {job_id} ★★★", extra={"job_id": job_id})
            try:
                pubsub.close()
            except Exception:
                pass

    return EventSourceResponse(
        event_generator(),
        headers={
            "X-Accel-Buffering": "no",  # Disable proxy buffering
            "Cache-Control": "no-cache",
            "Content-Type": "text/event-stream; charset=utf-8"
        }
    )


@router.get("/api/jobs/{job_id}/status")
async def get_job_status(job_id: str, user: User = Depends(get_current_user)):
    """Get current job status (polling alternative to SSE) - REQUIRES AUTHENTICATION"""
    db = next(get_db())

    try:
        job = db.query(JobState).filter(JobState.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Verify user owns this job
        extraction = db.query(Extraction).filter(Extraction.id == job.extraction_id).first()
        if not extraction or extraction.user_id != user.id:
            raise HTTPException(status_code=403, detail="You don't have permission to access this job")

        return {
            "job_id": job.id,
            "extraction_id": job.extraction_id,
            "status": job.status,
            "current_stage": job.current_stage,
            "progress_percent": job.progress_percent,
            "message": job.message,
            "details": job.details,
            "parsing_completed": job.parsing_completed,
            "chunking_completed": job.chunking_completed,
            "summarizing_completed": job.summarizing_completed,
            "extracting_completed": job.extracting_completed,
            "error": {
                "stage": job.error_stage,
                "message": job.error_message,
                "type": job.error_type,
                "retryable": job.is_retryable
            } if job.status == "failed" else None,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None
        }

    finally:
        db.close()


@router.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str, user: User = Depends(get_current_user)):
    """
    Retry a failed extraction job - REQUIRES AUTHENTICATION

    Currently only supports retrying LLM extraction failures (most common case).
    Other failures (parsing, chunking) require re-uploading the document.
    """
    db = next(get_db())

    try:
        job = db.query(JobState).filter(JobState.id == job_id).first()

        # Verify user owns this job
        if job:
            extraction = db.query(Extraction).filter(Extraction.id == job.extraction_id).first()
            if not extraction or extraction.user_id != user.id:
                raise HTTPException(status_code=403, detail="You don't have permission to retry this job")
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.status != "failed":
            raise HTTPException(status_code=400, detail="Only failed jobs can be retried")

        if not job.is_retryable:
            raise HTTPException(status_code=400, detail="This job cannot be retried")

        # Check if we can retry (only extraction stage supported)
        if not job.combined_context_path:
            raise HTTPException(
                status_code=400,
                detail="Cannot retry this job. Retry is only available for extraction failures. Please re-upload the document."
            )

        resume_stage = "extracting"
        resume_data_path = job.combined_context_path

        # Reset job state for retry
        job.status = "queued"
        job.error_stage = None
        job.error_message = None
        job.error_type = None
        job.message = f"Retrying from {resume_stage} stage"
        job.updated_at = datetime.now()
        db.commit()

        logger.info(f"Job {job_id} queued for retry from {resume_stage}", extra={
            "job_id": job_id,
            "resume_stage": resume_stage
        })

        # Trigger background retry processing
        asyncio.create_task(
            retry_document_async(
                job_id=job_id,
                extraction_id=job.extraction_id,
                resume_stage=resume_stage,
                resume_data_path=resume_data_path
            )
        )

        return {
            "success": True,
            "job_id": job_id,
            "extraction_id": job.extraction_id,
            "resume_stage": resume_stage,
            "message": f"Job retry initiated from {resume_stage} stage"
        }

    finally:
        db.close()
