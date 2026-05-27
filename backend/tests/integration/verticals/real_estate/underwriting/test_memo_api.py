"""API integration tests for the credit memo endpoints.

Tests cover: create memo, list memos, and download memo.
Uses the same TestClient + dependency-override pattern as the underwriting API tests.
"""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

try:
    import prometheus_client  # noqa: F401
except ModuleNotFoundError:
    class _MetricStub:
        def labels(self, *a, **kw): return self
        def inc(self, *a, **kw): return None
        def observe(self, *a, **kw): return None
        def set(self, *a, **kw): return None

    prometheus_stub = types.ModuleType("prometheus_client")
    prometheus_stub.Counter = lambda *a, **kw: _MetricStub()
    prometheus_stub.Histogram = lambda *a, **kw: _MetricStub()
    sys.modules["prometheus_client"] = prometheus_stub

try:
    import sentence_transformers  # noqa: F401
except ModuleNotFoundError:
    sentence_transformers_stub = types.ModuleType("sentence_transformers")
    sentence_transformers_stub.SentenceTransformer = lambda *a, **kw: None
    sys.modules["sentence_transformers"] = sentence_transformers_stub

try:
    import openai  # noqa: F401
except ModuleNotFoundError:
    openai_stub = types.ModuleType("openai")
    openai_stub.OpenAI = lambda *a, **kw: None
    sys.modules["openai"] = openai_stub

from app.auth import get_current_user
from app.database import get_db
from app.verticals.real_estate.api.memos import router as memos_router


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def memo_user(completed_run):
    """Minimal user whose id matches the completed_run owner."""
    return SimpleNamespace(
        id=completed_run.user_id,
        org_id="test-org-memo",
        tier="pro",
        allowed_verticals=["real_estate"],
    )


@pytest.fixture
def authed_client(db_session, memo_user):
    """TestClient wired to the memos router with auth and DB dependency overrides."""
    app = FastAPI()
    app.include_router(memos_router, prefix="/api/v1/re")

    app.dependency_overrides[get_current_user] = lambda: memo_user

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /api/v1/re/underwriting/runs/{run_id}/memos
# ---------------------------------------------------------------------------


