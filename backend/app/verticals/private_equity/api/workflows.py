"""Private Equity Workflows API - Vertical-specific workflow endpoints.

Routes: /api/v1/pe/workflows/*

Filters workflows by domain='private_equity' automatically.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import json

from app.database import get_db
from app.repositories.workflow_repository import WorkflowRepository
from app.auth import get_current_user
from app.db_models_users import User
from app.utils.logging import logger
from app.verticals.private_equity.workflows.tasks import start_workflow_chain
from app.schemas.workflows import (
    WorkflowTemplateListItem,
    WorkflowTemplateDetail,
    WorkflowVariableSchema,
    WorkflowRunListItem,
    WorkflowRunDetail,
    DocumentSummary,
)
from pydantic import BaseModel, Field

# Reuse schemas from main workflows API
from app.api.workflows import (
    CreateWorkflowRunRequest,
    RerunWorkflowRequest,
    WorkflowRunOut,
)

router = APIRouter(prefix="/workflows", tags=["pe_workflows"])


@router.get("/templates", response_model=List[WorkflowTemplateListItem])
def list_pe_workflow_templates(db: Session = Depends(get_db)):
    """List all active PE workflow templates.

    Automatically filters to domain='private_equity'.
    """
    repo = WorkflowRepository(db)
    workflows = repo.list_workflows(active_only=True, domain="private_equity")
    return [
        WorkflowTemplateListItem(
            id=wf.id,
            name=wf.name,
            domain=wf.domain,
            category=wf.category,
            description=wf.description,
            output_format=wf.output_format,
            prompt_template=wf.prompt_template,
            user_prompt_template=wf.user_prompt_template,
            user_prompt_max_length=wf.user_prompt_max_length,
            variables_schema=wf.variables_schema,
            min_documents=wf.min_documents,
            max_documents=wf.max_documents,
            version=wf.version,
            active=wf.active,
        )
        for wf in workflows
    ]


@router.get("/templates/{workflow_id}", response_model=WorkflowTemplateDetail)
def get_pe_workflow_template(workflow_id: str, db: Session = Depends(get_db)):
    """Get PE workflow template details."""
    repo = WorkflowRepository(db)
    wf = repo.get_workflow(workflow_id)
    if not wf or not wf.active:
        raise HTTPException(status_code=404, detail="Workflow not found or inactive")

    # Ensure this is a PE workflow
    if wf.domain != "private_equity":
        raise HTTPException(status_code=404, detail="Workflow not found in PE vertical")

    # Parse variables schema
    variables_schema = None
    if wf.variables_schema:
        try:
            schema_dict = json.loads(wf.variables_schema)
            variables_schema = [
                WorkflowVariableSchema(**var) for var in schema_dict.get("variables", [])
            ]
        except Exception as e:
            logger.error("Failed to parse variables_schema", extra={"workflow_id": workflow_id, "error": str(e)})

    return WorkflowTemplateDetail(
        id=wf.id,
        name=wf.name,
        domain=wf.domain,
        category=wf.category,
        description=wf.description,
        output_format=wf.output_format,
        prompt_template=wf.prompt_template,
        user_prompt_template=wf.user_prompt_template,
        user_prompt_max_length=wf.user_prompt_max_length,
        min_documents=wf.min_documents,
        max_documents=wf.max_documents,
        version=wf.version,
        active=wf.active,
        variables_schema=variables_schema,
    )


@router.post("/runs", response_model=WorkflowRunOut)
def create_pe_workflow_run(
    payload: CreateWorkflowRunRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new PE workflow run."""
    repo = WorkflowRepository(db)
    workflow = repo.get_workflow(payload.workflow_id)
    if not workflow or not workflow.active:
        raise HTTPException(status_code=404, detail="Workflow not found or inactive")

    # Ensure this is a PE workflow
    if workflow.domain != "private_equity":
        raise HTTPException(status_code=403, detail="Cannot run non-PE workflows from PE vertical")

    # Delegate to main workflows logic
    from app.api.workflows import create_workflow_run as main_create
    return main_create(payload, user, db)


@router.get("/runs/{run_id}", response_model=WorkflowRunOut)
def get_pe_workflow_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get PE workflow run details."""
    from app.api.workflows import get_workflow_run as main_get
    return main_get(run_id, user, db)


@router.get("/runs", response_model=List[WorkflowRunListItem])
def list_pe_workflow_runs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    """List user's PE workflow runs (filtered by domain='private_equity')."""
    logger.info("Listing PE workflow runs", extra={"user_id": user.id, "limit": limit, "offset": offset})
    repo = WorkflowRepository(db)

    # Get all runs for user
    all_runs = repo.list_runs_for_user(user.id, limit=limit * 2, offset=offset)  # Get more to filter

    # Filter to PE workflows only
    pe_runs = [run for run in all_runs if run.workflow and run.workflow.domain == "private_equity"][:limit]

    result = []
    for run in pe_runs:
        # Parse artifact (handle both old JSON strings and new Python objects)
        artifact = run.artifact
        if isinstance(artifact, str):
            artifact = json.loads(artifact) if artifact else None

        result.append(
            WorkflowRunListItem(
                id=run.id,
                workflow_id=run.workflow_id,
                workflow_name=run.workflow.name if run.workflow else None,
                status=run.status,
                mode=run.mode,
                output_format=run.output_format,
                created_at=run.created_at,
                completed_at=run.completed_at,
                latency_ms=run.latency_ms,
                cost_usd=run.cost_usd,
                error_message=run.error_message,
                artifact_json=artifact,
            )
        )
    return result


@router.get("/documents", response_model=List[DocumentSummary])
def list_pe_available_documents(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    collection_id: Optional[str] = None,
):
    """List documents available for PE workflows."""
    from app.api.workflows import list_available_documents as main_list
    return main_list(user, db, collection_id)


@router.get("/runs/{run_id}/artifact")
def get_pe_workflow_artifact(
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get PE workflow run artifact."""
    from app.api.workflows import get_workflow_artifact as main_get
    return main_get(run_id, user, db)


@router.delete("/runs/{run_id}")
def delete_pe_workflow_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a PE workflow run."""
    from app.api.workflows import delete_workflow_run as main_delete
    return main_delete(run_id, user, db)


@router.post("/runs/{run_id}/export")
def export_pe_workflow_run(
    run_id: str,
    format: str = 'word',
    delivery: str = 'stream',
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export PE workflow run to Word, Excel, or PDF."""
    from app.api.workflows import export_workflow_run as main_export
    return main_export(run_id, format, delivery, user, db)


@router.post("/runs/{run_id}/rerun", response_model=WorkflowRunOut)
def rerun_pe_workflow(
    run_id: str,
    payload: RerunWorkflowRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Re-run a PE workflow with modified parameters."""
    from app.api.workflows import rerun_workflow as main_rerun
    return main_rerun(run_id, payload, user, db)
