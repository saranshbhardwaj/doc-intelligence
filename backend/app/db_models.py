# backend/app/db_models.py
"""SQLAlchemy database models"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, Text, ForeignKey, Date, JSON
from sqlalchemy.sql import func
from app.database import Base
import uuid


class Extraction(Base):
    """Track all extraction requests"""
    __tablename__ = "extractions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(100), nullable=False)  # IP address or authenticated user ID
    user_tier = Column(String(20), default="free")  # free, pro, enterprise

    filename = Column(String(255), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    page_count = Column(Integer, nullable=False)
    pdf_type = Column(String(20))  # 'digital' or 'scanned'

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
    """Track real-time job progress through extraction pipeline"""
    __tablename__ = "job_states"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    extraction_id = Column(String(36), ForeignKey("extractions.id"), nullable=False, index=True)

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


class RateLimit(Base):
    """Rate limiting per user/IP with customizable limits"""
    __tablename__ = "rate_limits"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    identifier = Column(String(100), nullable=False, unique=True, index=True)  # IP or user_id
    identifier_type = Column(String(20), default="ip")  # 'ip' or 'user'

    tier = Column(String(20), default="free")  # free, pro, enterprise

    # Limits
    daily_limit = Column(Integer, default=2)
    monthly_limit = Column(Integer, default=60)

    # Current counts
    current_daily_count = Column(Integer, default=0)
    current_monthly_count = Column(Integer, default=0)

    # Reset tracking
    last_daily_reset = Column(Date, default=func.current_date())
    last_monthly_reset = Column(Date, default=func.current_date())

    # Custom notes (e.g., "Beta tester - unlimited")
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
