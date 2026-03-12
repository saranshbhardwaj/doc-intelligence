"""Database models for Private Equity diligence workflows."""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
import uuid


class PEDiligenceRoom(Base):
    __tablename__ = "pe_diligence_rooms"
    __table_args__ = (
        Index("idx_pe_diligence_rooms_org_id", "org_id"),
        Index("idx_pe_diligence_rooms_user_id", "user_id"),
        Index("idx_pe_diligence_rooms_status", "status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)

    name = Column(String(255), nullable=False)
    target_company = Column(String(255), nullable=True)
    status = Column(String(30), nullable=False, default="draft")
    notes = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_analyzed_at = Column(DateTime(timezone=True), nullable=True)

    documents = relationship("PEDiligenceRoomDocument", back_populates="room", cascade="all, delete-orphan")
    analysis_runs = relationship("PEDiligenceAnalysisRun", back_populates="room", cascade="all, delete-orphan")
    checklist_items = relationship("PEDiligenceChecklistItem", back_populates="room", cascade="all, delete-orphan")
    findings = relationship("PEDiligenceFinding", back_populates="room", cascade="all, delete-orphan")
    summaries = relationship("PEDiligenceSummary", back_populates="room", cascade="all, delete-orphan")
    evidence_spans = relationship("PEDiligenceEvidenceSpan", back_populates="room", cascade="all, delete-orphan")
    investigations = relationship("PEDiligenceInvestigation", back_populates="room", cascade="all, delete-orphan")
    investigation_runs = relationship("PEDiligenceInvestigationRun", back_populates="room", cascade="all, delete-orphan")
    investigation_claims = relationship("PEDiligenceInvestigationClaim", back_populates="room", cascade="all, delete-orphan")
    audit_events = relationship("PEDiligenceAuditEvent", back_populates="room", cascade="all, delete-orphan")


class PEDiligenceRoomDocument(Base):
    __tablename__ = "pe_diligence_room_documents"
    __table_args__ = (
        UniqueConstraint(
            "room_id",
            "document_id",
            name="uq_pe_diligence_room_documents_room_document",
        ),
        Index("idx_pe_diligence_room_documents_room_id", "room_id"),
        Index("idx_pe_diligence_room_documents_document_id", "document_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id = Column(String(36), ForeignKey("pe_diligence_rooms.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    ingest_status = Column(String(30), nullable=False, default="linked")
    folder = Column(String(120), nullable=True, index=True)
    metadata_json = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    room = relationship("PEDiligenceRoom", back_populates="documents")
    document = relationship("Document")


class PEDiligenceAnalysisRun(Base):
    __tablename__ = "pe_diligence_analysis_runs"
    __table_args__ = (
        Index("idx_pe_diligence_analysis_runs_room_id", "room_id"),
        Index("idx_pe_diligence_analysis_runs_status", "status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id = Column(String(36), ForeignKey("pe_diligence_rooms.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)

    status = Column(String(30), nullable=False, default="queued")
    current_stage = Column(String(50), nullable=True)
    progress_percent = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=True)

    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    room = relationship("PEDiligenceRoom", back_populates="analysis_runs")


class PEDiligenceChecklistItem(Base):
    __tablename__ = "pe_diligence_checklist_items"
    __table_args__ = (
        UniqueConstraint(
            "room_id",
            "item_key",
            name="uq_pe_diligence_checklist_items_room_item_key",
        ),
        Index("idx_pe_diligence_checklist_items_room_id", "room_id"),
        Index("idx_pe_diligence_checklist_items_status", "status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id = Column(String(36), ForeignKey("pe_diligence_rooms.id", ondelete="CASCADE"), nullable=False)
    item_key = Column(String(120), nullable=False)
    title = Column(String(255), nullable=False)
    category = Column(String(120), nullable=False)
    priority = Column(Integer, nullable=False, default=3)
    required = Column(Boolean, nullable=False, default=True)
    status = Column(String(30), nullable=False, default="missing")

    matched_document_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    matched_chunk_id = Column(String(120), nullable=True)
    matched_page_number = Column(Integer, nullable=True)
    evidence_quote = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    room = relationship("PEDiligenceRoom", back_populates="checklist_items")
    matched_document = relationship("Document")


class PEDiligenceFinding(Base):
    __tablename__ = "pe_diligence_findings"
    __table_args__ = (
        Index("idx_pe_diligence_findings_room_id", "room_id"),
        Index("idx_pe_diligence_findings_status", "status"),
        Index("idx_pe_diligence_findings_severity", "severity"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id = Column(String(36), ForeignKey("pe_diligence_rooms.id", ondelete="CASCADE"), nullable=False)
    analysis_run_id = Column(String(36), ForeignKey("pe_diligence_analysis_runs.id", ondelete="SET NULL"), nullable=True)

    category = Column(String(120), nullable=False)
    severity = Column(String(20), nullable=False, default="medium")
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="open")

    source_document_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    source_chunk_id = Column(String(120), nullable=True)
    source_page_number = Column(Integer, nullable=True)
    evidence_quote = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=True)

    resolution_note = Column(Text, nullable=True)
    resolved_by_user_id = Column(String(100), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    room = relationship("PEDiligenceRoom", back_populates="findings")
    source_document = relationship("Document")


class PEDiligenceSummary(Base):
    __tablename__ = "pe_diligence_summaries"
    __table_args__ = (
        UniqueConstraint(
            "room_id",
            "summary_type",
            name="uq_pe_diligence_summaries_room_summary_type",
        ),
        Index("idx_pe_diligence_summaries_room_id", "room_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id = Column(String(36), ForeignKey("pe_diligence_rooms.id", ondelete="CASCADE"), nullable=False)
    analysis_run_id = Column(String(36), ForeignKey("pe_diligence_analysis_runs.id", ondelete="SET NULL"), nullable=True)

    summary_type = Column(String(50), nullable=False, default="diligence_overview")
    status = Column(String(30), nullable=False, default="draft")
    content_markdown = Column(Text, nullable=True)
    citations = Column(JSONB, nullable=True)
    confidence = Column(Float, nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=True)

    created_by_user_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    room = relationship("PEDiligenceRoom", back_populates="summaries")


class PEDiligenceEvidenceSpan(Base):
    __tablename__ = "pe_diligence_evidence_spans"
    __table_args__ = (
        Index("idx_pe_diligence_evidence_spans_room_id", "room_id"),
        Index("idx_pe_diligence_evidence_spans_run_id", "analysis_run_id"),
        Index("idx_pe_diligence_evidence_spans_entity", "entity_type", "entity_id"),
        Index("idx_pe_diligence_evidence_spans_document", "source_document_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id = Column(String(36), ForeignKey("pe_diligence_rooms.id", ondelete="CASCADE"), nullable=False)
    analysis_run_id = Column(String(36), ForeignKey("pe_diligence_analysis_runs.id", ondelete="SET NULL"), nullable=True)

    entity_type = Column(String(40), nullable=False)  # checklist_item | finding | summary
    entity_id = Column(String(80), nullable=False)

    source_document_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    source_chunk_id = Column(String(120), nullable=True)
    source_page_number = Column(Integer, nullable=True)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)
    quote = Column(Text, nullable=False)
    confidence = Column(Float, nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    room = relationship("PEDiligenceRoom", back_populates="evidence_spans")
    source_document = relationship("Document")


class PEDiligenceInvestigation(Base):
    __tablename__ = "pe_diligence_investigations"
    __table_args__ = (
        Index("idx_pe_diligence_investigations_room_id", "room_id"),
        Index("idx_pe_diligence_investigations_status", "status"),
        Index("idx_pe_diligence_investigations_type", "investigation_type"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id = Column(String(36), ForeignKey("pe_diligence_rooms.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)

    investigation_type = Column(String(80), nullable=False)
    title = Column(String(255), nullable=False)
    question = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="queued")
    conclusion_markdown = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    coverage_score = Column(Float, nullable=True)
    coverage_status = Column(String(30), nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    room = relationship("PEDiligenceRoom", back_populates="investigations")
    runs = relationship("PEDiligenceInvestigationRun", back_populates="investigation", cascade="all, delete-orphan")
    claims = relationship("PEDiligenceInvestigationClaim", back_populates="investigation", cascade="all, delete-orphan")


class PEDiligenceInvestigationRun(Base):
    __tablename__ = "pe_diligence_investigation_runs"
    __table_args__ = (
        Index("idx_pe_diligence_investigation_runs_investigation_id", "investigation_id"),
        Index("idx_pe_diligence_investigation_runs_room_id", "room_id"),
        Index("idx_pe_diligence_investigation_runs_status", "status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    investigation_id = Column(String(36), ForeignKey("pe_diligence_investigations.id", ondelete="CASCADE"), nullable=False)
    room_id = Column(String(36), ForeignKey("pe_diligence_rooms.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)

    status = Column(String(30), nullable=False, default="queued")
    current_stage = Column(String(50), nullable=True)
    progress_percent = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=True)

    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    investigation = relationship("PEDiligenceInvestigation", back_populates="runs")
    room = relationship("PEDiligenceRoom", back_populates="investigation_runs")
    claims = relationship("PEDiligenceInvestigationClaim", back_populates="run", cascade="all, delete-orphan")


class PEDiligenceInvestigationClaim(Base):
    __tablename__ = "pe_diligence_investigation_claims"
    __table_args__ = (
        Index("idx_pe_diligence_investigation_claims_investigation_id", "investigation_id"),
        Index("idx_pe_diligence_investigation_claims_room_id", "room_id"),
        Index("idx_pe_diligence_investigation_claims_run_id", "run_id"),
        Index("idx_pe_diligence_investigation_claims_status", "status"),
        Index("idx_pe_diligence_investigation_claims_verification_status", "verification_status"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    investigation_id = Column(String(36), ForeignKey("pe_diligence_investigations.id", ondelete="CASCADE"), nullable=False)
    run_id = Column(String(36), ForeignKey("pe_diligence_investigation_runs.id", ondelete="SET NULL"), nullable=True)
    room_id = Column(String(36), ForeignKey("pe_diligence_rooms.id", ondelete="CASCADE"), nullable=False)

    claim_key = Column(String(120), nullable=False)
    claim_text = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="proposed")
    supersedes_claim_id = Column(String(36), nullable=True)
    stance = Column(String(30), nullable=False, default="inconclusive")
    severity = Column(String(20), nullable=False, default="medium")
    verification_status = Column(String(30), nullable=False, default="needs_review")
    confidence = Column(Float, nullable=True)
    interpretation_confidence = Column(Float, nullable=True)
    coverage_score = Column(Float, nullable=True)
    source_workers = Column(JSONB, nullable=True)
    confidence_history = Column(JSONB, nullable=True)
    metadata_json = Column("metadata", JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    investigation = relationship("PEDiligenceInvestigation", back_populates="claims")
    run = relationship("PEDiligenceInvestigationRun", back_populates="claims")
    room = relationship("PEDiligenceRoom", back_populates="investigation_claims")


class PEDiligenceAuditEvent(Base):
    __tablename__ = "pe_diligence_audit_events"
    __table_args__ = (
        Index("idx_pe_diligence_audit_events_room_id", "room_id"),
        Index("idx_pe_diligence_audit_events_run_id", "analysis_run_id"),
        Index("idx_pe_diligence_audit_events_event_type", "event_type"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id = Column(String(36), ForeignKey("pe_diligence_rooms.id", ondelete="CASCADE"), nullable=False)
    analysis_run_id = Column(String(36), ForeignKey("pe_diligence_analysis_runs.id", ondelete="SET NULL"), nullable=True)
    actor_user_id = Column(String(100), nullable=True)
    event_type = Column(String(80), nullable=False)
    entity_type = Column(String(80), nullable=True)
    entity_id = Column(String(80), nullable=True)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    room = relationship("PEDiligenceRoom", back_populates="audit_events")


# ─── Contract Families, Clauses, Playbooks ────────────────────────────────────


class PEDiligenceContractFamily(Base):
    """Groups a base document + its amendments into a logical contract unit."""
    __tablename__ = "pe_diligence_contract_families"
    __table_args__ = (
        Index("idx_pe_diligence_contract_families_room_id", "room_id"),
        Index("idx_pe_diligence_contract_families_base_doc", "base_document_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id = Column(String(36), ForeignKey("pe_diligence_rooms.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=True)
    base_document_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    family_type = Column(String(80), nullable=True)  # customer_contract, debt_facility, sha, etc.
    metadata_json = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    room = relationship("PEDiligenceRoom")
    base_document = relationship("Document")


class PEDiligenceClause(Base):
    """Structured clause extraction — one row per clause found in a document."""
    __tablename__ = "pe_diligence_clauses"
    __table_args__ = (
        Index("idx_pe_diligence_clauses_room_id", "room_id"),
        Index("idx_pe_diligence_clauses_run_id", "analysis_run_id"),
        Index("idx_pe_diligence_clauses_type", "clause_type"),
        Index("idx_pe_diligence_clauses_document", "source_document_id"),
        Index("idx_pe_diligence_clauses_family", "contract_family_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    room_id = Column(String(36), ForeignKey("pe_diligence_rooms.id", ondelete="CASCADE"), nullable=False)
    analysis_run_id = Column(String(36), ForeignKey("pe_diligence_analysis_runs.id", ondelete="SET NULL"), nullable=True)
    contract_family_id = Column(String(36), ForeignKey("pe_diligence_contract_families.id", ondelete="SET NULL"), nullable=True)

    source_document_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    source_chunk_id = Column(String(120), nullable=True)
    source_page_number = Column(Integer, nullable=True)

    clause_type = Column(String(80), nullable=False)
    playbook_id = Column(String(80), nullable=True)

    # Structured extraction fields (LLM output)
    extracted_fields = Column(JSONB, nullable=True)
    raw_quote = Column(Text, nullable=True)
    interpretation = Column(Text, nullable=True)

    confidence = Column(Float, nullable=True)
    engine = Column(String(50), nullable=True)  # "regex_v1" or "llm_v1"
    metadata_json = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    room = relationship("PEDiligenceRoom")
    source_document = relationship("Document")
    contract_family = relationship("PEDiligenceContractFamily")


class PEDiligencePlaybook(Base):
    """Reusable investigation playbook defining clause types to extract."""
    __tablename__ = "pe_diligence_playbooks"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_pe_diligence_playbooks_slug"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug = Column(String(80), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    clause_types = Column(JSONB, nullable=True)  # ["change_of_control", "assignment_consent", ...]
    prompt_template = Column(Text, nullable=True)
    output_schema = Column(JSONB, nullable=True)
    is_system = Column(Boolean, nullable=False, default=True)
    metadata_json = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
