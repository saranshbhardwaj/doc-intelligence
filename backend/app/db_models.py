# backend/app/db_models.py
"""SQLAlchemy database models for Extract mode and job tracking"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, Text, ForeignKey, Index
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
        Index("idx_extractions_org_id", "org_id"),
        Index("idx_extractions_document_id", "document_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    org_id = Column(String(64), nullable=False, index=True)  # Clerk org ID (tenant)
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

    # LLM token tracking for observability (separate from parser cost)
    llm_input_tokens = Column(Integer, nullable=True)
    llm_output_tokens = Column(Integer, nullable=True)
    llm_model_name = Column(String(100), nullable=True)
    llm_cost_usd = Column(Float, nullable=True)

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

    Uses a polymorphic entity_type + entity_id pattern — extensible to any new
    entity type without schema migrations. Integrity enforced at application level.

    Supported entity_type values:
    - "extraction"        — PE extraction run
    - "document"          — Library document indexing
    - "workflow_run"      — PE workflow run
    - "template_fill_run" — RE template fill run
    - "analysis_run"      — PE diligence analysis run
    - "investigation_run" — PE diligence investigation run
    """
    __tablename__ = "job_states"
    __table_args__ = (
        Index("idx_job_states_job_id", "job_id"),
        Index("idx_job_states_status", "status"),
        Index("idx_job_states_entity", "entity_type", "entity_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), unique=True, nullable=False)  # Job ID for tracking

    # Polymorphic entity reference — no FK constraint, integrity enforced at app level
    entity_type = Column(String(50), nullable=False)  # e.g. "extraction", "document", "workflow_run"
    entity_id = Column(String(36), nullable=False)    # UUID of the referenced entity

    # Current status
    status = Column(String(20), default="queued")  # queued, parsing, chunking, embedding, storing, completed, failed
    current_stage = Column(String(50), nullable=True)  # Detailed stage name
    progress_percent = Column(Integer, default=0)  # 0-100

    # Stage tracking flags (completed stages)
    parsing_completed = Column(Boolean, default=False)
    chunking_completed = Column(Boolean, default=False)
    embedding_completed = Column(Boolean, default=False)
    storing_completed = Column(Boolean, default=False)

    # Workflow-specific stage flags
    context_completed = Column(Boolean, default=False)
    artifact_completed = Column(Boolean, default=False)

    # Template fill-specific stage flags
    field_detection_completed = Column(Boolean, default=False)
    auto_mapping_completed = Column(Boolean, default=False)
    data_extraction_completed = Column(Boolean, default=False)
    excel_filling_completed = Column(Boolean, default=False)

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


class AnthropicUsageSnapshot(Base):
    """Daily usage and cost snapshots from Anthropic Admin API.

    Stores ground-truth token usage and costs as reported by Anthropic's billing system.
    Used for cost reconciliation and validating internal tracking accuracy.
    """
    __tablename__ = "anthropic_usage_snapshots"
    __table_args__ = (
        Index("idx_anthropic_snapshots_date", "snapshot_date"),
        Index("idx_anthropic_snapshots_date_model", "snapshot_date", "model"),
        {"schema": None},  # Use default schema
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Time dimensions
    snapshot_date = Column(
        DateTime(timezone=False),  # Store as date (no timezone)
        nullable=False,
        index=True,
        comment="The date this snapshot covers (UTC)"
    )
    fetched_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When we fetched this data from Anthropic API"
    )

    # Model dimension
    model = Column(
        String(100),
        nullable=False,
        comment="Model name (e.g., claude-sonnet-4-5-20250929)"
    )

    # Usage data (from /usage_report/messages)
    input_tokens = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Input tokens (user messages + context)"
    )
    output_tokens = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Output tokens (assistant responses)"
    )
    cache_read_input_tokens = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Tokens read from prompt cache"
    )
    cache_creation_input_tokens = Column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Tokens written to prompt cache"
    )

    # Cost data (from /cost_report)
    cost_usd = Column(
        Float,
        nullable=False,
        server_default="0",
        comment="Cost in USD as reported by Anthropic"
    )

    # Raw API responses (for debugging/audit)
    raw_usage_response = Column(
        JSONB,
        nullable=True,
        comment="Raw usage API response for this snapshot"
    )
    raw_cost_response = Column(
        JSONB,
        nullable=True,
        comment="Raw cost API response for this snapshot"
    )


# Import template models to ensure they're registered with SQLAlchemy when JobState is used
# This prevents "failed to locate a name" errors in the worker
from app.db_models_templates import TemplateFillRun  # noqa: F401, E402
