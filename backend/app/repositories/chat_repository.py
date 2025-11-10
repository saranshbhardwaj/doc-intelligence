"""Repository for chat session and message database operations.

Data Access Layer for Chat Mode conversations.

Pattern:
- All database queries go through repositories
- Endpoints/services call repositories (never SessionLocal directly)
- Repositories handle session management and error handling
- Makes testing easier with repository mocking
"""
from datetime import datetime
from typing import Optional, List
from contextlib import contextmanager
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.db_models_chat import ChatSession, ChatMessage
from app.utils.logging import logger


class ChatRepository:
    """Repository for chat session and message database operations.

    Encapsulates all database access for chat sessions and messages.
    Provides clean interface for CRUD operations.

    Usage:
        chat_repo = ChatRepository()
        chat_repo.create_session(...)
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

    # ============================================================================
    # CHAT SESSION OPERATIONS
    # ============================================================================

    def create_session(
        self,
        collection_id: str,
        user_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None
    ) -> Optional[ChatSession]:
        """Create a new chat session.

        Args:
            collection_id: Collection ID
            user_id: User ID (Clerk)
            title: Optional session title (auto-generated if not provided)
            description: Optional session description

        Returns:
            ChatSession object if successful, None on error
        """
        with self._get_session() as db:
            try:
                session = ChatSession(
                    collection_id=collection_id,
                    user_id=user_id,
                    title=title or "New Chat",
                    description=description,
                    message_count=0
                )
                db.add(session)
                db.commit()
                db.refresh(session)

                logger.info(
                    f"Created chat session",
                    extra={
                        "session_id": session.id,
                        "collection_id": collection_id,
                        "user_id": user_id
                    }
                )

                return session

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to create chat session: {e}",
                    extra={"collection_id": collection_id, "user_id": user_id, "error": str(e)}
                )
                db.rollback()
                return None

    def get_session(
        self,
        session_id: str,
        user_id: str
    ) -> Optional[ChatSession]:
        """Get chat session by ID (with user ownership check).

        Args:
            session_id: Session ID
            user_id: User ID (for ownership verification)

        Returns:
            ChatSession object if found and owned by user, None otherwise
        """
        with self._get_session() as db:
            try:
                return db.query(ChatSession).filter(
                    ChatSession.id == session_id,
                    ChatSession.user_id == user_id
                ).first()
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get chat session: {e}",
                    extra={"session_id": session_id, "error": str(e)}
                )
                return None

    def list_sessions(
        self,
        collection_id: str,
        limit: int = 20
    ) -> List[ChatSession]:
        """List chat sessions for a collection.

        Args:
            collection_id: Collection ID
            limit: Max results (default: 20)

        Returns:
            List of ChatSession objects, newest first
        """
        with self._get_session() as db:
            try:
                return db.query(ChatSession).filter(
                    ChatSession.collection_id == collection_id
                ).order_by(
                    ChatSession.updated_at.desc()
                ).limit(limit).all()

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to list chat sessions: {e}",
                    extra={"collection_id": collection_id, "error": str(e)}
                )
                return []

    def update_session(
        self,
        session_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        message_count: Optional[int] = None
    ) -> bool:
        """Update chat session metadata.

        Args:
            session_id: Session ID
            title: Updated title
            description: Updated description
            message_count: Updated message count

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                session = db.query(ChatSession).filter(
                    ChatSession.id == session_id
                ).first()

                if not session:
                    logger.warning(
                        f"Session not found for update: {session_id}",
                        extra={"session_id": session_id}
                    )
                    return False

                if title is not None:
                    session.title = title
                if description is not None:
                    session.description = description
                if message_count is not None:
                    session.message_count = message_count

                db.commit()

                logger.debug(
                    f"Updated chat session",
                    extra={"session_id": session_id}
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to update chat session: {e}",
                    extra={"session_id": session_id, "error": str(e)}
                )
                db.rollback()
                return False

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

    def delete_session(
        self,
        session_id: str,
        user_id: str
    ) -> bool:
        """Delete a chat session (cascades to messages).

        Args:
            session_id: Session ID
            user_id: User ID (for ownership verification)

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                session = db.query(ChatSession).filter(
                    ChatSession.id == session_id,
                    ChatSession.user_id == user_id
                ).first()

                if not session:
                    logger.warning(
                        f"Session not found for deletion: {session_id}",
                        extra={"session_id": session_id, "user_id": user_id}
                    )
                    return False

                db.delete(session)
                db.commit()

                logger.info(
                    f"Deleted chat session",
                    extra={"session_id": session_id, "user_id": user_id}
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to delete chat session: {e}",
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
        cost_usd: Optional[float] = None
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
            tokens_used: Tokens consumed
            cost_usd: Cost in USD

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
                    cost_usd=cost_usd
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
                    f"Deleted chat message",
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

        Args:
            session_id: Session ID

        Returns:
            Dictionary with stats (message_count, total_tokens, total_cost)
        """
        with self._get_session() as db:
            try:
                messages = db.query(ChatMessage).filter(
                    ChatMessage.session_id == session_id
                ).all()

                total_tokens = sum(m.tokens_used for m in messages if m.tokens_used)
                total_cost = sum(m.cost_usd for m in messages if m.cost_usd)

                return {
                    "message_count": len(messages),
                    "user_messages": len([m for m in messages if m.role == "user"]),
                    "assistant_messages": len([m for m in messages if m.role == "assistant"]),
                    "total_tokens": total_tokens,
                    "total_cost_usd": round(total_cost, 4)
                }

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get session stats: {e}",
                    extra={"session_id": session_id, "error": str(e)}
                )
                return {}
