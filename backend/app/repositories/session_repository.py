"""Repository for chat session-related database operations.

Handles CRUD operations for chat sessions and their document associations.
"""
from typing import Optional, List, Tuple, Generator
from contextlib import contextmanager
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy import func

from app.database import SessionLocal
from app.db_models_chat import ChatSession, SessionDocument, ChatMessage
from app.db_models_documents import Document
from app.utils.logging import logger


class SessionRepository:
    """Repository for chat session database operations.

    Manages:
    - Session CRUD
    - Session-document associations
    - Session queries with document details
    """

    @contextmanager
    def _get_session(self) -> Generator[Session, None, None]:
        """Context manager for database sessions."""
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    # =================================================================
    # Session CRUD
    # =================================================================

    def create_session(
        self,
        user_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None
    ) -> Optional[ChatSession]:
        """Create a new chat session.

        Args:
            user_id: User ID (Clerk)
            title: Optional session title
            description: Optional description

        Returns:
            ChatSession object or None on failure

        Logs:
            user_id, session_id
        """
        with self._get_session() as db:
            try:
                session = ChatSession(
                    user_id=user_id,
                    title=title or "New Chat",
                    description=description,
                    message_count=0
                )

                db.add(session)
                db.commit()
                db.refresh(session)

                logger.info(
                    "Created chat session",
                    extra={"user_id": user_id, "session_id": session.id}
                )

                return session

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to create session: {e}",
                    extra={"user_id": user_id, "error": str(e)}
                )
                db.rollback()
                return None

    def get_session(
        self,
        session_id: str,
        user_id: str
    ) -> Optional[ChatSession]:
        """Get session by ID with ownership check.

        Args:
            session_id: Session ID
            user_id: User ID for ownership verification

        Returns:
            ChatSession with document_links loaded, or None

        Logs:
            user_id, session_id
        """
        with self._get_session() as db:
            try:
                session = db.query(ChatSession).options(
                    joinedload(ChatSession.document_links).joinedload(SessionDocument.document)
                ).filter(
                    ChatSession.id == session_id,
                    ChatSession.user_id == user_id
                ).first()

                if not session:
                    logger.warning(
                        "Session not found or access denied",
                        extra={"user_id": user_id, "session_id": session_id}
                    )

                return session

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get session: {e}",
                    extra={"user_id": user_id, "session_id": session_id, "error": str(e)}
                )
                return None

    def list_sessions(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0
    ) -> Tuple[List[Tuple[ChatSession, int]], int]:
        """List user's sessions ordered by most recent with document counts.

        Args:
            user_id: User ID
            limit: Max results
            offset: Pagination offset

        Returns:
            ([(session, document_count), ...], total_count)

        Logs:
            user_id, count
        """
        with self._get_session() as db:
            try:
                # Query sessions with document counts using a subquery
                query = db.query(
                    ChatSession,
                    func.count(SessionDocument.document_id).label('doc_count')
                ).outerjoin(
                    SessionDocument,
                    ChatSession.id == SessionDocument.session_id
                ).filter(
                    ChatSession.user_id == user_id
                ).group_by(ChatSession.id).order_by(ChatSession.updated_at.desc())

                total = db.query(ChatSession).filter(ChatSession.user_id == user_id).count()
                results = query.limit(limit).offset(offset).all()

                logger.info(
                    "Listed sessions with document counts",
                    extra={"user_id": user_id, "count": len(results), "total": total}
                )

                return results, total

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to list sessions: {e}",
                    extra={"user_id": user_id, "error": str(e)}
                )
                return [], 0

    def update_session(
        self,
        session_id: str,
        user_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None
    ) -> Optional[ChatSession]:
        """Update session title and/or description.

        Args:
            session_id: Session ID
            user_id: User ID for ownership verification
            title: Optional new title
            description: Optional new description

        Returns:
            Updated ChatSession or None

        Logs:
            user_id, session_id
        """
        with self._get_session() as db:
            try:
                session = db.query(ChatSession).filter(
                    ChatSession.id == session_id,
                    ChatSession.user_id == user_id
                ).first()

                if not session:
                    logger.warning(
                        "Session not found or access denied",
                        extra={"user_id": user_id, "session_id": session_id}
                    )
                    return None

                # Update fields if provided
                if title is not None:
                    session.title = title
                if description is not None:
                    session.description = description

                db.commit()
                db.refresh(session)

                logger.info(
                    "Updated session",
                    extra={"user_id": user_id, "session_id": session_id}
                )

                return session

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to update session: {e}",
                    extra={"user_id": user_id, "session_id": session_id, "error": str(e)}
                )
                db.rollback()
                return None

    def delete_session(
        self,
        session_id: str,
        user_id: str
    ) -> bool:
        """Delete a session (cascades to messages and document links).

        Args:
            session_id: Session ID
            user_id: User ID for ownership verification

        Returns:
            True if successful

        Logs:
            user_id, session_id
        """
        with self._get_session() as db:
            try:
                session = db.query(ChatSession).filter(
                    ChatSession.id == session_id,
                    ChatSession.user_id == user_id
                ).first()

                if not session:
                    logger.warning(
                        "Session not found or access denied",
                        extra={"user_id": user_id, "session_id": session_id}
                    )
                    return False

                db.delete(session)
                db.commit()

                logger.info(
                    "Deleted session",
                    extra={"user_id": user_id, "session_id": session_id}
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to delete session: {e}",
                    extra={"user_id": user_id, "session_id": session_id, "error": str(e)}
                )
                db.rollback()
                return False

    # =================================================================
    # Session-Document Management
    # =================================================================

    def add_documents_to_session(
        self,
        session_id: str,
        document_ids: List[str],
        user_id: str
    ) -> int:
        """Add documents to a session.

        Args:
            session_id: Session ID
            document_ids: List of document IDs to add
            user_id: User ID (for logging)

        Returns:
            Number of documents added

        Logs:
            user_id, session_id, documents_added
        """
        with self._get_session() as db:
            try:
                # Verify session exists and user owns it
                session = db.query(ChatSession).filter(
                    ChatSession.id == session_id,
                    ChatSession.user_id == user_id
                ).first()

                if not session:
                    logger.warning(
                        "Session not found or access denied",
                        extra={"user_id": user_id, "session_id": session_id}
                    )
                    return 0

                added_count = 0

                for doc_id in document_ids:
                    # Check if document exists
                    doc = db.query(Document).filter(Document.id == doc_id).first()
                    if not doc:
                        logger.warning(
                            f"Document not found, skipping",
                            extra={"user_id": user_id, "document_id": doc_id}
                        )
                        continue

                    # Check if already linked
                    existing = db.query(SessionDocument).filter(
                        SessionDocument.session_id == session_id,
                        SessionDocument.document_id == doc_id
                    ).first()

                    if existing:
                        logger.debug(
                            "Document already in session, skipping",
                            extra={"user_id": user_id, "session_id": session_id, "document_id": doc_id}
                        )
                        continue

                    # Create link
                    link = SessionDocument(
                        session_id=session_id,
                        document_id=doc_id
                    )
                    db.add(link)
                    added_count += 1

                db.commit()

                logger.info(
                    "Added documents to session",
                    extra={
                        "user_id": user_id,
                        "session_id": session_id,
                        "documents_added": added_count
                    }
                )

                return added_count

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to add documents to session: {e}",
                    extra={
                        "user_id": user_id,
                        "session_id": session_id,
                        "error": str(e)
                    }
                )
                db.rollback()
                return 0

    def remove_document_from_session(
        self,
        session_id: str,
        document_id: str,
        user_id: str
    ) -> bool:
        """Remove a document from a session.

        Args:
            session_id: Session ID
            document_id: Document ID to remove
            user_id: User ID (for logging)

        Returns:
            True if successful

        Logs:
            user_id, session_id, document_id
        """
        with self._get_session() as db:
            try:
                # Verify session ownership
                session = db.query(ChatSession).filter(
                    ChatSession.id == session_id,
                    ChatSession.user_id == user_id
                ).first()

                if not session:
                    logger.warning(
                        "Session not found or access denied",
                        extra={"user_id": user_id, "session_id": session_id}
                    )
                    return False

                # Find and delete link
                link = db.query(SessionDocument).filter(
                    SessionDocument.session_id == session_id,
                    SessionDocument.document_id == document_id
                ).first()

                if not link:
                    logger.warning(
                        "Document not in session",
                        extra={
                            "user_id": user_id,
                            "session_id": session_id,
                            "document_id": document_id
                        }
                    )
                    return False

                db.delete(link)
                db.commit()

                logger.info(
                    "Removed document from session",
                    extra={
                        "user_id": user_id,
                        "session_id": session_id,
                        "document_id": document_id
                    }
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to remove document from session: {e}",
                    extra={
                        "user_id": user_id,
                        "session_id": session_id,
                        "document_id": document_id,
                        "error": str(e)
                    }
                )
                db.rollback()
                return False

    def get_session_document_ids(
        self,
        session_id: str
    ) -> List[str]:
        """Get list of document IDs in a session.

        Args:
            session_id: Session ID

        Returns:
            List of document IDs

        Logs:
            session_id, document_count
        """
        with self._get_session() as db:
            try:
                doc_ids = db.query(SessionDocument.document_id).filter(
                    SessionDocument.session_id == session_id
                ).all()

                doc_id_list = [doc_id[0] for doc_id in doc_ids]

                logger.debug(
                    "Retrieved session document IDs",
                    extra={"session_id": session_id, "document_count": len(doc_id_list)}
                )

                return doc_id_list

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get session documents: {e}",
                    extra={"session_id": session_id, "error": str(e)}
                )
                return []
