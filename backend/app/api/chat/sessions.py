# backend/app/api/chat/sessions.py
"""Chat session management endpoints for Chat Mode."""

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query

from app.auth import get_current_user
from app.db_models_users import User
from app.repositories.collection_repository import CollectionRepository
from app.repositories.chat_repository import ChatRepository
from app.utils.logging import logger

router = APIRouter()


@router.get("/collections/{collection_id}/sessions")
async def list_sessions(
    collection_id: str,
    user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100)
):
    """
    List chat sessions for a collection.

    Args:
        collection_id: Collection ID (UUID format)
        user: Current user
        limit: Max results (1-100, default: 20)

    Returns:
        List of chat sessions ordered by most recent first

    Raises:
        HTTPException 404: Collection not found or access denied
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

    logger.debug(
        f"Listed sessions for collection",
        extra={
            "collection_id": collection_id,
            "user_id": user.id,
            "session_count": len(sessions)
        }
    )

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
        session_id: Session ID (UUID format)
        user: Current user
        limit: Optional limit on messages (1-500, default: all messages)

    Returns:
        Chat messages ordered chronologically

    Raises:
        HTTPException 404: Session not found or access denied
    """
    # Use repository
    chat_repo = ChatRepository()

    # Verify session access
    session = chat_repo.get_session(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get messages from repository
    messages = chat_repo.get_messages(session_id, limit)

    logger.debug(
        f"Retrieved chat history",
        extra={
            "session_id": session_id,
            "user_id": user.id,
            "message_count": len(messages)
        }
    )

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
    Delete a chat session (cascades to messages).

    Args:
        session_id: Session ID (UUID format)
        user: Current user

    Returns:
        Success message

    Raises:
        HTTPException 404: Session not found or access denied
        HTTPException 500: Deletion failed
    """
    # Use repository
    chat_repo = ChatRepository()

    # Edge case: Verify session exists before attempting delete
    session = chat_repo.get_session(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Store info for logging before deletion
    collection_id = session.collection_id
    message_count = session.message_count

    success = chat_repo.delete_session(session_id, user.id)
    if not success:
        # Should not happen if the above check passed, but defensive
        raise HTTPException(status_code=500, detail="Failed to delete session")

    logger.info(
        f"Deleted chat session",
        extra={
            "session_id": session_id,
            "collection_id": collection_id,
            "user_id": user.id,
            "message_count": message_count
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

    Returns comprehensive session data including collection info,
    all messages, source citations, and timestamps. Frontend can
    convert this to markdown, Word, JSON, or other formats.

    Args:
        session_id: Session ID (UUID format)
        user: Current user

    Returns:
        Complete session data formatted for export

    Raises:
        HTTPException 404: Session or collection not found or access denied
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

    # Get all messages (no limit for export)
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

    logger.info(
        f"Exported chat session",
        extra={
            "session_id": session_id,
            "user_id": user.id,
            "message_count": len(messages)
        }
    )

    return export_data
