"""Repository for canonical Document operations (dedup & reuse)."""
from typing import Optional, Generator, Dict, List
from contextlib import contextmanager
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy import select, func
from app.database import SessionLocal
from app.db_models_documents import Document
from app.db_models_chat import DocumentChunk, SessionDocument, ChatSession
from app.db_models import Extraction
from app.db_models_workflows import WorkflowRun
from app.utils.logging import logger


class DocumentRepository:
    @contextmanager
    def _get_session(self) -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def get_by_hash(self, content_hash: str) -> Optional[Document]:
        """Get document by content hash (for deduplication)."""
        with self._get_session() as db:
            try:
                return db.execute(
                    select(Document).where(Document.content_hash == content_hash)
                ).scalar_one_or_none()
            except SQLAlchemyError as e:
                logger.error(
                    "Failed to get document by hash",
                    extra={"hash": content_hash, "error": str(e)}
                )
                return None

    def get_by_id(self, document_id: str) -> Optional[Document]:
        """Get document by ID."""
        with self._get_session() as db:
            try:
                return db.get(Document, document_id)
            except SQLAlchemyError as e:
                logger.error(
                    "Failed to get document by ID",
                    extra={"document_id": document_id, "error": str(e)}
                )
                return None

    def create_document(
        self,
        user_id: str,
        filename: str,
        file_path: str,
        file_size_bytes: int,
        content_hash: str,
        page_count: int = 0,
        status: str = "processing"
    ) -> Optional[Document]:
        """Create a new canonical document."""
        with self._get_session() as db:
            try:
                doc = Document(
                    user_id=user_id,
                    filename=filename,
                    file_path=file_path,
                    file_size_bytes=file_size_bytes,
                    content_hash=content_hash,
                    page_count=page_count,
                    chunk_count=0,
                    status=status
                )
                db.add(doc)
                db.commit()
                db.refresh(doc)
                logger.info(
                    "Created canonical document",
                    extra={
                        "document_id": doc.id,
                        "hash": content_hash,
                        "user_id": user_id
                    }
                )
                return doc
            except IntegrityError:
                db.rollback()
                logger.warning(
                    "Duplicate document hash encountered during create",
                    extra={"hash": content_hash}
                )
                # Return existing document
                return self.get_by_hash(content_hash)
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(
                    "Failed to create canonical document",
                    extra={"hash": content_hash, "error": str(e)},
                    exc_info=True
                )
                return None

    def update_document(
        self,
        document_id: str,
        page_count: Optional[int] = None,
        chunk_count: Optional[int] = None,
        status: Optional[str] = None,
        parser_used: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        cost_usd: Optional[float] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Update document metadata."""
        with self._get_session() as db:
            try:
                doc = db.get(Document, document_id)
                if not doc:
                    logger.warning(
                        "Document not found for update",
                        extra={"document_id": document_id}
                    )
                    return False

                if page_count is not None:
                    doc.page_count = page_count
                if chunk_count is not None:
                    doc.chunk_count = chunk_count
                if status is not None:
                    doc.status = status
                    if status == "completed":
                        doc.completed_at = func.now()
                if parser_used is not None:
                    doc.parser_used = parser_used
                if processing_time_ms is not None:
                    doc.processing_time_ms = processing_time_ms
                if cost_usd is not None:
                    doc.cost_usd = cost_usd
                if error_message is not None:
                    doc.error_message = error_message

                db.commit()
                return True
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(
                    "Failed to update document",
                    extra={"document_id": document_id, "error": str(e)},
                    exc_info=True
                )
                return False

    def mark_completed(
        self,
        document_id: str,
        chunk_count: int,
        page_count: int,
        processing_time_ms: int,
        parser_used: str
    ) -> bool:
        """Mark document as completed."""
        return self.update_document(
            document_id=document_id,
            status="completed",
            chunk_count=chunk_count,
            page_count=page_count,
            processing_time_ms=processing_time_ms,
            parser_used=parser_used
        )

    def mark_failed(self, document_id: str, error_message: str) -> bool:
        """Mark document as failed."""
        return self.update_document(
            document_id=document_id,
            status="failed",
            error_message=error_message
        )

    def delete_document(self, document_id: str) -> bool:
        """Delete a document (cascades to chunks, collection_documents, job_states)."""
        with self._get_session() as db:
            try:
                doc = db.get(Document, document_id)
                if not doc:
                    logger.warning(
                        "Document not found for deletion",
                        extra={"document_id": document_id}
                    )
                    return False

                db.delete(doc)
                db.commit()
                logger.info(
                    "Deleted canonical document",
                    extra={"document_id": document_id}
                )
                return True
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(
                    "Failed to delete document",
                    extra={"document_id": document_id, "error": str(e)},
                    exc_info=True
                )
                return False

    def get_chunk_count(self, document_id: str) -> int:
        """Get the number of chunks for a document."""
        with self._get_session() as db:
            try:
                count = db.query(func.count(DocumentChunk.id)).filter(
                    DocumentChunk.document_id == document_id
                ).scalar()
                return count or 0
            except SQLAlchemyError as e:
                logger.error(
                    "Failed to get chunk count",
                    extra={"document_id": document_id, "error": str(e)}
                )
                return 0

    def get_document_usage(self, document_id: str, user_id: str) -> Optional[Dict]:
        """
        Get usage statistics for a document across all modes.

        Args:
            document_id: Document ID
            user_id: User ID (for ownership verification)

        Returns:
            {
                "document_id": str,
                "document_name": str,
                "usage": {
                    "chat_sessions": [
                        {"session_id": str, "title": str, "created_at": str},
                        ...
                    ],
                    "extracts": [
                        {"request_id": str, "created_at": str, "status": str},
                        ...
                    ],
                    "workflows": [
                        {"run_id": str, "workflow_name": str, "created_at": str},
                        ...
                    ]
                },
                "total_usage_count": int
            }

        Input:
            - document_id: str
            - user_id: str

        Output:
            - Dictionary with usage details or None if document not found
        """
        with self._get_session() as db:
            try:
                # Verify document exists and user owns it
                document = db.get(Document, document_id)
                if not document:
                    logger.warning(
                        "Document not found for usage query",
                        extra={"document_id": document_id, "user_id": user_id}
                    )
                    return None

                if document.user_id != user_id:
                    logger.warning(
                        "User does not own document",
                        extra={"document_id": document_id, "user_id": user_id}
                    )
                    return None

                # Query chat sessions using this document
                chat_sessions = db.query(ChatSession).join(
                    SessionDocument,
                    SessionDocument.session_id == ChatSession.id
                ).filter(
                    SessionDocument.document_id == document_id,
                    ChatSession.user_id == user_id
                ).all()

                chat_sessions_list = [
                    {
                        "session_id": session.id,
                        "title": session.title,
                        "created_at": session.created_at.isoformat() if session.created_at else None
                    }
                    for session in chat_sessions
                ]

                # Query extractions using this document
                extracts = db.query(Extraction).filter(
                    Extraction.document_id == document_id,
                    Extraction.user_id == user_id
                ).all()

                extracts_list = [
                    {
                        "request_id": extraction.id,
                        "created_at": extraction.created_at.isoformat() if extraction.created_at else None,
                        "status": extraction.status
                    }
                    for extraction in extracts
                ]

                # Query workflow runs using this document
                workflows = db.query(WorkflowRun).filter(
                    WorkflowRun.document_id == document_id,
                    WorkflowRun.user_id == user_id
                ).all()

                workflows_list = [
                    {
                        "run_id": workflow.id,
                        "workflow_name": workflow.workflow_name,
                        "created_at": workflow.created_at.isoformat() if workflow.created_at else None
                    }
                    for workflow in workflows
                ]

                # Calculate total usage count
                total_usage = len(chat_sessions_list) + len(extracts_list) + len(workflows_list)

                logger.info(
                    "Retrieved document usage",
                    extra={
                        "document_id": document_id,
                        "user_id": user_id,
                        "chat_sessions": len(chat_sessions_list),
                        "extracts": len(extracts_list),
                        "workflows": len(workflows_list),
                        "total_usage": total_usage
                    }
                )

                return {
                    "document_id": document_id,
                    "document_name": document.filename,
                    "usage": {
                        "chat_sessions": chat_sessions_list,
                        "extracts": extracts_list,
                        "workflows": workflows_list
                    },
                    "total_usage_count": total_usage
                }

            except SQLAlchemyError as e:
                logger.error(
                    "Failed to get document usage",
                    extra={"document_id": document_id, "user_id": user_id, "error": str(e)},
                    exc_info=True
                )
                return None
