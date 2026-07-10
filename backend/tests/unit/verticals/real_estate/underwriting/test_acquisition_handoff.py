from types import SimpleNamespace

import pytest

from app.db_models_documents import Document
from app.repositories.re_acquisition_repository import AcquisitionCandidateRepository
from app.repositories.re_underwriting_repo import UnderwritingRunRepository
from app.verticals.real_estate.services.acquisition_handoff import create_underwriting_run_from_candidate


def _user():
    return SimpleNamespace(id="user-1", org_id="org-1")


def _document(db_session, *, filename="om.pdf", content_hash="hash-1", status="completed", chunk_count=3):
    doc = Document(
        user_id="user-1",
        org_id="org-1",
        filename=filename,
        file_path=f"/tmp/{filename}",
        file_size_bytes=1024,
        content_hash=content_hash,
        page_count=10,
        status=status,
        chunk_count=chunk_count,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


def _candidate(db_session, **payload_overrides):
    payload = {
        "name": "Tulsa Deal 169",
        "address": "1540 North Yale Avenue",
        "asset_class": "self_storage",
        "asset_class_confidence": 0.92,
        "source_type": "gmail",
        "source_name": "Broker email",
        "status": "ready_to_underwrite",
        "facts": {"price": 2500000},
    }
    payload.update(payload_overrides)
    return AcquisitionCandidateRepository(db_session).create("user-1", "org-1", payload)


def test_handoff_rejects_non_self_storage_candidate(db_session):
    candidate = _candidate(db_session, asset_class="retail")

    with pytest.raises(ValueError, match="not self-storage"):
        create_underwriting_run_from_candidate(db_session, candidate.id, _user())


def test_handoff_rejects_missing_om(db_session):
    candidate = _candidate(db_session)

    with pytest.raises(ValueError, match="Attach an indexed OM"):
        create_underwriting_run_from_candidate(db_session, candidate.id, _user())


def test_handoff_rejects_processing_om(db_session):
    candidate = _candidate(db_session)
    processing_om = _document(db_session, status="processing", chunk_count=0)
    AcquisitionCandidateRepository(db_session).attach_document(candidate.id, "user-1", processing_om.id, "om")

    with pytest.raises(ValueError, match="still processing"):
        create_underwriting_run_from_candidate(db_session, candidate.id, _user())


def test_handoff_creates_underwriting_run_with_ready_documents(db_session):
    candidate = _candidate(db_session)
    om = _document(db_session, filename="om.pdf", content_hash="om")
    rent_roll = _document(db_session, filename="rent-roll.xlsx", content_hash="rr")
    t12 = _document(db_session, filename="t12.xlsx", content_hash="t12")
    repo = AcquisitionCandidateRepository(db_session)
    repo.attach_document(candidate.id, "user-1", om.id, "om")
    repo.attach_document(candidate.id, "user-1", rent_roll.id, "rent_roll")
    repo.attach_document(candidate.id, "user-1", t12.id, "t12")

    result = create_underwriting_run_from_candidate(db_session, candidate.id, _user())

    assert result["candidate_id"] == candidate.id
    assert result["run_id"]
    assert result["status"] == "needs_review"
    assert result["extraction_job_id"] is None
    assert result["next_url"].endswith(f"run_id={result['run_id']}")

    run = UnderwritingRunRepository(db_session).get(result["run_id"], "user-1")
    assert run.name == "Tulsa Deal 169"
    assert run.status == "needs_review"
    assert run.extraction_job_id is None
    assert run.source_metadata["source"] == "acquisition_candidate"
    assert run.source_metadata["acquisition_candidate_id"] == candidate.id
    assert {doc["doc_type"] for doc in run.document_ids} == {"om", "rent_roll", "t12"}

    hydrated = repo.get(candidate.id, "user-1")
    assert hydrated.status == "in_underwriting"
    assert hydrated.underwriting_run_id == run.id


def test_handoff_returns_existing_run_when_candidate_already_promoted(db_session):
    candidate = _candidate(db_session)
    run = UnderwritingRunRepository(db_session).create(
        user_id="user-1",
        name="Existing Run",
        asset_type="self_storage",
        address="123 Main",
        document_ids=[],
    )
    candidate.underwriting_run_id = run.id
    candidate.status = "in_underwriting"
    db_session.commit()

    result = create_underwriting_run_from_candidate(db_session, candidate.id, _user())

    assert result["run_id"] == run.id
    assert result["status"] == "already_created"