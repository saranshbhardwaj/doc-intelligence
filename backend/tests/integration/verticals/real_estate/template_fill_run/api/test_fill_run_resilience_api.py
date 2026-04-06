from pathlib import Path

import pytest


class _MockStorageBackend:
    def __init__(self, payload: bytes):
        self._payload = payload

    def download(self, remote_path: str, local_path: str):
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        Path(local_path).write_bytes(self._payload)


@pytest.mark.integration
def test_get_fill_status_survives_deleted_source_assets(
    api_client,
    db_session,
    template_factory,
    document_factory,
    fill_run_factory,
):
    template = template_factory()
    document = document_factory()
    fill_run = fill_run_factory(
        template_id=template.id,
        document_id=document.id,
        status="completed",
        artifact={
            "backend": "r2",
            "key": "fills/test-filled.xlsx",
            "filename": "test-filled.xlsx",
        },
    )

    fill_run.template_id = None
    fill_run.document_id = None
    db_session.commit()

    response = api_client.get(f"/api/v1/re/templates/fills/{fill_run.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == fill_run.id
    assert body["status"] == "completed"
    assert body["template_id"] is None
    assert body["document_id"] is None
    assert body["document_metadata"] is None
    assert body["artifact"]["key"] == "fills/test-filled.xlsx"


@pytest.mark.integration
def test_download_filled_excel_works_when_source_assets_deleted(
    api_client,
    db_session,
    template_factory,
    document_factory,
    fill_run_factory,
    monkeypatch,
):
    template = template_factory()
    document = document_factory()
    fill_run = fill_run_factory(
        template_id=template.id,
        document_id=document.id,
        status="completed",
        artifact={
            "backend": "r2",
            "key": "fills/test-filled.xlsx",
            "filename": "test-filled.xlsx",
        },
    )

    fill_run.template_id = None
    fill_run.document_id = None
    db_session.commit()

    fake_xlsx = b"PK\x03\x04test-xlsx-bytes"
    monkeypatch.setattr(
        "app.verticals.real_estate.api.templates.get_storage_backend",
        lambda: _MockStorageBackend(fake_xlsx),
    )

    response = api_client.get(f"/api/v1/re/templates/fills/{fill_run.id}/download")

    assert response.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in response.headers.get(
        "content-type", ""
    )
    assert "test-filled.xlsx" in response.headers.get("content-disposition", "")
    assert response.content == fake_xlsx
