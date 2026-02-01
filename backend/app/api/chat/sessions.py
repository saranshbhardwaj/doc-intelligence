# backend/app/api/chat/sessions.py
"""Chat session management endpoints for Chat Mode.

Session-centric architecture:
- Sessions are independent of collections
- Each session maintains its own document selection
- Sessions can have documents from multiple collections
"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query, Body

from app.auth import get_current_user
from app.db_models_users import User
from app.repositories.session_repository import SessionRepository
from app.repositories.chat_repository import ChatRepository
from app.database import SessionLocal
from app.db_models_documents import Document
from app.utils.logging import logger
from app.models import CreateSessionRequest, UpdateSessionRequest, AddDocumentsRequest, SessionResponse, SessionDocumentInfo

router = APIRouter()


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    request: CreateSessionRequest,
    user: User = Depends(get_current_user)
):
    """
    Create a new chat session with optional documents.

    Args:
        request: CreateSessionRequest with title, description, and optional document_ids
        user: Current user

    Returns:
        SessionResponse with session data and documents

    Input: CreateSessionRequest {title?, description?, document_ids?: [str]}
    Output: SessionResponse {id, title, description, message_count, created_at, updated_at, documents: []}
    """
    session_repo = SessionRepository()

    # Create session
    session = session_repo.create_session(
        user_id=user.id,
        title=request.title,
        description=request.description
    )

    if not session:
        raise HTTPException(status_code=500, detail="Failed to create session")

    # Add documents if provided
    documents_info = []
    if request.document_ids:
        added_count = session_repo.add_documents_to_session(
            session_id=session.id,
            document_ids=request.document_ids,
            user_id=user.id
        )

        logger.info(
            "Created session with documents",
            extra={
                "user_id": user.id,
                "session_id": session.id,
                "documents_requested": len(request.document_ids),
                "documents_added": added_count
            }
        )

        # Fetch document details for response
        if added_count > 0:
            session_with_docs = session_repo.get_session(session.id, user.id)
            if session_with_docs and session_with_docs.document_links:
                documents_info = [
                    SessionDocumentInfo(
                        id=link.document.id,
                        name=link.document.filename,
                        added_at=link.added_at
                    )
                    for link in session_with_docs.document_links
                ]

    return SessionResponse(
        id=session.id,
        title=session.title,
        description=session.description,
        message_count=session.message_count,
        document_count=len(documents_info),
        created_at=session.created_at,
        updated_at=session.updated_at,
        documents=documents_info
    )


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
    user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    List all chat sessions for the current user.

    Args:
        user: Current user
        limit: Max results (1-100, default: 20)
        offset: Pagination offset (default: 0)

    Returns:
        List of SessionResponse objects ordered by most recent first

    Input: user_id (from auth), limit, offset
    Output: [SessionResponse {id, title, description, message_count, created_at, updated_at, documents: []}]
    """
    session_repo = SessionRepository()

    # Get sessions with pagination (now includes document counts)
    session_results, total = session_repo.list_sessions(user.id, limit, offset)

    logger.info(
        "Listed user sessions",
        extra={
            "user_id": user.id,
            "count": len(session_results),
            "total": total,
            "limit": limit,
            "offset": offset
        }
    )

    # Convert to response models (with document counts but without full document details)
    return [
        SessionResponse(
            id=session.id,
            title=session.title,
            description=session.description,
            message_count=session.message_count,
            document_count=doc_count,
            created_at=session.created_at,
            updated_at=session.updated_at,
            documents=[]  # Empty for list view - call get_session for full details
        )
        for session, doc_count in session_results
    ]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    user: User = Depends(get_current_user)
):
    """
    Get session details with full document list.

    Args:
        session_id: Session ID (UUID format)
        user: Current user

    Returns:
        SessionResponse with full document details

    Raises:
        HTTPException 404: Session not found or access denied

    Input: session_id, user_id (from auth)
    Output: SessionResponse {id, title, description, message_count, created_at, updated_at, documents: [{id, name, added_at}]}
    """
    session_repo = SessionRepository()

    # Get session with documents eagerly loaded
    session = session_repo.get_session(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Build document list
    documents_info = []
    if session.document_links:
        documents_info = [
            SessionDocumentInfo(
                id=link.document.id,
                name=link.document.filename,
                added_at=link.added_at
            )
            for link in session.document_links
        ]

    logger.debug(
        "Retrieved session details",
        extra={
            "user_id": user.id,
            "session_id": session_id,
            "document_count": len(documents_info)
        }
    )

    return SessionResponse(
        id=session.id,
        title=session.title,
        description=session.description,
        message_count=session.message_count,
        document_count=len(documents_info),
        created_at=session.created_at,
        updated_at=session.updated_at,
        documents=documents_info
    )


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    user: User = Depends(get_current_user)
):
    """
    Update session title and/or description.

    Args:
        session_id: Session ID (UUID format)
        request: UpdateSessionRequest with optional title and description
        user: Current user

    Returns:
        Updated SessionResponse

    Raises:
        HTTPException 404: Session not found or access denied
        HTTPException 400: No fields to update

    Input: session_id, UpdateSessionRequest {title?, description?}, user_id (from auth)
    Output: SessionResponse {id, title, description, message_count, document_count, created_at, updated_at, documents: []}
    """
    # Validate at least one field is provided
    if request.title is None and request.description is None:
        raise HTTPException(
            status_code=400,
            detail="At least one field (title or description) must be provided"
        )

    session_repo = SessionRepository()

    # Update session
    updated_session = session_repo.update_session(
        session_id=session_id,
        user_id=user.id,
        title=request.title,
        description=request.description
    )

    if not updated_session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get full session with documents
    session = session_repo.get_session(session_id, user.id)

    # Build document list
    documents_info = []
    if session and session.document_links:
        documents_info = [
            SessionDocumentInfo(
                id=link.document.id,
                name=link.document.filename,
                added_at=link.added_at
            )
            for link in session.document_links
        ]

    logger.info(
        "Updated session",
        extra={
            "user_id": user.id,
            "session_id": session_id,
            "updated_title": request.title is not None,
            "updated_description": request.description is not None
        }
    )

    return SessionResponse(
        id=session.id,
        title=session.title,
        description=session.description,
        message_count=session.message_count,
        document_count=len(documents_info),
        created_at=session.created_at,
        updated_at=session.updated_at,
        documents=documents_info
    )


