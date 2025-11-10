# backend/app/db_models.py
"""SQLAlchemy database models"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, Text, ForeignKey, Date, JSON, CheckConstraint
from sqlalchemy.sql import func
from app.database import Base
import uuid


class Extraction(Base):
    """Track all extraction requests"""
    __tablename__ = "extractions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(100), nullable=True, index=True)  # Clerk user ID (nullable for migration from IP-based)
    user_tier = Column(String(20), default="free")  # free, standard, pro, admin

    filename = Column(String(255), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    page_count = Column(Integer, nullable=False)
    pdf_type = Column(String(20))  # 'digital' or 'scanned'
    context = Column(Text, nullable=True)  # Optional user-provided context to guide extraction
    content_hash = Column(String(64), nullable=True, index=True)  # SHA256 hash of file content for duplicate detection

    parser_used = Column(String(50))  # 'pymupdf', 'llmwhisperer', etc.
    processing_time_ms = Column(Integer)
    cost_usd = Column(Float, default=0.0)

    status = Column(String(20), default="processing")  # processing, completed, failed
    error_message = Column(Text, nullable=True)

    from_cache = Column(Boolean, default=False)
    cache_hit = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class ParserOutput(Base):
    """Store raw parser outputs for debugging and comparison"""
    __tablename__ = "parser_outputs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    extraction_id = Column(String(36), ForeignKey("extractions.id"), nullable=False)

    parser_name = Column(String(50), nullable=False)
    parser_version = Column(String(20), nullable=True)
    pdf_type = Column(String(20))  # 'digital' or 'scanned'

    # Store the raw output from the parser (before LLM processing)
    raw_output = Column(JSON, nullable=True)  # For PostgreSQL JSONB, SQLite JSON
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
    Track real-time job progress through extraction pipeline.

    Supports both Extract Mode and Chat Mode:
    - Extract Mode: extraction_id is set, collection_document_id is NULL
    - Chat Mode: collection_document_id is set, extraction_id is NULL

    A CHECK constraint ensures exactly one foreign key is set (XOR logic).
    """
    __tablename__ = "job_states"
    __table_args__ = (
        # Ensure exactly one of extraction_id or collection_document_id is set
        CheckConstraint(
            '(extraction_id IS NOT NULL AND collection_document_id IS NULL) OR '
            '(extraction_id IS NULL AND collection_document_id IS NOT NULL)',
            name='job_states_entity_xor_check'
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    extraction_id = Column(String(36), ForeignKey("extractions.id", ondelete="CASCADE"), nullable=True, index=True)
    collection_document_id = Column(String(36), ForeignKey("collection_documents.id", ondelete="CASCADE"), nullable=True, index=True)

    # Current status
    status = Column(String(20), default="queued")  # queued, parsing, chunking, summarizing, extracting, completed, failed
    current_stage = Column(String(50), nullable=True)  # Detailed stage name
    progress_percent = Column(Integer, default=0)  # 0-100

    # Stage tracking (completed stages)
    parsing_completed = Column(Boolean, default=False)
    chunking_completed = Column(Boolean, default=False)
    summarizing_completed = Column(Boolean, default=False)
    extracting_completed = Column(Boolean, default=False)

    # File paths for cached intermediate results (for resume capability)
    parsed_output_path = Column(String(500), nullable=True)  # Saved ParserOutput
    chunks_path = Column(String(500), nullable=True)  # Saved chunks JSON
    summaries_path = Column(String(500), nullable=True)  # Saved summaries JSON
    combined_context_path = Column(String(500), nullable=True)  # Saved combined context

    # Error handling
    error_stage = Column(String(50), nullable=True)  # Stage where error occurred
    error_message = Column(Text, nullable=True)
    error_type = Column(String(50), nullable=True)  # parsing_error, llm_error, validation_error, etc.
    is_retryable = Column(Boolean, default=True)

    # Metadata
    message = Column(Text, nullable=True)  # Current user-facing message
    details = Column(JSON, nullable=True)  # Additional details (stats, metrics, etc.)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)