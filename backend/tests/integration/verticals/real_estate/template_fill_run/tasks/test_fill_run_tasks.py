import uuid

import pytest

from app.verticals.real_estate.template_filling import tasks as re_tasks


class _SessionProxy:
    """Wrap pytest db_session but ignore close() calls from task code."""

    def __init__(self, session):
        self._session = session

    def close(self):
        # Task code may call db.close(); keep session usable for assertions.
        return None

    def __getattr__(self, item):
        return getattr(self._session, item)


@pytest.mark.integration
def test_detect_fields_task_idempotent_skip_returns_existing_fields(
    db_session,
    fill_run_factory,
    template_factory,
    document_factory,
    monkeypatch,
):
    template = template_factory()
    document = document_factory()
    fill_run = fill_run_factory(
        template_id=template.id,
        document_id=document.id,
        status="awaiting_review",
        field_mapping={"pdf_fields": [{"id": "kv_1", "name": "Property Name"}], "mappings": []},
    )

    monkeypatch.setattr(re_tasks, "_get_db_session", lambda: _SessionProxy(db_session))

    payload = {
        "fill_run_id": fill_run.id,
        "template_id": template.id,
        "document_id": document.id,
        "job_id": str(uuid.uuid4()),
    }

    result = re_tasks.detect_fields_task.run(payload)

    assert result["fill_run_id"] == fill_run.id
    assert "detection_result" in result
    assert result["detection_result"]["fields"][0]["id"] == "kv_1"


@pytest.mark.integration
def test_auto_map_fields_task_idempotent_skip_returns_existing_mapping(
    db_session,
    fill_run_factory,
    template_factory,
    document_factory,
    monkeypatch,
):
    template = template_factory()
    document = document_factory()
    existing_mapping = {"pdf_fields": [], "mappings": [{"excel_sheet": "Summary", "excel_cell": "B2"}]}
    fill_run = fill_run_factory(
        template_id=template.id,
        document_id=document.id,
        status="awaiting_review",
        field_mapping=existing_mapping,
    )

    monkeypatch.setattr(re_tasks, "_get_db_session", lambda: _SessionProxy(db_session))

    payload = {
        "fill_run_id": fill_run.id,
        "template_id": template.id,
        "job_id": str(uuid.uuid4()),
        "detection_result": {"fields": []},
    }

    result = re_tasks.auto_map_fields_task.run(payload)

    assert result["fill_run_id"] == fill_run.id
    assert result["mapping_result"] == existing_mapping


@pytest.mark.integration
def test_fill_excel_task_idempotent_skip_returns_completed(
    db_session,
    fill_run_factory,
    template_factory,
    document_factory,
    monkeypatch,
):
    template = template_factory()
    document = document_factory()
    fill_run = fill_run_factory(
        template_id=template.id,
        document_id=document.id,
        status="completed",
    )

    monkeypatch.setattr(re_tasks, "_get_db_session", lambda: _SessionProxy(db_session))

    payload = {
        "fill_run_id": fill_run.id,
        "template_id": template.id,
        "job_id": str(uuid.uuid4()),
    }

    result = re_tasks.fill_excel_task.run(payload)

    assert result["fill_run_id"] == fill_run.id
    assert result["status"] == "completed"


@pytest.mark.integration
def test_fill_excel_task_marks_failed_when_template_missing(
    db_session,
    fill_run_factory,
    template_factory,
    document_factory,
    job_state_factory,
    monkeypatch,
):
    template = template_factory()
    document = document_factory()
    missing_template_id = str(uuid.uuid4())
    fill_run = fill_run_factory(
        template_id=template.id,
        document_id=document.id,
        status="filling",
        current_stage="excel_filling",
    )
    job_id = str(uuid.uuid4())
    job_state_factory(
        job_id=job_id,
        entity_type="template_fill_run",
        entity_id=fill_run.id,
        status="filling",
        current_stage="excel_filling",
        progress_percent=90,
    )

    monkeypatch.setattr(re_tasks, "_get_db_session", lambda: _SessionProxy(db_session))

    payload = {
        "fill_run_id": fill_run.id,
        "template_id": missing_template_id,
        "job_id": job_id,
    }

    result = re_tasks.fill_excel_task.run(payload)

    db_session.refresh(fill_run)

    assert result["status"] == "failed"
    assert "Template not found" in result["error"]
    assert fill_run.status == "failed"
    assert fill_run.error_stage == "excel_filling"
