# backend/app/api/chat/messages.py
"""Chat messaging endpoint with SSE streaming for Chat Mode.

Session-centric architecture:
- Chat happens within a session (not directly with collection)
- Session maintains its own document selection
- RAG retrieval uses session's documents
"""

from typing import Optional
from fastapi import APIRouter, Form, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db_models_users import User
from app.database import get_db
from app.core.rag import RAGService
from app.repositories.session_repository import SessionRepository
from app.repositories.rag_repository import RAGRepository
from app.utils.logging import logger
from app.services.service_locator import get_reranker

router = APIRouter()


@router.post("/sessions/{session_id}/chat")
async def chat_with_session(
    session_id: str,
    message: str = Form(...),
    num_chunks: int = Form(5),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)  # Still needed for RAGService
):
    """
    Send a chat message to a session and get streaming response (SSE).

    Flow:
    1. Verify session exists and get session's documents
    2. Embed user question
    3. Vector search for relevant chunks (filtered by session's documents)
    4. Stream response from Claude with RAG context
    5. Save chat history

    Args:
        session_id: Session ID (UUID format)
        message: User's message/question (1-4000 chars)
        num_chunks: Number of chunks to retrieve (1-20, default: 5)
        user: Current user
        db: Database session (for RAGService)

    Yields:
        SSE events with streaming chat response

    Raises:
        HTTPException 400: Invalid input (empty message, no documents, invalid num_chunks)
        HTTPException 404: Session not found or access denied
        HTTPException 500: Server error during chat processing

    SSE Events:
        - session: Session ID (sent first)
        - chunk: Text chunk from streaming response
        - done: Streaming completed
        - error: Error during streaming

    Input: session_id, message, num_chunks, user_id (from auth)
    Output: SSE stream with chunks
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
    session_repo = SessionRepository()
    rag_repo = RAGRepository(db)

    # Verify session exists and belongs to user (with documents eagerly loaded)
    session = session_repo.get_session(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Edge case: Check if session has any documents
    if not session.document_links or len(session.document_links) == 0:
        raise HTTPException(
            status_code=400,
            detail="Session has no documents. Add documents to the session first."
        )

    # Extract document IDs from session
    document_ids = [link.document_id for link in session.document_links]
    document_names = [link.document.filename for link in session.document_links]

    # Edge case: Validate documents are indexed (have chunks)
    chunk_count = rag_repo.count_chunks_for_documents(document_ids)

    if chunk_count == 0:
        logger.warning(
            "Documents not indexed yet for session",
            extra={
                "session_id": session_id,
                "document_count": len(document_ids),
                "document_names": document_names[:3]
            }
        )
        raise HTTPException(
            status_code=400,
            detail="Documents haven't been indexed yet. Please wait for document processing to complete before chatting."
        )

    logger.info(
        "Starting chat in session",
        extra={
            "session_id": session_id,
            "user_id": user.id,
            "document_count": len(document_ids),
            "document_names": document_names[:5],  # Log first 5 for debugging
            "total_chunks": chunk_count
        }
    )

    # Initialize RAG service (still needs db session for vector search)
    reranker = get_reranker()
    rag_service = RAGService(db, reranker=reranker)

    # Stream chat response
    async def event_generator():
        """Stream chat response chunks as SSE events (manually formatted)"""
        import json

        logger.info(
            f"[Chat SSE] ★★★ Starting event stream for session {session_id}",
            extra={"session_id": session_id}
        )

        # Send session_id first
        logger.info(f"[Chat SSE] Sending session event", extra={"session_id": session_id})
        yield f"event: session\ndata: {json.dumps({'session_id': session_id})}\n\n"

        # Send thinking event to show progress feedback
        logger.info(f"[Chat SSE] Sending thinking event", extra={"session_id": session_id})
        yield f"event: thinking\ndata: {json.dumps({'message': 'Analyzing documents...'})}\n\n"

        # Stream response chunks from RAG
        try:
            chunk_count = 0
            comparison_context_sent = False

            async for chunk in rag_service.chat(
                session_id=session_id,
                collection_id=None,  # Sessions are independent of collections
                user_message=message,
                user_id=user.id,
                num_chunks=num_chunks,
                document_ids=document_ids  # Use session's documents
            ):
                # Send comparison context before first chunk (if available)
                if not comparison_context_sent and rag_service.last_comparison_context:
                    logger.info(f"[Chat SSE] Sending comparison context", extra={"session_id": session_id})
                    yield f"event: comparison_context\ndata: {json.dumps(rag_service.last_comparison_context)}\n\n"
                    comparison_context_sent = True
                    # Don't clear yet - needed for message saving after streaming completes

                chunk_count += 1
                logger.debug(f"[Chat SSE] Sending chunk #{chunk_count}", extra={"session_id": session_id})
                yield f"event: chunk\ndata: {json.dumps({'chunk': chunk})}\n\n"

            # Send completion event
            logger.info(
                f"[Chat SSE] Sending done event (streamed {chunk_count} chunks)",
                extra={"session_id": session_id, "chunk_count": chunk_count}
            )
            yield f"event: done\ndata: {json.dumps({'status': 'completed'})}\n\n"

        except Exception as e:
            logger.error(
                f"[Chat SSE] Streaming error: {e}",
                exc_info=True,
                extra={"session_id": session_id}
            )
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

        logger.info(
            f"[Chat SSE] ★★★ Event stream ended for session {session_id}",
            extra={"session_id": session_id}
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
