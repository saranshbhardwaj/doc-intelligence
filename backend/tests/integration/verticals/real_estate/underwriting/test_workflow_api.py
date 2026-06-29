from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.database import get_db
from app.repositories.re_memo_repository import ReMemoRepository
from app.verticals.real_estate.api.underwriting import router as underwriting_router


@pytest.fixture
def memo_user(completed_run):
    return SimpleNamespace(
        id=completed_run.user_id,
        org_id="test-org-memo",
        tier="pro",
        allowed_verticals=["real_estate"],
    )


def _client(db_session, user):
    app = FastAPI()
    app.include_router(underwriting_router, prefix="/api/v1/re")
    app.dependency_overrides[get_current_user] = lambda: user

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def test_workflow_endpoint_returns_self_storage_state(db_session, completed_run, memo_user):
    client = _client(db_session, memo_user)

    resp = client.get(f"/api/v1/re/underwriting/runs/{completed_run.id}/workflow")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["workflow_key"] == "self_storage_acquisition_underwrite"
    assert [phase["id"] for phase in body["phases"]][:2] == ["intake", "extraction"]
    assert {gate["id"] for gate in body["gates"]} >= {"data_quality", "investment_screen", "memo_readiness"}


def test_workflow_endpoint_returns_404_for_unknown_run(db_session, memo_user):
    client = _client(db_session, memo_user)

    resp = client.get("/api/v1/re/underwriting/runs/does-not-exist/workflow")

    assert resp.status_code == 404


def test_workflow_endpoint_includes_active_memo_blocker(db_session, completed_run, memo_user):
    repo = ReMemoRepository(db_session)
    repo.create(completed_run.id, completed_run.user_id, {}, {}, None)
    client = _client(db_session, memo_user)

    resp = client.get(f"/api/v1/re/underwriting/runs/{completed_run.id}/workflow")

    assert resp.status_code == 200
    memo_gate = next(gate for gate in resp.json()["gates"] if gate["id"] == "memo_readiness")
    assert memo_gate["status"] == "blocked"
    assert resp.json()["memo_generation"]["allowed"] is False