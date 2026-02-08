"""Repository for Excel template and template fill run operations."""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import and_, desc, or_
from sqlalchemy.orm import Session

from app.database import SessionLocal

from app.core.storage.storage_factory import get_storage_backend
from app.db_models_templates import ExcelTemplate, TemplateFillRun
from app.utils.logging import logger


class TemplateRepository:
    """Repository for template and fill run CRUD operations."""

    def __init__(self, db_session: Session):
        self.db = db_session

    # ==================== Template Operations ====================

    def create_template(
        self,
        org_id: str,
        user_id: str,
        name: str,
        file_path: str,
        file_size_bytes: int,
        content_hash: str,
        file_extension: str = ".xlsx",
        description: Optional[str] = None,
        category: Optional[str] = None,
        schema_metadata: Optional[Dict] = None,
    ) -> ExcelTemplate:
        """Create a new Excel template."""
        template = ExcelTemplate(
            id=str(uuid.uuid4()),
            org_id=org_id,
            user_id=user_id,
            name=name,
            description=description,
            category=category,
            file_path=file_path,
            file_extension=file_extension,
            file_size_bytes=file_size_bytes,
            content_hash=content_hash,
            schema_metadata=schema_metadata or {},
            usage_count=0,
            active=True,
        )

        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)

        logger.info(f"Created template: {template.id} ({template.name}) for user {user_id}", extra={"org_id": org_id})
        return template

    def get_template(self, template_id: str, org_id: Optional[str] = None) -> Optional[ExcelTemplate]:
        """Get template by ID, optionally scoped to tenant."""
        query = self.db.query(ExcelTemplate).filter(ExcelTemplate.id == template_id)
        if org_id:
            query = query.filter(ExcelTemplate.org_id == org_id)
        return query.first()

    def list_user_templates(
        self,
        user_id: str,
        org_id: str,
        active_only: bool = True,
        category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ExcelTemplate]:
        """List user's templates."""
        query = self.db.query(ExcelTemplate).filter(
            ExcelTemplate.user_id == user_id,
            ExcelTemplate.org_id == org_id
        )

        if active_only:
            query = query.filter(ExcelTemplate.active == True)

        if category:
            query = query.filter(ExcelTemplate.category == category)

        query = query.order_by(desc(ExcelTemplate.created_at))
        query = query.limit(limit).offset(offset)

        return query.all()

    def update_template(
        self,
        template_id: str,
        **kwargs,
    ) -> Optional[ExcelTemplate]:
        """Update template fields."""
        template = self.get_template(template_id)
        if not template:
            logger.warning(f"Template not found: {template_id}")
            return None

        # Update allowed fields
        allowed_fields = [
            "name",
            "description",
            "category",
            "file_path",
            "schema_metadata",
            "usage_count",
            "last_used_at",
            "active",
        ]

        for field, value in kwargs.items():
            if field in allowed_fields:
                setattr(template, field, value)

        self.db.commit()
        self.db.refresh(template)

        logger.info(f"Updated template: {template_id}")
        return template

    def delete_template(self, template_id: str, force: bool = False) -> Dict:
        """
        Delete template and remove file from storage.

        Args:
            template_id: Template ID to delete
            force: If True, skip in-progress check (use with caution)

        Returns:
            Dict with success status and any warnings
        """
        template = self.get_template(template_id)
        if not template:
            return {"success": False, "error": "Template not found"}

        # Get usage info before deletion for return message
        usage = self.get_template_usage(template_id)
        affected_runs = usage["total_fill_runs"] if usage else 0

        # Check for in-progress fill runs (unless forced)
        if not force and usage and not usage["can_delete"]:
            return {
                "success": False,
                "error": usage["warning"],
                "in_progress_runs": usage["in_progress_runs"],
            }

        # Hard delete file from R2 storage
        try:
            storage = get_storage_backend()
            storage.delete(template.file_path)
            logger.info(f"Deleted template file from storage: {template.file_path}")
        except Exception as e:
            logger.warning(f"Failed to delete template file from storage: {e}")
            # Continue with DB deletion even if storage deletion fails

        # Hard delete from database
        # Note: fill_runs.template_id will be SET NULL due to FK constraint
        self.db.delete(template)
        self.db.commit()

        logger.info(f"Permanently deleted template: {template_id} (affected {affected_runs} fill runs)")

        return {
            "success": True,
            "message": "Template deleted successfully",
            "affected_fill_runs": affected_runs,
        }

    def increment_usage(self, template_id: str) -> Optional[ExcelTemplate]:
        """Increment template usage count."""
        template = self.get_template(template_id)
        if not template:
            return None

        template.usage_count += 1
        template.last_used_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(template)

        return template

    def get_template_usage(self, template_id: str) -> Optional[Dict]:
        """
        Get usage statistics for a template before deletion.

        Returns:
            Dict with usage stats and deletion safety info, or None if template not found
        """
        template = self.get_template(template_id)
        if not template:
            return None

        # Get all fill runs referencing this template
        fill_runs = (
            self.db.query(TemplateFillRun)
            .filter(TemplateFillRun.template_id == template_id)
            .all()
        )

        # Count by status
        completed_count = sum(1 for run in fill_runs if run.status == "completed")
        in_progress_count = sum(
            1
            for run in fill_runs
            if run.status in ["queued", "processing", "awaiting_review"]
        )
        failed_count = sum(1 for run in fill_runs if run.status == "failed")

        # Determine if deletion is safe
        can_delete = in_progress_count == 0
        warning_message = None

        if not can_delete:
            warning_message = (
                f"Cannot delete: {in_progress_count} fill run(s) are currently in progress. "
                f"Please wait for them to complete or fail them first."
            )
        elif len(fill_runs) > 0:
            warning_message = (
                f"This template has {len(fill_runs)} associated fill run(s) "
                f"({completed_count} completed, {failed_count} failed). "
                f"Fill runs will be preserved but will show '[Deleted Template]'."
            )

        return {
            "template_id": template_id,
            "template_name": template.name,
            "total_fill_runs": len(fill_runs),
            "completed_runs": completed_count,
            "in_progress_runs": in_progress_count,
            "failed_runs": failed_count,
            "last_used_at": template.last_used_at.isoformat() if template.last_used_at else None,
            "can_delete": can_delete,
            "warning": warning_message,
        }

    # ==================== Fill Run Operations ====================

    def create_fill_run(
        self,
        template_id: str,
        document_id: str,
        org_id: str,
        user_id: str,
        template_snapshot: Dict,
    ) -> TemplateFillRun:
        """Create a new template fill run."""
        fill_run = TemplateFillRun(
            id=str(uuid.uuid4()),
            template_id=template_id,
            document_id=document_id,
            org_id=org_id,
            user_id=user_id,
            template_snapshot=template_snapshot,
            field_mapping={"pdf_fields": [], "mappings": []},
            extracted_data={},
            status="queued",
        )

        self.db.add(fill_run)
        self.db.commit()
        self.db.refresh(fill_run)

        # Increment template usage
        self.increment_usage(template_id)

        logger.info(
            f"Created fill run: {fill_run.id} (template: {template_id}, document: {document_id})",
            extra={"org_id": org_id, "user_id": user_id}
        )
        return fill_run

    def get_fill_run(self, fill_run_id: str, org_id: Optional[str] = None) -> Optional[TemplateFillRun]:
        """Get fill run by ID, optionally scoped to tenant."""
        query = self.db.query(TemplateFillRun).filter(TemplateFillRun.id == fill_run_id)
        if org_id:
            query = query.filter(TemplateFillRun.org_id == org_id)
        return query.first()

    @classmethod
    def get_fill_run_by_id(cls, fill_run_id: str) -> Optional[TemplateFillRun]:
        """Fetch a fill run by ID using an internal session."""
        db = SessionLocal()
        try:
            repo = cls(db)
            return repo.get_fill_run(fill_run_id)
        finally:
            db.close()

    def update_fill_run(self, fill_run_id: str, **kwargs) -> Optional[TemplateFillRun]:
        """Update fill run fields."""
        from sqlalchemy.orm.attributes import flag_modified

        fill_run = self.get_fill_run(fill_run_id)
        if not fill_run:
            logger.warning(f"Fill run not found: {fill_run_id}")
            return None

        # Update allowed fields
        allowed_fields = [
            "status",
            "current_stage",
            "field_mapping",
            "extracted_data",
            "artifact",
            "field_detection_completed",
            "auto_mapping_completed",
            "user_review_completed",
            "extraction_completed",
            "filling_completed",
            "total_fields_detected",
            "total_fields_mapped",
            "total_fields_filled",
            "auto_mapped_count",
            "user_edited_count",
            "cost_usd",
            "processing_time_ms",
            "error_stage",
            "error_message",
            "started_at",
            "completed_at",
            # Token tracking for observability
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "model_name",
            "llm_batches_count",
            "cache_hit_rate",
        ]

        # JSONB fields that need explicit dirty tracking
        jsonb_fields = ["field_mapping", "extracted_data", "artifact"]

        for field, value in kwargs.items():
            if field in allowed_fields:
                setattr(fill_run, field, value)
                # For JSONB columns, explicitly mark as modified to ensure SQLAlchemy detects the change
                if field in jsonb_fields:
                    flag_modified(fill_run, field)

        self.db.commit()
        self.db.refresh(fill_run)

        logger.debug(f"Updated fill run: {fill_run_id}")
        return fill_run

    def list_user_fill_runs(
        self,
        user_id: str,
        org_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[TemplateFillRun]:
        """List user's fill runs with eager loading of related data."""
        from sqlalchemy.orm import joinedload

        query = self.db.query(TemplateFillRun).filter(
            TemplateFillRun.user_id == user_id,
            TemplateFillRun.org_id == org_id
        )

        if status:
            query = query.filter(TemplateFillRun.status == status)

        # Eager load template relationship to avoid N+1 queries
        query = query.options(joinedload(TemplateFillRun.template))
        query = query.order_by(desc(TemplateFillRun.created_at))
        query = query.limit(limit).offset(offset)

        return query.all()

    def delete_fill_run(self, fill_run_id: str) -> bool:
        """Delete fill run and remove filled file from storage."""
        fill_run = self.get_fill_run(fill_run_id)
        if not fill_run:
            return False

        # Delete filled Excel file from R2 storage if it exists
        if fill_run.artifact and fill_run.artifact.get("key"):
            try:
                storage = get_storage_backend()
                storage_key = fill_run.artifact["key"]
                storage.delete(storage_key)
                logger.info(f"Deleted fill run file from storage: {storage_key}")
            except Exception as e:
                logger.warning(f"Failed to delete fill run file from storage: {e}")
                # Continue with DB deletion even if storage deletion fails

        # Hard delete from database
        self.db.delete(fill_run)
        self.db.commit()

        logger.info(f"Deleted fill run: {fill_run_id}")
        return True

    # ==================== Field Mapping Operations ====================

    def update_field_mapping(self, fill_run_id: str, field_mapping: Dict) -> Optional[TemplateFillRun]:
        """Update field mapping for a fill run."""
        return self.update_fill_run(fill_run_id, field_mapping=field_mapping)

    def get_field_mapping(self, fill_run_id: str) -> Optional[Dict]:
        """Get field mapping for a fill run."""
        fill_run = self.get_fill_run(fill_run_id)
        return fill_run.field_mapping if fill_run else None

    # ==================== Extracted Data Operations ====================

    def update_extracted_data(self, fill_run_id: str, extracted_data: Dict) -> Optional[TemplateFillRun]:
        """Update extracted data for a fill run."""
        return self.update_fill_run(fill_run_id, extracted_data=extracted_data)

    def get_extracted_data(self, fill_run_id: str) -> Optional[Dict]:
        """Get extracted data for a fill run."""
        fill_run = self.get_fill_run(fill_run_id)
        return fill_run.extracted_data if fill_run else None
