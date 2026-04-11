from datetime import datetime
import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth import get_current_user
from app.database import get_db
from app.db_models import JobState
from app.db_models_documents import Document
from app.db_models_templates import ExcelTemplate, FillRunData, TemplateFillRun


@pytest.fixture
def mock_user():
    class MockUser:
        id = "test-user"
        org_id = "test-org"
        tier = "beta"
        allowed_verticals = ["real_estate"]

    return MockUser()


@pytest.fixture
def api_client(db_session, mock_user):
    """FastAPI client with auth and DB overrides bound to the test session."""
    from main import app

    def override_current_user():
        return mock_user

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def template_factory(db_session, mock_user):
    def _create(**overrides):
        template_data = {
            "id": str(uuid.uuid4()),
            "org_id": mock_user.org_id,
            "user_id": mock_user.id,
            "name": "Template A",
            "description": "Template for integration tests",
            "file_path": "templates/template-a.xlsx",
            "file_extension": ".xlsx",
            "file_size_bytes": 2048,
            "content_hash": uuid.uuid4().hex,
            "schema_metadata": {},
            "usage_count": 0,
            "active": True,
            "created_at": datetime.utcnow(),
        }
        template_data.update(overrides)

        template = ExcelTemplate(**template_data)
        db_session.add(template)
        db_session.commit()
        db_session.refresh(template)
        return template

    return _create


@pytest.fixture
def document_factory(db_session, mock_user):
    def _create(**overrides):
        document_data = {
            "id": str(uuid.uuid4()),
            "org_id": mock_user.org_id,
            "user_id": mock_user.id,
            "filename": "source.pdf",
            "file_path": "documents/source.pdf",
            "file_size_bytes": 4096,
            "content_hash": uuid.uuid4().hex,
            "page_count": 8,
            "chunk_count": 1,
            "status": "completed",
            "created_at": datetime.utcnow(),
        }
        document_data.update(overrides)

        document = Document(**document_data)
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)
        return document

    return _create


@pytest.fixture
def fill_run_factory(db_session, mock_user):
    def _create(template_id, document_id, **overrides):
        # Separate blob overrides from lean row overrides
        blob_keys = {"field_mapping", "extracted_data", "citation_context"}
        blob_overrides = {k: overrides.pop(k) for k in blob_keys if k in overrides}

        lean_defaults = {
            "id": str(uuid.uuid4()),
            "org_id": mock_user.org_id,
            "user_id": mock_user.id,
            "template_id": template_id,
            "document_id": document_id,
            "status": "queued",
            "current_stage": "pending",
            "template_snapshot": {"name": "Template A", "schema_metadata": {}},
            "created_at": datetime.utcnow(),
        }
        lean_defaults.update(overrides)

        fill_run = TemplateFillRun(**lean_defaults)
        db_session.add(fill_run)
        db_session.flush()  # Assigns fill_run.id within the transaction

        fill_run_data_defaults = {
            "fill_run_id": fill_run.id,
            "field_mapping": {"pdf_fields": [], "mappings": []},
            "extracted_data": {"llm_extracted": {}, "manual_edits": {}},
            "citation_context": None,
        }
        fill_run_data_defaults.update(blob_overrides)

        fill_run_data = FillRunData(**fill_run_data_defaults)
        db_session.add(fill_run_data)
        db_session.commit()
        db_session.refresh(fill_run)
        return fill_run

    return _create


@pytest.fixture
def job_state_factory(db_session):
    def _create(job_id, entity_type, entity_id, **overrides):
        job_data = {
            "id": str(uuid.uuid4()),
            "job_id": job_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "status": "queued",
            "current_stage": "queued",
            "progress_percent": 0,
            "message": "Queued",
            "details": {},
            "is_retryable": True,
            "created_at": datetime.utcnow(),
        }
        job_data.update(overrides)

        job = JobState(**job_data)
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)
        return job

    return _create
