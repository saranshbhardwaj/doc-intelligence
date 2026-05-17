from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.db_models_templates import TemplateFillRun
from app.services.beta_limits import enforce_fill_run_concurrency_limit


class _FakeQuery:
    def __init__(self, active_count):
        self.active_count = active_count
        self.filters = []

    def filter(self, *conditions):
        self.filters.extend(conditions)
        return self

    def scalar(self):
        return self.active_count


class _FakeSession:
    def __init__(self, active_count):
        self.query_obj = _FakeQuery(active_count)

    def query(self, *_args, **_kwargs):
        return self.query_obj


class _ComparableColumn:
    def __eq__(self, _other):
        return True

    def __ge__(self, _other):
        return True


def test_template_fill_processing_statuses_exclude_awaiting_review():
    assert "awaiting_review" in TemplateFillRun.ACTIVE_STATUSES
    assert "awaiting_review" not in TemplateFillRun.PROCESSING_STATUSES
    assert TemplateFillRun.PROCESSING_STATUSES <= TemplateFillRun.ACTIVE_STATUSES


def test_concurrency_limit_uses_processing_statuses(monkeypatch):
    captured = {}

    class _StatusColumn:
        def in_(self, statuses):
            captured["statuses"] = statuses
            return ("status_in", statuses)

    monkeypatch.setattr(TemplateFillRun, "status", _StatusColumn(), raising=False)
    monkeypatch.setattr(TemplateFillRun, "user_id", _ComparableColumn(), raising=False)
    monkeypatch.setattr(TemplateFillRun, "org_id", _ComparableColumn(), raising=False)
    monkeypatch.setattr(TemplateFillRun, "created_at", _ComparableColumn(), raising=False)

    db = _FakeSession(active_count=0)
    user = SimpleNamespace(id="user-1", org_id="org-1", tier="standard")

    enforce_fill_run_concurrency_limit(user, db)

    assert captured["statuses"] == TemplateFillRun.PROCESSING_STATUSES


def test_concurrency_limit_raises_when_processing_runs_hit_limit(monkeypatch):
    class _StatusColumn:
        def in_(self, statuses):
            return ("status_in", statuses)

    monkeypatch.setattr(TemplateFillRun, "status", _StatusColumn(), raising=False)
    monkeypatch.setattr(TemplateFillRun, "user_id", _ComparableColumn(), raising=False)
    monkeypatch.setattr(TemplateFillRun, "org_id", _ComparableColumn(), raising=False)
    monkeypatch.setattr(TemplateFillRun, "created_at", _ComparableColumn(), raising=False)

    db = _FakeSession(active_count=3)
    user = SimpleNamespace(id="user-1", org_id="org-1", tier="standard")

    with pytest.raises(HTTPException) as exc_info:
        enforce_fill_run_concurrency_limit(user, db)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["error"] == "fill_run_concurrency_limit_exceeded"
