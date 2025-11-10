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
from sse_starlette.sse import ServerSentEvent

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
    async def event_generator():
        """Stream progress events until job completes or fails"""
        import json
        import asyncio
        from app.services.pubsub import subscribe_to_job

        # Subscribe to Redis pub/sub for this job
        async for event in subscribe_to_job(job_id):
            if event["type"] == "progress":
                yield ServerSentEvent(
                    data=json.dumps(event["data"]),
                    event="progress"
                )

                # Stop streaming if job completed or failed
                if event["data"].get("status") in ["completed", "failed"]:
                    break

            await asyncio.sleep(0)  # Yield control

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
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
        """Stream chat response chunks"""
        import json

        # Send session_id first (for new sessions)
        yield ServerSentEvent(
            data=json.dumps({"session_id": session.id}),
            event="session"
        )

        # Stream response chunks from RAG
        try:
            async for chunk in rag_service.chat(
                session_id=session.id,
                collection_id=collection_id,
                user_message=message,
                num_chunks=num_chunks
            ):
                yield ServerSentEvent(
                    data=json.dumps({"chunk": chunk}),
                    event="chunk"
                )

            # Send completion event
            yield ServerSentEvent(
                data=json.dumps({"status": "completed"}),
                event="done"
            )

        except Exception as e:
            logger.error(f"Chat streaming error: {e}", exc_info=True)
            yield ServerSentEvent(
                data=json.dumps({"error": str(e)}),
                event="error"
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
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
