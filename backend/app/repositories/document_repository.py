"""Repository for canonical Document operations (dedup & reuse)."""
from typing import Optional, Generator, Dict, List
from contextlib import contextmanager
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy import select, func
from app.database import SessionLocal
from app.db_models_documents import Document
from app.db_models_chat import DocumentChunk, SessionDocument, ChatSession, CollectionDocument, Collection
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

    def get_by_hash(self, content_hash: str, org_id: str) -> Optional[Document]:
        """Get document by content hash (for deduplication) within a tenant."""
        with self._get_session() as db:
            try:
                return db.execute(
                    select(Document).where(
                        Document.content_hash == content_hash,
                        Document.org_id == org_id
                    )
                ).scalar_one_or_none()
            except SQLAlchemyError as e:
                logger.error(
                    "Failed to get document by hash",
                    extra={"hash": content_hash, "org_id": org_id, "error": str(e)}
                )
                return None

    def get_by_id(self, document_id: str, org_id: Optional[str] = None) -> Optional[Document]:
        """Get document by ID, optionally scoped to tenant."""
        with self._get_session() as db:
            try:
                if org_id:
                    return db.query(Document).filter(
                        Document.id == document_id,
                        Document.org_id == org_id
                    ).first()
                return db.get(Document, document_id)
            except SQLAlchemyError as e:
                logger.error(
                    "Failed to get document by ID",
                    extra={"document_id": document_id, "org_id": org_id, "error": str(e)}
                )
                return None

    def create_document(
        self,
        org_id: str,
        user_id: str,
        filename: str,
        file_path: str,
        file_size_bytes: int,
        content_hash: str,
        page_count: int = 0,
        status: str = "processing",
        document_id: Optional[str] = None
    ) -> Optional[Document]:
        """Create a new canonical document."""
        with self._get_session() as db:
            try:
                doc = Document(
                    id=document_id if document_id else None,
                    org_id=org_id,
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
                        "org_id": org_id,
                        "user_id": user_id
                    }
                )
                return doc
            except IntegrityError:
                db.rollback()
                logger.warning(
                    "Duplicate document hash encountered during create",
                    extra={"hash": content_hash, "org_id": org_id}
                )
                # Return existing document
                return self.get_by_hash(content_hash, org_id)
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(
                    "Failed to create canonical document",
                    extra={"hash": content_hash, "org_id": org_id, "error": str(e)},
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
        error_message: Optional[str] = None,
        file_path: Optional[str] = None
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
                if file_path is not None:
                    doc.file_path = file_path

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

    def update_file_path(self, document_id: str, file_path: str) -> bool:
        """Update document file path."""
        return self.update_document(
            document_id=document_id,
            file_path=file_path
        )

    def mark_failed(self, document_id: str, error_message: str) -> bool:
        """Mark document as failed."""
        return self.update_document(
            document_id=document_id,
            status="failed",
            error_message=error_message
        )

    def delete_document(self, document_id: str) -> bool:
        """Delete a document (cascades to chunks, collection_documents, job_states).

        Preserves extractions and workflows - they will have NULL document_id after deletion.
        Handles cleanup of foreign key references to prevent constraint violations.
        """
        with self._get_session() as db:
            try:
                doc = db.get(Document, document_id)
                if not doc:
                    logger.warning(
                        "Document not found for deletion",
                        extra={"document_id": document_id}
                    )
                    return False

                # Nullify extraction.document_id to prevent foreign key violation
                extractions_updated = db.query(Extraction).filter(
                    Extraction.document_id == document_id
                ).update(
                    {Extraction.document_id: None},
                    synchronize_session=False
                )

                if extractions_updated > 0:
                    logger.info(
                        f"Nullified document_id in {extractions_updated} extractions",
                        extra={"document_id": document_id}
                    )

                # Delete the document (cascades to chunks, collection_documents, job_states)
                db.delete(doc)
                db.commit()

                logger.info(
                    "Deleted canonical document (preserved extractions/workflows)",
                    extra={
                        "document_id": document_id,
                        "extractions_preserved": extractions_updated
                    }
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

    def get_chunks_for_document(self, document_id: str, order_by_index: bool = True) -> List[DocumentChunk]:
        """Get all chunks for a document, optionally ordered by chunk_index."""
        with self._get_session() as db:
            try:
                query = db.query(DocumentChunk).filter(
                    DocumentChunk.document_id == document_id
                )
                if order_by_index:
                    query = query.order_by(DocumentChunk.chunk_index.asc())
                return query.all()
            except SQLAlchemyError as e:
                logger.error(
                    "Failed to get chunks for document",
                    extra={"document_id": document_id, "error": str(e)}
                )
                return []

    def get_completed_document_ids_for_collection(self, collection_id: str, org_id: str) -> List[str]:
        """Get completed document IDs for a collection."""
        with self._get_session() as db:
            try:
                result = db.query(Document.id).join(
                    CollectionDocument, Document.id == CollectionDocument.document_id
                ).filter(
                    CollectionDocument.collection_id == collection_id,
                    Document.status == "completed",
                    Document.org_id == org_id
                ).all()
                return [r[0] for r in result]
            except SQLAlchemyError as e:
                logger.error(
                    "Failed to list documents for collection",
                    extra={"collection_id": collection_id, "org_id": org_id, "error": str(e)}
                )
                return []

    def get_document_ids_with_embeddings(self, document_ids: List[str], org_id: str) -> List[str]:
        """Return document IDs that have at least one embedding."""
        if not document_ids:
            return []
        with self._get_session() as db:
            try:
                docs_with_embeddings = db.query(Document.id).join(
                    DocumentChunk, Document.id == DocumentChunk.document_id
                ).filter(
                    Document.id.in_(document_ids),
                    Document.org_id == org_id,
                    DocumentChunk.embedding.isnot(None)
                ).distinct().all()
                return [r[0] for r in docs_with_embeddings]
            except SQLAlchemyError as e:
                logger.error(
                    "Failed to list documents with embeddings",
                    extra={"document_ids_count": len(document_ids), "org_id": org_id, "error": str(e)}
                )
                return []

    def get_doc_info_by_ids(self, document_ids: List[str], org_id: Optional[str] = None) -> List[Dict[str, str]]:
        """Return minimal document info for a list of IDs."""
        if not document_ids:
            return []
        with self._get_session() as db:
            try:
                stmt = select(Document.id, Document.filename).where(Document.id.in_(document_ids))
                if org_id:
                    stmt = stmt.where(Document.org_id == org_id)
                result = db.execute(stmt).all()
                return [{"id": str(row.id), "filename": row.filename} for row in result]
            except SQLAlchemyError as e:
                logger.error(
                    "Failed to load document info",
                    extra={"document_ids_count": len(document_ids), "org_id": org_id, "error": str(e)}
                )
                return []

    def get_doc_metadata_by_ids(self, document_ids: List[str], org_id: Optional[str] = None) -> List[Dict[str, Optional[str]]]:
        """Return document metadata for a list of IDs."""
        if not document_ids:
            return []
        with self._get_session() as db:
            try:
                stmt = select(
                    Document.id,
                    Document.filename,
                    Document.page_count,
                    Document.file_size_bytes
                ).where(Document.id.in_(document_ids))
                if org_id:
                    stmt = stmt.where(Document.org_id == org_id)
                result = db.execute(stmt).all()
                return [
                    {
                        "id": str(row.id),
                        "filename": row.filename,
                        "page_count": row.page_count,
                        "file_size_bytes": row.file_size_bytes,
                    }
                    for row in result
                ]
            except SQLAlchemyError as e:
                logger.error(
                    "Failed to load document metadata",
                    extra={"document_ids_count": len(document_ids), "error": str(e)}
                )
                return []

    def list_available_documents_for_user(
        self,
        user_id: str,
        org_id: str,
        collection_id: Optional[str] = None,
    ) -> List[Dict]:
        """List completed documents available for workflows with chunk/embedding counts."""
        with self._get_session() as db:
            try:
                query = db.query(
                    Document.id,
                    Document.filename,
                    Document.page_count,
                    Document.status,
                    Document.created_at,
                    func.count(DocumentChunk.id.distinct()).label("chunk_count"),
                    func.count(DocumentChunk.embedding).label("embeddings_count"),
                ).join(
                    CollectionDocument, Document.id == CollectionDocument.document_id
                ).join(
                    Collection, CollectionDocument.collection_id == Collection.id
                ).outerjoin(
                    DocumentChunk, Document.id == DocumentChunk.document_id
                ).filter(
                    Collection.user_id == user_id,
                    Collection.org_id == org_id,
                    Document.status == "completed",
                )

                if collection_id:
                    query = query.filter(Collection.id == collection_id)

                query = query.group_by(
                    Document.id,
                    Document.filename,
                    Document.page_count,
                    Document.status,
                    Document.created_at,
                ).order_by(Document.created_at.desc())

                results = query.all()
                return [
                    {
                        "id": r.id,
                        "filename": r.filename,
                        "page_count": r.page_count,
                        "status": r.status,
                        "created_at": r.created_at,
                        "chunk_count": int(r.chunk_count or 0),
                        "embeddings_count": int(r.embeddings_count or 0),
                    }
                    for r in results
                ]
            except SQLAlchemyError as e:
                logger.error(
                    "Failed to list available documents",
                    extra={"user_id": user_id, "org_id": org_id, "collection_id": collection_id, "error": str(e)}
                )
                return []

    def get_document_usage(self, document_id: str, user_id: str, org_id: str) -> Optional[Dict]:
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
                document = db.query(Document).filter(
                    Document.id == document_id,
                    Document.org_id == org_id
                ).first()
                if not document:
                    logger.warning(
                        "Document not found for usage query",
                        extra={"document_id": document_id, "user_id": user_id, "org_id": org_id}
                    )
                    return None

                if document.user_id != user_id:
                    logger.warning(
                        "User does not own document",
                        extra={"document_id": document_id, "user_id": user_id, "org_id": org_id}
                    )
                    return None

                # Query chat sessions using this document
                chat_sessions = db.query(ChatSession).join(
                    SessionDocument,
                    SessionDocument.session_id == ChatSession.id
                ).filter(
                    SessionDocument.document_id == document_id,
                    ChatSession.user_id == user_id,
                    ChatSession.org_id == org_id
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
                    Extraction.user_id == user_id,
                    Extraction.org_id == org_id
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
                    WorkflowRun.document_ids.contains([document_id]),
                    WorkflowRun.user_id == user_id,
                    WorkflowRun.org_id == org_id
                ).all()

                workflows_list = []
                for workflow_run in workflows:
                    # Get workflow name from snapshot (preferred) or relationship (fallback)
                    workflow_name = "Unknown Workflow"
                    if workflow_run.workflow_snapshot and isinstance(workflow_run.workflow_snapshot, dict):
                        workflow_name = workflow_run.workflow_snapshot.get("name", "Unknown Workflow")
                    elif workflow_run.workflow:
                        workflow_name = workflow_run.workflow.name

                    workflows_list.append({
                        "run_id": workflow_run.id,
                        "workflow_name": workflow_name,
                        "created_at": workflow_run.created_at.isoformat() if workflow_run.created_at else None
                    })

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
