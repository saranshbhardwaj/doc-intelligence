"""Fixtures for underwriting API integration tests."""
import sys
import types
from uuid import uuid4
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.database import get_db
from app.repositories.re_underwriting_repo import UnderwritingRunRepository

try:
    import prometheus_client  # noqa: F401
except ModuleNotFoundError:
    # Local-test fallback: keep integration tests runnable without optional metrics deps.
    class _MetricStub:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            return None

        def observe(self, *args, **kwargs):
            return None

        def set(self, *args, **kwargs):
            return None

    prometheus_stub = types.ModuleType("prometheus_client")
    prometheus_stub.Counter = lambda *args, **kwargs: _MetricStub()
    prometheus_stub.Histogram = lambda *args, **kwargs: _MetricStub()
    sys.modules["prometheus_client"] = prometheus_stub

from app.verticals.real_estate.api.underwriting import router as underwriting_router


@pytest.fixture
def mock_user():
    """Minimal user with real_estate vertical access."""
    return SimpleNamespace(
        id=str(uuid4()),
        org_id=str(uuid4()),
        tier="pro",
        allowed_verticals=["real_estate"],
    )


@pytest.fixture
def api_client(db_session, mock_user):
    """TestClient with auth and DB overrides."""
    app = FastAPI()
    app.include_router(underwriting_router, prefix="/api/v1/re")

    app.dependency_overrides[get_current_user] = lambda: mock_user

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    client = TestClient(app)
    yield client

    # Cleanup
    app.dependency_overrides.clear()


@pytest.fixture
def run_factory(db_session, mock_user):
    """Factory to create UnderwritingRun rows directly in DB."""

    def _create(**overrides):
        repo = UnderwritingRunRepository(db_session)

        run = repo.create(
            user_id=mock_user.id,
            name=overrides.get("name", "Test Storage"),
            asset_type=overrides.get("asset_type", "self_storage"),
            address=overrides.get("address", None),
            document_ids=overrides.get("document_ids", []),
        )

        if "status" in overrides:
            repo.update_status(run.id, overrides["status"])

        if "inputs" in overrides:
            repo.update_inputs(run.id, mock_user.id, overrides["inputs"])

        if "result_artifact" in overrides:
            repo.update_result(
                run.id,
                overrides["result_artifact"],
                overrides.get("typed_metrics", {}),
            )

        db_session.refresh(run)
        return run

    return _create