class TestCreateMemo:
    def test_happy_path_returns_memo_id_and_job_id(self, authed_client, completed_run):
        """Happy path: valid completed run → 200, memo_id + job_id returned, task dispatched."""
        with patch(
            "app.verticals.real_estate.api.memos.generate_credit_memo_task.apply_async"
        ) as mock_dispatch:
            resp = authed_client.post(
                f"/api/v1/re/underwriting/runs/{completed_run.id}/memos",
                json={
                    "cover_data": {
                        "deal_name": "Test Deal",
                        "prepared_by": "Alice",
                        "firm": "Acme Capital",
                        "date": "2026-05-20",
                        "address": "123 Test Ave",
                    },
                    "sponsor_data": {"sponsor_name": "StorageCo LLC"},
                    "market_notes": None,
                },
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "memo_id" in body
        assert "job_id" in body
        assert "version" in body
        assert body["version"] == 1
        mock_dispatch.assert_called_once()
        # Verify task was dispatched with (memo_id, run_id, user_id)
        call_kwargs = mock_dispatch.call_args
        assert call_kwargs.kwargs["args"][0] == body["memo_id"]
        assert call_kwargs.kwargs["args"][1] == completed_run.id

    def test_run_without_result_artifact_returns_400(
        self, authed_client, db_session, completed_run
    ):
        """Run with no result_artifact must be rejected with 400 before any DB/task work."""
        completed_run.result_artifact = None
        db_session.commit()

        resp = authed_client.post(
            f"/api/v1/re/underwriting/runs/{completed_run.id}/memos",
            json={"cover_data": {}, "sponsor_data": {}, "market_notes": None},
        )

        assert resp.status_code == 400
        assert "completed" in resp.json()["detail"].lower()

    def test_unknown_run_returns_404(self, authed_client):
        """Non-existent run_id → 404."""
        resp = authed_client.post(
            "/api/v1/re/underwriting/runs/does-not-exist/memos",
            json={"cover_data": {}, "sponsor_data": {}, "market_notes": None},
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/re/underwriting/runs/{run_id}/memos
# ---------------------------------------------------------------------------


class TestListMemos:
    def test_empty_list_for_run_with_no_memos(self, authed_client, completed_run):
        """No memos yet → 200 with empty list."""
        resp = authed_client.get(
            f"/api/v1/re/underwriting/runs/{completed_run.id}/memos"
        )

        assert resp.status_code == 200
        assert resp.json()["memos"] == []

    def test_returns_memos_sorted_desc_by_version(
        self, authed_client, completed_run, db_session
    ):
        """Multiple memos → returned in descending version order."""
        from app.repositories.re_memo_repository import ReMemoRepository

        repo = ReMemoRepository(db_session)
        for _ in range(3):
            repo.create(
                run_id=completed_run.id,
                user_id=completed_run.user_id,
                cover_data={"deal_name": "X"},
                sponsor_data={},
                market_notes=None,
            )

        resp = authed_client.get(
            f"/api/v1/re/underwriting/runs/{completed_run.id}/memos"
        )

        assert resp.status_code == 200
        memos = resp.json()["memos"]
        assert len(memos) == 3
        versions = [m["version"] for m in memos]
        assert versions == sorted(versions, reverse=True)

    def test_memo_summary_fields_present(self, authed_client, completed_run, db_session):
        """Each memo summary includes all required fields."""
        from app.repositories.re_memo_repository import ReMemoRepository

        repo = ReMemoRepository(db_session)
        repo.create(
            run_id=completed_run.id,
            user_id=completed_run.user_id,
            cover_data={},
            sponsor_data={},
            market_notes=None,
        )

        resp = authed_client.get(
            f"/api/v1/re/underwriting/runs/{completed_run.id}/memos"
        )

        memo = resp.json()["memos"][0]
        for field in ("id", "version", "status", "created_at", "section_warnings",
                      "cover_data", "sponsor_data", "market_notes"):
            assert field in memo, f"missing field: {field}"
        assert memo["status"] == "pending"
        assert isinstance(memo["section_warnings"], list)
        assert isinstance(memo["cover_data"], dict)
        assert isinstance(memo["sponsor_data"], dict)


# ---------------------------------------------------------------------------
# GET /api/v1/re/underwriting/memos/{memo_id}/download
# ---------------------------------------------------------------------------


class TestDownloadMemo:
    def test_returns_presigned_url_for_complete_memo(
        self, authed_client, completed_run, db_session
    ):
        """Complete memo with r2_key → 200 with presigned URL."""
        from app.repositories.re_memo_repository import ReMemoRepository

        repo = ReMemoRepository(db_session)
        memo = repo.create(
            run_id=completed_run.id,
            user_id=completed_run.user_id,
            cover_data={},
            sponsor_data={},
            market_notes=None,
        )
        repo.mark_complete(memo.id, r2_key="re-underwriting-memos/u/r/m_v1.docx", file_size_bytes=5000)

        with patch("app.verticals.real_estate.api.memos._presign_r2") as mock_presign:
            mock_presign.return_value = "https://r2.example/presigned?sig=abc"
            resp = authed_client.get(
                f"/api/v1/re/underwriting/memos/{memo.id}/download"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "url" in body
        assert body["filename"].endswith("_IC_Memo_v1.docx")
        assert body["url"].startswith("https://")
        mock_presign.assert_called_once_with(
            "re-underwriting-memos/u/r/m_v1.docx",
            filename=body["filename"],
        )

    def test_incomplete_memo_returns_409(
        self, authed_client, completed_run, db_session
    ):
        """Memo still in 'pending' status → 409 Conflict."""
        from app.repositories.re_memo_repository import ReMemoRepository

        repo = ReMemoRepository(db_session)
        memo = repo.create(
            run_id=completed_run.id,
            user_id=completed_run.user_id,
            cover_data={},
            sponsor_data={},
            market_notes=None,
        )

        resp = authed_client.get(
            f"/api/v1/re/underwriting/memos/{memo.id}/download"
        )

        assert resp.status_code == 409
        assert "not ready" in resp.json()["detail"].lower()

    def test_unknown_memo_returns_404(self, authed_client):
        """Non-existent memo_id → 404."""
        resp = authed_client.get(
            "/api/v1/re/underwriting/memos/does-not-exist/download"
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/v1/re/underwriting/memos/{memo_id}
# ---------------------------------------------------------------------------


class TestDeleteMemo:
    def test_complete_memo_deletes_database_row_and_storage(
        self, authed_client, completed_run, db_session
    ):
        """Complete memo with r2_key → DB row removed and storage delete called."""
        from app.repositories.re_memo_repository import ReMemoRepository

        repo = ReMemoRepository(db_session)
        memo = repo.create(
            run_id=completed_run.id,
            user_id=completed_run.user_id,
            cover_data={},
            sponsor_data={},
            market_notes=None,
        )
        repo.mark_complete(memo.id, r2_key="re-underwriting-memos/u/r/m_v1.docx", file_size_bytes=5000)

        with patch("app.verticals.real_estate.api.memos.get_storage_backend") as mock_storage_factory:
            mock_storage = mock_storage_factory.return_value
            resp = authed_client.delete(f"/api/v1/re/underwriting/memos/{memo.id}")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["storage_deleted"] is True
        assert body["warnings"] == []
        mock_storage.delete.assert_called_once_with("re-underwriting-memos/u/r/m_v1.docx")
        assert repo.get(memo.id, completed_run.user_id) is None

    def test_failed_memo_without_storage_deletes_database_row(
        self, authed_client, completed_run, db_session
    ):
        """Failed memo without r2_key → DB row removed, no storage call required."""
        from app.repositories.re_memo_repository import ReMemoRepository

        repo = ReMemoRepository(db_session)
        memo = repo.create(
            run_id=completed_run.id,
            user_id=completed_run.user_id,
            cover_data={},
            sponsor_data={},
            market_notes=None,
        )
        repo.mark_failed(memo.id, "generation failed")

        with patch("app.verticals.real_estate.api.memos.get_storage_backend") as mock_storage_factory:
            resp = authed_client.delete(f"/api/v1/re/underwriting/memos/{memo.id}")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["storage_deleted"] is False
        assert body["warnings"] == []
        mock_storage_factory.assert_not_called()
        assert repo.get(memo.id, completed_run.user_id) is None

    def test_pending_memo_delete_returns_409(
        self, authed_client, completed_run, db_session
    ):
        """Pending memo cannot be deleted because generation may still update it."""
        from app.repositories.re_memo_repository import ReMemoRepository

        repo = ReMemoRepository(db_session)
        memo = repo.create(
            run_id=completed_run.id,
            user_id=completed_run.user_id,
            cover_data={},
            sponsor_data={},
            market_notes=None,
        )

        resp = authed_client.delete(f"/api/v1/re/underwriting/memos/{memo.id}")

        assert resp.status_code == 409
        assert "still generating" in resp.json()["detail"].lower()
        assert repo.get(memo.id, completed_run.user_id) is not None

    def test_storage_cleanup_failure_returns_warning_after_db_delete(
        self, authed_client, completed_run, db_session
    ):
        """Storage failure is reported as warning, while the memo row stays deleted."""
        from app.repositories.re_memo_repository import ReMemoRepository

        repo = ReMemoRepository(db_session)
        memo = repo.create(
            run_id=completed_run.id,
            user_id=completed_run.user_id,
            cover_data={},
            sponsor_data={},
            market_notes=None,
        )
        repo.mark_complete(memo.id, r2_key="re-underwriting-memos/u/r/m_v2.docx", file_size_bytes=5000)

        with patch("app.verticals.real_estate.api.memos.get_storage_backend") as mock_storage_factory:
            mock_storage_factory.return_value.delete.side_effect = RuntimeError("r2 unavailable")
            resp = authed_client.delete(f"/api/v1/re/underwriting/memos/{memo.id}")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["storage_deleted"] is False
        assert body["warnings"]
        assert "file cleanup failed" in body["warnings"][0].lower()
        assert repo.get(memo.id, completed_run.user_id) is None