@router.post("/sessions/{session_id}/documents")
async def add_documents_to_session(
    session_id: str,
    request: AddDocumentsRequest,
    user: User = Depends(get_current_user)
):
    """
    Add documents to a session.

    Args:
        session_id: Session ID (UUID format)
        request: AddDocumentsRequest with document_ids
        user: Current user

    Returns:
        Success message with count of documents added

    Raises:
        HTTPException 404: Session not found or access denied

    Input: session_id, AddDocumentsRequest {document_ids: [str]}, user_id (from auth)
    Output: {success: bool, message: str, documents_added: int}
    """
    session_repo = SessionRepository()

    # Verify session exists
    session = session_repo.get_session(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Add documents
    added_count = session_repo.add_documents_to_session(
        session_id=session_id,
        document_ids=request.document_ids,
        user_id=user.id
    )

    logger.info(
        "Added documents to session",
        extra={
            "user_id": user.id,
            "session_id": session_id,
            "documents_requested": len(request.document_ids),
            "documents_added": added_count
        }
    )

    return {
        "success": True,
        "message": f"Added {added_count} document(s) to session",
        "documents_added": added_count
    }


@router.delete("/sessions/{session_id}/documents/{document_id}")
async def remove_document_from_session(
    session_id: str,
    document_id: str,
    user: User = Depends(get_current_user)
):
    """
    Remove a document from a session.

    Args:
        session_id: Session ID (UUID format)
        document_id: Document ID (UUID format)
        user: Current user

    Returns:
        Success message

    Raises:
        HTTPException 404: Session or document link not found

    Input: session_id, document_id, user_id (from auth)
    Output: {success: bool, message: str}
    """
    session_repo = SessionRepository()

    # Remove document
    success = session_repo.remove_document_from_session(
        session_id=session_id,
        document_id=document_id,
        user_id=user.id
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail="Session not found or document not in session"
        )

    logger.info(
        "Removed document from session",
        extra={
            "user_id": user.id,
            "session_id": session_id,
            "document_id": document_id
        }
    )

    return {
        "success": True,
        "message": "Document removed from session"
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
        session_id: Session ID (UUID format)
        user: Current user
        limit: Optional limit on messages (1-500, default: all messages)

    Returns:
        Chat messages ordered chronologically

    Raises:
        HTTPException 404: Session not found or access denied

    Input: session_id, user_id (from auth), limit?
    Output: {session_id, messages: [{role, content, message_index, created_at, source_chunks, num_chunks_retrieved}], total}
    """
    # Use repositories
    session_repo = SessionRepository()
    chat_repo = ChatRepository()

    # Verify session access
    session = session_repo.get_session(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get messages from repository
    messages = chat_repo.get_messages(session_id, limit)

    logger.debug(
        "Retrieved chat history",
        extra={
            "session_id": session_id,
            "user_id": user.id,
            "message_count": len(messages)
        }
    )

    import json

    return {
        "session_id": session.id,
        "messages": [
            {
                "role": msg.role,
                "content": msg.content,
                "message_index": msg.message_index,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "source_chunks": msg.source_chunks,
                "num_chunks_retrieved": msg.num_chunks_retrieved,
                "comparison_metadata": json.loads(msg.comparison_metadata) if msg.comparison_metadata else None
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
    Delete a chat session (cascades to messages and document links).

    Args:
        session_id: Session ID (UUID format)
        user: Current user

    Returns:
        Success message

    Raises:
        HTTPException 404: Session not found or access denied
        HTTPException 500: Deletion failed

    Input: session_id, user_id (from auth)
    Output: {success: bool, message: str}
    """
    session_repo = SessionRepository()

    # Verify session exists before attempting delete
    session = session_repo.get_session(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Store info for logging before deletion
    message_count = session.message_count
    document_count = len(session.document_links) if session.document_links else 0

    success = session_repo.delete_session(session_id, user.id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete session")

    logger.info(
        "Deleted chat session",
        extra={
            "session_id": session_id,
            "user_id": user.id,
            "message_count": message_count,
            "document_count": document_count
        }
    )

    return {"success": True, "message": "Session deleted"}


@router.get("/sessions/{session_id}/export")
async def export_session(
    session_id: str,
    user: User = Depends(get_current_user)
):
    """
    Export a chat session with full metadata for download.

    Returns comprehensive session data including document info,
    all messages, source citations, and timestamps. Frontend can
    convert this to markdown, Word, JSON, or other formats.

    Args:
        session_id: Session ID (UUID format)
        user: Current user

    Returns:
        Complete session data formatted for export

    Raises:
        HTTPException 404: Session not found or access denied

    Input: session_id, user_id (from auth)
    Output: {session: {}, documents: [], messages: [], export_metadata: {}}
    """
    # Use repositories
    session_repo = SessionRepository()
    chat_repo = ChatRepository()

    # Verify session access and get session with documents
    session = session_repo.get_session(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get all messages (no limit for export)
    messages = chat_repo.get_messages(session_id, limit=None)

    # Build document list
    documents_info = []
    if session.document_links:
        documents_info = [
            {
                "id": link.document.id,
                "name": link.document.filename,
                "added_at": link.added_at.isoformat() if link.added_at else None
            }
            for link in session.document_links
        ]

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
        "documents": documents_info,
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
            "total_messages": len(messages),
            "total_documents": len(documents_info)
        }
    }

    logger.info(
        "Exported chat session",
        extra={
            "session_id": session_id,
            "user_id": user.id,
            "message_count": len(messages),
            "document_count": len(documents_info)
        }
    )

    return export_data
