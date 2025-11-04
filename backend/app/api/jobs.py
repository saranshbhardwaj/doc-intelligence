# app/api/jobs.py
"""Real-time job progress tracking with Server-Sent Events (SSE)"""
import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
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

router = APIRouter()

# Initialize Clerk client for token verification
clerk = Clerk(bearer_auth=settings.clerk_secret_key)


class JobProgressTracker:
    """Manages job state updates and broadcasts progress events"""

    def __init__(self, db: Session, job_id: str):
        self.db = db
        self.job_id = job_id
        self._listeners = []

    def get_job_state(self) -> JobState:
        """Get current job state from database"""
        job = self.db.query(JobState).filter(JobState.id == self.job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {self.job_id} not found")
        return job

    def update_progress(
        self,
        status: str = None,
        current_stage: str = None,
        progress_percent: int = None,
        message: str = None,
        details: dict = None,
        **stage_flags
    ):
        """Update job progress and persist to database"""
        job = self.get_job_state()

        if status:
            job.status = status
        if current_stage:
            job.current_stage = current_stage
        if progress_percent is not None:
            job.progress_percent = progress_percent
        if message:
            job.message = message
        if details:
            job.details = details

        # Update stage completion flags
        for flag_name, flag_value in stage_flags.items():
            if hasattr(job, flag_name):
                setattr(job, flag_name, flag_value)

        job.updated_at = datetime.now()
        self.db.commit()
        self.db.refresh(job)

        logger.info(f"Job {self.job_id} updated: {status or 'progress'} - {message}", extra={
            "job_id": self.job_id,
            "status": job.status,
            "progress": job.progress_percent
        })

    def mark_error(
        self,
        error_stage: str,
        error_message: str,
        error_type: str = "unknown_error",
        is_retryable: bool = True
    ):
        """Mark job as failed with error details"""
        job = self.get_job_state()
        job.status = "failed"
        job.error_stage = error_stage
        job.error_message = error_message[:1000]  # Truncate long errors
        job.error_type = error_type
        job.is_retryable = is_retryable
        job.updated_at = datetime.now()
        self.db.commit()
        self.db.refresh(job)

        logger.error(f"Job {self.job_id} failed at {error_stage}: {error_message}", extra={
            "job_id": self.job_id,
            "error_stage": error_stage,
            "error_type": error_type
        })

    def mark_completed(self):
        """Mark job as successfully completed"""
        job = self.get_job_state()
        job.status = "completed"
        job.progress_percent = 100
        job.current_stage = "completed"
        job.message = "Extraction completed successfully"
        job.completed_at = datetime.now()
        job.updated_at = datetime.now()
        self.db.commit()
        self.db.refresh(job)

        logger.info(f"Job {self.job_id} completed successfully", extra={
            "job_id": self.job_id
        })

    def save_intermediate_result(
        self,
        stage: str,
        file_path: str
    ):
        """Save path to intermediate result for resume capability"""
        job = self.get_job_state()

        path_mapping = {
            "parsing": "parsed_output_path",
            "chunking": "chunks_path",
            "summarizing": "summaries_path",
            "combining": "combined_context_path"
        }

        if stage in path_mapping:
            setattr(job, path_mapping[stage], file_path)
            job.updated_at = datetime.now()
            self.db.commit()

            logger.info(f"Saved {stage} result to {file_path}", extra={
                "job_id": self.job_id,
                "stage": stage
            })


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
        """Generate SSE events by polling database.

        Improvements:
        - Include both legacy and new field names (progress + progress_percent, stage + current_stage)
        - Emit a progress heartbeat every N polls even if no DB change so frontend UI stays lively
        - Use small non-blocking sleep and offload blocking DB refresh to thread to reduce loop starvation
        """
        logger.info(f"[SSE] ★★★ Generator function STARTED for job {job_id} ★★★", extra={"job_id": job_id})

        db = next(get_db())

        try:
            # Verify job exists
            logger.info(f"[SSE] Checking if job exists in database...", extra={"job_id": job_id})
            job = db.query(JobState).filter(JobState.id == job_id).first()

            if not job:
                logger.error(f"[SSE] Job NOT FOUND in database!", extra={"job_id": job_id})
                yield ServerSentEvent(data=json.dumps({'message': 'Job not found'}), event="error")
                return

            logger.info(f"[SSE] Job found! Starting polling loop. Initial status={job.status}, progress={job.progress_percent}%", extra={"job_id": job_id})

            # Yield initial state immediately to force stream to start
            # Check if job is already completed or failed
            if job.status == "completed":
                complete_data = {
                    "message": job.message or "Extraction completed successfully",
                    "extraction_id": job.extraction_id
                }
                yield ServerSentEvent(data=json.dumps(complete_data), event="complete")
                # Explicit end event so frontend can distinguish graceful close
                yield ServerSentEvent(data=json.dumps({'reason': 'completed', 'job_id': job_id}), event="end")
                logger.info(f"[SSE] Job already completed, sent complete + end events and exiting", extra={"job_id": job_id})
                return
            elif job.status == "failed":
                error_data = {
                    "stage": job.error_stage,
                    "message": job.error_message,
                    "type": job.error_type,
                    "retryable": job.is_retryable
                }
                yield ServerSentEvent(data=json.dumps(error_data), event="error")
                yield ServerSentEvent(data=json.dumps({'reason': 'failed', 'job_id': job_id}), event="end")
                logger.info(f"[SSE] Job already failed, sent error + end events and exiting", extra={"job_id": job_id})
                return

            # Job is in progress - send initial progress event
            initial_event = {
                "status": job.status,
                "stage": job.current_stage,
                "progress": job.progress_percent,
                "message": job.message,
                "details": job.details or {},
            }
            yield ServerSentEvent(data=json.dumps(initial_event), event="progress")
            logger.info(f"[SSE] Sent initial progress event", extra={"job_id": job_id})

            last_update = job.updated_at
            poll_interval = 2  # Poll every 2 seconds
            max_duration = 800  # Timeout after 800 seconds
            elapsed = 0
            heartbeat_counter = 0  # send forced progress event every few keepalives

            while elapsed < max_duration:
                # Expire the current object and reload from database
                # This ensures we get the latest data from other sessions
                # Offload potentially blocking refresh calls
                try:
                    db.expire(job)
                    db.refresh(job)
                except Exception as refresh_err:
                    logger.warning("[SSE] DB refresh warning", extra={"job_id": job_id, "error": str(refresh_err)})

                # Log every poll to see what's happening
                poll_count = elapsed // poll_interval
                logger.info(f"[SSE Poll #{poll_count}] status={job.status}, progress={job.progress_percent}%, updated_at={job.updated_at}, last_update={last_update}", extra={"job_id": job_id})

                # Only send update if something changed
                if job.updated_at != last_update:
                    logger.info(f"[SSE] CHANGE DETECTED! Sending event: {job.status} at {job.progress_percent}%", extra={"job_id": job_id})
                    last_update = job.updated_at

                    # Prepare event data
                    event_data = {
                        "status": job.status,
                        "stage": job.current_stage,
                        "progress": job.progress_percent,
                        "message": job.message,
                        "details": job.details or {}
                    }

                    # Send appropriate event type
                    if job.status == "failed":
                        error_data = {
                            "stage": job.error_stage,
                            "message": job.error_message,
                            "type": job.error_type,
                            "retryable": job.is_retryable
                        }
                        yield ServerSentEvent(data=json.dumps(error_data), event="error")
                        yield ServerSentEvent(data=json.dumps({'reason': 'failed', 'job_id': job_id}), event="end")
                        break

                    elif job.status == "completed":
                        complete_data = {
                            "message": job.message or "Extraction completed successfully",
                            "extraction_id": job.extraction_id
                        }
                        yield ServerSentEvent(data=json.dumps(complete_data), event="complete")
                        yield ServerSentEvent(data=json.dumps({'reason': 'completed', 'job_id': job_id}), event="end")
                        break

                    else:
                        # Progress update
                        yield ServerSentEvent(data=json.dumps(event_data), event="progress")
                else:
                    logger.info(f"[SSE] No change detected", extra={"job_id": job_id})
                    # Yield keepalive comment
                    yield ": keepalive\n\n"

                    # Force send duplicate progress every 5 heartbeats (approx every 10s) so frontend can show spinner
                    heartbeat_counter += 1
                    if heartbeat_counter >= 5 and job.status not in ("failed", "completed"):
                        heartbeat_counter = 0
                        forced_event = {
                            "status": job.status,
                            "stage": job.current_stage,
                            "progress": job.progress_percent,
                            "message": job.message,
                            "details": job.details or {}
                        }
                        yield ServerSentEvent(data=json.dumps(forced_event), event="progress")

                # Wait before next poll
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            # Timeout
            if elapsed >= max_duration:
                yield ServerSentEvent(data=json.dumps({'message': 'Job timeout', 'type': 'timeout'}), event="error")
                yield ServerSentEvent(data=json.dumps({'reason': 'timeout', 'job_id': job_id}), event="end")

        except Exception as e:
            logger.exception(f"SSE stream error for job {job_id}", extra={"error": str(e)})
            yield ServerSentEvent(data=json.dumps({'message': 'Stream error', 'type': 'stream_error'}), event="error")
            yield ServerSentEvent(data=json.dumps({'reason': 'stream_error', 'job_id': job_id}), event="end")

        finally:
            db.close()

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
            "stage": job.current_stage,
            "progress": job.progress_percent,
            "message": job.message,
            "details": job.details,
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
    Retry a failed job from the last successful stage - REQUIRES AUTHENTICATION

    Uses cached intermediate results to avoid re-running expensive operations
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

        # Determine which stage to resume from
        resume_stage = None
        resume_data_path = None

        if job.extracting_completed or job.combined_context_path:
            # LLM extraction failed - retry from extraction
            resume_stage = "extracting"
            resume_data_path = job.combined_context_path
        elif job.summarizing_completed or job.summaries_path:
            # Summarization failed - retry from summarization
            resume_stage = "summarizing"
            resume_data_path = job.summaries_path
        elif job.chunking_completed or job.chunks_path:
            # Chunking failed - retry from chunking
            resume_stage = "chunking"
            resume_data_path = job.chunks_path
        elif job.parsing_completed or job.parsed_output_path:
            # Parsing failed - retry from parsing
            resume_stage = "parsing"
            resume_data_path = job.parsed_output_path
        else:
            # No progress saved - restart from beginning
            resume_stage = "queued"

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

        # TODO: Trigger pipeline processing with resume data
        # This will be implemented in the next step when we update extraction_pipeline

        return {
            "success": True,
            "job_id": job_id,
            "resume_stage": resume_stage,
            "message": f"Job queued for retry from {resume_stage} stage"
        }

    finally:
        db.close()
