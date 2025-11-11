# backend/app/api/chat.py
"""
Chat Mode API endpoints.

Endpoints:
- Collections: Create, list, get, delete collections
- Documents: Upload PDFs to collections (triggers async indexing)
- Chat: Send messages with SSE streaming responses
- Sessions: Manage chat sessions and history
- Export: Export chat sessions with full metadata for download
"""
import uuid
import os
import hashlib
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.auth import get_current_user
from app.db_models_users import User
from app.database import get_db
from app.services.tasks import start_chat_indexing_chain
from app.services.rag import RAGService
from app.repositories.collection_repository import CollectionRepository
from app.repositories.chat_repository import ChatRepository
from app.repositories.job_repository import JobRepository
from app.utils.logging import logger

router = APIRouter(prefix="/api/chat", tags=["Chat Mode"])


# ============================================================================
# COLLECTIONS ENDPOINTS
# ============================================================================


@router.post("/collections")
async def create_collection(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    user: User = Depends(get_current_user)
):
    """
    Create a new collection for multi-document chat.

    Args:
        name: Collection name
        description: Optional description
        user: Current user (from auth)

    Returns:
        Collection details
    """
    # Use repository for database operations
    collection_repo = CollectionRepository()
    collection = collection_repo.create_collection(
        user_id=user.id,
        name=name,
        description=description
    )

    if not collection:
        raise HTTPException(status_code=500, detail="Failed to create collection")

    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "document_count": collection.document_count,
        "total_chunks": collection.total_chunks,
        "created_at": collection.created_at.isoformat() if collection.created_at else None,
    }


