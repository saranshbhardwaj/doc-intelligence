"""Shared test fixtures for all test modules."""
import json
import pytest
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# Fixtures directory paths
FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXCEL_FIXTURES = FIXTURES_DIR / "excel"
RESPONSES_FIXTURES = FIXTURES_DIR / "responses"
DOCUMENTS_FIXTURES = FIXTURES_DIR / "documents"


# ============================================================================
# REPOSITORY FIXTURES
# ============================================================================

@pytest.fixture
def template_repo(override_db_session):
    """TemplateRepository with test database session."""
    from app.repositories.template_repository import TemplateRepository
    return TemplateRepository()


@pytest.fixture
def document_repo(override_db_session):
    """DocumentRepository with test database session."""
    from app.repositories.document_repository import DocumentRepository
    return DocumentRepository()


# ============================================================================
# MODEL FIXTURES - ExcelTemplate
# ============================================================================

@pytest.fixture
def sample_template(db_session):
    """ExcelTemplate instance for testing."""
    from app.db_models_templates import ExcelTemplate
    import uuid

    template = ExcelTemplate(
        id=str(uuid.uuid4()),
        org_id="test-org",
        user_id="test-user",
        name="Test Rent Roll Template",
        file_path="fixtures/excel/test_rent_roll.xlsx",
        file_size=15000,
        version=1,
        is_active=True,
        created_at=datetime.utcnow()
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)
    return template


# ============================================================================
# MODEL FIXTURES - Document
# ============================================================================

@pytest.fixture
def sample_document(db_session):
    """Document instance with mock Azure DI chunks."""
    from app.db_models_documents import Document
    import uuid

    document = Document(
        id=str(uuid.uuid4()),
        org_id="test-org",
        user_id="test-user",
        filename="test_property_info.pdf",
        file_path="fixtures/documents/test_property_info.pdf",
        file_size=50000,
        status="completed",
        num_pages=5,
        chunks=[],  # Will be populated by sample_document_with_chunks
        created_at=datetime.utcnow()
    )
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


@pytest.fixture
def sample_document_with_chunks(sample_document):
    """Document with realistic Azure DI chunks (key-value pairs and tables)."""
    # Realistic Azure DI chunk structure
    sample_document.chunks = [
        {
            "section_type": "key_value_pairs",
            "key_value_pairs": [
                {
                    "key": {"content": "Property Name"},
                    "value": {"content": "Sunset Plaza"},
                    "confidence": 0.95
                },
                {
                    "key": {"content": "Purchase Price"},
                    "value": {"content": "$45,000,000"},
                    "confidence": 0.92
                },
                {
                    "key": {"content": "Cap Rate"},
                    "value": {"content": "5.5%"},
                    "confidence": 0.88
                },
                {
                    "key": {"content": "Acquisition Date"},
                    "value": {"content": "01/15/2024"},
                    "confidence": 0.91
                }
            ]
        },
        {
            "section_type": "table",
            "column_headers": ["Unit", "Sq Ft", "Rent", "Tenant"],
            "table_data": [
                ["101", "850", "$2,100", "John Doe"],
                ["102", "950", "$2,400", "Jane Smith"],
                ["103", "850", "$2,150", "Bob Johnson"]
            ]
        }
    ]
    return sample_document


# ============================================================================
# MODEL FIXTURES - TemplateFillRun
# ============================================================================

@pytest.fixture
def sample_fill_run(db_session, sample_template, sample_document):
    """TemplateFillRun instance in 'queued' state."""
    from app.db_models_templates import TemplateFillRun
    import uuid

    fill_run = TemplateFillRun(
        id=str(uuid.uuid4()),
        org_id="test-org",
        user_id="test-user",
        template_id=sample_template.id,
        document_id=sample_document.id,
        status="queued",
        current_stage="pending",
        field_mapping={},
        extracted_data={},
        created_at=datetime.utcnow()
    )
    db_session.add(fill_run)
    db_session.commit()
    db_session.refresh(fill_run)
    return fill_run


# ============================================================================
# SAMPLE DATA FIXTURES
# ============================================================================

