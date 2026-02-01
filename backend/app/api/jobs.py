# app/api/jobs.py
"""Real-time job progress tracking with Server-Sent Events (SSE)"""
import asyncio
import json
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
import httpx

from app.db_models_users import User
from app.utils.logging import logger
from app.auth import get_current_user
from app.repositories.job_repository import JobRepository
from app.repositories.extraction_repository import ExtractionRepository
from app.repositories.document_repository import DocumentRepository
from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions
from app.config import settings

# Import job progress tracker (separate module to avoid circular imports)
from app.services.job_tracker import JobProgressTracker
from app.services.pubsub import safe_subscribe

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
    # Note: We check job existence inside event_generator to send proper error events
    # This initial check is just for ownership verification
    job_repo = JobRepository()
    extraction_repo = ExtractionRepository()

    job = job_repo.get_job(job_id)

    # If job doesn't exist, we'll handle it gracefully in the SSE stream
    # by sending error events instead of raising 404 here
    if not job:
        # Skip ownership check, let event_generator handle the not-found case
        async def event_generator():
            logger.warning(f"[SSE] Job {job_id} not found during auth check", extra={"job_id": job_id})
            yield ServerSentEvent(
                data=json.dumps({
                    'message': 'Job not found',
                    'type': 'not_found',
                    'isRetryable': False
                }),
                event="error"
            )
            yield ServerSentEvent(data=json.dumps({'reason': 'not_found', 'job_id': job_id}), event="end")

        return EventSourceResponse(
            event_generator(),
            headers={
                "X-Accel-Buffering": "no",
                "Cache-Control": "no-cache",
                "Content-Type": "text/event-stream; charset=utf-8"
            }
        )

    # Generic ownership verification: check which entity type this job belongs to
    # JobState supports: extraction_id, document_id, workflow_run_id (exactly one is set)
    entity_owner_id = None
    entity_type = None

    if job.extraction_id:
        # Extract Mode: verify through extraction
        extraction = extraction_repo.get_extraction(job.extraction_id)
        if not extraction:
            raise HTTPException(status_code=404, detail=f"Extraction not found for job {job_id}")
        entity_owner_id = extraction.user_id
        entity_type = "extraction"

    elif job.workflow_run_id:
        # Workflow Mode: verify through workflow run
        from app.repositories.workflow_repository import WorkflowRepository
        run = WorkflowRepository.get_run_by_id(job.workflow_run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Workflow run not found for job {job_id}")
        entity_owner_id = run.user_id
        entity_type = "workflow"

    elif job.document_id:
        # Chat Mode: verify through document
        doc_repo = DocumentRepository()
        doc = doc_repo.get_by_id(job.document_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document not found for job {job_id}")
        entity_owner_id = doc.user_id
        entity_type = "document"

    elif job.template_fill_run_id:
        # Template Fill Mode: verify through template fill run
        from app.repositories.template_repository import TemplateRepository
        fill_run = TemplateRepository.get_fill_run_by_id(job.template_fill_run_id)
        if not fill_run:
            raise HTTPException(status_code=404, detail=f"Template fill run not found for job {job_id}")
        entity_owner_id = fill_run.user_id
        entity_type = "template_fill"

    else:
        # No entity associated with job (should never happen due to DB constraints)
        logger.error(f"[SSE] Job {job_id} has no associated entity (extraction_id, workflow_run_id, document_id, or template_fill_run_id)",
                    extra={"job_id": job_id})
        raise HTTPException(status_code=404, detail=f"Job {job_id} has no associated entity")

    # Verify ownership
    if entity_owner_id != user_id:
        logger.warning(
            f"[SSE] User {user_id} attempted to access {entity_type} job {job_id} owned by {entity_owner_id}",
            extra={"job_id": job_id, "user_id": user_id, "owner_id": entity_owner_id, "entity_type": entity_type}
        )
        raise HTTPException(status_code=403, detail="You don't have permission to access this job")

    logger.info(
        f"[SSE] User {user_id} authorized to stream {entity_type} job {job_id}",
        extra={"job_id": job_id, "entity_type": entity_type}
    )

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
        job_repo = JobRepository()
        job = job_repo.get_job(job_id)

        if not job:
            # Send proper error event instead of raising 404
            # This allows frontend to handle gracefully and clear state
            logger.warning(f"[SSE] Job {job_id} not found - sending error event", extra={"job_id": job_id})
            yield ServerSentEvent(
                data=json.dumps({
                    'message': 'Job not found',
                    'type': 'not_found',
                    'isRetryable': False
                }),
                event="error"
            )
            yield ServerSentEvent(data=json.dumps({'reason': 'not_found', 'job_id': job_id}), event="end")
            return

        if job.status == "completed":
            complete_data = {
                'message': job.message or 'Job completed successfully',
            }
            # Include the relevant entity ID based on job type
            if job.extraction_id:
                complete_data['extraction_id'] = job.extraction_id
            if job.workflow_run_id:
                complete_data['run_id'] = job.workflow_run_id
            if job.template_fill_run_id:
                complete_data['fill_run_id'] = job.template_fill_run_id
            if job.document_id:
                complete_data['document_id'] = job.document_id

            yield ServerSentEvent(data=json.dumps(complete_data), event="complete")
            yield ServerSentEvent(data=json.dumps({'reason': 'completed', 'job_id': job_id}), event="end")
            return

        # Template fill specific: Handle awaiting_review status
        # This occurs after auto-mapping completes and user needs to review
        if job.status in ("mapped", "awaiting_review"):
            # Check if this is a template fill job
            if job.template_fill_run_id:
                from app.repositories.template_repository import TemplateRepository
                fill_run = TemplateRepository.get_fill_run_by_id(job.template_fill_run_id)
                if fill_run and fill_run.status == "awaiting_review":
                    # Auto-mapping is complete, user needs to review
                    yield ServerSentEvent(data=json.dumps({
                        'message': job.message or 'Mapping complete - ready for review',
                        'fill_run_id': job.template_fill_run_id,
                        'status': 'awaiting_review'
                    }), event="complete")
                    yield ServerSentEvent(data=json.dumps({'reason': 'awaiting_review', 'job_id': job_id}), event="end")
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

        pubsub = safe_subscribe(job_id)
        max_duration = 800  # seconds
        elapsed = 0
        keepalive_interval = 8  # seconds for keepalive comment
        last_keepalive = 0

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
    job_repo = JobRepository()
    extraction_repo = ExtractionRepository()

    job = job_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Generic ownership verification (same as SSE endpoint)
    entity_owner_id = None

    if job.extraction_id:
        extraction = extraction_repo.get_extraction(job.extraction_id)
        if not extraction:
            raise HTTPException(status_code=404, detail="Extraction not found")
        entity_owner_id = extraction.user_id

    elif job.workflow_run_id:
        from app.repositories.workflow_repository import WorkflowRepository
        run = WorkflowRepository.get_run_by_id(job.workflow_run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Workflow run not found")
        entity_owner_id = run.user_id

    elif job.document_id:
        doc_repo = DocumentRepository()
        doc = doc_repo.get_by_id(job.document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        entity_owner_id = doc.user_id

    elif job.template_fill_run_id:
        # Template Fill Mode: verify through template fill run
        from app.repositories.template_repository import TemplateRepository
        fill_run = TemplateRepository.get_fill_run_by_id(job.template_fill_run_id)
        if not fill_run:
            raise HTTPException(status_code=404, detail="Template fill run not found")
        entity_owner_id = fill_run.user_id

    else:
        raise HTTPException(status_code=404, detail="Job has no associated entity")

    # Verify ownership
    if entity_owner_id != user.id:
        raise HTTPException(status_code=403, detail="You don't have permission to access this job")

    return {
        "job_id": job.id,
        "extraction_id": job.extraction_id,
        "workflow_run_id": job.workflow_run_id,
        "document_id": job.document_id,
        "template_fill_run_id": job.template_fill_run_id,
        "status": job.status,
        "current_stage": job.current_stage,
        "progress_percent": job.progress_percent,
        "message": job.message,
        "details": job.details,
        "parsing_completed": job.parsing_completed,
        "chunking_completed": job.chunking_completed,
        "summarizing_completed": job.summarizing_completed,
        "extracting_completed": job.extracting_completed,
        # Template fill specific flags
        "field_detection_completed": job.field_detection_completed,
        "auto_mapping_completed": job.auto_mapping_completed,
        "data_extraction_completed": job.data_extraction_completed,
        "excel_filling_completed": job.excel_filling_completed,
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


@router.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str, user: User = Depends(get_current_user)):
    """
    Retry a failed extraction job - REQUIRES AUTHENTICATION

    Currently only supports retrying LLM extraction failures (most common case).
    Other failures (parsing, chunking) require re-uploading the document.
    """
    job_repo = JobRepository()
    extraction_repo = ExtractionRepository()

    job = job_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Generic ownership verification (same as SSE endpoint)
    entity_owner_id = None
    extraction = None

    if job.extraction_id:
        extraction = extraction_repo.get_extraction(job.extraction_id)
        if not extraction:
            raise HTTPException(status_code=404, detail="Extraction not found")
        entity_owner_id = extraction.user_id

    elif job.workflow_run_id:
        from app.repositories.workflow_repository import WorkflowRepository
        run = WorkflowRepository.get_run_by_id(job.workflow_run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Workflow run not found")
        entity_owner_id = run.user_id

    elif job.document_id:
        doc_repo = DocumentRepository()
        doc = doc_repo.get_by_id(job.document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        entity_owner_id = doc.user_id

    elif job.template_fill_run_id:
        # Template Fill Mode: verify through template fill run
        from app.repositories.template_repository import TemplateRepository
        fill_run = TemplateRepository.get_fill_run_by_id(job.template_fill_run_id)
        if not fill_run:
            raise HTTPException(status_code=404, detail="Template fill run not found")
        entity_owner_id = fill_run.user_id

    else:
        raise HTTPException(status_code=404, detail="Job has no associated entity")

    # Verify ownership
    if entity_owner_id != user.id:
        raise HTTPException(status_code=403, detail="You don't have permission to retry this job")

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

    # Reset job state for retry using repository
    # Note: We need to add a method to handle complex updates like this
    # For now, we'll use update_job but we need to handle error_* fields
    # TODO: Add a reset_for_retry method to JobRepository
    job_repo.update_job(
        job_id=job_id,
        status="queued",
        message=f"Retrying from {resume_stage} stage"
    )

    logger.info(f"Job {job_id} queued for retry from {resume_stage}", extra={
        "job_id": job_id,
        "resume_stage": resume_stage
    })

    # # Trigger background retry processing
    # asyncio.create_task(
    #     retry_document_async(
    #         job_id=job_id,
    #         extraction_id=job.extraction_id,
    #         resume_stage=resume_stage,
    #         resume_data_path=resume_data_path
    #     )
    # )

    return {
        "success": True,
        "job_id": job_id,
        "extraction_id": job.extraction_id,
        "resume_stage": resume_stage,
        "message": f"Job retry initiated from {resume_stage} stage"
    }
