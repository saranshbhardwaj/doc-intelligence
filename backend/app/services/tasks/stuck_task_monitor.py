"""Background task to clean up stuck workflow runs and template fills.

Runs periodically via Celery Beat to fail tasks stuck in 'queued' or 'running'
status for longer than the configured threshold (default: 20 minutes).

This prevents:
- UI hanging forever on stuck workflows
- Database bloat from abandoned runs
- Confusion from stale "in progress" tasks

Add to Celery Beat schedule:
    celery_app.conf.beat_schedule = {
        'cleanup-stuck-tasks': {
            'task': 'app.services.tasks.stuck_task_monitor.cleanup_stuck_tasks',
            'schedule': crontab(minute='*/10'),  # Run every 10 minutes
        },
    }
"""
from datetime import datetime, timedelta
from typing import Dict, Any
import logging

from celery import shared_task
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_models import JobState
from app.db_models_workflows import WorkflowRun
from app.db_models_templates import TemplateFillRun
from app.services.pubsub import publish_event

logger = logging.getLogger(__name__)

# Threshold: fail tasks stuck longer than this
STUCK_THRESHOLD_MINUTES = 20


@shared_task(name="app.services.tasks.stuck_task_monitor.cleanup_stuck_tasks")
def cleanup_stuck_tasks() -> Dict[str, Any]:
    """Find and fail workflow/template runs stuck in queued/running status.

    Returns:
        Dict with cleanup statistics:
        {
            "workflow_runs_failed": 3,
            "template_fill_runs_failed": 1,
            "threshold_minutes": 20
        }
    """
    threshold = datetime.utcnow() - timedelta(minutes=STUCK_THRESHOLD_MINUTES)

    workflow_count = 0
    template_count = 0

    try:
        with next(get_db()) as db:
            # Clean up stuck workflow runs
            workflow_count = _cleanup_stuck_workflow_runs(db, threshold)

            # Clean up stuck template fill runs
            template_count = _cleanup_stuck_template_fills(db, threshold)

            db.commit()

            if workflow_count + template_count > 0:
                logger.warning(
                    f"Cleaned up {workflow_count} stuck workflow runs and "
                    f"{template_count} stuck template fills (threshold: {STUCK_THRESHOLD_MINUTES} min)"
                )

            return {
                "workflow_runs_failed": workflow_count,
                "template_fill_runs_failed": template_count,
                "threshold_minutes": STUCK_THRESHOLD_MINUTES,
            }

    except Exception as e:
        logger.error(f"Failed to cleanup stuck tasks: {e}", exc_info=True)
        return {
            "error": str(e),
            "workflow_runs_failed": workflow_count,
            "template_fill_runs_failed": template_count,
        }


def _cleanup_stuck_workflow_runs(db: Session, threshold: datetime) -> int:
    """Fail workflow runs stuck in queued/running status."""
    stuck_runs = db.query(WorkflowRun).filter(
        WorkflowRun.status.in_(["queued", "running"]),
        WorkflowRun.created_at < threshold
    ).all()

    if not stuck_runs:
        return 0

    # Batch-fetch JobState records for all stuck runs (avoids N+1 queries)
    run_ids = [run.id for run in stuck_runs]
    jobs_by_run_id = {
        job.workflow_run_id: job
        for job in db.query(JobState).filter(
            JobState.workflow_run_id.in_(run_ids)
        ).all()
        if job.workflow_run_id
    }

    for run in stuck_runs:
        original_status = run.status
        logger.warning(
            f"Failing stuck workflow run {run.id} "
            f"(status={original_status}, created_at={run.created_at}, "
            f"workflow_id={run.workflow_id})"
        )

        run.status = "failed"
        run.error_message = (
            f"Task timeout - exceeded {STUCK_THRESHOLD_MINUTES} minute threshold. "
            f"Original status: {original_status}"
        )
        run.completed_at = datetime.utcnow()

        job = jobs_by_run_id.get(run.id)
        if job:
            # publish_event sends {"event": ..., "payload": ...} — the format api/jobs.py expects.
            # SSE endpoint auto-sends "end" after "error", so one publish is enough.
            publish_event(job.job_id, "error", {
                "message": run.error_message,
                "stage": "monitoring",
                "type": "timeout",
                "isRetryable": False,
            })
            logger.info(f"Published SSE timeout event for stuck workflow {run.id} (job_id={job.job_id})")

    return len(stuck_runs)


def _cleanup_stuck_template_fills(db: Session, threshold: datetime) -> int:
    """Fail template fill runs stuck in queued/running status."""
    stuck_runs = db.query(TemplateFillRun).filter(
        TemplateFillRun.status.in_(["queued", "running"]),
        TemplateFillRun.created_at < threshold
    ).all()

    if not stuck_runs:
        return 0

    # Batch-fetch JobState records for all stuck runs (avoids N+1 queries)
    run_ids = [run.id for run in stuck_runs]
    jobs_by_run_id = {
        job.entity_id: job
        for job in db.query(JobState).filter(
            JobState.entity_type == "template_fill_run",
            JobState.entity_id.in_(run_ids),
        ).all()
    }

    for run in stuck_runs:
        original_status = run.status
        logger.warning(
            f"Failing stuck template fill run {run.id} "
            f"(status={original_status}, created_at={run.created_at})"
        )
        run.status = "failed"
        run.error_message = (
            f"Task timeout - exceeded {STUCK_THRESHOLD_MINUTES} minute threshold. "
            f"Original status: {original_status}"
        )
        run.completed_at = datetime.utcnow()

        job = jobs_by_run_id.get(run.id)
        if job:
            publish_event(job.job_id, "error", {
                "message": run.error_message,
                "stage": "monitoring",
                "type": "timeout",
                "isRetryable": False,
            })
            logger.info(f"Published SSE timeout event for stuck template fill {run.id} (job_id={job.job_id})")

    return len(stuck_runs)