@pytest.fixture
def sample_pdf_fields() -> List[Dict[str, Any]]:
    """Realistic PDF fields extracted from Azure DI."""
    return [
        {
            "id": "kv_1",
            "name": "Property Name",
            "type": "text",
            "extracted_value": "Sunset Plaza",
            "confidence": 0.95,
            "citations": ["[D1:p1]"],
            "source": "key_value_pairs"
        },
        {
            "id": "kv_2",
            "name": "Purchase Price",
            "type": "currency",
            "extracted_value": "$45,000,000",
            "confidence": 0.92,
            "citations": ["[D1:p1]"],
            "source": "key_value_pairs"
        },
        {
            "id": "kv_3",
            "name": "Cap Rate",
            "type": "percentage",
            "extracted_value": "5.5%",
            "confidence": 0.88,
            "citations": ["[D1:p2]"],
            "source": "key_value_pairs"
        },
        {
            "id": "kv_4",
            "name": "Acquisition Date",
            "type": "date",
            "extracted_value": "01/15/2024",
            "confidence": 0.91,
            "citations": ["[D1:p1]"],
            "source": "key_value_pairs"
        }
    ]


@pytest.fixture
def sample_excel_schema() -> Dict[str, Any]:
    """Realistic Excel template structure (sheet + cell metadata)."""
    return {
        "sheets": [
            {
                "name": "Summary",
                "cells": [
                    {
                        "cell": "B2",
                        "label": "Property Name",
                        "value_type": "text",
                        "is_header": False
                    },
                    {
                        "cell": "B3",
                        "label": "Purchase Price",
                        "value_type": "currency",
                        "is_header": False
                    },
                    {
                        "cell": "B5",
                        "label": "Going-In Cap Rate",  # Alternative terminology
                        "value_type": "percentage",
                        "is_header": False
                    },
                    {
                        "cell": "B6",
                        "label": "Close Date",  # Alternative terminology
                        "value_type": "date",
                        "is_header": False
                    }
                ]
            }
        ]
    }


@pytest.fixture
def sample_field_mapping() -> Dict[str, Any]:
    """Realistic field mapping structure (output from LLM)."""
    return {
        "pdf_fields": [
            {
                "id": "kv_1",
                "name": "Property Name",
                "type": "text",
                "extracted_value": "Sunset Plaza",
                "confidence": 0.95
            },
            {
                "id": "kv_2",
                "name": "Purchase Price",
                "type": "currency",
                "extracted_value": "$45,000,000",
                "confidence": 0.92
            }
        ],
        "mappings": [
            {
                "pdf_field_id": "kv_1",
                "pdf_field_name": "Property Name",
                "excel_sheet": "Summary",
                "excel_cell": "B2",
                "excel_label": "Property Name",
                "confidence": 0.98,
                "source": "schema",
                "reasoning": "Exact terminology match"
            },
            {
                "pdf_field_id": "kv_2",
                "pdf_field_name": "Purchase Price",
                "excel_sheet": "Summary",
                "excel_cell": "B3",
                "excel_label": "Purchase Price",
                "confidence": 0.95,
                "source": "schema",
                "reasoning": "Exact terminology match"
            }
        ]
    }


# ============================================================================
# LLM MOCKING FIXTURES
# ============================================================================

@pytest.fixture
def mock_anthropic_response():
    """Mock successful Anthropic API response."""
    return {
        "id": "msg_test123",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": json.dumps({
                    "mappings": [
                        {
                            "pdf_field_id": "kv_1",
                            "pdf_field_name": "Property Name",
                            "excel_sheet": "Summary",
                            "excel_cell": "B2",
                            "excel_label": "Property Name",
                            "confidence": 0.98,
                            "source": "llm",
                            "reasoning": "Exact terminology match"
                        }
                    ]
                })
            }
        ],
        "model": "claude-haiku-4-5-20251001",
        "usage": {
            "input_tokens": 1500,
            "output_tokens": 200,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0
        }
    }


@pytest.fixture
def mock_storage_backend(tmp_path, monkeypatch):
    """Mock storage backend (S3/R2) to use local filesystem."""
    class MockStorageBackend:
        def __init__(self):
            self.base_path = tmp_path

        def download(self, remote_path: str, local_path: str):
            """Simulate download by copying from fixtures."""
            # For testing, just create an empty file
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            Path(local_path).touch()

        def upload(self, local_path: str, remote_path: str) -> str:
            """Simulate upload by copying to tmp directory."""
            dest = self.base_path / remote_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            if Path(local_path).exists():
                dest.write_bytes(Path(local_path).read_bytes())
            return str(dest)

    mock_backend = MockStorageBackend()
    monkeypatch.setattr("app.storage.get_storage_backend", lambda: mock_backend)
    return mock_backend
