"""Fixtures for underwriting API integration tests."""
from uuid import uuid4
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.auth import get_current_user
from app.db import get_db
from app.repositories.re_underwriting_repo import UnderwritingRunRepository


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
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: db_session

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
