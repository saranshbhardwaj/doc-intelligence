# backend/app/api/chat/messages.py
"""Chat messaging endpoint with SSE streaming for Chat Mode."""

from typing import Optional
from fastapi import APIRouter, Form, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db_models_users import User
from app.database import get_db
from app.services.rag import RAGService
from app.repositories.collection_repository import CollectionRepository
from app.repositories.chat_repository import ChatRepository
from app.utils.logging import logger

router = APIRouter()


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
        collection_id: Collection ID (UUID format)
        message: User's message/question (1-4000 chars)
        session_id: Optional session ID (creates new if not provided)
        num_chunks: Number of chunks to retrieve (1-20, default: 5)
        user: Current user
        db: Database session (for RAGService)

    Yields:
        SSE events with streaming chat response

    Raises:
        HTTPException 400: Invalid input (empty message, collection has no docs, invalid num_chunks)
        HTTPException 404: Collection or session not found
        HTTPException 500: Server error during chat processing

    SSE Events:
        - session: Session ID (sent first for new sessions)
        - chunk: Text chunk from streaming response
        - done: Streaming completed
        - error: Error during streaming
    """
    # Edge case: Validate message is not empty
    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    message = message.strip()

    # Edge case: Validate message length
    if len(message) > 4000:
        raise HTTPException(status_code=400, detail="Message too long (max 4000 characters)")

    # Edge case: Validate num_chunks range
    if num_chunks < 1 or num_chunks > 20:
        raise HTTPException(status_code=400, detail="num_chunks must be between 1 and 20")

    # Use repositories
    collection_repo = CollectionRepository()
    chat_repo = ChatRepository()

    # Verify collection exists and belongs to user
    collection = collection_repo.get_collection(collection_id, user.id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Edge case: Check if collection has any indexed documents
    if collection.document_count == 0:
        raise HTTPException(
            status_code=400,
            detail="Collection has no documents. Upload and index documents first."
        )

    # Edge case: Check if collection has any chunks (documents might be uploaded but not indexed)
    if (collection.total_chunks or 0) == 0:
        raise HTTPException(
            status_code=400,
            detail="Collection has no indexed chunks. Wait for document indexing to complete."
        )

    # Create or get chat session
    if session_id:
        # Edge case: Validate session exists and belongs to user
        session = chat_repo.get_session(session_id, user.id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Edge case: Verify session belongs to the same collection
        if session.collection_id != collection_id:
            raise HTTPException(
                status_code=400,
                detail=f"Session {session_id} belongs to a different collection"
            )
    else:
        # Create new session with truncated message as title
        title = message[:50] + "..." if len(message) > 50 else message
        session = chat_repo.create_session(
            collection_id=collection_id,
            user_id=user.id,
            title=title
        )
        if not session:
            raise HTTPException(status_code=500, detail="Failed to create session")

        logger.info(
            f"Created new chat session",
            extra={
                "session_id": session.id,
                "collection_id": collection_id,
                "user_id": user.id
            }
        )

    # Initialize RAG service (still needs db session for vector search)
    rag_service = RAGService(db)

    # Stream chat response
    async def event_generator():
        """Stream chat response chunks as SSE events (manually formatted)"""
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
                user_id=user.id,
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
