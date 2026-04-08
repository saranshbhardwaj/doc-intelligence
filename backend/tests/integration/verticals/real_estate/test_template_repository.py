"""Integration tests for TemplateRepository.

Tests repository methods with a real (test) database session.
"""
import pytest
from datetime import datetime
from app.repositories.template_repository import TemplateRepository


class TestTemplateRepositoryCreation:
    """Test template and fill run creation methods."""

    @pytest.mark.integration
    def test_create_template(self, template_repo):
        """Should create a new Excel template."""
        template = template_repo.create_template(
            org_id="test-org",
            user_id="test-user",
            name="Test Template",
            file_path="test/path/template.xlsx",
            file_size_bytes=10000,
            content_hash="abc123",
        )

        assert template is not None
        assert template.id is not None
        assert template.name == "Test Template"
        assert template.org_id == "test-org"
        assert template.user_id == "test-user"
        assert template.active is True

    @pytest.mark.integration
    def test_create_fill_run(self, template_repo, sample_template, sample_document):
        """Should create a new TemplateFillRun."""
        fill_run = template_repo.create_fill_run(
            template_id=sample_template.id,
            document_id=sample_document.id,
            org_id="test-org",
            user_id="test-user",
            template_snapshot={},
        )

        assert fill_run is not None
        assert fill_run.id is not None
        assert fill_run.template_id == sample_template.id
        assert fill_run.document_id == sample_document.id
        assert fill_run.status == "queued"
        assert fill_run.field_mapping == {"pdf_fields": [], "mappings": []}
        assert fill_run.extracted_data == {}


class TestTemplateRepositoryRetrieval:
    """Test retrieval methods."""

    @pytest.mark.integration
    def test_get_template(self, template_repo, sample_template):
        """Should retrieve an existing template by ID."""
        retrieved = template_repo.get_template(
            template_id=sample_template.id,
            org_id="test-org"
        )

        assert retrieved is not None
        assert retrieved.id == sample_template.id
        assert retrieved.name == sample_template.name

    @pytest.mark.integration
    def test_get_template_with_wrong_org_returns_none(self, template_repo, sample_template):
        """Should return None if org_id doesn't match."""
        retrieved = template_repo.get_template(
            template_id=sample_template.id,
            org_id="wrong-org"
        )

        assert retrieved is None

    @pytest.mark.integration
    def test_get_fill_run(self, template_repo, sample_fill_run):
        """Should retrieve an existing fill run by ID."""
        retrieved = template_repo.get_fill_run(
            fill_run_id=sample_fill_run.id,
            org_id="test-org"
        )

        assert retrieved is not None
        assert retrieved.id == sample_fill_run.id
        assert retrieved.status == "queued"

    @pytest.mark.integration
    def test_list_user_templates(self, template_repo, sample_template):
        """Should list all templates for a user."""
        templates = template_repo.list_user_templates(
            user_id="test-user",
            org_id="test-org"
        )

        assert len(templates) > 0
        assert any(t.id == sample_template.id for t in templates)

    @pytest.mark.integration
    def test_list_user_fill_runs(self, template_repo, sample_fill_run):
        """Should list all fill runs for a user."""
        fill_runs = template_repo.list_user_fill_runs(
            user_id="test-user",
            org_id="test-org",
            limit=10,
            offset=0
        )

        assert len(fill_runs) > 0
        assert any(fr.id == sample_fill_run.id for fr in fill_runs)


