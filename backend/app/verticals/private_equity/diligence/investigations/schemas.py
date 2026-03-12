"""Pydantic schemas for PE diligence investigations."""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.verticals.private_equity.diligence.schemas import EvidenceSpanOut


class CreateInvestigationRequest(BaseModel):
    investigation_type: str = Field(..., min_length=1, max_length=80)
    title: Optional[str] = Field(default=None, max_length=255)
    question: Optional[str] = None


class InvestigationRunOut(BaseModel):
    id: str
    investigation_id: str
    room_id: str
    status: str
    current_stage: Optional[str]
    progress_percent: int
    error_message: Optional[str]
    metadata: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InvestigationClaimOut(BaseModel):
    id: str
    investigation_id: str
    run_id: Optional[str]
    claim_key: str
    claim_text: str
    status: str
    supersedes_claim_id: Optional[str]
    stance: str
    severity: str
    verification_status: str
    confidence: Optional[float]
    interpretation_confidence: Optional[float]
    coverage_score: Optional[float]
    source_workers: Optional[List[str]] = None
    confidence_history: Optional[List[float]] = None
    reason_codes: List[str] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None
    evidence_spans: List[EvidenceSpanOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InvestigationOut(BaseModel):
    id: str
    room_id: str
    investigation_type: str
    title: str
    question: Optional[str]
    status: str
    confidence: Optional[float]
    coverage_score: Optional[float]
    coverage_status: Optional[str]
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    latest_run: Optional[InvestigationRunOut] = None

    class Config:
        from_attributes = True


class InvestigationDetailOut(InvestigationOut):
    conclusion_markdown: Optional[str]
    claims: List[InvestigationClaimOut] = Field(default_factory=list)
    conclusion_evidence_spans: List[EvidenceSpanOut] = Field(default_factory=list)


class RerunInvestigationResponse(BaseModel):
    investigation: InvestigationOut
    run: InvestigationRunOut
    reused_running_run: bool = False


class CreateInvestigationResponse(BaseModel):
    investigation: InvestigationOut
    run: InvestigationRunOut
    reused_running_run: bool = False


class OverrideClaimRequest(BaseModel):
    verification_status: Literal["verified", "needs_review", "dismissed"]
    override_reason: Optional[str] = Field(default=None, max_length=500)
    reviewer_notes: Optional[str] = Field(default=None, max_length=2000)


class EvidenceSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=1000)
    document_ids: Optional[List[str]] = None
    top_k: int = Field(default=20, ge=1, le=50)


class EvidenceSearchResultOut(BaseModel):
    chunk_id: str
    document_id: str
    page_number: Optional[int]
    page_range: List[int] = Field(default_factory=list)
    quote: str
    hybrid_score: float
    bbox: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class EvidenceSearchResponse(BaseModel):
    query: str
    top_k: int
    results: List[EvidenceSearchResultOut] = Field(default_factory=list)

