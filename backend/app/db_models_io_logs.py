"""SQLAlchemy model for LLM I/O log entries (opt-in capture for eval/debugging)."""
from sqlalchemy import Column, String, Text, Integer, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class LLMIOLog(Base):
    """
    Unified table for all LLM prompt/response captures across verticals.

    Populated only when CAPTURE_LLM_IO_LOG=true.
    Used exclusively for eval dataset export — not for production features.

    source_type values: 'template_fill' | 'rag_chat' | 'pe_workflow'
    """
    __tablename__ = "llm_io_logs"

    id = Column(String(36), primary_key=True)
    source_type = Column(String(50), nullable=False)   # 'template_fill' | 'rag_chat'
    source_id = Column(String(255), nullable=False)    # fill_run_id or chat_message_id
    stage = Column(String(100), nullable=False)        # 'extract_schema_fields', 'rag_chat', etc.
    prompt_version = Column(String(20), nullable=True)

    system_prompt = Column(Text, nullable=True)
    user_message = Column(Text, nullable=True)
    output = Column(Text, nullable=True)               # JSON string or freeform text

    metadata_ = Column("metadata", JSONB, nullable=True)  # stage-specific extras

    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cache_creation_tokens = Column(Integer, default=0)
    cache_read_tokens = Column(Integer, default=0)
    duration_ms = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_llm_io_logs_source", "source_type", "source_id"),
        Index("idx_llm_io_logs_stage", "stage"),
        Index("idx_llm_io_logs_created", "created_at"),
    )
