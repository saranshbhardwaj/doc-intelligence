from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.database import get_db
from app.db_models_documents import Document


pytestmark = pytest.mark.integration


@pytest.fixture
def acq_user():
    return SimpleNamespace(
        id=str(uuid4()),
        org_id=str(uuid4()),
        tier="pro",
        allowed_verticals=["real_estate"],
    )


@pytest.fixture
def acq_api_client(db_session, acq_user):
    from app.verticals.real_estate.api.acquisitions import router as acquisitions_router
    from app.verticals.real_estate.api.underwriting import router as underwriting_router

    app = FastAPI()
    app.include_router(underwriting_router, prefix="/api/v1/re")
    app.include_router(acquisitions_router, prefix="/api/v1/re")
    app.dependency_overrides[get_current_user] = lambda: acq_user

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def _document(db_session, acq_user, *, filename="om.pdf", content_hash="hash-1", status="completed", chunk_count=3):
    doc = Document(
        user_id=acq_user.id,
        org_id=acq_user.org_id,
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


def _candidate(acq_api_client, **overrides):
    payload = {
        "name": "Tulsa Deal 169",
        "address": "1540 North Yale Avenue",
        "asset_class": "self_storage",
        "asset_class_confidence": 0.92,
        "source_type": "gmail",
        "source_name": "Broker email",
        "status": "needs_docs",
        "priority": "high",
        "facts": {"price": 2500000},
        "evidence": [{"label": "Self-storage language"}],
        "missing_items": ["rent_roll", "t12"],
    }
    payload.update(overrides)
    response = acq_api_client.post("/api/v1/re/acquisitions/candidates", json=payload)
    assert response.status_code == 200
    return response.json()


def test_create_list_and_get_candidate(acq_api_client):
    candidate = _candidate(acq_api_client)

    assert candidate["id"]
    assert candidate["name"] == "Tulsa Deal 169"
    assert candidate["documents"] == []

    response = acq_api_client.get("/api/v1/re/acquisitions/candidates")
    assert response.status_code == 200
    assert response.json()["candidates"][0]["id"] == candidate["id"]

    response = acq_api_client.get(f"/api/v1/re/acquisitions/candidates/{candidate['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == candidate["id"]


def test_attach_document_to_candidate(acq_api_client, db_session, acq_user):
    candidate = _candidate(acq_api_client)
    doc = _document(db_session, acq_user, filename="om.pdf", content_hash="api-om")

    response = acq_api_client.post(
        f"/api/v1/re/acquisitions/candidates/{candidate['id']}/documents",
        json={"document_id": doc.id, "doc_type": "om"},
    )

    assert response.status_code == 200
    data = response.json()
    attached = data["documents"][0]
    assert attached["document_id"] == doc.id
    assert attached["doc_type"] == "om"
    assert attached["filename"] == "om.pdf"
    assert attached["processing_status"] == "completed"
    assert attached["chunk_count"] == 3
    assert attached["has_embeddings"] is True
    assert "om" not in data["missing_items"]


def test_handoff_blocks_missing_om(acq_api_client):
    candidate = _candidate(acq_api_client)

    response = acq_api_client.post(
        f"/api/v1/re/acquisitions/candidates/{candidate['id']}/create-underwriting-run",
        json={"confirmed": True},
    )

    assert response.status_code == 422
    assert "Attach an indexed OM" in response.json()["detail"]


def test_handoff_blocks_processing_om(acq_api_client, db_session, acq_user):
    candidate = _candidate(acq_api_client)
    doc = _document(db_session, acq_user, filename="om.pdf", content_hash="processing-om", status="processing", chunk_count=0)
    acq_api_client.post(
        f"/api/v1/re/acquisitions/candidates/{candidate['id']}/documents",
        json={"document_id": doc.id, "doc_type": "om"},
    )

    response = acq_api_client.post(
        f"/api/v1/re/acquisitions/candidates/{candidate['id']}/create-underwriting-run",
        json={"confirmed": True},
    )

    assert response.status_code == 409
    assert "still processing" in response.json()["detail"]


def test_handoff_creates_underwriting_run(acq_api_client, db_session, acq_user):
    candidate = _candidate(acq_api_client)
    doc = _document(db_session, acq_user, filename="om.pdf", content_hash="ready-om")
    rent_roll = _document(db_session, acq_user, filename="rent-roll.xlsx", content_hash="ready-rr")
    t12 = _document(db_session, acq_user, filename="t12.xlsx", content_hash="ready-t12")
    acq_api_client.post(
        f"/api/v1/re/acquisitions/candidates/{candidate['id']}/documents",
        json={"document_id": doc.id, "doc_type": "om"},
    )
    acq_api_client.post(
        f"/api/v1/re/acquisitions/candidates/{candidate['id']}/documents",
        json={"document_id": rent_roll.id, "doc_type": "rent_roll"},
    )
    acq_api_client.post(
        f"/api/v1/re/acquisitions/candidates/{candidate['id']}/documents",
        json={"document_id": t12.id, "doc_type": "t12"},
    )

    response = acq_api_client.post(
        f"/api/v1/re/acquisitions/candidates/{candidate['id']}/create-underwriting-run",
        json={"confirmed": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"]
    assert data["status"] == "needs_review"
    assert data["extraction_job_id"] is None
    assert data["next_url"].endswith(f"run_id={data['run_id']}")

    run_response = acq_api_client.get(f"/api/v1/re/underwriting/runs/{data['run_id']}")
    assert run_response.status_code == 200
    run = run_response.json()
    assert run["status"] == "needs_review"
    assert {doc["doc_type"] for doc in run["document_ids"]} == {"om", "rent_roll", "t12"}