"""Repository for Real Estate AI Underwriting runs."""
from __future__ import annotations

import logging
from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.db_models_re import UnderwritingRun

logger = logging.getLogger(__name__)


class UnderwritingRunRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        user_id: str,
        name: str,
        asset_type: str = "self_storage",
        address: str | None = None,
        document_ids: list | None = None,
    ) -> UnderwritingRun:
        """Create and persist a new underwriting run, returning the hydrated record."""
        try:
            run = UnderwritingRun(
                user_id=user_id,
                name=name,
                asset_type=asset_type,
                address=address,
                document_ids=document_ids,
            )
            self.db.add(run)
            self.db.commit()
            self.db.refresh(run)
            return run
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("Failed to create underwriting run for user %s", user_id)
            raise

    def get(self, run_id: str, user_id: str) -> Optional[UnderwritingRun]:
        """Fetch a single run — always filters by user_id for security."""
        stmt = (
            select(UnderwritingRun)
            .where(UnderwritingRun.id == run_id)
            .where(UnderwritingRun.user_id == user_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_id(self, run_id: str) -> Optional[UnderwritingRun]:
        """Fetch by ID only — used for ownership resolution in SSE auth (no user filter)."""
        stmt = select(UnderwritingRun).where(UnderwritingRun.id == run_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list(self, user_id: str, limit: int = 20, offset: int = 0) -> List[UnderwritingRun]:
        """List runs for a user, newest first."""
        stmt = (
            select(UnderwritingRun)
            .where(UnderwritingRun.user_id == user_id)
            .order_by(UnderwritingRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())

    def update_status(
        self,
        run_id: str,
        status: str,
        error_message: str | None = None,
    ) -> bool:
        """Set the status (and optional error message) on a run. Returns False if not found."""
        run = self.db.get(UnderwritingRun, run_id)
        if not run:
            return False
        try:
            run.status = status
            if error_message is not None:
                run.error_message = error_message
            self.db.commit()
            return True
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("Failed to update status for run %s", run_id)
            raise

    def update_extraction(
        self,
        run_id: str,
        inputs: dict | None,
        field_citations: dict | None,
        discrepancies: list | None,
        extraction_job_id: str | None = None,
        citation_context: dict | None = None,
    ) -> bool:
        """Persist extracted inputs, citations, discrepancies, and citation_context onto the run."""
        run = self.db.get(UnderwritingRun, run_id)
        if not run:
            return False
        try:
            if inputs is not None:
                run.inputs = inputs
            if field_citations is not None:
                run.field_citations = field_citations
            if discrepancies is not None:
                run.discrepancies = discrepancies
            if extraction_job_id is not None:
                run.extraction_job_id = extraction_job_id
            if citation_context is not None:
                run.citation_context = citation_context
            self.db.commit()
            return True
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("Failed to update extraction for run %s", run_id)
            raise

    def update_result(self, run_id: str, result: dict, typed_metrics: dict) -> bool:
        """Store full calculation artifact, typed metric columns, verdict, and mark completed."""
        run = self.db.get(UnderwritingRun, run_id)
        if not run:
            return False

        try:
            run.result_artifact = result
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)

            # Typed metric columns
            metric_fields = [
                "irr", "cash_on_cash", "equity_multiple", "dscr_year_one",
                "ltv", "cap_rate_year_one", "cap_rate_pro_forma", "noi_year_one",
                "total_profit", "monthly_cashflow",
            ]
            for field in metric_fields:
                if field in typed_metrics:
                    setattr(run, field, typed_metrics[field])

            # Verdict
            if "verdict_status" in typed_metrics:
                run.verdict_status = typed_metrics["verdict_status"]
            if "verdict_failures" in typed_metrics:
                run.verdict_failures = typed_metrics["verdict_failures"]

            self.db.commit()
            return True
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("Failed to update result for run %s", run_id)
            raise

    def update_inputs(
        self,
        run_id: str,
        user_id: str,
        inputs: dict,
        field_citations: dict | None = None,
    ) -> bool:
        """Update wizard inputs after user edits — scoped to user for security."""
        run = self.get(run_id, user_id)
        if not run:
            return False
        try:
            run.inputs = inputs
            if field_citations is not None:
                run.field_citations = field_citations
            self.db.commit()
            return True
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("Failed to update inputs for run %s", run_id)
            raise

    def update_metadata(self, run_id: str, user_id: str, updates: dict) -> bool:
        """Update editable run metadata and mirror name/address into saved project inputs."""
        run = self.get(run_id, user_id)
        if not run:
            return False
        try:
            if "name" in updates:
                run.name = updates["name"]
            if "address" in updates:
                run.address = updates["address"]

            if run.inputs and any(key in updates for key in ("name", "address")):
                inputs = dict(run.inputs)
                project = dict(inputs.get("project") or {})
                if "name" in updates:
                    project["name"] = updates["name"]
                if "address" in updates:
                    project["address"] = updates["address"]
                inputs["project"] = project
                run.inputs = inputs

            self.db.commit()
            return True
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("Failed to update metadata for run %s", run_id)
            raise

    def update_loi_inputs(self, run_id: str, user_id: str, loi_inputs: dict) -> bool:
        """Update LOI inputs for a deal — scoped to user for security."""
        run = self.get(run_id, user_id)
        if not run:
            return False
        try:
            run.loi_inputs = loi_inputs
            self.db.commit()
            return True
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("Failed to update LOI inputs for run %s", run_id)
            raise

    def delete(self, run_id: str, user_id: str) -> bool:
        """Delete a run — scoped to user for security. Returns False if not found."""
        run = self.get(run_id, user_id)
        if not run:
            return False
        try:
            self.db.delete(run)
            self.db.commit()
            return True
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("Failed to delete run %s", run_id)
            raise

    def count(self, user_id: str) -> int:
        """Return the total number of runs for a user."""
        stmt = (
            select(func.count())
            .select_from(UnderwritingRun)
            .where(UnderwritingRun.user_id == user_id)
        )
        return self.db.execute(stmt).scalar_one()
