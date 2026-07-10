"""Acquisition candidate API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.db_models_documents import Document
from app.db_models_users import User
from app.repositories.re_acquisition_repository import AcquisitionCandidateRepository
from app.verticals.real_estate.schemas.acquisitions import (
    AcquisitionCandidateCreate,
    AcquisitionCandidateUpdate,
    CandidateDocumentAttachRequest,
    CandidateHandoffRequest,
)
from app.verticals.real_estate.services.acquisition_handoff import create_underwriting_run_from_candidate

router = APIRouter(prefix="/acquisitions", tags=["re_acquisitions"])


def _document_payload(link) -> dict:
    document = getattr(link, "document", None)
    payload = {
        "id": link.id,
        "candidate_id": link.candidate_id,
        "document_id": link.document_id,
        "doc_type": link.doc_type,
        "status": link.status,
        "source": link.source,
    }
    if document:
        payload.update(
            {
                "filename": document.filename,
                "name": document.filename,
                "page_count": document.page_count,
                "chunk_count": document.chunk_count or 0,
                "processing_status": document.status,
                "has_embeddings": document.is_ready(),
            }
        )
    return payload


def _candidate_payload(candidate) -> dict:
    return {
        "id": candidate.id,
        "org_id": candidate.org_id,
        "user_id": candidate.user_id,
        "name": candidate.name,
        "address": candidate.address,
        "market": candidate.market,
        "asset_class": candidate.asset_class,
        "asset_class_confidence": candidate.asset_class_confidence,
        "source_type": candidate.source_type,
        "source_name": candidate.source_name,
        "source_status": candidate.source_status,
        "source_metadata": candidate.source_metadata or {},
        "status": candidate.status,
        "priority": candidate.priority,
        "readiness_score": candidate.readiness_score,
        "facts": candidate.facts or {},
        "evidence": candidate.evidence or [],
        "missing_items": candidate.missing_items or [],
        "underwriting_run_id": candidate.underwriting_run_id,
        "documents": [_document_payload(link) for link in candidate.documents if link.status == "attached"],
        "created_at": candidate.created_at,
        "updated_at": candidate.updated_at,
    }


def _get_document(db: Session, document_id: str, org_id: str | None) -> Document | None:
    query = db.query(Document).filter(Document.id == document_id)
    if org_id:
        query = query.filter(Document.org_id == org_id)
    return query.first()


@router.post("/candidates", response_model=dict)
def create_candidate(
    payload: AcquisitionCandidateCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = AcquisitionCandidateRepository(db)
    candidate = repo.create(
        user_id=user.id,
        org_id=getattr(user, "org_id", None),
        payload=payload.model_dump(),
    )
    return _candidate_payload(candidate)


@router.get("/candidates", response_model=dict)
def list_candidates(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    repo = AcquisitionCandidateRepository(db)
    return {
        "candidates": [_candidate_payload(candidate) for candidate in repo.list(user.id, limit=limit, offset=offset)],
    }


@router.get("/candidates/{candidate_id}", response_model=dict)
def get_candidate(
    candidate_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = AcquisitionCandidateRepository(db)
    candidate = repo.get(candidate_id, user.id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return _candidate_payload(candidate)


@router.patch("/candidates/{candidate_id}", response_model=dict)
def update_candidate(
    candidate_id: str,
    payload: AcquisitionCandidateUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = AcquisitionCandidateRepository(db)
    candidate = repo.update(candidate_id, user.id, payload.model_dump(exclude_unset=True))
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return _candidate_payload(candidate)


@router.post("/candidates/{candidate_id}/documents", response_model=dict)
def attach_candidate_document(
    candidate_id: str,
    payload: CandidateDocumentAttachRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _get_document(db, payload.document_id, getattr(user, "org_id", None)):
        raise HTTPException(status_code=404, detail="Document not found")
    repo = AcquisitionCandidateRepository(db)
    link = repo.attach_document(candidate_id, user.id, payload.document_id, payload.doc_type, payload.source)
    if not link:
        raise HTTPException(status_code=404, detail="Candidate not found")
    candidate = repo.get(candidate_id, user.id)
    return _candidate_payload(candidate)


@router.delete("/candidates/{candidate_id}/documents/{document_id}", response_model=dict)
def detach_candidate_document(
    candidate_id: str,
    document_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = AcquisitionCandidateRepository(db)
    if not repo.detach_document(candidate_id, user.id, document_id):
        raise HTTPException(status_code=404, detail="Candidate document link not found")
    candidate = repo.get(candidate_id, user.id)
    return _candidate_payload(candidate)


@router.post("/candidates/{candidate_id}/create-underwriting-run", response_model=dict)
def create_underwriting_from_candidate(
    candidate_id: str,
    payload: CandidateHandoffRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="Handoff confirmation is required")
    try:
        return create_underwriting_run_from_candidate(db, candidate_id, user)
    except ValueError as exc:
        message = str(exc)
        if message == "Candidate not found":
            raise HTTPException(status_code=404, detail=message)
        if "still processing" in message:
            raise HTTPException(status_code=409, detail=message)
        raise HTTPException(status_code=422, detail=message)