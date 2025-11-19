"""Repository for canonical Document operations (dedup & reuse)."""
from typing import Optional, Generator
from contextlib import contextmanager
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy import select, func
from app.database import SessionLocal
from app.db_models_documents import Document
from app.db_models_chat import DocumentChunk
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
