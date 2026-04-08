"""Repository for chat session and message database operations.

Data Access Layer for Chat Mode conversations.

Pattern:
- All database queries go through repositories
- Endpoints/services call repositories (never SessionLocal directly)
- Repositories handle session management and error handling
- Makes testing easier with repository mocking
"""
from typing import Optional, List
from contextlib import contextmanager
from sqlalchemy import func, case
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.db_models_chat import ChatSession, ChatMessage, SessionDocument
from app.utils.logging import logger


class ChatRepository:
    """Repository for chat session and message database operations.

    Encapsulates all database access for chat sessions and messages.
    Provides clean interface for CRUD operations.

    Usage:
        chat_repo = ChatRepository()
        chat_repo.save_message(...)
    """

    @contextmanager
    def _get_session(self) -> Session:
        """Context manager for database sessions.

        Ensures sessions are properly closed even on errors.

        Yields:
            Session: SQLAlchemy database session
        """
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def increment_message_count(
        self,
        session_id: str,
        increment: int = 1
    ) -> bool:
        """Increment session message count.

        Args:
            session_id: Session ID
            increment: Number to increment by (default: 1)

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                session = db.query(ChatSession).filter(
                    ChatSession.id == session_id
                ).first()

                if not session:
                    return False

                session.message_count = (session.message_count or 0) + increment
                db.commit()

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to increment message count: {e}",
                    extra={"session_id": session_id, "error": str(e)}
                )
                db.rollback()
                return False

    # ============================================================================
    # CHAT MESSAGE OPERATIONS
    # ============================================================================

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        message_index: int,
        retrieval_query: Optional[str] = None,
        source_chunks: Optional[str] = None,
        num_chunks_retrieved: Optional[int] = None,
        model_used: Optional[str] = None,
        tokens_used: Optional[int] = None,
        cost_usd: Optional[float] = None,
        comparison_metadata: Optional[str] = None,
        citation_metadata: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        cache_read_tokens: Optional[int] = None,
        cache_write_tokens: Optional[int] = None
    ) -> Optional[ChatMessage]:
        """Save a chat message (user or assistant).

        Args:
            session_id: Session ID
            role: Message role ("user" or "assistant")
            content: Message content
            message_index: Message index in session (for ordering)
            retrieval_query: Query used for RAG retrieval (for assistant messages)
            source_chunks: JSON array of chunk IDs used (for assistant messages)
            num_chunks_retrieved: Number of chunks retrieved
            model_used: LLM model used (for assistant messages)
            tokens_used: Tokens consumed (legacy, total)
            cost_usd: Cost in USD
            comparison_metadata: JSON serialized ComparisonContext (for comparison queries)
            citation_metadata: JSON serialized citation context (for clickable citations)
            input_tokens: Granular input tokens for observability
            output_tokens: Granular output tokens for observability
            cache_read_tokens: Cache read tokens for observability
            cache_write_tokens: Cache write tokens for observability

        Returns:
            ChatMessage object if successful, None on error
        """
        with self._get_session() as db:
            try:
                message = ChatMessage(
                    session_id=session_id,
                    role=role,
                    content=content,
                    message_index=message_index,
                    retrieval_query=retrieval_query,
                    source_chunks=source_chunks,
                    num_chunks_retrieved=num_chunks_retrieved,
                    model_used=model_used,
                    tokens_used=tokens_used,
                    cost_usd=cost_usd,
                    comparison_metadata=comparison_metadata,
                    citation_metadata=citation_metadata,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_tokens=cache_read_tokens,
                    cache_write_tokens=cache_write_tokens
                )
                db.add(message)
                db.commit()
                db.refresh(message)

                logger.debug(
                    f"Saved {role} message",
                    extra={
                        "message_id": message.id,
                        "session_id": session_id,
                        "role": role
                    }
                )

                return message

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to save chat message: {e}",
                    extra={"session_id": session_id, "role": role, "error": str(e)}
                )
                db.rollback()
                return None

    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[ChatMessage]:
        """Get chat messages for a session.

        Args:
            session_id: Session ID
            limit: Optional limit on number of messages
            offset: Pagination offset (default: 0)

        Returns:
            List of ChatMessage objects, ordered by message_index
        """
        with self._get_session() as db:
            try:
                query = db.query(ChatMessage).filter(
                    ChatMessage.session_id == session_id
                ).order_by(ChatMessage.message_index)

                if limit:
                    query = query.limit(limit).offset(offset)

                return query.all()

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get chat messages: {e}",
                    extra={"session_id": session_id, "error": str(e)}
                )
                return []

    def get_message_count(
        self,
        session_id: str
    ) -> int:
        """Get total message count for a session.

        Args:
            session_id: Session ID

        Returns:
            Number of messages in session
        """
        with self._get_session() as db:
            try:
                return db.query(ChatMessage).filter(
                    ChatMessage.session_id == session_id
                ).count()
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to count messages: {e}",
                    extra={"session_id": session_id, "error": str(e)}
                )
                return 0

    def get_user_message_count(
        self,
        session_id: str
    ) -> int:
        """Get count of user messages in a session (for session length warning).

        Args:
            session_id: Session ID

        Returns:
            Number of user messages in session
        """
        with self._get_session() as db:
            try:
                return db.query(ChatMessage).filter(
                    ChatMessage.session_id == session_id,
                    ChatMessage.role == "user"
                ).count()
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to count user messages: {e}",
                    extra={"session_id": session_id, "error": str(e)}
                )
                return 0

    def delete_message(
        self,
        message_id: str
    ) -> bool:
        """Delete a chat message.

        Args:
            message_id: Message ID

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                message = db.query(ChatMessage).filter(
                    ChatMessage.id == message_id
                ).first()

                if not message:
                    logger.warning(
                        f"Message not found for deletion: {message_id}",
                        extra={"message_id": message_id}
                    )
                    return False

                db.delete(message)
                db.commit()

                logger.debug(
                    "Deleted chat message",
                    extra={"message_id": message_id}
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to delete chat message: {e}",
                    extra={"message_id": message_id, "error": str(e)}
                )
                db.rollback()
                return False

    def get_session_stats(
        self,
        session_id: str
    ) -> dict:
        """Get statistics for a chat session.

        Uses SQL aggregation for efficiency (single query instead of loading all messages).

        Args:
            session_id: Session ID

        Returns:
            Dictionary with stats (message_count, total_tokens, total_cost)
        """
        with self._get_session() as db:
            try:
                # Use SQL aggregation to avoid loading all messages into memory
                result = db.query(
                    func.count(ChatMessage.id).label("message_count"),
                    func.sum(case(
                        (ChatMessage.role == "user", 1),
                        else_=0
                    )).label("user_messages"),
                    func.sum(case(
                        (ChatMessage.role == "assistant", 1),
                        else_=0
                    )).label("assistant_messages"),
                    func.coalesce(func.sum(ChatMessage.tokens_used), 0).label("total_tokens"),
                    func.coalesce(func.sum(ChatMessage.cost_usd), 0).label("total_cost")
                ).filter(
                    ChatMessage.session_id == session_id
                ).first()

                return {
                    "message_count": result.message_count or 0,
                    "user_messages": result.user_messages or 0,
                    "assistant_messages": result.assistant_messages or 0,
                    "total_tokens": result.total_tokens or 0,
                    "total_cost_usd": round(float(result.total_cost or 0), 4)
                }

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get session stats: {e}",
                    extra={"session_id": session_id, "error": str(e)}
                )
                return {}

    def get_or_build_document_index(self, session_id: str) -> dict:
        """
        Return the stable D-number → document_id mapping for a session, building
        it on first call and persisting it to the DB.

        Ordering: session_documents.added_at ASC — first document added = D1, etc.
        Once built the index is frozen; new documents appended to the session get
        the next available D-number on the next call.

        Returns: {"D1": "doc-uuid-A", "D2": "doc-uuid-B", ...}
        """
        with self._get_session() as db:
            session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if not session:
                return {}

            existing = session.document_index or {}

            # Fetch all documents currently in the session, ordered by addition time
            session_docs = (
                db.query(SessionDocument)
                .filter(SessionDocument.session_id == session_id)
                .order_by(SessionDocument.added_at.asc())
                .all()
            )

            if not session_docs:
                return existing

            # Build reverse map: doc_id → D-label (from existing index)
            doc_id_to_label = {v: k for k, v in existing.items()}

            # All documents already indexed — nothing to do
            if len(doc_id_to_label) == len(session_docs):
                return existing

            updated = dict(existing)
            changed = False
            next_num = len(existing) + 1

            for sd in session_docs:
                if sd.document_id not in doc_id_to_label:
                    label = f"D{next_num}"
                    updated[label] = sd.document_id
                    doc_id_to_label[sd.document_id] = label
                    next_num += 1
                    changed = True

            if changed:
                try:
                    session.document_index = updated
                    db.commit()
                    logger.info(
                        f"Built document_index for session {session_id}: {list(updated.keys())}"
                    )
                except SQLAlchemyError as e:
                    logger.warning(f"Failed to persist document_index for session {session_id}: {e}")
                    db.rollback()

            return updated
