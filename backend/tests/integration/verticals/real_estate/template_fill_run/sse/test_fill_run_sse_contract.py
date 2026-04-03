import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from main import app

from tests.integration.verticals.real_estate.template_fill_run.helpers.stubs import PubSubStub


@pytest.fixture
def sse_client(monkeypatch):
    # Simplify auth path so tests can pass lightweight tokens.
    monkeypatch.setattr("app.api.jobs._verify_token", lambda token: {"sub": "test-user", "org_id": "test-org"})
    monkeypatch.setattr("app.api.jobs._claim", lambda key: key)

    with TestClient(app) as client:
        yield client


def _collect_sse_events(raw_text):
    events = []
    current_event = None
    current_data_lines = []

    for line in raw_text.splitlines():
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            current_data_lines.append(line.split(":", 1)[1].strip())
        elif line == "":
            if current_event is not None:
                payload = "\n".join(current_data_lines)
                try:
                    payload = json.loads(payload)
                except Exception:
                    pass
                events.append((current_event, payload))
            current_event = None
            current_data_lines = []

    return events


@pytest.mark.integration
def test_sse_failed_job_emits_error_then_end(sse_client, monkeypatch):
    failed_job = SimpleNamespace(
        job_id="job-failed-1",
        status="failed",
        error_stage="excel_filling",
        error_message="Template missing",
        error_type="fill_error",
        is_retryable=False,
        entity_type="template_fill_run",
        entity_id="fill-1",
    )

    class _JobRepoStub:
        def get_job(self, _job_id):
            return failed_job

    monkeypatch.setattr("app.api.jobs.JobRepository", lambda: _JobRepoStub())

    response = sse_client.get("/api/jobs/job-failed-1/stream?token=fake")
    events = _collect_sse_events(response.text)

    assert events[0][0] == "error"
    assert events[0][1]["stage"] == "excel_filling"
    assert events[1][0] == "end"
    assert events[1][1]["reason"] == "failed"


@pytest.mark.integration
def test_sse_completed_job_emits_complete_then_end(sse_client, monkeypatch):
    completed_job = SimpleNamespace(
        job_id="job-complete-1",
        status="completed",
        entity_type="template_fill_run",
        entity_id="fill-2",
    )

    class _JobRepoStub:
        def get_job(self, _job_id):
            return completed_job

    monkeypatch.setattr("app.api.jobs.JobRepository", lambda: _JobRepoStub())
    monkeypatch.setattr("app.api.jobs.build_entity_complete_event", lambda job: {"message": "Done", "job_id": job.job_id})

    response = sse_client.get("/api/jobs/job-complete-1/stream?token=fake")
    events = _collect_sse_events(response.text)

    assert events[0][0] == "complete"
    assert events[0][1]["job_id"] == "job-complete-1"
    assert events[1][0] == "end"
    assert events[1][1]["reason"] == "completed"


@pytest.mark.integration
def test_sse_awaiting_review_job_emits_complete_then_end(sse_client, monkeypatch):
    mapped_job = SimpleNamespace(
        job_id="job-awaiting-1",
        status="awaiting_review",
        message="Ready for review",
        entity_type="template_fill_run",
        entity_id="fill-3",
    )

    class _JobRepoStub:
        def get_job(self, _job_id):
            return mapped_job

    class _FillRunStub:
        status = "awaiting_review"

    monkeypatch.setattr("app.api.jobs.JobRepository", lambda: _JobRepoStub())
    monkeypatch.setattr("app.api.jobs.resolve_entity_owner", lambda entity_type, entity_id, org_id: ("test-user", "test-org"))
    monkeypatch.setattr("app.api.jobs.safe_subscribe", lambda _job_id: PubSubStub())
    monkeypatch.setattr("app.repositories.template_repository.TemplateRepository.get_fill_run_by_id", lambda _fill_run_id: _FillRunStub())

    response = sse_client.get("/api/jobs/job-awaiting-1/stream?token=fake")
    events = _collect_sse_events(response.text)

    assert events[0][0] == "complete"
    assert events[0][1]["status"] == "awaiting_review"
    assert events[1][0] == "end"
    assert events[1][1]["reason"] == "awaiting_review"
