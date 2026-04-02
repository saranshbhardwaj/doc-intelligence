# backend/app/api/chat/messages.py
"""Chat messaging endpoint with SSE streaming for Chat Mode.

Session-centric architecture:
- Chat happens within a session (not directly with collection)
- Session maintains its own document selection
- RAG retrieval uses session's documents
"""

from fastapi import APIRouter, Form, HTTPException, Depends, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.auth import get_current_user
from app.db_models_users import User
from app.database import get_db
from app.core.rag import RAGService
from app.repositories.session_repository import SessionRepository
from app.repositories.rag_repository import RAGRepository
from app.services.beta_limits import enforce_chat_message_limit, log_shadow_credits
from app.utils.logging import logger
from app.api.chat.schemas import ComparisonConfirmRequest

router = APIRouter()


@router.post("/sessions/{session_id}/chat")
async def chat_with_session(
    session_id: str,
    message: str = Form(...),
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
        user: Current user
        db: Database session (for RAGService)

    Yields:
        SSE events with streaming chat response

    Raises:
        HTTPException 400: Invalid input (empty message, no documents)
        HTTPException 404: Session not found or access denied
        HTTPException 500: Server error during chat processing

    SSE Events:
        - session: Session ID (sent first)
        - chunk: Text chunk from streaming response
        - done: Streaming completed
        - error: Error during streaming

    Input: session_id, message, user_id (from auth)
    Output: SSE stream with chunks
    """
    # Edge case: Validate message is not empty
    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    message = message.strip()

    # Edge case: Validate message length
    if len(message) > 4000:
        raise HTTPException(status_code=400, detail="Message too long (max 4000 characters)")

    # Use repositories
    session_repo = SessionRepository()
    rag_repo = RAGRepository(db)

    # Verify session exists and belongs to user (with documents eagerly loaded)
    session = session_repo.get_session(session_id, user.id, user.org_id)
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

    enforce_chat_message_limit(user)

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
    rag_service = RAGService(db, capture_io_log=settings.capture_llm_io_log)

    log_shadow_credits(
        user=user,
        operation_type="chat_message",
        reference_id=session_id,
        metadata={"route": "chat_with_session", "document_count": len(document_ids)},
    )

    # Stream chat response
    async def event_generator():
        """Stream chat response chunks as SSE events (manually formatted)"""
        import json

        # Send session_id first
        yield f"event: session\ndata: {json.dumps({'session_id': session_id})}\n\n"

        # Check session length and send warning if needed
        from app.repositories.chat_repository import ChatRepository
        from app.config import settings
        chat_repo = ChatRepository()
        user_message_count = chat_repo.get_user_message_count(session_id)

        if user_message_count >= settings.chat_max_turns_before_warning:
            logger.info(
                f"[Chat SSE] Sending session warning: {user_message_count} user messages",
                extra={"session_id": session_id, "user_message_count": user_message_count}
            )
            warning_data = {
                "long_conversation": True,
                "message_count": user_message_count,
                "recommendation": "Consider starting a new session for best results"
            }
            yield f"event: session_warning\ndata: {json.dumps(warning_data)}\n\n"

        # Stream response from RAG — dispatches on tagged tuples from rag_service.chat()
        try:
            chunk_count = 0
            comparison_context_sent = False
            citation_context_sent = False

            async for event in rag_service.chat(
                session_id=session_id,
                collection_id=None,  # Sessions are independent of collections
                user_message=message,
                user_id=user.id,
                org_id=user.org_id,
                document_ids=document_ids  # Use session's documents
            ):
                # Dispatch on tagged tuples from rag_service
                if isinstance(event, tuple):
                    tag, data = event
                    if tag == "thinking":
                        yield f"event: thinking\ndata: {json.dumps({'message': data})}\n\n"
                        continue
                    elif tag == "comparison_selection":
                        yield f"event: comparison_selection\ndata: {json.dumps(data)}\n\n"
                        continue
                    else:
                        # tag == "chunk"
                        chunk_data = data
                else:
                    # Legacy fallback: bare string = chunk
                    chunk_data = event

                # Send comparison context before first content chunk (if available)
                if not comparison_context_sent and rag_service.last_comparison_context:
                    yield f"event: comparison_context\ndata: {json.dumps(rag_service.last_comparison_context)}\n\n"
                    comparison_context_sent = True

                # Send citation context before first content chunk (if available)
                if not citation_context_sent and rag_service.last_citation_context:
                    yield f"event: citation_context\ndata: {json.dumps(rag_service.last_citation_context)}\n\n"
                    citation_context_sent = True

                chunk_count += 1
                yield f"event: chunk\ndata: {json.dumps({'chunk': chunk_data})}\n\n"

            yield f"event: done\ndata: {json.dumps({'status': 'completed'})}\n\n"

        except Exception as e:
            logger.error(
                f"[Chat SSE] Streaming error: {e}",
                exc_info=True,
                extra={"session_id": session_id}
            )
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/sessions/{session_id}/chat/comparison")
async def confirm_comparison_selection(
    session_id: str,
    request: ComparisonConfirmRequest = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Confirm comparison with selected documents or skip to normal RAG.

    Called after user selects documents in the comparison picker UI or clicks "Not comparing".

    Flow:
    - If skip_comparison=True: Route to normal RAG with all session documents
    - If skip_comparison=False: Route to comparison with selected document_ids

    Args:
        session_id: Session ID (UUID format)
        request: Comparison confirmation request with document_ids, original_query, skip_comparison
        user: Current user
        db: Database session (for RAGService)

    Returns:
        SSE stream with chat response

    Raises:
        HTTPException 400: Invalid input (empty query, <2 documents selected when comparing)
        HTTPException 404: Session not found or access denied
    """
    # Validate original query
    if not request.original_query or not request.original_query.strip():
        raise HTTPException(status_code=400, detail="Original query cannot be empty")

    original_query = request.original_query.strip()

    # Validate document selection for comparison
    if not request.skip_comparison:
        if len(request.document_ids) < 2:
            raise HTTPException(
                status_code=400,
                detail="At least 2 documents required for comparison"
            )
        if len(request.document_ids) > 3:
            raise HTTPException(
                status_code=400,
                detail="Maximum 3 documents allowed for comparison"
            )

    # Use repositories
    session_repo = SessionRepository()
    rag_repo = RAGRepository(db)

    # Verify session exists and belongs to user
    session = session_repo.get_session(session_id, user.id, user.org_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Extract all document IDs from session
    all_document_ids = [link.document_id for link in session.document_links]

    # Determine which documents to use
    if request.skip_comparison:
        # User clicked "Not comparing" - use all session documents with normal RAG
        document_ids = all_document_ids
        force_comparison = False
        logger.info(
            "User chose to skip comparison, using normal RAG",
            extra={
                "session_id": session_id,
                "user_id": user.id,
                "document_count": len(document_ids)
            }
        )
    else:
        # User selected specific documents for comparison
        document_ids = request.document_ids
        force_comparison = True

        # Validate selected documents belong to session
        invalid_docs = set(document_ids) - set(all_document_ids)
        if invalid_docs:
            raise HTTPException(
                status_code=400,
                detail=f"Selected documents do not belong to session: {invalid_docs}"
            )

        logger.info(
            "User confirmed comparison with selected documents",
            extra={
                "session_id": session_id,
                "user_id": user.id,
                "selected_document_count": len(document_ids)
            }
        )

    # Validate documents are indexed
    chunk_count = rag_repo.count_chunks_for_documents(document_ids)
    if chunk_count == 0:
        raise HTTPException(
            status_code=400,
            detail="Selected documents haven't been indexed yet"
        )

    enforce_chat_message_limit(user)

    # Initialize RAG service
    rag_service = RAGService(db, capture_io_log=settings.capture_llm_io_log)

    log_shadow_credits(
        user=user,
        operation_type="chat_message",
        reference_id=session_id,
        metadata={
            "route": "confirm_comparison_selection",
            "force_comparison": force_comparison,
            "document_count": len(document_ids),
        },
    )

    # Stream chat response
    async def event_generator():
        """Stream chat response chunks as SSE events"""
        import json

        # Send session_id first
        yield f"event: session\ndata: {json.dumps({'session_id': session_id})}\n\n"

        # Stream response from RAG with force_comparison flag
        try:
            chunk_count = 0
            comparison_context_sent = False

            async for event in rag_service.chat(
                session_id=session_id,
                collection_id=None,
                user_message=original_query,
                user_id=user.id,
                document_ids=document_ids,
                force_comparison=force_comparison  # Force comparison mode on/off
            ):
                # Dispatch on tagged tuples from rag_service
                if isinstance(event, tuple):
                    tag, data = event
                    if tag == "thinking":
                        yield f"event: thinking\ndata: {json.dumps({'message': data})}\n\n"
                        continue
                    elif tag == "comparison_selection":
                        yield f"event: comparison_selection\ndata: {json.dumps(data)}\n\n"
                        continue
                    else:
                        chunk_data = data
                else:
                    chunk_data = event

                # Send comparison context before first content chunk (if comparison mode)
                if not comparison_context_sent and rag_service.last_comparison_context:
                    yield f"event: comparison_context\ndata: {json.dumps(rag_service.last_comparison_context)}\n\n"
                    comparison_context_sent = True

                chunk_count += 1
                yield f"event: chunk\ndata: {json.dumps({'chunk': chunk_data})}\n\n"

            yield f"event: done\ndata: {json.dumps({'status': 'completed'})}\n\n"

        except Exception as e:
            logger.error(
                f"[Comparison Confirm SSE] Streaming error: {e}",
                exc_info=True,
                extra={"session_id": session_id}
            )
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
