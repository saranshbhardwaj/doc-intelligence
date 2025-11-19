"""Repository for extraction-related database operations.

This is the Data Access Layer (DAL) for extractions

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
from app.db_models import Extraction, ParserOutput, CacheEntry
from app.utils.logging import logger


class ExtractionRepository:
    """Repository for extraction database operations.

    Encapsulates all database access for extractions, parser outputs,
    and cache entries. Provides clean interface for CRUD operations.

    Usage:
        # In dependencies.py:
        extraction_repo = ExtractionRepository()

        # In endpoints/services:
        extraction_repo.create_extraction(...)
        extraction_repo.update_status(...)
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

    def create_extraction(
        self,
        extraction_id: str,
        user_id: str,
        user_tier: str,
        filename: str,
        file_size_bytes: int,
        page_count: int,
        pdf_type: str,
        parser_used: str,
        processing_time_ms: int,
        cost_usd: float,
        from_cache: bool = False
    ) -> Optional[Extraction]:
        """Create new extraction record.

        Args:
            extraction_id: Unique ID for this extraction (usually UUID)
            user_id: User identifier (IP or authenticated user ID)
            user_tier: User subscription tier (free, pro, enterprise)
            filename: Original filename
            file_size_bytes: File size in bytes
            page_count: Number of pages in document
            pdf_type: Type of PDF (digital or scanned)
            parser_used: Parser name that processed this document
            processing_time_ms: Parser processing time in milliseconds
            cost_usd: Processing cost in USD
            from_cache: Whether result came from cache

        Returns:
            Extraction object if successful, None on error
        """
        with self._get_session() as db:
            try:
                extraction = Extraction(
                    id=extraction_id,
                    user_id=user_id,
                    user_tier=user_tier,
                    filename=filename,
                    file_size_bytes=file_size_bytes,
                    page_count=page_count,
                    pdf_type=pdf_type,
                    parser_used=parser_used,
                    processing_time_ms=processing_time_ms,
                    cost_usd=cost_usd,
                    status="processing",
                    from_cache=from_cache
                )
                db.add(extraction)
                db.commit()
                db.refresh(extraction)

                logger.debug(
                    f"Created extraction record: {extraction_id}",
                    extra={"extraction_id": extraction_id}
                )

                return extraction

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to create extraction: {e}",
                    extra={"extraction_id": extraction_id, "error": str(e)}
                )
                db.rollback()
                return None

    def create_parser_output(
        self,
        extraction_id: str,
        parser_name: str,
        parser_version: Optional[str],
        pdf_type: str,
        raw_output: dict,
        raw_output_length: int,
        processing_time_ms: int,
        cost_usd: float
    ) -> Optional[ParserOutput]:
        """Store raw parser output for debugging/comparison.

        Args:
            extraction_id: Foreign key to extraction record
            parser_name: Name of parser used
            parser_version: Parser version (optional)
            pdf_type: Type of PDF processed
            raw_output: Raw output from parser (truncated)
            raw_output_length: Full output character count
            processing_time_ms: Processing time in milliseconds
            cost_usd: Processing cost in USD

        Returns:
            ParserOutput object if successful, None on error
        """
        with self._get_session() as db:
            try:
                parser_output = ParserOutput(
                    extraction_id=extraction_id,
                    parser_name=parser_name,
                    parser_version=parser_version,
                    pdf_type=pdf_type,
                    raw_output=raw_output,
                    raw_output_length=raw_output_length,
                    processing_time_ms=processing_time_ms,
                    cost_usd=cost_usd
                )
                db.add(parser_output)
                db.commit()
                db.refresh(parser_output)

                logger.debug(
                    f"Stored parser output for extraction: {extraction_id}",
                    extra={"extraction_id": extraction_id, "parser": parser_name}
                )

                return parser_output

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to store parser output: {e}",
                    extra={"extraction_id": extraction_id, "error": str(e)}
                )
                db.rollback()
                return None

    def update_extraction(
        self,
        extraction_id: str,
        **kwargs
    ) -> bool:
        """Update extraction fields.

        Args:
            extraction_id: ID of extraction to update
            **kwargs: Fields to update (page_count, pdf_type, parser_used, etc.)

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                extraction = db.query(Extraction).filter(
                    Extraction.id == extraction_id
                ).first()

                if not extraction:
                    logger.warning(
                        f"Extraction not found for update: {extraction_id}",
                        extra={"extraction_id": extraction_id}
                    )
                    return False

                # Update provided fields
                for key, value in kwargs.items():
                    if hasattr(extraction, key) and value is not None:
                        setattr(extraction, key, value)

                db.commit()

                logger.debug(
                    f"Updated extraction fields: {list(kwargs.keys())}",
                    extra={"extraction_id": extraction_id}
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to update extraction: {e}",
                    extra={"extraction_id": extraction_id, "error": str(e)}
                )
                db.rollback()
                return False

    def update_status(
        self,
        extraction_id: str,
        status: str,
        error_message: Optional[str] = None
    ) -> bool:
        """Update extraction status.

        Args:
            extraction_id: ID of extraction to update
            status: New status (processing, completed, failed)
            error_message: Error message if status is failed

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                extraction = db.query(Extraction).filter(
                    Extraction.id == extraction_id
                ).first()

                if not extraction:
                    logger.warning(
                        f"Extraction not found for status update: {extraction_id}",
                        extra={"extraction_id": extraction_id}
                    )
                    return False

                extraction.status = status
                if error_message:
                    extraction.error_message = error_message[:500]  # Limit length

                if status == "completed":
                    extraction.completed_at = datetime.now()

                db.commit()

                logger.debug(
                    f"Updated extraction status to '{status}'",
                    extra={"extraction_id": extraction_id, "status": status}
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to update extraction status: {e}",
                    extra={"extraction_id": extraction_id, "error": str(e)}
                )
                db.rollback()
                return False

    def mark_completed(self, extraction_id: str) -> bool:
        """Mark extraction as completed.

        Convenience method for updating status to completed.

        Args:
            extraction_id: ID of extraction to mark as completed

        Returns:
            True if successful, False otherwise
        """
        return self.update_status(extraction_id, "completed")

    def mark_failed(
        self,
        extraction_id: str,
        error_message: str
    ) -> bool:
        """Mark extraction as failed with error message.

        Convenience method for updating status to failed.

        Args:
            extraction_id: ID of extraction to mark as failed
            error_message: Description of what went wrong

        Returns:
            True if successful, False otherwise
        """
        return self.update_status(extraction_id, "failed", error_message)

    def get_extraction(self, extraction_id: str) -> Optional[Extraction]:
        """Get extraction by ID.

        Args:
            extraction_id: ID of extraction to retrieve

        Returns:
            Extraction object if found, None otherwise
        """
        with self._get_session() as db:
            try:
                return db.query(Extraction).filter(
                    Extraction.id == extraction_id
                ).first()
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get extraction: {e}",
                    extra={"extraction_id": extraction_id, "error": str(e)}
                )
                return None

    def check_duplicate_extraction(
        self,
        user_id: str,
        content_hash: str
    ) -> Optional[Extraction]:
        """Check if user already has completed extraction for this document.

        Args:
            user_id: User ID
            content_hash: SHA256 hash of document content

        Returns:
            Existing completed extraction if found, None otherwise
        """
        with self._get_session() as db:
            try:
                return db.query(Extraction).filter(
                    Extraction.user_id == user_id,
                    Extraction.content_hash == content_hash,
                    Extraction.status == "completed"
                ).first()
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to check duplicate extraction: {e}",
                    extra={"user_id": user_id, "error": str(e)}
                )
                return None

    def create_extraction_from_document(
        self,
        extraction_id: str,
        document_id: str,
        user_id: str,
        context: Optional[str] = None,
        status: str = "processing"
    ) -> Optional[Extraction]:
        """Create extraction record linked to existing document.

        Args:
            extraction_id: Unique extraction ID
            document_id: Document ID (FK to documents table)
            user_id: User ID
            context: Optional user-provided context to guide extraction
            status: Status (processing, completed, failed)

        Returns:
            Extraction object if successful, None on error
        """
        with self._get_session() as db:
            try:
                extraction = Extraction(
                    id=extraction_id,
                    document_id=document_id,
                    user_id=user_id,
                    context=context,
                    status=status,
                    from_cache=False,
                    from_history=False
                )

                db.add(extraction)
                db.commit()
                db.refresh(extraction)

                logger.debug(
                    f"Created extraction record: {extraction_id}",
                    extra={"extraction_id": extraction_id, "document_id": document_id}
                )

                return extraction

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to create extraction record: {e}",
                    extra={"extraction_id": extraction_id, "error": str(e)}
                )
                db.rollback()
                return None

    def create_extraction_record(
        self,
        extraction_id: str,
        user_id: str,
        user_tier: str,
        filename: str,
        file_size_bytes: int,
        content_hash: str,
        status: str = "processing",
        page_count: int = 0,
        from_cache: bool = False,
        context: Optional[str] = None
    ) -> Optional[Extraction]:
        """Create basic extraction record (for initial creation or cache hits).

        Args:
            extraction_id: Unique extraction ID
            user_id: User ID
            user_tier: User tier
            filename: Original filename
            file_size_bytes: File size in bytes
            content_hash: SHA256 hash of content
            status: Status (processing or completed)
            page_count: Number of pages (default: 0)
            from_cache: Whether from cache (default: False)
            context: Optional user context

        Returns:
            Extraction object if successful, None on error
        """
        with self._get_session() as db:
            try:
                extraction = Extraction(
                    id=extraction_id,
                    user_id=user_id,
                    user_tier=user_tier,
                    filename=filename,
                    file_size_bytes=file_size_bytes,
                    page_count=page_count,
                    content_hash=content_hash,
                    status=status,
                    from_cache=from_cache,
                    context=context
                )

                # Set completed_at if status is completed
                if status == "completed":
                    extraction.completed_at = datetime.now()

                db.add(extraction)
                db.commit()
                db.refresh(extraction)

                logger.debug(
                    f"Created extraction record: {extraction_id}",
                    extra={"extraction_id": extraction_id, "status": status}
                )

                return extraction

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to create extraction record: {e}",
                    extra={"extraction_id": extraction_id, "error": str(e)}
                )
                db.rollback()
                return None

    def get_user_extractions(
        self,
        user_id: str,
        limit: int = 50
    ) -> List[Extraction]:
        """Get recent extractions for a user.

        Args:
            user_id: User identifier (IP or authenticated user ID)
            limit: Maximum number of results (default 50)

        Returns:
            List of Extraction objects, newest first
        """
        with self._get_session() as db:
            try:
                return db.query(Extraction).filter(
                    Extraction.user_id == user_id
                ).order_by(
                    Extraction.created_at.desc()
                ).limit(limit).all()
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get user extractions: {e}",
                    extra={"user_id": user_id, "error": str(e)}
                )
                return []

    def list_user_extractions(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None
    ) -> tuple[List[Extraction], int]:
        """List user extractions with pagination and filtering.

        Args:
            user_id: User identifier
            limit: Maximum number of results (default: 50)
            offset: Pagination offset (default: 0)
            status: Optional status filter (completed, processing, failed)

        Returns:
            Tuple of (extractions list, total count)
        """
        with self._get_session() as db:
            try:
                query = db.query(Extraction).filter(
                    Extraction.user_id == user_id
                )

                # Apply status filter if provided
                if status:
                    query = query.filter(Extraction.status == status)

                total = query.count()

                extractions = query.order_by(
                    Extraction.created_at.desc()
                ).limit(limit).offset(offset).all()

                return extractions, total

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to list user extractions: {e}",
                    extra={"user_id": user_id, "error": str(e)}
                )
                return [], 0

    def delete_extraction(
        self,
        extraction_id: str,
        user_id: str
    ) -> bool:
        """Delete an extraction (with ownership verification).

        Args:
            extraction_id: Extraction ID
            user_id: User ID (for ownership verification)

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                extraction = db.query(Extraction).filter(
                    Extraction.id == extraction_id
                ).first()

                if not extraction:
                    logger.warning(
                        f"Extraction not found for deletion: {extraction_id}",
                        extra={"extraction_id": extraction_id, "user_id": user_id}
                    )
                    return False

                # Verify ownership
                if extraction.user_id != user_id:
                    logger.warning(
                        f"User {user_id} attempted to delete extraction owned by {extraction.user_id}",
                        extra={"extraction_id": extraction_id, "user_id": user_id}
                    )
                    return False

                db.delete(extraction)
                db.commit()

                logger.info(
                    f"Deleted extraction: {extraction.filename}",
                    extra={"extraction_id": extraction_id, "user_id": user_id}
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to delete extraction: {e}",
                    extra={"extraction_id": extraction_id, "error": str(e)}
                )
                db.rollback()
                return False

    def get_extraction_stats(self, user_id: str) -> dict:
        """Get extraction statistics for a user.

        Args:
            user_id: User identifier

        Returns:
            Dictionary with stats (total_extractions, total_pages, etc.)
        """
        with self._get_session() as db:
            try:
                extractions = db.query(Extraction).filter(
                    Extraction.user_id == user_id
                ).all()

                return {
                    "total_extractions": len(extractions),
                    "total_pages": sum(e.page_count for e in extractions if e.page_count),
                    "total_cost_usd": sum(e.cost_usd for e in extractions if e.cost_usd),
                    "successful": len([e for e in extractions if e.status == "completed"]),
                    "failed": len([e for e in extractions if e.status == "failed"]),
                    "from_cache": len([e for e in extractions if e.from_cache])
                }
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get extraction stats: {e}",
                    extra={"user_id": user_id, "error": str(e)}
                )
                return {}

    def create_cache_entry(
        self,
        content_hash: str,
        file_path: str,
        original_filename: str,
        page_count: int,
        company_name: Optional[str] = None,
        industry: Optional[str] = None
    ) -> Optional[CacheEntry]:
        """Create cache entry record.

        Args:
            content_hash: SHA256 hash of file content
            file_path: Path to cached JSON file
            original_filename: Original filename
            page_count: Number of pages
            company_name: Extracted company name (optional)
            industry: Extracted industry (optional)

        Returns:
            CacheEntry object if successful, None on error
        """
        with self._get_session() as db:
            try:
                # Check if entry already exists
                existing = db.query(CacheEntry).filter(
                    CacheEntry.content_hash == content_hash
                ).first()

                if existing:
                    # Update last accessed
                    existing.last_accessed_at = datetime.now()
                    existing.access_count += 1
                    db.commit()
                    return existing

                # Create new entry
                cache_entry = CacheEntry(
                    content_hash=content_hash,
                    file_path=file_path,
                    original_filename=original_filename,
                    page_count=page_count,
                    company_name=company_name,
                    industry=industry
                )
                db.add(cache_entry)
                db.commit()
                db.refresh(cache_entry)

                logger.debug(
                    f"Created cache entry: {content_hash[:16]}...",
                    extra={"content_hash": content_hash}
                )

                return cache_entry

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to create cache entry: {e}",
                    extra={"content_hash": content_hash, "error": str(e)}
                )
                db.rollback()
                return None

    def update_extraction_artifact(
        self,
        extraction_id: str,
        artifact: dict,
        status: str = "completed",
        total_cost_usd: float = 0.0
    ) -> bool:
        """Update extraction with artifact and mark as completed.

        Args:
            extraction_id: Extraction ID
            artifact: Artifact JSON (R2 pointer or inline data)
            status: Status (default: completed)
            total_cost_usd: Total cost in USD

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                extraction = db.query(Extraction).filter(
                    Extraction.id == extraction_id
                ).first()

                if not extraction:
                    logger.warning(
                        f"Extraction not found for artifact update: {extraction_id}",
                        extra={"extraction_id": extraction_id}
                    )
                    return False

                extraction.artifact = artifact
                extraction.status = status
                extraction.total_cost_usd = total_cost_usd

                if status == "completed":
                    extraction.completed_at = datetime.now()

                db.commit()

                logger.info(
                    f"Updated extraction artifact: {extraction_id}",
                    extra={"extraction_id": extraction_id, "status": status}
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to update extraction artifact: {e}",
                    extra={"extraction_id": extraction_id, "error": str(e)}
                )
                db.rollback()
                return False

    def mark_extraction_failed(
        self,
        extraction_id: str,
        error_message: str
    ) -> bool:
        """Mark extraction as failed with error message.

        Args:
            extraction_id: Extraction ID
            error_message: Error description

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                extraction = db.query(Extraction).filter(
                    Extraction.id == extraction_id
                ).first()

                if not extraction:
                    return False

                extraction.status = "failed"
                extraction.error_message = error_message[:500]  # Limit length

                db.commit()

                logger.info(
                    f"Marked extraction as failed: {extraction_id}",
                    extra={"extraction_id": extraction_id}
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to mark extraction as failed: {e}",
                    extra={"extraction_id": extraction_id, "error": str(e)}
                )
                db.rollback()
                return False

    def check_duplicate_by_content_hash(
        self,
        content_hash: str,
        user_id: str,
        context: Optional[str] = None
    ) -> Optional[Extraction]:
        """Check if user already extracted this file with same context.

        Uses content_hash to detect duplicates across different documents.
        Duplicate = Same file content + Same context + Same user

        IMPORTANT: Scoped per user! Different users extracting the same file
        will each get their own extraction record and R2 artifact. This allows
        independent deletion and maintains user privacy.

        Args:
            content_hash: SHA256 hash of file content
            user_id: User ID (scopes duplicate check to this user only)
            context: Optional extraction context

        Returns:
            Existing completed extraction if found, None otherwise
        """
        with self._get_session() as db:
            try:
                from app.db_models_documents import Document

                # Join Extraction with Document to check content_hash
                query = db.query(Extraction).join(
                    Document, Extraction.document_id == Document.id
                ).filter(
                    Document.content_hash == content_hash,
                    Extraction.user_id == user_id,
                    Extraction.status == "completed"
                )

                # Match context (both None or both same string)
                if context is None:
                    query = query.filter(Extraction.context.is_(None))
                else:
                    query = query.filter(Extraction.context == context)

                return query.first()

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to check duplicate extraction: {e}",
                    extra={"content_hash": content_hash, "user_id": user_id, "error": str(e)}
                )
                return None

    def check_duplicate_by_document_id(
        self,
        document_id: str,
        user_id: str,
        context: Optional[str] = None
    ) -> Optional[Extraction]:
        """Check if user already extracted this specific document with same context.

        Used for EXISTING library documents (faster than content_hash join).
        Duplicate = Same document_id + Same context + Same user

        IMPORTANT: Scoped per user! Even if multiple users have the same document
        in their libraries, each user gets their own extraction record and R2 artifact.

        Args:
            document_id: Document ID (from library)
            user_id: User ID (scopes duplicate check to this user only)
            context: Optional extraction context

        Returns:
            Existing completed extraction if found, None otherwise
        """
        with self._get_session() as db:
            try:
                query = db.query(Extraction).filter(
                    Extraction.document_id == document_id,
                    Extraction.user_id == user_id,
                    Extraction.status == "completed"
                )

                # Match context (both None or both same string)
                if context is None:
                    query = query.filter(Extraction.context.is_(None))
                else:
                    query = query.filter(Extraction.context == context)

                return query.first()

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to check duplicate extraction: {e}",
                    extra={"document_id": document_id, "user_id": user_id, "error": str(e)}
                )
                return None
