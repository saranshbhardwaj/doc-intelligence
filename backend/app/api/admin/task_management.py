"""Admin endpoints for managing stuck or problematic tasks.

Provides manual intervention tools for:
- Cancelling stuck workflow runs
- Cancelling stuck template fill runs
- Viewing task queue statistics
"""
from datetime import datetime
from typing import Dict
import logging

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.db_models_workflows import WorkflowRun
from app.db_models_templates import TemplateFillRun

router = APIRouter(prefix="/tasks", tags=["admin-tasks"])
logger = logging.getLogger(__name__)


class CancelTaskResponse(BaseModel):
    """Response model for task cancellation."""
    status: str
    task_id: str
    task_type: str  # "workflow_run" | "template_fill_run"
    previous_status: str
    message: str


class TaskStatistics(BaseModel):
    """Statistics about tasks in various states."""
    workflow_runs: Dict[str, int]  # {"queued": 2, "running": 1, "completed": 50, "failed": 3}
    template_fill_runs: Dict[str, int]
    total_stuck: int  # Total tasks in queued/running for >20 min


@router.post("/workflows/{run_id}/cancel", response_model=CancelTaskResponse)
async def cancel_workflow_run(run_id: str, db: Session = Depends(get_db)):
    """Manually cancel a stuck workflow run.

    Sets status to 'failed' with appropriate error message.
    Use this when a workflow is stuck in 'queued' or 'running' state.

    Args:
        run_id: Workflow run UUID

    Returns:
        Cancellation confirmation with previous status

    Raises:
        HTTPException 404: Workflow run not found
        HTTPException 400: Workflow already completed/failed
    """
    run = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()

    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")

    if run.status in ["completed", "failed"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel workflow that is already {run.status}"
        )

    previous_status = run.status
    run.status = "failed"
    run.error_message = "Manually cancelled by admin via /api/admin/tasks/workflows/{run_id}/cancel"
    run.completed_at = datetime.utcnow()

    db.commit()

    logger.warning(
        f"Admin cancelled workflow run {run_id} "
        f"(previous_status={previous_status}, workflow_id={run.workflow_id})"
    )

    return CancelTaskResponse(
        status="cancelled",
        task_id=run_id,
        task_type="workflow_run",
        previous_status=previous_status,
        message=f"Workflow run cancelled (was {previous_status})"
    )


@router.post("/template-fills/{run_id}/cancel", response_model=CancelTaskResponse)
async def cancel_template_fill_run(run_id: str, db: Session = Depends(get_db)):
    """Manually cancel a stuck template fill run.

    Sets status to 'failed' with appropriate error message.
    Use this when a template fill is stuck in 'queued' or 'running' state.

    Args:
        run_id: Template fill run UUID

    Returns:
        Cancellation confirmation with previous status

    Raises:
        HTTPException 404: Template fill run not found
        HTTPException 400: Template fill already completed/failed
    """
    run = db.query(TemplateFillRun).filter(TemplateFillRun.id == run_id).first()

    if not run:
        raise HTTPException(status_code=404, detail="Template fill run not found")

    if run.status in ["completed", "failed"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel template fill that is already {run.status}"
        )

    previous_status = run.status
    run.status = "failed"
    run.error_message = "Manually cancelled by admin via /api/admin/tasks/template-fills/{run_id}/cancel"
    run.completed_at = datetime.utcnow()

    db.commit()

    logger.warning(
        f"Admin cancelled template fill run {run_id} "
        f"(previous_status={previous_status})"
    )

    return CancelTaskResponse(
        status="cancelled",
        task_id=run_id,
        task_type="template_fill_run",
        previous_status=previous_status,
        message=f"Template fill run cancelled (was {previous_status})"
    )


@router.get("/statistics", response_model=TaskStatistics)
async def get_task_statistics(db: Session = Depends(get_db)):
    """Get statistics about tasks in various states.

    Useful for monitoring stuck tasks and overall system health.

    Returns:
        Task counts by status for workflow runs and template fills
    """
    from datetime import timedelta
    from sqlalchemy import func

    # Workflow run statistics
    workflow_stats = dict(
        db.query(WorkflowRun.status, func.count(WorkflowRun.id))
        .group_by(WorkflowRun.status)
        .all()
    )

    # Template fill statistics
    template_stats = dict(
        db.query(TemplateFillRun.status, func.count(TemplateFillRun.id))
        .group_by(TemplateFillRun.status)
        .all()
    )

    # Count stuck tasks (queued/running for >20 min)
    threshold = datetime.utcnow() - timedelta(minutes=20)
    stuck_workflows = db.query(WorkflowRun).filter(
        WorkflowRun.status.in_(["queued", "running"]),
        WorkflowRun.created_at < threshold
    ).count()

    stuck_templates = db.query(TemplateFillRun).filter(
        TemplateFillRun.status.in_(["queued", "running"]),
        TemplateFillRun.created_at < threshold
    ).count()

    return TaskStatistics(
        workflow_runs=workflow_stats,
        template_fill_runs=template_stats,
        total_stuck=stuck_workflows + stuck_templates
    )
