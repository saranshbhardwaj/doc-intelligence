"""Repository for collection-related database operations.

Data Access Layer for Chat Mode collections and documents.

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
from sqlalchemy import func

from app.database import SessionLocal
from app.db_models_chat import Collection, CollectionDocument, DocumentChunk
from app.utils.logging import logger


class CollectionRepository:
    """Repository for collection database operations.

    Encapsulates all database access for collections and collection documents.
    Provides clean interface for CRUD operations.

    Usage:
        collection_repo = CollectionRepository()
        collection_repo.create_collection(...)
        collection_repo.add_document(...)
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
    # COLLECTION OPERATIONS
    # ============================================================================

    def create_collection(
        self,
        user_id: str,
        name: str,
        description: Optional[str] = None
    ) -> Optional[Collection]:
        """Create a new collection.

        Args:
            user_id: User ID (Clerk)
            name: Collection name
            description: Optional description

        Returns:
            Collection object if successful, None on error
        """
        with self._get_session() as db:
            try:
                collection = Collection(
                    user_id=user_id,
                    name=name,
                    description=description,
                    document_count=0,
                    total_chunks=0
                )
                db.add(collection)
                db.commit()
                db.refresh(collection)

                logger.info(
                    f"Created collection: {name}",
                    extra={"collection_id": collection.id, "user_id": user_id}
                )

                return collection

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to create collection: {e}",
                    extra={"user_id": user_id, "collection_name": name, "error": str(e)}
                )
                db.rollback()
                return None

    def get_collection(
        self,
        collection_id: str,
        user_id: str
    ) -> Optional[Collection]:
        """Get collection by ID (with user ownership check).

        Args:
            collection_id: Collection ID
            user_id: User ID (for ownership verification)

        Returns:
            Collection object if found and owned by user, None otherwise
        """
        with self._get_session() as db:
            try:
                return db.query(Collection).filter(
                    Collection.id == collection_id,
                    Collection.user_id == user_id
                ).first()
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get collection: {e}",
                    extra={"collection_id": collection_id, "error": str(e)}
                )
                return None

    def get_collection_by_id(
        self,
        collection_id: str
    ) -> Optional[Collection]:
        """Get collection by ID (without ownership check - for background tasks).

        Use this method in background tasks where user context is not available.
        For API endpoints, use get_collection() with user_id for security.

        Args:
            collection_id: Collection ID

        Returns:
            Collection object if found, None otherwise
        """
        with self._get_session() as db:
            try:
                return db.query(Collection).filter(
                    Collection.id == collection_id
                ).first()
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get collection by ID: {e}",
                    extra={"collection_id": collection_id, "error": str(e)}
                )
                return None

    def list_collections(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> tuple[List[Collection], int]:
        """List collections for a user with pagination.

        Args:
            user_id: User ID
            limit: Max results (default: 50)
            offset: Pagination offset (default: 0)

        Returns:
            Tuple of (collections list, total count)
        """
        with self._get_session() as db:
            try:
                query = db.query(Collection).filter(
                    Collection.user_id == user_id
                )

                total = query.count()

                collections = query.order_by(
                    Collection.updated_at.desc()
                ).limit(limit).offset(offset).all()

                return collections, total

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to list collections: {e}",
                    extra={"user_id": user_id, "error": str(e)}
                )
                return [], 0

    def delete_collection(
        self,
        collection_id: str,
        user_id: str
    ) -> bool:
        """Delete a collection (cascades to documents, chunks, sessions).

        Args:
            collection_id: Collection ID
            user_id: User ID (for ownership verification)

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                collection = db.query(Collection).filter(
                    Collection.id == collection_id,
                    Collection.user_id == user_id
                ).first()

                if not collection:
                    logger.warning(
                        f"Collection not found for deletion: {collection_id}",
                        extra={"collection_id": collection_id, "user_id": user_id}
                    )
                    return False

                db.delete(collection)
                db.commit()

                logger.info(
                    f"Deleted collection: {collection.name}",
                    extra={"collection_id": collection_id, "user_id": user_id}
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to delete collection: {e}",
                    extra={"collection_id": collection_id, "error": str(e)}
                )
                db.rollback()
                return False

    def update_collection_stats(
        self,
        collection_id: str,
        document_count: Optional[int] = None,
        total_chunks: Optional[int] = None,
        embedding_model: Optional[str] = None,
        embedding_dimension: Optional[int] = None
    ) -> bool:
        """Update collection statistics.

        **DEPRECATED for count updates**: Use `recompute_collection_stats()` instead
        to update document_count and total_chunks. This method uses manual counts
        that can drift out of sync and has race conditions.

        This method is still appropriate for setting embedding_model and
        embedding_dimension metadata.

        Args:
            collection_id: Collection ID
            document_count: Updated document count (DEPRECATED - use recompute_collection_stats)
            total_chunks: Updated chunk count (DEPRECATED - use recompute_collection_stats)
            embedding_model: Embedding model used
            embedding_dimension: Embedding vector dimension

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                collection = db.query(Collection).filter(
                    Collection.id == collection_id
                ).first()

                if not collection:
                    logger.warning(
                        f"Collection not found for stats update: {collection_id}",
                        extra={"collection_id": collection_id}
                    )
                    return False

                if document_count is not None:
                    collection.document_count = document_count
                if total_chunks is not None:
                    collection.total_chunks = total_chunks
                if embedding_model is not None:
                    collection.embedding_model = embedding_model
                if embedding_dimension is not None:
                    collection.embedding_dimension = embedding_dimension

                db.commit()

                logger.debug(
                    f"Updated collection stats",
                    extra={"collection_id": collection_id}
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to update collection stats: {e}",
                    extra={"collection_id": collection_id, "error": str(e)}
                )
                db.rollback()
                return False

    def recompute_collection_stats(
        self,
        collection_id: str,
        embedding_model: Optional[str] = None,
        embedding_dimension: Optional[int] = None
    ) -> bool:
        """Recompute collection statistics from database using aggregate functions.

        This is the CORRECT way to update collection stats - it computes the values
        directly from the database rather than maintaining a cached counter that can
        drift out of sync.

        Benefits:
        - Always accurate (single source of truth)
        - No race conditions (atomic query)
        - Simpler logic (no manual increment/decrement)
        - Self-healing (fixes any previous drift)

        Args:
            collection_id: Collection ID
            embedding_model: Optional embedding model to set
            embedding_dimension: Optional embedding dimension to set

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                collection = db.query(Collection).filter(
                    Collection.id == collection_id
                ).first()

                if not collection:
                    logger.warning(
                        f"Collection not found for stats recompute: {collection_id}",
                        extra={"collection_id": collection_id}
                    )
                    return False

                # Compute document_count from collection_documents table
                document_count = db.query(func.count(CollectionDocument.id)).filter(
                    CollectionDocument.collection_id == collection_id
                ).scalar() or 0

                # Compute total_chunks from document_chunks table
                # Join through collection_documents to ensure we only count chunks
                # from documents in this collection
                total_chunks = db.query(func.count(DocumentChunk.id)).join(
                    CollectionDocument,
                    DocumentChunk.document_id == CollectionDocument.id
                ).filter(
                    CollectionDocument.collection_id == collection_id
                ).scalar() or 0

                # Update collection with computed values
                collection.document_count = document_count
                collection.total_chunks = total_chunks

                if embedding_model is not None:
                    collection.embedding_model = embedding_model
                if embedding_dimension is not None:
                    collection.embedding_dimension = embedding_dimension

                db.commit()

                logger.info(
                    f"Recomputed collection stats",
                    extra={
                        "collection_id": collection_id,
                        "document_count": document_count,
                        "total_chunks": total_chunks
                    }
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to recompute collection stats: {e}",
                    extra={"collection_id": collection_id, "error": str(e)}
                )
                db.rollback()
                return False

    # ============================================================================
    # COLLECTION DOCUMENT OPERATIONS
    # ============================================================================

    def create_document(
        self,
        collection_id: str,
        filename: str,
        file_size_bytes: int,
        page_count: int,
        content_hash: str,
        file_path: Optional[str] = None,
        extraction_id: Optional[str] = None,
        status: str = "processing"
    ) -> Optional[CollectionDocument]:
        """Add a document to a collection.

        Args:
            collection_id: Collection ID
            filename: Original filename
            file_size_bytes: File size in bytes
            page_count: Number of pages
            content_hash: SHA256 hash for duplicate detection
            file_path: Path to uploaded PDF file
            extraction_id: Optional link to extraction record
            status: Document status (default: "processing")

        Returns:
            CollectionDocument object if successful, None on error
        """
        with self._get_session() as db:
            try:
                document = CollectionDocument(
                    collection_id=collection_id,
                    filename=filename,
                    file_path=file_path,
                    file_size_bytes=file_size_bytes,
                    page_count=page_count,
                    content_hash=content_hash,
                    extraction_id=extraction_id,
                    status=status,
                    chunk_count=0
                )
                db.add(document)
                db.commit()
                db.refresh(document)

                logger.info(
                    f"Created document in collection",
                    extra={
                        "document_id": document.id,
                        "collection_id": collection_id,
                        "file_name": filename
                    }
                )

                return document

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to create document: {e}",
                    extra={"collection_id": collection_id, "filename": filename, "error": str(e)}
                )
                db.rollback()
                return None

    def get_document(
        self,
        document_id: str
    ) -> Optional[CollectionDocument]:
        """Get document by ID.

        Args:
            document_id: Document ID

        Returns:
            CollectionDocument object if found, None otherwise
        """
        with self._get_session() as db:
            try:
                return db.query(CollectionDocument).filter(
                    CollectionDocument.id == document_id
                ).first()
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get document: {e}",
                    extra={"document_id": document_id, "error": str(e)}
                )
                return None

    def list_documents(
        self,
        collection_id: str,
        limit: Optional[int] = None
    ) -> List[CollectionDocument]:
        """List documents in a collection.

        Args:
            collection_id: Collection ID
            limit: Optional limit on results

        Returns:
            List of CollectionDocument objects
        """
        with self._get_session() as db:
            try:
                query = db.query(CollectionDocument).filter(
                    CollectionDocument.collection_id == collection_id
                ).order_by(CollectionDocument.created_at.desc())

                if limit:
                    query = query.limit(limit)

                return query.all()

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to list documents: {e}",
                    extra={"collection_id": collection_id, "error": str(e)}
                )
                return []

    def check_duplicate_document(
        self,
        collection_id: str,
        content_hash: str
    ) -> Optional[CollectionDocument]:
        """Check if document already exists in collection (by content hash).

        Args:
            collection_id: Collection ID
            content_hash: SHA256 hash of file content

        Returns:
            Existing document if found, None otherwise
        """
        with self._get_session() as db:
            try:
                return db.query(CollectionDocument).filter(
                    CollectionDocument.collection_id == collection_id,
                    CollectionDocument.content_hash == content_hash
                ).first()
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to check duplicate document: {e}",
                    extra={"collection_id": collection_id, "error": str(e)}
                )
                return None

    def update_document_status(
        self,
        document_id: str,
        status: str,
        chunk_count: Optional[int] = None,
        page_count: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Update document status and stats.

        Args:
            document_id: Document ID
            status: New status (processing, completed, failed)
            chunk_count: Number of chunks created
            page_count: Number of pages in document
            error_message: Error message if status is failed

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                document = db.query(CollectionDocument).filter(
                    CollectionDocument.id == document_id
                ).first()

                if not document:
                    logger.warning(
                        f"Document not found for status update: {document_id}",
                        extra={"document_id": document_id}
                    )
                    return False

                document.status = status
                if chunk_count is not None:
                    document.chunk_count = chunk_count
                if page_count is not None:
                    document.page_count = page_count
                if error_message:
                    document.error_message = error_message[:500]

                if status == "completed":
                    document.completed_at = datetime.now()

                db.commit()

                logger.debug(
                    f"Updated document status to '{status}'",
                    extra={"document_id": document_id, "status": status}
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to update document status: {e}",
                    extra={"document_id": document_id, "error": str(e)}
                )
                db.rollback()
                return False

    def delete_document(
        self,
        document_id: str
    ) -> bool:
        """Delete a document (cascades to chunks).

        Args:
            document_id: Document ID

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                document = db.query(CollectionDocument).filter(
                    CollectionDocument.id == document_id
                ).first()

                if not document:
                    logger.warning(
                        f"Document not found for deletion: {document_id}",
                        extra={"document_id": document_id}
                    )
                    return False

                db.delete(document)
                db.commit()

                logger.info(
                    f"Deleted document: {document.filename}",
                    extra={"document_id": document_id}
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to delete document: {e}",
                    extra={"document_id": document_id, "error": str(e)}
                )
                db.rollback()
                return False
