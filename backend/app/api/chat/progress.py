# backend/app/api/chat/progress.py
"""SSE progress tracking endpoint for document indexing in Chat Mode."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from app.repositories.collection_repository import CollectionRepository
from app.repositories.job_repository import JobRepository
from app.utils.logging import logger

router = APIRouter()


@router.get("/jobs/{job_id}/progress")
async def get_indexing_progress(
    job_id: str,
    token: Optional[str] = Query(None)
):
    """
    Get document indexing progress (SSE streaming).

    NOTE: EventSource doesn't support custom headers, so auth token must be passed as query parameter.

    Args:
        job_id: JobState ID
        token: Authentication token (query parameter)

    Yields:
        SSE events with progress updates

    Raises:
        HTTPException 401: Missing or invalid authentication token
        HTTPException 403: User doesn't own the job
        HTTPException 404: Job not found

    SSE Events:
        - progress: Current indexing progress (status, stage, percent, message)
        - complete: Indexing completed successfully
        - error: Indexing failed with error details
        - end: Stream termination (always sent last)
    """

    # Edge case: Validate token is provided
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    # Verify authentication via token query parameter
    try:
        # Convert token to httpx request for Clerk SDK authentication
        import httpx
        from clerk_backend_api import Clerk
        from clerk_backend_api.security.types import AuthenticateRequestOptions
        from app.config import settings

        clerk = Clerk(bearer_auth=settings.clerk_secret_key)

        httpx_request = httpx.Request(
            method="GET",
            url=f"http://localhost/api/chat/jobs/{job_id}/progress",
            headers={"Authorization": f"Bearer {token}"}
        )

        request_state = clerk.authenticate_request(
            httpx_request,
            AuthenticateRequestOptions()
        )

        if not request_state.is_signed_in:
            logger.error(f"[Chat SSE] User not signed in for job {job_id}", extra={"job_id": job_id})
            raise HTTPException(status_code=401, detail="Not signed in")

        user_id = request_state.payload.get('sub') if request_state.payload else None

        if not user_id:
            logger.error(f"[Chat SSE] Could not extract user_id from token", extra={"job_id": job_id})
            raise HTTPException(status_code=401, detail="Could not extract user_id from token")

        logger.info(f"[Chat SSE] Authenticated user {user_id} for job {job_id}", extra={"job_id": job_id, "user_id": user_id})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Chat SSE] Auth error: {e}", extra={"job_id": job_id})
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

    # Verify user owns this job
    job_repo = JobRepository()
    collection_repo = CollectionRepository()

    job = job_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    # Get the collection document to check user ownership
    if not job.collection_document_id:
        raise HTTPException(status_code=400, detail="Job is not associated with a collection document")

    # Get collection to verify ownership
    # Note: collection_repo.get_document returns CollectionDocument which has collection_id
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        from app.db_models_chat import CollectionDocument
        doc = db.query(CollectionDocument).filter(CollectionDocument.id == job.collection_document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document not found for job {job_id}")

        collection = collection_repo.get_collection(doc.collection_id, user_id)
        if not collection:
            logger.warning(
                f"[Chat SSE] User {user_id} attempted to access job {job_id} for collection {doc.collection_id}",
                extra={"job_id": job_id, "user_id": user_id, "collection_id": doc.collection_id}
            )
            raise HTTPException(status_code=403, detail="You don't have permission to access this job")
    finally:
        db.close()

    logger.info(f"[Chat SSE] User {user_id} authorized to stream job {job_id}", extra={"job_id": job_id})

    async def event_generator():
        """Async generator bridging Redis pub/sub to SSE.

        Pattern matches Extract Mode implementation in jobs.py
        """
        import json
        import asyncio
        from app.services.pubsub import safe_subscribe

        logger.info(f"[Chat SSE] ★★★ PubSub stream STARTED for job {job_id} ★★★", extra={"job_id": job_id})

        end_sent = False  # Track if we've sent end event

        # Initial DB snapshot for immediate feedback
        job_repo = JobRepository()
        job = job_repo.get_job(job_id)

        if not job:
            yield ServerSentEvent(data=json.dumps({'message': 'Job not found'}), event="error")
            yield ServerSentEvent(data=json.dumps({'reason': 'not_found', 'job_id': job_id}), event="end")
            return

        if job.status == "completed":
            yield ServerSentEvent(data=json.dumps({
                'message': job.message or 'Document indexing completed successfully',
                'document_id': job.collection_document_id
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

        pubsub = safe_subscribe(job_id)
        channel_name = f"job:progress:{job_id}"
        logger.info(f"[Chat SSE] Subscribed to Redis channel: {channel_name}", extra={"job_id": job_id})

        max_duration = 800  # seconds
        elapsed = 0
        keepalive_interval = 8  # seconds for keepalive comment
        last_keepalive = 0
        messages_received = 0

        try:
            while elapsed < max_duration:
                # Non-blocking attempt to get message every second
                message = pubsub.get_message(timeout=1.0)
                if message:
                    logger.debug(f"[Chat SSE] Received message type: {message.get('type')}", extra={"job_id": job_id, "message": str(message)[:200]})
                if message and message.get('type') == 'message':
                    messages_received += 1
                    logger.info(f"[Chat SSE] 📨 Received pub/sub message #{messages_received}", extra={"job_id": job_id})
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
                        logger.warning("[Chat SSE] Malformed pubsub message", extra={"job_id": job_id, "error": str(e)})
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
            logger.exception(f"[Chat SSE] PubSub stream error for job {job_id}", extra={"error": str(e)})
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
            logger.info(
                f"[Chat SSE] ★★★ PubSub stream ENDED for job {job_id} ★★★ Total messages received: {messages_received}",
                extra={"job_id": job_id, "messages_received": messages_received, "elapsed_seconds": elapsed}
            )
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
