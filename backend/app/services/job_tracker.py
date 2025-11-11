# app/services/job_tracker.py
"""Job progress tracking service

Manages job state updates and persistence.
Separated from jobs.py API to avoid circular imports with orchestrator services.
"""
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.db_models import JobState
from app.repositories.job_repository import JobRepository
from app.utils.logging import logger
from app.services.pubsub import publish_event  # lightweight fire-and-forget


class JobProgressTracker:
    """Manages job state updates and broadcasts progress events"""

    def __init__(self, db: Session, job_id: str):
        self.db = db
        self.job_id = job_id
        self._listeners = []
        # Commit throttling state to avoid hammering the DB and blocking event loop
        self._last_progress_percent: int | None = None
        self._last_status: str | None = None
        self._last_stage: str | None = None
        self._last_commit_monotonic: float = 0.0
        self._throttle_seconds: float = 0.75  # minimum interval between lightweight progress commits
        self._min_progress_delta: int = 3     # commit only if progress advanced this much

    def get_job_state(self) -> JobState:
        """Get current job state from database using the tracker's session"""
        job = self.db.query(JobState).filter(JobState.id == self.job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {self.job_id} not found")
        return job

    def update_progress(
        self,
        status: str = None,
        current_stage: str = None,
        progress_percent: int = None,
        message: str = None,
        details: dict = None,
        **stage_flags
    ):
        """Update job progress and persist to database"""
        job = self.get_job_state()

        if status:
            job.status = status
        if current_stage:
            job.current_stage = current_stage
        if progress_percent is not None:
            job.progress_percent = progress_percent
        if message:
            job.message = message
        if details:
            job.details = details

        # Update stage completion flags
        for flag_name, flag_value in stage_flags.items():
            if hasattr(job, flag_name):
                setattr(job, flag_name, flag_value)

        # Decide whether to commit (throttle simple progress updates)
        import time as _time
        now = _time.monotonic()

        stage_changed = (current_stage and current_stage != self._last_stage)
        status_changed = (status and status != self._last_status)
        progress_changed = (
            progress_percent is not None and
            (self._last_progress_percent is None or abs(progress_percent - self._last_progress_percent) >= self._min_progress_delta)
        )

        # Force commit if stage/status changed or we have flags marking stage completion
        flags_set = any(stage_flags.values())
        time_elapsed = (now - self._last_commit_monotonic) >= self._throttle_seconds

        should_commit = stage_changed or status_changed or flags_set or progress_changed or time_elapsed

        if should_commit:
            job.updated_at = datetime.now()
            self.db.commit()
            # refresh only on substantive change to reduce DB round-trips
            if stage_changed or status_changed or flags_set:
                self.db.refresh(job)

            # Update last commit state trackers
            if progress_percent is not None:
                self._last_progress_percent = progress_percent
            if status:
                self._last_status = status
            if current_stage:
                self._last_stage = current_stage
            self._last_commit_monotonic = now

        if should_commit:
            logger.info(
                f"Job {self.job_id} updated: {status or 'progress'} - {message}",
                extra={
                    "job_id": self.job_id,
                    "status": job.status,
                    "progress": job.progress_percent,
                    "details": job.details if job.details else {},
                    "throttled": False
                }
            )
            # Publish progress event (only on commit)
            try:
                publish_event(self.job_id, "progress", {
                    "status": job.status,
                    "current_stage": job.current_stage,
                    "progress_percent": job.progress_percent,
                    "message": job.message,
                    "details": job.details or {}
                })
            except Exception:
                # Already logged inside publish_event; no re-raise
                pass
        else:
            logger.debug(f"Job {self.job_id} progress throttled (no commit)", extra={
                "job_id": self.job_id,
                "status": job.status,
                "progress": job.progress_percent,
                "details": job.details or {},
                "throttled": True
            })

    def mark_error(
        self,
        error_stage: str,
        error_message: str,
        error_type: str = "unknown_error",
        is_retryable: bool = True
    ):
        """Mark job as failed with error details"""
        job = self.get_job_state()
        job.status = "failed"
        job.error_stage = error_stage
        job.error_message = error_message[:1000]  # Truncate long errors
        job.error_type = error_type
        job.is_retryable = is_retryable
        job.updated_at = datetime.now()
        self.db.commit()
        self.db.refresh(job)

        logger.error(f"Job {self.job_id} failed at {error_stage}: {error_message}", extra={
            "job_id": self.job_id,
            "error_stage": error_stage,
            "error_type": error_type,
            "details": job.details or {}
        })
        try:
            publish_event(self.job_id, "error", {
                "stage": job.error_stage,
                "message": job.error_message,
                "type": job.error_type,
                "retryable": job.is_retryable
            })
            publish_event(self.job_id, "end", {"reason": "failed", "job_id": self.job_id})
        except Exception:
            pass

    def mark_completed(self):
        """Mark job as successfully completed"""
        job = self.get_job_state()
        job.status = "completed"
        job.progress_percent = 100
        job.current_stage = "completed"
        job.message = "Extraction completed successfully"
        job.completed_at = datetime.now()
        job.updated_at = datetime.now()
        self.db.commit()
        self.db.refresh(job)

        logger.info(f"Job {self.job_id} completed successfully", extra={
            "job_id": self.job_id
        })
        try:
            publish_event(self.job_id, "complete", {
                "message": job.message or "Extraction completed successfully",
                "extraction_id": job.extraction_id
            })
            publish_event(self.job_id, "end", {"reason": "completed", "job_id": self.job_id})
        except Exception:
            pass

    def save_intermediate_result(
        self,
        stage: str,
        file_path: str
    ):
        """Save path to intermediate result for resume capability"""
        job = self.get_job_state()

        path_mapping = {
            "parsing": "parsed_output_path",
            "chunking": "chunks_path",
            "summarizing": "summaries_path",
            "combining": "combined_context_path"
        }

        if stage in path_mapping:
            setattr(job, path_mapping[stage], file_path)
            job.updated_at = datetime.now()
            self.db.commit()

            logger.info(f"Saved {stage} result to {file_path}", extra={
                "job_id": self.job_id,
                "stage": stage
            })
            # Optional: publish intermediate artifact path for frontend debugging (not consumed yet)
            try:
                publish_event(self.job_id, "progress", {
                    "status": job.status,
                    "current_stage": stage,
                    "progress_percent": job.progress_percent,
                    "message": f"Saved {stage} result",
                    "details": {"artifact_path": file_path}
                })
            except Exception:
                pass