class TestTemplateRepositoryUpdates:
    """Test update methods for fill runs."""

    @pytest.mark.integration
    def test_update_fill_run_status(self, template_repo, sample_fill_run):
        """Should update fill run status and stage."""
        updated = template_repo.update_fill_run(
            fill_run_id=sample_fill_run.id,
            status="detecting_fields",
            current_stage="field_detection"
        )

        assert updated is not None
        assert updated.status == "detecting_fields"
        assert updated.current_stage == "field_detection"

    @pytest.mark.integration
    def test_update_field_mapping(self, template_repo, sample_fill_run, sample_field_mapping):
        """Should update field mapping structure."""
        updated = template_repo.update_field_mapping(
            fill_run_id=sample_fill_run.id,
            field_mapping=sample_field_mapping
        )

        assert updated is not None
        assert updated.field_mapping == sample_field_mapping
        assert "pdf_fields" in updated.field_mapping
        assert "mappings" in updated.field_mapping

    @pytest.mark.integration
    def test_update_extracted_data(self, template_repo, sample_fill_run):
        """Should update extracted data structure."""
        extracted_data = {
            "llm_extracted": {
                "Property Name": "Sunset Plaza",
                "Purchase Price": "$45,000,000"
            },
            "manual_edits": {}
        }

        updated = template_repo.update_extracted_data(
            fill_run_id=sample_fill_run.id,
            extracted_data=extracted_data
        )

        assert updated is not None
        assert updated.extracted_data == extracted_data

    @pytest.mark.integration
    def test_update_fill_run_completion_flags(self, template_repo, sample_fill_run):
        """Should update completion stage flags."""
        updated = template_repo.update_fill_run(
            fill_run_id=sample_fill_run.id,
            field_detection_completed=True,
            auto_mapping_completed=True,
            total_fields_detected=10,
            total_fields_mapped=8
        )

        assert updated is not None
        assert updated.field_detection_completed is True
        assert updated.auto_mapping_completed is True
        assert updated.total_fields_detected == 10
        assert updated.total_fields_mapped == 8

    @pytest.mark.integration
    def test_update_fill_run_token_metrics(self, template_repo, sample_fill_run):
        """Should update LLM token usage metrics."""
        updated = template_repo.update_fill_run(
            fill_run_id=sample_fill_run.id,
            input_tokens=1500,
            output_tokens=300,
            cache_read_tokens=1000,
            cache_write_tokens=500,
            model_name="claude-haiku-4-5-20251001"
        )

        assert updated is not None
        assert updated.input_tokens == 1500
        assert updated.output_tokens == 300
        assert updated.cache_read_tokens == 1000
        assert updated.cache_write_tokens == 500
        assert updated.model_name == "claude-haiku-4-5-20251001"

    @pytest.mark.integration
    def test_update_fill_run_to_completed(self, template_repo, sample_fill_run):
        """Should mark fill run as completed with artifact."""
        artifact = {
            "file_path": "output/filled_template.xlsx",
            "file_size": 25000,
            "download_url": "https://storage.example.com/filled.xlsx"
        }

        updated = template_repo.update_fill_run(
            fill_run_id=sample_fill_run.id,
            status="completed",
            filling_completed=True,
            artifact=artifact,
            completed_at=datetime.utcnow()
        )

        assert updated is not None
        assert updated.status == "completed"
        assert updated.filling_completed is True
        assert updated.artifact == artifact
        assert updated.completed_at is not None

    @pytest.mark.integration
    def test_update_fill_run_to_failed(self, template_repo, sample_fill_run):
        """Should mark fill run as failed with error details."""
        updated = template_repo.update_fill_run(
            fill_run_id=sample_fill_run.id,
            status="failed",
            error_message="LLM API timeout",
            error_stage="auto_mapping",
        )

        assert updated is not None
        assert updated.status == "failed"
        assert updated.error_message == "LLM API timeout"
        assert updated.error_stage == "auto_mapping"


class TestTemplateRepositoryMetrics:
    """Test metrics and usage methods."""

    @pytest.mark.integration
    def test_get_template_usage_no_runs(self, template_repo, sample_template):
        """Should return zero usage for template with no runs."""
        usage = template_repo.get_template_usage(template_id=sample_template.id)

        assert usage is not None
        assert usage["total_runs"] == 0
        assert usage["completed_runs"] == 0
        assert usage["failed_runs"] == 0
        assert usage["can_delete"] is True

    @pytest.mark.integration
    def test_get_template_usage_with_runs(self, template_repo, sample_template, sample_fill_run):
        """Should return correct usage metrics."""
        # Create additional fill runs with different statuses
        template_repo.create_fill_run(
            template_id=sample_template.id,
            document_id=sample_fill_run.document_id,
            org_id="test-org",
            user_id="test-user",
            template_snapshot={},
        )

        # Update one to completed
        template_repo.update_fill_run(
            fill_run_id=sample_fill_run.id,
            status="completed"
        )

        usage = template_repo.get_template_usage(template_id=sample_template.id)

        assert usage is not None
        assert usage["total_runs"] >= 2
        assert usage["completed_runs"] >= 1


class TestTemplateRepositoryDeletion:
    """Test deletion methods."""

    @pytest.mark.integration
    def test_delete_template(self, template_repo, sample_template):
        """Should soft-delete a template (mark as inactive)."""
        result = template_repo.delete_template(
            template_id=sample_template.id,
        )

        assert result["success"] is True

        # Verify template is deleted
        deleted = template_repo.get_template(
            template_id=sample_template.id,
            org_id="test-org"
        )
        assert deleted is None

    @pytest.mark.integration
    def test_delete_fill_run(self, template_repo, sample_fill_run):
        """Should delete a fill run."""
        result = template_repo.delete_fill_run(
            fill_run_id=sample_fill_run.id,
        )

        assert result is True

        # Verify fill run is deleted
        deleted = template_repo.get_fill_run(
            fill_run_id=sample_fill_run.id,
            org_id="test-org"
        )
        assert deleted is None
