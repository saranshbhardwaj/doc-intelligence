"""Repository for job state database operations.

Data Access Layer for job tracking (used by both extraction and chat modes).

Pattern:
- All database queries go through repositories
- Endpoints/services call repositories (never SessionLocal directly)
- Repositories handle session management and error handling
- Makes testing easier with repository mocking
"""
from datetime import datetime
from typing import Optional
from contextlib import contextmanager
from typing import Generator
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import SessionLocal
from app.db_models import JobState
from app.utils.logging import logger
from app.utils.id_generator import generate_id


class JobRepository:
    """Repository for job state database operations.

    Encapsulates all database access for job tracking.
    Provides clean interface for CRUD operations.

    Usage:
        job_repo = JobRepository()
        job_repo.create_job(...)
        job_repo.update_progress(...)
    """

    @contextmanager
    def _get_session(self) -> Generator[Session, None, None]:
        """Context manager for database sessions.

        Ensures sessions are properly closed even on errors.

        Yields:
            Session: SQLAlchemy database session
        """
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    # ============================================================================
    # JOB CREATION
    # ============================================================================

    def create_job(
        self,
        extraction_id: Optional[str] = None,
        document_id: Optional[str] = None,
        workflow_run_id: Optional[str] = None,
        template_fill_run_id: Optional[str] = None,
        status: str = "queued",
        current_stage: str = "queued",
        progress_percent: int = 0,
        message: str = "Queued for processing...",
        job_id: Optional[str] = None
    ) -> Optional[JobState]:
        """Create a new job state record.

        Supports Extract Mode, Chat Mode, and Workflow Mode:
        - Extract Mode: Pass extraction_id
        - Chat Mode: Pass document_id (references canonical documents table)
        - Workflow Mode: Pass workflow_run_id

        Args:
            extraction_id: ID of extraction (for Extract Mode)
            document_id: ID of canonical document (for Chat Mode)
            workflow_run_id: ID of workflow run (for Workflow Mode)
            status: Job status (default: "queued")
            current_stage: Current processing stage (default: "queued")
            progress_percent: Progress percentage 0-100 (default: 0)
            message: Status message (default: "Queued for processing...")
            job_id: Optional custom job ID (default: auto-generated)

        Returns:
            JobState object if successful, None on error
        """
        if not extraction_id and not document_id and not workflow_run_id and not template_fill_run_id:
            logger.error("Must provide one of extraction_id, document_id, workflow_run_id, or template_fill_run_id")
            return None
        # Ensure caller does not set more than one (business rule; DB constraint will also enforce)
        provided = [v for v in [extraction_id, document_id, workflow_run_id, template_fill_run_id] if v]
        if len(provided) != 1:
            logger.error("Exactly one of extraction_id, document_id, workflow_run_id, template_fill_run_id must be provided", extra={
                "extraction_id": extraction_id,
                "document_id": document_id,
                "workflow_run_id": workflow_run_id,
                "template_fill_run_id": template_fill_run_id
            })
            return None

        with self._get_session() as db:
            try:
                # Generate job_id if not provided
                if not job_id:
                    job_id = generate_id()

                job = JobState(
                    job_id=job_id,  # Job tracking ID (required)
                    extraction_id=extraction_id,
                    document_id=document_id,
                    workflow_run_id=workflow_run_id,
                    template_fill_run_id=template_fill_run_id,
                    status=status,
                    current_stage=current_stage,
                    progress_percent=progress_percent,
                    message=message
                )
                db.add(job)
                db.commit()
                db.refresh(job)

                logger.info(
                    f"Created job state record",
                    extra={
                        "job_id": job.job_id,  # Log tracking ID, not primary key
                        "extraction_id": extraction_id,
                        "document_id": document_id,
                        "status": status,
                        "workflow_run_id": workflow_run_id
                    }
                )

                return job

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to create job state: {e}",
                    extra={
                        "extraction_id": extraction_id,
                        "document_id": document_id,
                        "error": str(e)
                    }
                )
                db.rollback()
                return None

    # ============================================================================
    # JOB RETRIEVAL
    # ============================================================================

    def get_job(self, job_id: str) -> Optional[JobState]:
        """Get job by job_id (tracking ID).

        Args:
            job_id: Job tracking ID

        Returns:
            JobState object if found, None otherwise
        """
        with self._get_session() as db:
            try:
                return db.query(JobState).filter(
                    JobState.job_id == job_id
                ).first()
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get job: {e}",
                    extra={"job_id": job_id, "error": str(e)}
                )
                return None

    def get_job_by_extraction_id(self, extraction_id: str) -> Optional[JobState]:
        """Get job by extraction ID.

        Args:
            extraction_id: Extraction ID

        Returns:
            JobState object if found, None otherwise
        """
        with self._get_session() as db:
            try:
                return db.query(JobState).filter(
                    JobState.extraction_id == extraction_id
                ).first()
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get job by extraction_id: {e}",
                    extra={"extraction_id": extraction_id, "error": str(e)}
                )
                return None

    def get_job_by_document_id(self, document_id: str) -> Optional[JobState]:
        """Get job by document ID.

        Args:
            document_id: Canonical document ID

        Returns:
            JobState object if found, None otherwise
        """
        with self._get_session() as db:
            try:
                return db.query(JobState).filter(
                    JobState.document_id == document_id
                ).first()
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get job by document_id: {e}",
                    extra={"document_id": document_id, "error": str(e)}
                )
                return None

    def get_job_by_workflow_run_id(self, workflow_run_id: str) -> Optional[JobState]:
        """Get job by workflow run ID.

        Args:
            workflow_run_id: WorkflowRun ID

        Returns:
            JobState object if found, None otherwise
        """
        with self._get_session() as db:
            try:
                return db.query(JobState).filter(
                    JobState.workflow_run_id == workflow_run_id
                ).first()
            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to get job by workflow_run_id: {e}",
                    extra={"workflow_run_id": workflow_run_id, "error": str(e)}
                )
                return None

    # ============================================================================
    # JOB UPDATES
    # ============================================================================

    def update_job(
        self,
        job_id: str,
        status: Optional[str] = None,
        current_stage: Optional[str] = None,
        progress_percent: Optional[int] = None,
        message: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> bool:
        """Update job state fields.

        Args:
            job_id: Job tracking ID
            status: Updated status (processing, completed, failed)
            current_stage: Updated processing stage
            progress_percent: Updated progress percentage (0-100)
            message: Updated status message
            metadata: Additional metadata

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                job = db.query(JobState).filter(
                    JobState.job_id == job_id
                ).first()

                if not job:
                    logger.warning(
                        f"Job not found for update: {job_id}",
                        extra={"job_id": job_id}
                    )
                    return False

                # Update provided fields
                if status is not None:
                    job.status = status
                if current_stage is not None:
                    job.current_stage = current_stage
                if progress_percent is not None:
                    job.progress_percent = progress_percent
                if message is not None:
                    job.message = message
                if metadata is not None:
                    job.metadata = metadata

                # Update timestamps
                if status == "completed":
                    job.completed_at = datetime.now()
                elif status == "failed":
                    job.failed_at = datetime.now()

                db.commit()

                logger.debug(
                    f"Updated job state",
                    extra={"job_id": job_id, "status": status}
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to update job state: {e}",
                    extra={"job_id": job_id, "error": str(e)}
                )
                db.rollback()
                return False

    def update_progress(
        self,
        job_id: str,
        progress_percent: int,
        message: str,
        current_stage: Optional[str] = None
    ) -> bool:
        """Update job progress.

        Convenience method for updating progress during processing.

        Args:
            job_id: Job ID
            progress_percent: Progress percentage (0-100)
            message: Status message
            current_stage: Optional stage update

        Returns:
            True if successful, False otherwise
        """
        return self.update_job(
            job_id=job_id,
            status="processing",
            current_stage=current_stage,
            progress_percent=progress_percent,
            message=message
        )

    def reset_for_retry(
        self,
        job_id: str,
        message: str = "Queued for retry (extracting stage)"
    ) -> bool:
        """Reset a job back to queued state for retry.

        Clears error fields and marks job as retryable.

        Args:
            job_id: Job tracking ID
            message: Status message for retry queueing

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                job = db.query(JobState).filter(JobState.job_id == job_id).first()
                if not job:
                    logger.warning(
                        "Job not found for retry reset",
                        extra={"job_id": job_id}
                    )
                    return False

                job.status = "queued"
                job.current_stage = "queued"
                job.progress_percent = 0
                job.message = message
                job.error_stage = None
                job.error_message = None
                job.error_type = None
                job.is_retryable = True

                db.commit()
                logger.info(
                    "Reset job state for retry",
                    extra={"job_id": job_id}
                )
                return True
            except SQLAlchemyError as e:
                db.rollback()
                logger.error(
                    "Failed to reset job state for retry",
                    extra={"job_id": job_id, "error": str(e)}
                )
                return False

    def mark_completed(
        self,
        job_id: str,
        message: str = "Processing completed successfully"
    ) -> bool:
        """Mark job as completed.

        Args:
            job_id: Job ID
            message: Completion message

        Returns:
            True if successful, False otherwise
        """
        return self.update_job(
            job_id=job_id,
            status="completed",
            progress_percent=100,
            message=message
        )

    def mark_failed(
        self,
        job_id: str,
        error_message: str
    ) -> bool:
        """Mark job as failed.

        Args:
            job_id: Job ID
            error_message: Error description

        Returns:
            True if successful, False otherwise
        """
        return self.update_job(
            job_id=job_id,
            status="failed",
            message=error_message
        )

    def delete_job(self, job_id: str) -> bool:
        """Delete a job state record.

        Args:
            job_id: Job tracking ID

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                job = db.query(JobState).filter(
                    JobState.job_id == job_id
                ).first()

                if not job:
                    logger.warning(
                        f"Job not found for deletion: {job_id}",
                        extra={"job_id": job_id}
                    )
                    return False

                db.delete(job)
                db.commit()

                logger.info(
                    f"Deleted job state",
                    extra={"job_id": job_id}
                )

                return True

            except SQLAlchemyError as e:
                logger.error(
                    f"Failed to delete job state: {e}",
                    extra={"job_id": job_id, "error": str(e)}
                )
                db.rollback()
                return False
