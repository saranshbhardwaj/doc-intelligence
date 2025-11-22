# backend/app/db_models.py
"""SQLAlchemy database models for Extract mode and job tracking"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, Text, ForeignKey, JSON, CheckConstraint, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base
import uuid


class Extraction(Base):
    """
    Extraction results for Extract mode.

    Links to canonical documents table for file metadata.
    Stores extraction-specific data (context, results, cache info).
    """
    __tablename__ = "extractions"
    __table_args__ = (
        Index("idx_extractions_user_id", "user_id"),
        Index("idx_extractions_document_id", "document_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(100), nullable=False, index=True)  # Clerk user ID

    # Snapshot of source document & parsing metadata (duplicated for fast access & historical audit)
    filename = Column(String(255), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    page_count = Column(Integer, nullable=True)  # May be null for legacy records until backfilled
    pdf_type = Column(String(20), nullable=True)  # 'digital' or 'scanned'
    parser_used = Column(String(50), nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)  # Parser cost (LLM extraction cost tracked separately)
    content_hash = Column(String(64), nullable=True, index=True)  # For duplicate detection & caching

    # Extraction-specific data
    context = Column(Text, nullable=True)  # User-provided context to guide extraction
    result = Column(JSONB, nullable=True)  # Extracted structured data (JSONB) - for small results or inline storage
    artifact = Column(JSONB, nullable=True)  # R2 pointer or inline artifact (same pattern as WorkflowRun)

    # Status lifecycle
    status = Column(String(20), nullable=False, default="processing")  # processing | completed | failed | queued
    error_message = Column(Text, nullable=True)

    # Cache/history flags
    from_cache = Column(Boolean, default=False)
    from_history = Column(Boolean, default=False)

    # Aggregated total cost (parser + LLM + storage, etc.)
    total_cost_usd = Column(Float, default=0.0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    document = relationship("Document", back_populates="extractions")


class ParserOutput(Base):
    """Store raw parser outputs for debugging and comparison"""
    __tablename__ = "parser_outputs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    extraction_id = Column(String(36), ForeignKey("extractions.id", ondelete="CASCADE"), nullable=False)

    parser_name = Column(String(50), nullable=False)
    parser_version = Column(String(20), nullable=True)
    pdf_type = Column(String(20))  # 'digital' or 'scanned'

    # Store the raw output from the parser (before LLM processing)
    raw_output = Column(JSONB, nullable=True)  # For PostgreSQL JSONB, SQLite JSON
    raw_output_length = Column(Integer)  # Character count

    processing_time_ms = Column(Integer)
    cost_usd = Column(Float, default=0.0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CacheEntry(Base):
    """Cache metadata (actual cache files stored on disk)"""
    __tablename__ = "cache_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    content_hash = Column(String(64), unique=True, nullable=False, index=True)  # SHA256

    file_path = Column(String(500), nullable=False)  # Path to JSON cache file
    original_filename = Column(String(255), nullable=False)
    page_count = Column(Integer, nullable=False)

    # Quick lookup fields (extracted from cache for queries)
    company_name = Column(String(255), nullable=True)
    industry = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_accessed_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    access_count = Column(Integer, default=0)


class JobState(Base):
    """
    Track real-time job progress through processing pipeline.

    Supports Extract Mode, Chat Mode, and Workflow Mode:
    - Extract Mode: extraction_id is set
    - Chat Mode: document_id is set (for chat indexing)
    - Workflow Mode: workflow_run_id is set

    A CHECK constraint ensures exactly one foreign key is set (XOR logic).
    """
    __tablename__ = "job_states"
    __table_args__ = (
        # Ensure exactly ONE of extraction_id, document_id, workflow_run_id is set
        CheckConstraint(
            '((extraction_id IS NOT NULL AND document_id IS NULL AND workflow_run_id IS NULL) OR '
            '(extraction_id IS NULL AND document_id IS NOT NULL AND workflow_run_id IS NULL) OR '
            '(extraction_id IS NULL AND document_id IS NULL AND workflow_run_id IS NOT NULL))',
            name='job_states_entity_exactly_one_fk_check'
        ),
        Index("idx_job_states_job_id", "job_id"),
        Index("idx_job_states_status", "status"),
        Index("idx_job_states_extraction_id", "extraction_id"),
        Index("idx_job_states_document_id", "document_id"),
        Index("idx_job_states_workflow_run_id", "workflow_run_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), unique=True, nullable=False)  # Job ID for tracking

    # Entity being processed (exactly one must be set)
    extraction_id = Column(String(36), ForeignKey("extractions.id", ondelete="CASCADE"), nullable=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    workflow_run_id = Column(String(36), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=True)

    # Current status
    status = Column(String(20), default="queued")  # queued, parsing, chunking, embedding, storing, completed, failed
    current_stage = Column(String(50), nullable=True)  # Detailed stage name
    progress_percent = Column(Integer, default=0)  # 0-100

    # Stage tracking flags (completed stages)
    parsing_completed = Column(Boolean, default=False)
    chunking_completed = Column(Boolean, default=False)
    summarizing_completed = Column(Boolean, default=False)
    extracting_completed = Column(Boolean, default=False)
    embedding_completed = Column(Boolean, default=False)
    storing_completed = Column(Boolean, default=False)

    # Workflow-specific stage flags
    context_completed = Column(Boolean, default=False)
    artifact_completed = Column(Boolean, default=False)
    validation_completed = Column(Boolean, default=False)

    # File paths for cached intermediate results (for resume capability)
    parsed_output_path = Column(String(500), nullable=True)
    chunks_path = Column(String(500), nullable=True)
    summaries_path = Column(String(500), nullable=True)
    combined_context_path = Column(String(500), nullable=True)

    # Error handling
    error_stage = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    error_type = Column(String(50), nullable=True)
    is_retryable = Column(Boolean, default=True)

    # Metadata
    message = Column(Text, nullable=True)  # Current user-facing message
    details = Column(JSONB, nullable=True)  # Additional details (stats, metrics, etc.)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
