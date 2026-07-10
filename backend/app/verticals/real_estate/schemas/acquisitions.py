from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DocType = Literal["om", "rent_roll", "t12", "photos", "other"]


class AcquisitionCandidateCreate(BaseModel):
    name: str = Field(min_length=1)
    address: str | None = None
    market: str | None = None
    asset_class: str = "self_storage"
    asset_class_confidence: float | None = None
    source_type: str = "manual"
    source_name: str | None = None
    source_status: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    status: str = "new"
    priority: str = "medium"
    readiness_score: int | None = None
    facts: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    missing_items: list[str] = Field(default_factory=list)


class AcquisitionCandidateUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    market: str | None = None
    status: str | None = None
    priority: str | None = None
    facts: dict[str, Any] | None = None
    evidence: list[dict[str, Any]] | None = None
    missing_items: list[str] | None = None


class CandidateDocumentAttachRequest(BaseModel):
    document_id: str
    doc_type: DocType
    source: str = "library"


class CandidateHandoffRequest(BaseModel):
    confirmed: bool = False