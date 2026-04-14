import pytest
from app.db_models_templates import TemplateFillRun

from tests.integration.verticals.real_estate.template_fill_run.helpers.stubs import (
    DispatchOnlyTaskStub,
    StorageStub,
    TaskStub,
)


@pytest.mark.integration
def test_start_fill_returns_ids_and_dispatches_chain(
    api_client,
    template_factory,
    document_factory,
    monkeypatch,
):
    template = template_factory()
    document = document_factory()

    task_stub = TaskStub("fill-run-123")

    monkeypatch.setattr(
        "app.verticals.real_estate.api.templates.start_fill_run_chain",
        task_stub,
    )
    monkeypatch.setattr(
        "app.verticals.real_estate.api.templates.enforce_template_fill_limit",
        lambda user: None,
    )

    reserve_calls = []

    def _reserve_shadow_credits(**kwargs):
        reserve_calls.append(kwargs)

    monkeypatch.setattr(
        "app.verticals.real_estate.api.templates.reserve_shadow_credits",
        _reserve_shadow_credits,
    )

    response = api_client.post(
        f"/api/v1/re/templates/{template.id}/fill",
        json={"document_id": document.id, "name": "Q2 Fill"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["fill_run_id"] == "fill-run-123"
    assert body["job_id"] == "fill-run-123"
    assert body["status"] == "processing"

    assert len(task_stub.calls) == 1
    assert task_stub.calls[0]["template_id"] == template.id
    assert task_stub.calls[0]["document_id"] == document.id
    assert task_stub.calls[0]["fill_run_name"] == "Q2 Fill"

    assert len(reserve_calls) == 1
    assert reserve_calls[0]["operation_type"] == "template_fill_run"
    assert reserve_calls[0]["reference_id"] == "fill-run-123"


@pytest.mark.integration
def test_update_mappings_dedupes_cells_and_resets_completed_run(
    api_client,
    fill_run_factory,
    template_factory,
    document_factory,
    db_session,
    monkeypatch,
):
    template = template_factory()
    document = document_factory()
    fill_run = fill_run_factory(
        template_id=template.id,
        document_id=document.id,
        status="completed",
        artifact={"key": "fills/old-output.xlsx", "filename": "old-output.xlsx"},
        filling_completed=True,
    )

    storage_stub = StorageStub()
    monkeypatch.setattr(
        "app.core.storage.storage_factory.get_storage_backend",
        lambda: storage_stub,
    )

    mappings_payload = {
        "mappings": [
            {
                "pdf_field_id": "f1",
                "excel_sheet": "Summary",
                "excel_cell": "B2",
                "status": "auto_mapped",
                "confidence": 0.8,
            },
            {
                "pdf_field_id": "f2",
                "excel_sheet": "Summary",
                "excel_cell": "B2",
                "status": "user_edited",
                "confidence": 0.9,
            },
            {
                "pdf_field_id": "f3",
                "excel_sheet": "Summary",
                "excel_cell": "C2",
                "status": "manual",
                "confidence": 0.95,
            },
        ]
    }

    response = api_client.put(
        f"/api/v1/re/templates/fills/{fill_run.id}/mappings",
        json=mappings_payload,
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Mappings updated successfully"

    db_session.refresh(fill_run)
    db_session.refresh(fill_run.fill_run_data)
    saved_mappings = fill_run.fill_run_data.field_mapping.get("mappings", [])
    assert len(saved_mappings) == 2
    assert {f"{m['excel_sheet']}!{m['excel_cell']}" for m in saved_mappings} == {
        "Summary!B2",
        "Summary!C2",
    }

    assert fill_run.status == "awaiting_review"
    assert fill_run.artifact is None
    assert fill_run.filling_completed is False
    assert fill_run.user_edited_count == 2
    assert storage_stub.deleted_keys == ["fills/old-output.xlsx"]


@pytest.mark.integration
def test_update_extracted_data_counts_nested_fields_and_resets_completed(
    api_client,
    fill_run_factory,
    template_factory,
    document_factory,
    db_session,
    monkeypatch,
):
    template = template_factory()
    document = document_factory()
    fill_run = fill_run_factory(
        template_id=template.id,
        document_id=document.id,
        status="completed",
        artifact={"key": "fills/old-output.xlsx", "filename": "old-output.xlsx"},
        filling_completed=True,
    )

    storage_stub = StorageStub()
    monkeypatch.setattr(
        "app.core.storage.storage_factory.get_storage_backend",
        lambda: storage_stub,
    )

    payload = {
        "llm_extracted": {
            "f1": {"value": "Sunset Plaza", "confidence": 0.95, "citations": ["[S1:p2]"]},
            "f2": {"value": "$12,000,000", "confidence": 0.92, "citations": ["[S2:p3]"]},
        },
        "manual_edits": {
            "Summary": {
                "C10": {"value": "Override", "confidence": 1.0, "citations": []}
            }
        },
    }

    response = api_client.put(
        f"/api/v1/re/templates/fills/{fill_run.id}/extracted-data",
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Extracted data updated successfully"

    db_session.refresh(fill_run)
    assert fill_run.total_fields_filled == 3
    assert fill_run.status == "awaiting_review"
    assert fill_run.artifact is None
    assert fill_run.filling_completed is False
    assert storage_stub.deleted_keys == ["fills/old-output.xlsx"]


@pytest.mark.integration
def test_continue_fill_creates_job_and_dispatches_continuation(
    api_client,
    fill_run_factory,
    template_factory,
    document_factory,
    monkeypatch,
):
    template = template_factory()
    document = document_factory()
    fill_run = fill_run_factory(template_id=template.id, document_id=document.id)

    class _JobRepoStub:
        def __init__(self):
            self.calls = []

        def create_job(self, **kwargs):
            self.calls.append(kwargs)
            return {"job_id": kwargs.get("job_id")}

    job_repo_stub = _JobRepoStub()
    continuation_stub = DispatchOnlyTaskStub()

    monkeypatch.setattr(
        "app.verticals.real_estate.api.templates.JobRepository",
        lambda: job_repo_stub,
    )
    monkeypatch.setattr(
        "app.verticals.real_estate.api.templates.generate_id",
        lambda: "job-abc-123",
    )
    monkeypatch.setattr(
        "app.verticals.real_estate.api.templates.continue_fill_run_chain",
        continuation_stub,
    )

    response = api_client.post(
        f"/api/v1/re/templates/fills/{fill_run.id}/continue",
        json={},
    )

    assert response.status_code == 200
    assert response.json()["job_id"] == "job-abc-123"

    assert len(job_repo_stub.calls) == 1
    assert job_repo_stub.calls[0]["entity_type"] == "template_fill_run"
    assert job_repo_stub.calls[0]["entity_id"] == fill_run.id

    assert len(continuation_stub.calls) == 1
    assert continuation_stub.calls[0]["fill_run_id"] == fill_run.id
    assert continuation_stub.calls[0]["job_id"] == "job-abc-123"


@pytest.mark.integration
def test_download_filled_excel_returns_400_when_artifact_missing(
    api_client,
    fill_run_factory,
    template_factory,
    document_factory,
):
    template = template_factory()
    document = document_factory()
    fill_run = fill_run_factory(
        template_id=template.id,
        document_id=document.id,
        status="awaiting_review",
        artifact=None,
    )

    response = api_client.get(f"/api/v1/re/templates/fills/{fill_run.id}/download")

    assert response.status_code == 400
    assert "not completed" in response.json().get("detail", "").lower()


@pytest.mark.integration
def test_delete_template_blocks_when_run_is_awaiting_review(
    api_client,
    template_factory,
    document_factory,
    fill_run_factory,
):
    template = template_factory(file_path="templates/block-delete.xlsx")
    document = document_factory()
    fill_run_factory(
        template_id=template.id,
        document_id=document.id,
        status="awaiting_review",
    )

    response = api_client.delete(f"/api/v1/re/templates/{template.id}")

    assert response.status_code == 400
    assert "in progress" in response.json().get("detail", "").lower()


@pytest.mark.integration
def test_delete_template_allows_terminal_runs_and_preserves_history(
    api_client,
    template_factory,
    document_factory,
    fill_run_factory,
    db_session,
    monkeypatch,
):
    template = template_factory(file_path="templates/delete-terminal.xlsx")
    document = document_factory()
    completed_run = fill_run_factory(
        template_id=template.id,
        document_id=document.id,
        status="completed",
    )
    fill_run_factory(
        template_id=template.id,
        document_id=document.id,
        status="failed",
    )

    storage_stub = StorageStub()
    monkeypatch.setattr(
        "app.repositories.template_repository.get_storage_backend",
        lambda: storage_stub,
    )

    response = api_client.delete(f"/api/v1/re/templates/{template.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Template deleted successfully"
    assert body["affected_fill_runs"] == 2

    remaining_run = db_session.query(TemplateFillRun).filter(TemplateFillRun.id == completed_run.id).first()
    assert remaining_run is not None
    assert remaining_run.template_id is None
    assert storage_stub.deleted_keys == ["templates/delete-terminal.xlsx"]


@pytest.mark.integration
def test_delete_template_returns_warning_when_storage_cleanup_fails(
    api_client,
    template_factory,
    monkeypatch,
):
    template = template_factory(file_path="templates/delete-warning.xlsx")

    class _StorageFailStub:
        def delete(self, _key):
            raise RuntimeError("r2 unavailable")

    monkeypatch.setattr(
        "app.repositories.template_repository.get_storage_backend",
        lambda: _StorageFailStub(),
    )

    response = api_client.delete(f"/api/v1/re/templates/{template.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Template deleted successfully"
    assert body.get("warnings")
    assert "failed to delete storage file" in body["warnings"][0].lower()
