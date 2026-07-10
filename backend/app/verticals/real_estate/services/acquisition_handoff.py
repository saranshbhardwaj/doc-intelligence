"""Create underwriting runs from acquisition candidates."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db_models_documents import Document
from app.repositories.re_acquisition_repository import AcquisitionCandidateRepository
from app.repositories.re_underwriting_repo import UnderwritingRunRepository


def _ready_document_map(db: Session, document_ids: list[str], org_id: str | None) -> dict[str, Document]:
    if not document_ids:
        return {}
    stmt = select(Document).where(Document.id.in_(document_ids))
    if org_id:
        stmt = stmt.where(Document.org_id == org_id)
    docs = list(db.execute(stmt).scalars())
    return {doc.id: doc for doc in docs}


def _active_candidate_documents(candidate) -> list:
    return [doc for doc in candidate.documents if doc.status == "attached"]


def create_underwriting_run_from_candidate(db: Session, candidate_id: str, user) -> dict:
    candidate_repo = AcquisitionCandidateRepository(db)
    candidate = candidate_repo.get(candidate_id, user.id)
    if not candidate:
        raise ValueError("Candidate not found")
    if candidate.asset_class != "self_storage":
        raise ValueError("Candidate is not self-storage")
    if candidate.underwriting_run_id:
        return {
            "candidate_id": candidate.id,
            "run_id": candidate.underwriting_run_id,
            "extraction_job_id": None,
            "status": "already_created",
            "next_url": f"/app/re/underwriting/new?run_id={candidate.underwriting_run_id}",
        }

    active_links = _active_candidate_documents(candidate)
    document_map = _ready_document_map(db, [link.document_id for link in active_links], getattr(user, "org_id", None))
    docs_by_type = {link.doc_type: document_map.get(link.document_id) for link in active_links}
    om_document = docs_by_type.get("om")
    if not om_document:
        raise ValueError("Attach an indexed OM document before creating an underwriting run")
    if not om_document.is_ready():
        raise ValueError("OM is still processing in Library")

    doc_specs = []
    for link in active_links:
        document = document_map.get(link.document_id)
        if not document or not document.is_ready():
            continue
        if link.doc_type not in {"om", "rent_roll", "t12"}:
            continue
        doc_specs.append({"document_id": link.document_id, "doc_type": link.doc_type})

    source_metadata = {
        "source": "acquisition_candidate",
        "acquisition_candidate_id": candidate.id,
        "candidate_source_type": candidate.source_type,
        "candidate_source_name": candidate.source_name,
        "asset_class_confidence": candidate.asset_class_confidence,
    }

    run_repo = UnderwritingRunRepository(db)
    run = run_repo.create(
        user_id=user.id,
        name=candidate.name,
        asset_type="self_storage",
        address=candidate.address,
        document_ids=doc_specs,
        source_metadata=source_metadata,
    )
    run_repo.update_status(run.id, "needs_review")
    candidate.underwriting_run_id = run.id
    candidate.status = "in_underwriting"
    db.commit()

    return {
        "candidate_id": candidate.id,
        "run_id": run.id,
        "extraction_job_id": None,
        "status": "needs_review",
        "next_url": f"/app/re/underwriting/new?run_id={run.id}",
    }