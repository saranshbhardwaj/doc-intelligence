"""Database models for Real Estate AI Underwriting."""
from sqlalchemy import Column, String, DateTime, Text, Float, ForeignKey, Index, Integer
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
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

    # Upstream provenance, e.g. acquisition candidate handoff metadata.
    source_metadata = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class AcquisitionCandidate(Base):
    """Upstream self-storage deal candidate before underwriting run creation."""

    __tablename__ = "re_acquisition_candidates"
    __table_args__ = (
        Index("idx_re_acq_candidates_user_status", "user_id", "status"),
        Index("idx_re_acq_candidates_org_created", "org_id", "created_at"),
        Index("idx_re_acq_candidates_run", "underwriting_run_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id = Column(String(64), nullable=True, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    address = Column(String(500), nullable=True)
    market = Column(String(255), nullable=True)
    asset_class = Column(String(50), nullable=False, default="self_storage")
    asset_class_confidence = Column(Float, nullable=True)
    source_type = Column(String(50), nullable=False, default="manual")
    source_name = Column(String(255), nullable=True)
    source_status = Column(String(50), nullable=True)
    source_metadata = Column(JSONB, nullable=False, default=dict)
    status = Column(String(50), nullable=False, default="new")
    priority = Column(String(20), nullable=False, default="medium")
    readiness_score = Column(Integer, nullable=True)
    facts = Column(JSONB, nullable=False, default=dict)
    evidence = Column(JSONB, nullable=False, default=list)
    missing_items = Column(JSONB, nullable=False, default=list)
    underwriting_run_id = Column(
        String(36),
        ForeignKey("re_underwriting_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    documents = relationship(
        "AcquisitionCandidateDocument",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    underwriting_run = relationship("UnderwritingRun")


class AcquisitionCandidateDocument(Base):
    """Library document assigned to a candidate underwriting document slot."""

    __tablename__ = "re_acquisition_candidate_documents"
    __table_args__ = (
        Index("idx_re_acq_candidate_docs_candidate", "candidate_id"),
        Index("idx_re_acq_candidate_docs_document", "document_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id = Column(
        String(36),
        ForeignKey("re_acquisition_candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    doc_type = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False, default="attached")
    source = Column(String(50), nullable=False, default="library")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    candidate = relationship("AcquisitionCandidate", back_populates="documents")
    document = relationship("Document")
