"""Repository for collection-related database operations.

Data Access Layer for Chat Mode collections and documents.

Pattern:
- All database queries go through repositories
- Endpoints/services call repositories (never SessionLocal directly)
- Repositories handle session management and error handling
- Makes testing easier with repository mocking
"""
from typing import Optional, List, Generator
from contextlib import contextmanager
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func

from app.database import SessionLocal
from app.db_models_chat import Collection, CollectionDocument, DocumentChunk
from app.db_models_documents import Document
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
    def _get_session(self) -> Generator[Session, None, None]:
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
                    DocumentChunk.document_id == CollectionDocument.document_id
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

    def link_document_to_collection(
        self,
        collection_id: str,
        document_id: str
    ) -> Optional[CollectionDocument]:
        """Link an existing canonical document to a collection.

        Creates a CollectionDocument join record. The document must already exist
        in the canonical documents table (created via DocumentRepository).

        Args:
            collection_id: Collection ID
            document_id: Canonical document ID (from documents table)

        Returns:
            CollectionDocument link object if successful, None on error
        """
        with self._get_session() as db:
            try:
                # Verify collection exists
                coll = db.query(Collection).filter(Collection.id == collection_id).first()
                if not coll:
                    logger.warning(
                        "Collection not found during document link",
                        extra={"collection_id": collection_id}
                    )
                    return None

                # Verify document exists
                doc = db.query(Document).filter(Document.id == document_id).first()
                if not doc:
                    logger.warning(
                        "Document not found during collection link",
                        extra={"document_id": document_id}
                    )
                    return None

                # Create link
                collection_doc = CollectionDocument(
                    collection_id=collection_id,
                    document_id=document_id
                )
                db.add(collection_doc)
                db.commit()
                db.refresh(collection_doc)

                # Recompute collection stats after adding document
                self.recompute_collection_stats(collection_id)

                logger.info(
                    "Linked document to collection",
                    extra={
                        "link_id": collection_doc.id,
                        "collection_id": collection_id,
                        "document_id": document_id,
                        "document_name": doc.filename
                    }
                )

                return collection_doc

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to link document to collection: {e}",
                    extra={"collection_id": collection_id, "document_id": document_id, "error": str(e)}
                )
                db.rollback()
                return None

    def unlink_document_from_collection(
        self,
        link_id: str
    ) -> bool:
        """Unlink a document from a collection.

        Deletes the CollectionDocument join record. The canonical document
        remains in the documents table.

        Args:
            link_id: CollectionDocument link ID

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                link = db.query(CollectionDocument).filter(
                    CollectionDocument.id == link_id
                ).first()

                if not link:
                    logger.warning(
                        f"Collection document link not found: {link_id}",
                        extra={"link_id": link_id}
                    )
                    return False

                collection_id = link.collection_id
                document_id = link.document_id

                db.delete(link)
                db.commit()

                logger.info(
                    "Unlinked document from collection",
                    extra={
                        "link_id": link_id,
                        "collection_id": collection_id,
                        "document_id": document_id
                    }
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to unlink document from collection: {e}",
                    extra={"link_id": link_id, "error": str(e)}
                )
                db.rollback()
                return False

    def remove_document_from_collection(
        self,
        collection_id: str,
        document_id: str
    ) -> bool:
        """Remove a document from a specific collection.

        Finds and deletes the CollectionDocument link between the collection
        and document. The document itself remains in the documents table and
        may still be linked to other collections.

        Args:
            collection_id: Collection ID
            document_id: Document ID

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                link = db.query(CollectionDocument).filter(
                    CollectionDocument.collection_id == collection_id,
                    CollectionDocument.document_id == document_id
                ).first()

                if not link:
                    logger.warning(
                        f"Document not found in collection",
                        extra={"collection_id": collection_id, "document_id": document_id}
                    )
                    return False

                db.delete(link)
                db.commit()

                # Recompute collection stats after removal
                self.recompute_collection_stats(collection_id)

                logger.info(
                    "Removed document from collection",
                    extra={
                        "collection_id": collection_id,
                        "document_id": document_id,
                        "link_id": link.id
                    }
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to remove document from collection: {e}",
                    extra={"collection_id": collection_id, "document_id": document_id, "error": str(e)}
                )
                db.rollback()
                return False

    def get_collection_document_link(
        self,
        link_id: str
    ) -> Optional[CollectionDocument]:
        """Get collection-document link by ID.

        Args:
            link_id: CollectionDocument link ID

        Returns:
            CollectionDocument link object if found, None otherwise
        """
        with self._get_session() as db:
            try:
                return db.query(CollectionDocument).filter(
                    CollectionDocument.id == link_id
                ).first()
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get collection document link: {e}",
                    extra={"link_id": link_id, "error": str(e)}
                )
                return None

    def list_documents(
        self,
        collection_id: str,
        limit: Optional[int] = None
    ) -> List[Document]:
        """List documents in a collection.

        Joins through collection_documents to get canonical document metadata.

        Args:
            collection_id: Collection ID
            limit: Optional limit on results

        Returns:
            List of Document objects (from canonical documents table)
        """
        with self._get_session() as db:
            try:
                query = (
                    db.query(Document)
                    .join(CollectionDocument, Document.id == CollectionDocument.document_id)
                    .filter(CollectionDocument.collection_id == collection_id)
                    .order_by(CollectionDocument.added_at.desc())
                )

                if limit:
                    query = query.limit(limit)

                return query.all()

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to list documents: {e}",
                    extra={"collection_id": collection_id, "error": str(e)}
                )
                return []

