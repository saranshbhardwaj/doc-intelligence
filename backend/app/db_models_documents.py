"""Canonical Document model - single source of truth for all modes.

This model represents uploaded documents used across:
- Extract mode: Single document extraction
- Chat mode: Multi-document RAG in collections
- Workflow mode: Document processing workflows

Key features:
- Content-based deduplication via content_hash (SHA256)
- Single status tracking (processing, completed, failed)
- Chunks reference documents directly (not collection_documents)
"""
from sqlalchemy import Column, String, Integer, DateTime, Text, UniqueConstraint, Index, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import uuid


class Document(Base):
    """
    Canonical document table - single source of truth for ALL modes.

    Deduplication: Documents with same content_hash are reused (no re-upload).
    Used by: Extract, Chat (via collections), Workflows
    """
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("org_id", "content_hash", name="uq_documents_org_id_content_hash"),
        Index("idx_documents_org_id", "org_id"),
        Index("idx_documents_user_id", "user_id"),
        Index("idx_documents_content_hash", "content_hash"),
        Index("idx_documents_status", "status"),
    )

    # Primary key
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id = Column(String(64), nullable=False, index=True)  # Clerk org ID (tenant)
    user_id = Column(String(100), nullable=False, index=True)  # Clerk user ID

    # File metadata
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=True)
    file_size_bytes = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=False, unique=True)  # SHA256 for deduplication

    # Document metadata
    page_count = Column(Integer, nullable=False)
    chunk_count = Column(Integer, default=0)  # Total chunks created

    # Processing status
    status = Column(String(20), default="processing")  # processing, completed, failed
    error_message = Column(Text, nullable=True)

    # Processing metadata
    parser_used = Column(String(50), nullable=True)  # azure_document_intelligence, etc.
    processing_time_ms = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    collection_links = relationship("CollectionDocument", back_populates="document", cascade="all, delete-orphan")
    extractions = relationship("Extraction", back_populates="document", cascade="all, delete-orphan")

    def is_ready(self) -> bool:
        """Return True if document is ready for use (completed processing with chunks)."""
        return self.status == "completed" and self.chunk_count > 0
