"""SQLAlchemy model for generated underwriting credit memos."""
from __future__ import annotations

from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class UnderwritingMemo(Base):
    """One generated IC memo per (run, version)."""

    __tablename__ = "underwriting_memos"
    __table_args__ = (
        UniqueConstraint("run_id", "version", name="uq_underwriting_memos_run_version"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(
        String(36),
        ForeignKey("re_underwriting_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(String(100), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="pending")
    # pending | generating | complete | failed
    job_id = Column(String(36), nullable=True, index=True)
    r2_key = Column(String(500), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    cover_data = Column(JSONB, nullable=False, default=dict)
    sponsor_data = Column(JSONB, nullable=False, default=dict)
    market_notes = Column(Text, nullable=True)
    # Analyst-entered thesis & strategy inputs that shape narration:
    #   thesis_text, strategy_type, hold_period_years, verdict_override,
    #   verdict_override_reason, custom_conditions, sourcing_type, sourcing_detail
    thesis_data = Column(JSONB, nullable=False, default=dict)
    # System-side metadata: per-section usage totals, cost, duration. Populated
    # by the Celery task post-narration; never written by the analyst.
    # Named ``metadata_json`` because SQLAlchemy reserves ``metadata`` on the base.
    metadata_json = Column(JSONB, nullable=False, default=dict)
    section_warnings = Column(JSONB, nullable=False, default=list)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    run = relationship("UnderwritingRun", backref="memos")

    def __repr__(self) -> str:
        return (
            f"<UnderwritingMemo(id={self.id}, run_id={self.run_id}, "
            f"version={self.version}, status={self.status})>"
        )
