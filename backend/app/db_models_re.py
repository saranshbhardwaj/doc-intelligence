"""Database models for Real Estate AI Underwriting."""
from sqlalchemy import Column, String, DateTime, Text, Float, Index
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base
import uuid


class UnderwritingRun(Base):
    """A single RE underwriting analysis run for a deal."""

    __tablename__ = "re_underwriting_runs"
    __table_args__ = (
        Index("idx_re_uw_runs_user_id_created", "user_id", "created_at"),
        Index("idx_re_uw_runs_verdict_status", "user_id", "verdict_status"),
        Index("idx_re_uw_runs_extraction_job_id", "extraction_job_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)           # e.g. "3050 Orange Ave"
    asset_type = Column(String(50), nullable=False, default="self_storage")
    address = Column(String(500), nullable=True)

    # Source documents (list of {document_id, doc_type:"om"|"rent_roll"|"t12"})
    document_ids = Column(JSONB, nullable=True)

    # Wizard inputs after AI prefill + user edits (SelfStorageInputs Pydantic dump)
    inputs = Column(JSONB, nullable=True)

    # Per-field citations: {field_name: {doc_type, confidence, citations, source_text}}
    field_citations = Column(JSONB, nullable=True)

    # Citation token lookup: {"S1:p5": {page, filename, document_id, source_index}}
    citation_context = Column(JSONB, nullable=True)

    # Cross-doc discrepancies: [{field, sources:[{doc_id,value,page}], severity, note}]
    discrepancies = Column(JSONB, nullable=True)

    # Typed metric columns for fast dashboard queries
    irr = Column(Float, nullable=True)
    cash_on_cash = Column(Float, nullable=True)
    equity_multiple = Column(Float, nullable=True)
    dscr_year_one = Column(Float, nullable=True)
    ltv = Column(Float, nullable=True)
    cap_rate_year_one = Column(Float, nullable=True)
    cap_rate_pro_forma = Column(Float, nullable=True)
    noi_year_one = Column(Float, nullable=True)
    total_profit = Column(Float, nullable=True)
    monthly_cashflow = Column(Float, nullable=True)

    # Full calculation result (projections, capital structure, sensitivity, stress tests, rollover)
    result_artifact = Column(JSONB, nullable=True)

    # Verdict
    verdict_status = Column(String(20), nullable=True)   # "worth_pursuing" | "below_standards"
    verdict_failures = Column(JSONB, nullable=True)       # [{metric, target, actual, gap}]

    # Status lifecycle
    status = Column(String(30), nullable=False, default="extracting")
    # "extracting" | "needs_review" | "calculating" | "completed" | "failed"
    error_message = Column(Text, nullable=True)
    extraction_job_id = Column(String(100), nullable=True)

    # LOI per deal
    loi_inputs = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