@router.get("/collections")
async def list_collections(
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    List all collections for the current user.

    Args:
        user: Current user
        limit: Max results (default: 50)
        offset: Pagination offset (default: 0)

    Returns:
        List of collections
    """
    collection_repo = CollectionRepository()
    collections, total = collection_repo.list_collections(
        user_id=user.id,
        limit=limit,
        offset=offset
    )

    return {
        "collections": [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "document_count": c.document_count,
                "total_chunks": c.total_chunks,
                "embedding_model": c.embedding_model,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in collections
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/collections/{collection_id}")
async def get_collection(
    collection_id: str,
    user: User = Depends(get_current_user)
):
    """
    Get collection details including documents.

    Args:
        collection_id: Collection ID
        user: Current user

    Returns:
        Collection with documents list
    """
    collection_repo = CollectionRepository()

    # Get collection (with ownership check)
    collection = collection_repo.get_collection(collection_id, user.id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Get documents in collection
    documents = collection_repo.list_documents(collection_id)

    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "document_count": collection.document_count,
        "total_chunks": collection.total_chunks,
        "embedding_model": collection.embedding_model,
        "embedding_dimension": collection.embedding_dimension,
        "created_at": collection.created_at.isoformat() if collection.created_at else None,
        "updated_at": collection.updated_at.isoformat() if collection.updated_at else None,
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "page_count": d.page_count,
                "chunk_count": d.chunk_count,
                "status": d.status,
                "error_message": d.error_message,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "completed_at": d.completed_at.isoformat() if d.completed_at else None,
            }
            for d in documents
        ]
    }


@router.delete("/collections/{collection_id}")
async def delete_collection(
    collection_id: str,
    user: User = Depends(get_current_user)
):
    """
    Delete a collection (cascades to documents, chunks, sessions).

    Args:
        collection_id: Collection ID
        user: Current user

    Returns:
        Success message
    """
    collection_repo = CollectionRepository()

    success = collection_repo.delete_collection(collection_id, user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Collection not found")

    return {"success": True, "message": "Collection deleted"}


# ============================================================================
# DOCUMENTS ENDPOINTS
# ============================================================================


@router.post("/collections/{collection_id}/documents")
async def upload_document(
    collection_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user)
):
    """
    Upload a PDF to a collection and start async indexing.

    Flow:
    1. Save file
    2. Create CollectionDocument record
    3. Create JobState for progress tracking
    4. Start Celery indexing chain (parse → chunk → embed → store)
    5. Return job_id for SSE progress tracking

    Args:
        collection_id: Collection ID
        file: PDF file to upload
        user: Current user

    Returns:
        job_id for tracking indexing progress
    """
    # Verify collection exists and belongs to user
    collection_repo = CollectionRepository()

    # Get collection (with ownership check)
    collection = collection_repo.get_collection(collection_id, user.id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Read file and calculate hash
    file_bytes = await file.read()
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    # Check for duplicate in this collection
    existing_doc = collection_repo.check_duplicate_document(collection_id, content_hash)

    if existing_doc:
        raise HTTPException(
            status_code=409,
            detail=f"This document already exists in the collection: {existing_doc.filename}"
        )

    # Save file to disk
    upload_dir = os.path.join("uploads", "chat", collection_id)
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, f"{uuid.uuid4()}_{file.filename}")
    document = None
    job_repo = JobRepository()

    try:
        # Save file
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        # Create CollectionDocument record
        document = collection_repo.create_document(
            collection_id=collection_id,
            filename=file.filename,
            file_path=file_path,
            file_size_bytes=len(file_bytes),
            page_count=0,  # Will be updated during parsing
            content_hash=content_hash
        )

        if not document:
            raise HTTPException(status_code=500, detail="Failed to create document record")

        # Create JobState for progress tracking (Chat Mode)
        job = job_repo.create_job(
            collection_document_id=document.id,  # Chat Mode uses collection_document_id
            status="queued",
            current_stage="queued",
            progress_percent=0,
            message="Queued for processing..."
        )

        if not job:
            raise HTTPException(status_code=500, detail="Failed to create job tracking record")

        # Update collection document count
        documents = collection_repo.list_documents(collection_id)
        collection_repo.update_collection_stats(
            collection_id=collection_id,
            document_count=len(documents)
        )

        # Start Celery indexing chain
        task_id = start_chat_indexing_chain(
            file_path=file_path,
            filename=file.filename,
            job_id=job.id,
            document_id=document.id,
            collection_id=collection_id,
            user_id=user.id
        )

        logger.info(
            f"Started document indexing",
            extra={
                "document_id": document.id,
                "collection_id": collection_id,
                "job_id": job.id,
                "task_id": task_id,
                "file_name": file.filename
            }
        )

        return {
            "document_id": document.id,
            "job_id": job.id,
            "task_id": task_id,
            "filename": file.filename,
            "status": "processing",
            "message": "Document indexing started. Use job_id to track progress via SSE."
        }

    except Exception as e:
        # Cleanup on failure: delete document (cascades to job_state), delete file
        logger.error(
            f"Upload failed, cleaning up",
            extra={
                "collection_id": collection_id,
                "file_name": file.filename,
                "error": str(e)
            }
        )

        # Delete document record (cascades to job_state due to ON DELETE CASCADE)
        if document:
            collection_repo.delete_document(document.id)

        # Delete uploaded file
        if os.path.exists(file_path):
            os.remove(file_path)

        # Re-raise the exception
        raise


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    user: User = Depends(get_current_user)
):
    """
    Delete a document from a collection.

    Removes document record, associated chunks, job states, and physical file.
    Requires user to own the collection.

    Args:
        document_id: Document ID to delete
        user: Authenticated user

    Returns:
        Success message with deleted document details
    """
    collection_repo = CollectionRepository()

    # Get document (with collection ownership check via repository)
    from app.database import SessionLocal
    from app.db_models_chat import CollectionDocument

    db = SessionLocal()
    try:
        document = db.query(CollectionDocument).filter(
            CollectionDocument.id == document_id
        ).first()

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        # Verify user owns the collection
        collection = collection_repo.get_collection(document.collection_id, user.id)
        if not collection:
            raise HTTPException(status_code=403, detail="You don't have permission to delete this document")

        # Store info for response before deletion
        filename = document.filename
        collection_id = document.collection_id
        file_path = document.file_path

    finally:
        db.close()

    # Delete document from database (cascades to chunks and job_states)
    success = collection_repo.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete document")

    # Delete physical file if it exists
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.info(
                f"Deleted physical file",
                extra={"document_id": document_id, "file_path": file_path}
            )
        except Exception as e:
            logger.warning(
                f"Failed to delete physical file: {e}",
                extra={"document_id": document_id, "file_path": file_path, "error": str(e)}
            )

    # Update collection document count
    collection_repo.update_collection_stats(
        collection_id=collection_id,
        total_chunks=max(0, (collection.total_chunks or 0) - (document.chunk_count or 0))
    )

    logger.info(
        f"Document deleted",
        extra={
            "document_id": document_id,
            "collection_id": collection_id,
            "file_name": filename
        }
    )

    return {
        "success": True,
        "document_id": document_id,
        "filename": filename,
        "message": f"Document '{filename}' deleted successfully"
    }


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
    """

    # Verify authentication via token query parameter
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")

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
        from sse_starlette.sse import ServerSentEvent

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


# ============================================================================
# CHAT ENDPOINTS
# ============================================================================


@router.post("/collections/{collection_id}/chat")
async def chat_with_collection(
    collection_id: str,
    message: str = Form(...),
    session_id: Optional[str] = Form(None),
    num_chunks: int = Form(5),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)  # Still needed for RAGService
):
    """
    Send a chat message and get streaming response (SSE).

    Flow:
    1. Verify collection exists
    2. Create or get chat session
    3. Embed user question
    4. Vector search for relevant chunks
    5. Stream response from Claude with RAG context
    6. Save chat history

    Args:
        collection_id: Collection ID
        message: User's message/question
        session_id: Optional session ID (creates new if not provided)
        num_chunks: Number of chunks to retrieve (default: 5)
        user: Current user
        db: Database session (for RAGService)

    Yields:
        SSE events with streaming chat response
    """
    # Use repositories
    collection_repo = CollectionRepository()
    chat_repo = ChatRepository()

    # Verify collection exists and belongs to user
    collection = collection_repo.get_collection(collection_id, user.id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Check if collection has any indexed documents
    if collection.document_count == 0:
        raise HTTPException(
            status_code=400,
            detail="Collection has no documents. Upload and index documents first."
        )

    # Create or get chat session
    if session_id:
        session = chat_repo.get_session(session_id, user.id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        # Create new session
        title = message[:50] + "..." if len(message) > 50 else message
        session = chat_repo.create_session(
            collection_id=collection_id,
            user_id=user.id,
            title=title
        )
        if not session:
            raise HTTPException(status_code=500, detail="Failed to create session")

    # Initialize RAG service (still needs db session for vector search)
    rag_service = RAGService(db)

    # Stream chat response
    async def event_generator():
        """Stream chat response chunks as SSE events"""
        import json

        logger.info(f"[Chat SSE] ★★★ Starting event stream for session {session.id}", extra={"session_id": session.id})

        # Send session_id first (for new sessions)
        logger.info(f"[Chat SSE] Sending session event", extra={"session_id": session.id})
        yield f"event: session\ndata: {json.dumps({'session_id': session.id})}\n\n"

        # Stream response chunks from RAG
        try:
            chunk_count = 0
            async for chunk in rag_service.chat(
                session_id=session.id,
                collection_id=collection_id,
                user_message=message,
                num_chunks=num_chunks
            ):
                chunk_count += 1
                logger.debug(f"[Chat SSE] Sending chunk #{chunk_count}", extra={"session_id": session.id})
                yield f"event: chunk\ndata: {json.dumps({'chunk': chunk})}\n\n"

            # Send completion event
            logger.info(f"[Chat SSE] Sending done event (streamed {chunk_count} chunks)", extra={"session_id": session.id, "chunk_count": chunk_count})
            yield f"event: done\ndata: {json.dumps({'status': 'completed'})}\n\n"

        except Exception as e:
            logger.error(f"[Chat SSE] Streaming error: {e}", exc_info=True, extra={"session_id": session.id})
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

        logger.info(f"[Chat SSE] ★★★ Event stream ended for session {session.id}", extra={"session_id": session.id})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ============================================================================
# SESSIONS & HISTORY ENDPOINTS
# ============================================================================


@router.get("/collections/{collection_id}/sessions")
async def list_sessions(
    collection_id: str,
    user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100)
):
    """
    List chat sessions for a collection.

    Args:
        collection_id: Collection ID
        user: Current user
        limit: Max results (default: 20)

    Returns:
        List of chat sessions
    """
    # Use repositories
    collection_repo = CollectionRepository()
    chat_repo = ChatRepository()

    # Verify collection access
    collection = collection_repo.get_collection(collection_id, user.id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Get sessions
    sessions = chat_repo.list_sessions(collection_id, limit)

    return {
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "description": s.description,
                "message_count": s.message_count,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in sessions
        ]
    }


@router.get("/sessions/{session_id}/messages")
async def get_chat_history(
    session_id: str,
    user: User = Depends(get_current_user),
    limit: Optional[int] = Query(None, ge=1, le=500)
):
    """
    Get chat history for a session.

    Args:
        session_id: Session ID
        user: Current user
        limit: Optional limit on messages

    Returns:
        Chat messages
    """
    # Use repository
    chat_repo = ChatRepository()

    # Verify session access
    session = chat_repo.get_session(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get messages from repository
    messages = chat_repo.get_messages(session_id, limit)

    return {
        "session_id": session.id,
        "collection_id": session.collection_id,
        "messages": [
            {
                "role": msg.role,
                "content": msg.content,
                "message_index": msg.message_index,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "source_chunks": msg.source_chunks,
                "num_chunks_retrieved": msg.num_chunks_retrieved
            }
            for msg in messages
        ],
        "total": len(messages)
    }


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: User = Depends(get_current_user)
):
    """
    Delete a chat session.

    Args:
        session_id: Session ID
        user: Current user

    Returns:
        Success message
    """
    # Use repository
    chat_repo = ChatRepository()

    success = chat_repo.delete_session(session_id, user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"success": True, "message": "Session deleted"}


@router.get("/sessions/{session_id}/export")
async def export_session(
    session_id: str,
    user: User = Depends(get_current_user)
):
    """
    Export a chat session with full metadata for download.

    Returns comprehensive session data including collection info,
    all messages, source citations, and timestamps. Frontend can
    convert this to markdown, Word, JSON, or other formats.

    Args:
        session_id: Session ID
        user: Current user

    Returns:
        Complete session data formatted for export
    """
    # Use repositories
    collection_repo = CollectionRepository()
    chat_repo = ChatRepository()

    # Verify session access
    session = chat_repo.get_session(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get collection details
    collection = collection_repo.get_collection(session.collection_id, user.id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Get all messages
    messages = chat_repo.get_messages(session_id, limit=None)

    # Format export data
    export_data = {
        "session": {
            "id": session.id,
            "title": session.title,
            "description": session.description,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
            "message_count": session.message_count
        },
        "collection": {
            "id": collection.id,
            "name": collection.name,
            "description": collection.description,
            "document_count": collection.document_count
        },
        "messages": [
            {
                "role": msg.role,
                "content": msg.content,
                "message_index": msg.message_index,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "source_chunks": msg.source_chunks,
                "num_chunks_retrieved": msg.num_chunks_retrieved
            }
            for msg in messages
        ],
        "export_metadata": {
            "exported_at": datetime.utcnow().isoformat(),
            "exported_by": user.id,
            "total_messages": len(messages)
        }
    }

    return export_data
