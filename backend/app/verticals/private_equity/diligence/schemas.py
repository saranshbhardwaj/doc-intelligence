"""Pydantic schemas for PE diligence API."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from typing import Literal

from pydantic import BaseModel, Field


class DiligenceRoomCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    target_company: Optional[str] = Field(default=None, max_length=255)
    notes: Optional[str] = None


class DiligenceRoomOut(BaseModel):
    id: str
    name: str
    target_company: Optional[str]
    status: str
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    documents_count: int = 0
    open_flags_count: int = 0
    checklist_completion_pct: float = 0.0

    class Config:
        from_attributes = True


class AttachRoomDocumentsRequest(BaseModel):
    document_ids: List[str] = Field(default_factory=list)


class RoomDocumentOut(BaseModel):
    id: str
    room_id: str
    document_id: Optional[str]
    filename: Optional[str] = None
    ingest_status: str
    job_id: Optional[str] = None
    progress_percent: Optional[int] = None
    status_detail: Optional[str] = None
    page_count: Optional[int] = None
    folder: Optional[str] = None
    document_type: Optional[str] = None
    classification_confidence: Optional[float] = None
    classification_needs_review: Optional[bool] = None
    classification_signals: List[str] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UploadRoomDocumentOut(BaseModel):
    document_id: str
    room_document_id: Optional[str] = None
    job_id: Optional[str] = None
    task_id: Optional[str] = None
    filename: str
    status: str
    reuse: bool = False
    attached: bool = True
    message: str
    ingest_status: Optional[str] = None
    document_type: Optional[str] = None
    classification_confidence: Optional[float] = None
    classification_needs_review: Optional[bool] = None
    classification_signals: List[str] = Field(default_factory=list)


class StartAnalysisRequest(BaseModel):
    force_reanalyze: bool = False
    incremental: bool = False


class AnalysisRunOut(BaseModel):
    id: str
    room_id: str
    status: str
    current_stage: Optional[str]
    progress_percent: int
    error_message: Optional[str]
    job_id: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    verification_total: int = 0
    verification_verified: int = 0
    verification_needs_review: int = 0
    document_classification_total: int = 0
    document_classification_needs_review: int = 0
    document_type_counts: Dict[str, int] = Field(default_factory=dict)
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class EvidenceSpanOut(BaseModel):
    id: str
    analysis_run_id: Optional[str]
    entity_type: str
    entity_id: str
    source_document_id: Optional[str]
    source_chunk_id: Optional[str]
    source_page_number: Optional[int]
    char_start: Optional[int]
    char_end: Optional[int]
    quote: str
    confidence: Optional[float]
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChecklistItemOut(BaseModel):
    id: str
    item_key: str
    title: str
    category: str
    priority: int
    required: bool
    status: str
    matched_document_id: Optional[str]
    matched_chunk_id: Optional[str]
    matched_page_number: Optional[int]
    evidence_quote: Optional[str]
    confidence: Optional[float]
    metadata: Optional[Dict[str, Any]] = None
    evidence_spans: List[EvidenceSpanOut] = Field(default_factory=list)

    class Config:
        from_attributes = True


class FindingOut(BaseModel):
    id: str
    analysis_run_id: Optional[str]
    category: str
    severity: str
    title: str
    description: str
    recommendation: Optional[str]
    status: str
    source_document_id: Optional[str]
    source_chunk_id: Optional[str]
    source_page_number: Optional[int]
    evidence_quote: Optional[str]
    confidence: Optional[float]
    metadata: Optional[Dict[str, Any]] = None
    evidence_spans: List[EvidenceSpanOut] = Field(default_factory=list)
    resolution_note: Optional[str]
    resolved_by_user_id: Optional[str]
    resolved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UpdateFindingRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=30)
    resolution_note: Optional[str] = None


class SummaryOut(BaseModel):
    id: str
    summary_type: str
    status: str
    content_markdown: Optional[str]
    citations: Optional[List[Dict[str, Any]]] = None
    confidence: Optional[float]
    overview: Optional[Dict[str, Any]] = None
    triage: Optional[Dict[str, Any]] = None
    coverage: Optional[Dict[str, Any]] = None
    top_risks: List[Dict[str, Any]] = Field(default_factory=list)
    contradictions: List[Dict[str, Any]] = Field(default_factory=list)
    valuation_signals: List[Dict[str, Any]] = Field(default_factory=list)
    deal_blockers: List[Dict[str, Any]] = Field(default_factory=list)
    management_questions: List[Dict[str, Any]] = Field(default_factory=list)
    follow_up_requests: List[Dict[str, Any]] = Field(default_factory=list)
    missing_key_documents: List[Dict[str, Any]] = Field(default_factory=list)
    document_gap_register: List[Dict[str, Any]] = Field(default_factory=list)
    ic_memo_inputs: Optional[Dict[str, Any]] = None
    ic_readiness: Optional[Dict[str, Any]] = None
    suggested_investigations: List[Dict[str, Any]] = Field(default_factory=list)
    data_quality_assessment: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    evidence_spans: List[EvidenceSpanOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UpdateAmendmentLinkRequest(BaseModel):
    parent_document_id: Optional[str] = None  # null to unlink
    amendment_type: Optional[str] = Field(default="modifies", max_length=30)


class UpdateFolderRequest(BaseModel):
    folder: Optional[str] = Field(default=None, max_length=120)


class ClauseOut(BaseModel):
    id: str
    room_id: str
    analysis_run_id: Optional[str]
    contract_family_id: Optional[str]
    source_document_id: Optional[str]
    source_chunk_id: Optional[str]
    source_page_number: Optional[int]
    clause_type: str
    playbook_id: Optional[str]
    extracted_fields: Optional[Dict[str, Any]] = None
    raw_quote: Optional[str]
    interpretation: Optional[str]
    confidence: Optional[float]
    engine: Optional[str]
    metadata: Optional[Dict[str, Any]] = None
    review_status: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    corrected_fields: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ClauseReviewIn(BaseModel):
    status: Literal["approved", "flagged", "edited", "pending"]
    corrected_fields: Optional[Dict[str, Any]] = None


class ContractFamilyOut(BaseModel):
    id: str
    room_id: str
    name: Optional[str]
    base_document_id: Optional[str]
    family_type: Optional[str]
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PlaybookOut(BaseModel):
    id: str
    slug: str
    title: str
    description: Optional[str]
    clause_types: Optional[List[str]] = None
    output_schema: Optional[Dict[str, Any]] = None
    is_system: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AuditEventOut(BaseModel):
    id: str
    analysis_run_id: Optional[str]
    actor_user_id: Optional[str]
    event_type: str
    entity_type: Optional[str]
    entity_id: Optional[str]
    payload: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class GenerateICMemoResponse(BaseModel):
    workflow_run_id: str
    job_id: Optional[str]
    message: str
