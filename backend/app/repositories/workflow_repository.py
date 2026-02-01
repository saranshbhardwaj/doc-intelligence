"""Repository for workflow templates and workflow runs."""
from typing import Optional, List
from contextlib import contextmanager
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db_models_workflows import Workflow, WorkflowRun
from app.database import SessionLocal
import json
from app.utils.id_generator import generate_id


class WorkflowRepository:
    def __init__(self, db: Session):
        self.db = db

    @contextmanager
    def _get_session(self):
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    @classmethod
    def get_run_by_id(cls, run_id: str) -> Optional[WorkflowRun]:
        """Fetch a WorkflowRun by ID using an internal session."""
        repo = cls(SessionLocal())
        try:
            return repo.db.get(WorkflowRun, run_id)
        finally:
            repo.db.close()

    # ---- Workflows ----
    def list_workflows(self, active_only: bool = True, domain: str | None = None) -> List[Workflow]:
        stmt = select(Workflow)
        if active_only:
            stmt = stmt.where(Workflow.active == True)  # noqa: E712
        if domain:
            stmt = stmt.where(Workflow.domain == domain)
        return list(self.db.execute(stmt).scalars())

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        return self.db.get(Workflow, workflow_id)

    def create_workflow(self, name: str, prompt_template: str, domain: str = "private_equity",
                        category: str | None = None,
                        variables_schema: dict | None = None, retrieval_spec: list | None = None,
                        output_schema: dict = None,
                        output_format: str = "markdown",
                        min_documents: int = 1, max_documents: int | None = None, version: int = 1,
                        description: str | None = None, user_prompt_template: str | None = None,
                        user_prompt_max_length: int | None = None) -> Workflow:
        wf = Workflow(
            name=name,
            domain=domain,
            category=category,
            description=description,
            prompt_template=prompt_template,
            user_prompt_template=user_prompt_template,
            user_prompt_max_length=user_prompt_max_length,
            variables_schema=json.dumps(variables_schema or {}),
            retrieval_spec_json=json.dumps(retrieval_spec) if retrieval_spec else None,
            output_schema=json.dumps(output_schema) if output_schema else None,
            output_format=output_format,
            min_documents=min_documents,
            max_documents=max_documents,
            version=version,
        )
        self.db.add(wf)
        self.db.commit()
        self.db.refresh(wf)
        return wf

    def delete_workflow(self, name: str) -> bool:
        stmt = select(Workflow).where(Workflow.name == name)
        wf = self.db.execute(stmt).scalar_one_or_none()
        if not wf:
            return False
        self.db.delete(wf)
        self.db.commit()
        return True
    # ---- Workflow Runs ----
    def create_run(self, workflow: Workflow, user_id: str, collection_id: str | None,
                   document_ids: List[str], variables: dict, mode: str, strategy: str) -> WorkflowRun:
        # Create snapshot of workflow at execution time to preserve context
        workflow_snapshot = {
            "name": workflow.name,
            "description": workflow.description,
            "version": workflow.version,
            "category": workflow.category,
        }

        run = WorkflowRun(
            id=generate_id(),
            workflow_id=workflow.id,
            user_id=user_id,
            collection_id=collection_id,
            document_ids=document_ids,  # JSON column auto-serializes
            variables=variables,        # JSON column auto-serializes
            workflow_snapshot=workflow_snapshot,  # Snapshot for historical preservation
            mode=mode,
            strategy=strategy,
            version=workflow.version,
            output_format=workflow.output_format,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def update_run_status(self, run_id: str, status: str, error_message: str | None = None,
                          artifact_json: dict | None = None, token_usage: int | None = None,
                          cost_usd: float | None = None, latency_ms: int | None = None, currency: str | None = None,
                          citations_count: int | None = None, citation_invalid_count: int | None = None,
                          attempts: int | None = None, validation_errors_json: str | None = None,
                          context_stats_json: dict | None = None):
        run = self.db.get(WorkflowRun, run_id)
        if not run:
            return False
        run.status = status
        if error_message:
            run.error_message = error_message[:500]
        if artifact_json:
            run.artifact = artifact_json  # JSON column auto-serializes, no need for json.dumps()
        if token_usage is not None:
            run.token_usage = token_usage
        if cost_usd is not None:
            run.cost_usd = cost_usd
        if latency_ms is not None:
            run.latency_ms = latency_ms
        if currency is not None:
            run.currency = currency
        if citations_count is not None:
            run.citations_count = citations_count
        if citation_invalid_count is not None:
            run.citation_invalid_count = citation_invalid_count
        if attempts is not None:
            run.attempts = attempts
        if validation_errors_json is not None:
            # Note: parameter named _json but column is just validation_errors
            # Currently receiving pre-serialized string, but JSON column expects dict/list
            run.validation_errors = json.loads(validation_errors_json) if isinstance(validation_errors_json, str) else validation_errors_json
        if context_stats_json is not None:
            run.context_stats = context_stats_json  # JSON column auto-serializes
        if status == "running" and run.started_at is None:
            from datetime import datetime
            run.started_at = datetime.utcnow()
        if status == "completed" and run.completed_at is None:
            from datetime import datetime
            run.completed_at = datetime.utcnow()
        self.db.commit()
        return True

    def get_run(self, run_id: str) -> Optional[WorkflowRun]:
        return self.db.get(WorkflowRun, run_id)

    def update_run_metadata(self, run_id: str, metadata: dict) -> bool:
        """
        Update JSONB metadata fields for a workflow run.

        Args:
            run_id: Workflow run ID
            metadata: Dict with metadata fields to update (e.g., {"section_summaries": {...}})

        Returns:
            True if successful, False if run not found
        """
        run = self.db.get(WorkflowRun, run_id)
        if not run:
            return False

        # Update metadata fields (JSONB columns auto-serialize)
        for key, value in metadata.items():
            if hasattr(run, key):
                setattr(run, key, value)
            else:
                # Log warning if field doesn't exist
                import logging
                logging.warning(f"WorkflowRun has no attribute '{key}', skipping metadata update")

        self.db.commit()
        return True

    def list_runs_for_user(self, user_id: str, limit: int = 50, offset: int = 0) -> List[WorkflowRun]:
        """List workflow runs for a user with pagination.

        Args:
            user_id: The user whose runs to list.
            limit: Max number of runs to return.
            offset: Number of runs to skip (for pagination).
        """
        # Sanitize pagination inputs
        if limit <= 0:
            limit = 50
        if offset < 0:
            offset = 0

        stmt = (
            select(WorkflowRun)
            .where(WorkflowRun.user_id == user_id)
            .order_by(WorkflowRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())
