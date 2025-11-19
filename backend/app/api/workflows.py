"""API endpoints for workflow templates and workflow runs."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from typing import List, Optional
import json

from app.database import get_db
from app.repositories.workflow_repository import WorkflowRepository
from app.db_models_workflows import Workflow, WorkflowRun
from app.db_models_chat import CollectionDocument, DocumentChunk, Collection
from app.db_models_documents import Document
from app.auth import get_current_user
from app.db_models_users import User
from app.utils.logging import logger
from app.services.tasks.workflows import start_workflow_chain
from app.schemas.workflows import (
    WorkflowTemplateListItem,
    WorkflowTemplateDetail,
    WorkflowVariableSchema,
    WorkflowRunListItem,
    WorkflowRunDetail,
    DocumentSummary,
)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


# -------------------- Pydantic Schemas --------------------
from pydantic import BaseModel, Field


class WorkflowTemplateOut(BaseModel):
    id: str
    name: str
    category: Optional[str]
    description: Optional[str]
    output_format: str
    min_documents: int
    max_documents: Optional[int]
    version: int
    active: bool

    class Config:
        from_attributes = True


class CreateWorkflowRunRequest(BaseModel):
    workflow_id: str = Field(..., description="ID of workflow template")
    collection_id: Optional[str] = Field(None, description="Collection to draw documents from")
    document_ids: Optional[List[str]] = Field(None, description="Specific document IDs (override collection)")
    variables: dict = Field(default_factory=dict)
    strategy: Optional[str] = Field(None, description="Context assembly strategy override")
    custom_prompt: Optional[str] = Field(None, description="User-edited prompt (uses template's user_prompt_max_length)", max_length=10000)


class RerunWorkflowRequest(BaseModel):
    """Request to re-run a workflow with optionally modified parameters."""
    collection_id: Optional[str] = Field(None, description="Override collection (uses original if not provided)")
    document_ids: Optional[List[str]] = Field(None, description="Override documents (uses original if not provided)")
    variables: dict = Field(default_factory=dict, description="Variables to override (merged with original)")
    strategy: Optional[str] = Field(None, description="Context assembly strategy override")
    custom_prompt: Optional[str] = Field(None, description="Custom prompt override", max_length=10000)


class WorkflowRunOut(BaseModel):
    id: str
    workflow_id: str
    workflow_name: str
    status: str
    mode: str
    strategy: Optional[str]
    output_format: Optional[str]
    version: int
    document_ids: List[str]
    variables: dict
    artifact_json: Optional[dict]
    error_message: Optional[str]
    job_id: Optional[str] = Field(None, description="Associated job state ID for progress streaming")

    class Config:
        from_attributes = True


# -------------------- Endpoints --------------------

@router.get("/templates", response_model=List[WorkflowTemplateListItem])
def list_workflow_templates(db: Session = Depends(get_db)):
    """List all active workflow templates."""
    repo = WorkflowRepository(db)
    workflows = repo.list_workflows(active_only=True)
    return [
        WorkflowTemplateListItem(
            id=wf.id,
            name=wf.name,
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
def get_workflow_template(workflow_id: str, db: Session = Depends(get_db)):
    """Get workflow template details including variable schema."""
    repo = WorkflowRepository(db)
    wf = repo.get_workflow(workflow_id)
    if not wf or not wf.active:
        raise HTTPException(status_code=404, detail="Workflow not found or inactive")

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
def create_workflow_run(payload: CreateWorkflowRunRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = WorkflowRepository(db)
    workflow = repo.get_workflow(payload.workflow_id)
    if not workflow or not workflow.active:
        raise HTTPException(status_code=404, detail="Workflow not found or inactive")

    # Resolve documents
    doc_ids: List[str] = []
    if payload.document_ids:
        doc_ids = payload.document_ids
    elif payload.collection_id:
        # Load completed documents from collection (query canonical Document table)
        result = db.query(Document.id).join(
            CollectionDocument, Document.id == CollectionDocument.document_id
        ).filter(
            CollectionDocument.collection_id == payload.collection_id,
            Document.status == "completed"
        ).all()
        doc_ids = [r[0] for r in result]
    else:
        raise HTTPException(status_code=400, detail="Either document_ids or collection_id must be provided")

    if len(doc_ids) < workflow.min_documents:
        raise HTTPException(status_code=400, detail=f"Workflow requires at least {workflow.min_documents} document(s)")
    if workflow.max_documents and len(doc_ids) > workflow.max_documents:
        raise HTTPException(status_code=400, detail=f"Workflow accepts at most {workflow.max_documents} document(s)")

    # Validate documents exist and have embeddings (for multi-doc mode)
    if len(doc_ids) > 1:
        from app.db_models_chat import DocumentChunk
        # Query canonical Document table and check for embeddings
        docs_with_embeddings = db.query(Document.id).join(
            DocumentChunk, Document.id == DocumentChunk.document_id
        ).filter(
            Document.id.in_(doc_ids),
            DocumentChunk.embedding.isnot(None)
        ).distinct().all()
        docs_with_embeddings_ids = {r[0] for r in docs_with_embeddings}
        missing_embeddings = set(doc_ids) - docs_with_embeddings_ids
        if missing_embeddings:
            raise HTTPException(
                status_code=400,
                detail=f"Documents missing embeddings (required for multi-doc workflows): {list(missing_embeddings)[:3]}"
            )

    # Validate required variables from workflow schema
    if workflow.variables_schema:
        schema = json.loads(workflow.variables_schema)
        required_vars = [v["name"] for v in schema.get("variables", []) if v.get("required", False)]
        missing_vars = [v for v in required_vars if v not in payload.variables]
        if missing_vars:
            raise HTTPException(status_code=400, detail=f"Missing required variables: {', '.join(missing_vars)}")

        # Validate variable types and constraints
        for var_def in schema.get("variables", []):
            var_name = var_def["name"]
            if var_name not in payload.variables:
                continue
            var_value = payload.variables[var_name]
            var_type = var_def.get("type")

            # Type validation
            if var_type == "integer" and not isinstance(var_value, int):
                raise HTTPException(status_code=400, detail=f"Variable '{var_name}' must be an integer")
            if var_type == "boolean" and not isinstance(var_value, bool):
                raise HTTPException(status_code=400, detail=f"Variable '{var_name}' must be a boolean")
            if var_type == "string" and not isinstance(var_value, str):
                raise HTTPException(status_code=400, detail=f"Variable '{var_name}' must be a string")
            if var_type == "number" and not isinstance(var_value, (int, float)):
                raise HTTPException(status_code=400, detail=f"Variable '{var_name}' must be a number")

            # Enum validation
            if var_type == "enum":
                choices = var_def.get("choices", [])
                if var_value not in choices:
                    raise HTTPException(status_code=400, detail=f"Variable '{var_name}' must be one of: {', '.join(choices)}")

            # Range validation for integers/numbers
            if var_type in ["integer", "number"]:
                if "min" in var_def and var_value < var_def["min"]:
                    raise HTTPException(status_code=400, detail=f"Variable '{var_name}' must be >= {var_def['min']}")
                if "max" in var_def and var_value > var_def["max"]:
                    raise HTTPException(status_code=400, detail=f"Variable '{var_name}' must be <= {var_def['max']}")

    # Determine mode & strategy
    mode = "single_doc" if len(doc_ids) == 1 else "multi_doc"
    strategy = payload.strategy or ("full_context" if mode == "single_doc" else "retrieval")

    run = repo.create_run(
        workflow=workflow,
        user_id=user.id,
        collection_id=payload.collection_id,
        document_ids=doc_ids,
        variables=payload.variables,
        mode=mode,
        strategy=strategy,
    )
    
    # Create JobState for progress streaming
    from app.repositories.job_repository import JobRepository
    job_repo = JobRepository()
    job = job_repo.create_job(workflow_run_id=run.id, status="queued", current_stage="queued", message="Workflow queued")
    job_id = job.job_id if job else None  # FIXED: Use job.job_id instead of job.id

    logger.info("Workflow run created", extra={"workflow_id": workflow.id, "run_id": run.id, "job_id": job_id, "user_id": user.id})
    try:
        start_workflow_chain(run.id, job_id, custom_prompt=payload.custom_prompt)
    except Exception as e:
        logger.error("Failed to start workflow chain", extra={"run_id": run.id, "user_id": user.id, "error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to start workflow execution")

    # Handle both old data (JSON strings) and new data (Python objects)
    document_ids = run.document_ids
    if isinstance(document_ids, str):
        document_ids = json.loads(document_ids)
    document_ids = document_ids or []

    variables = run.variables
    if isinstance(variables, str):
        variables = json.loads(variables)
    variables = variables or {}

    artifact = run.artifact
    if isinstance(artifact, str):
        artifact = json.loads(artifact) if artifact else None

    return WorkflowRunOut(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_name=workflow.name,
        status=run.status,
        mode=run.mode,
        strategy=run.strategy,
        output_format=run.output_format,
        version=run.version,
        document_ids=document_ids,
        variables=variables,
        artifact_json=artifact,
        error_message=run.error_message,
        job_id=job_id,
    )


@router.get("/runs/{run_id}", response_model=WorkflowRunOut)
def get_workflow_run(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = WorkflowRepository(db)
    run = repo.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this run")

    # Lookup associated job for progress streaming (optional)
    from app.repositories.job_repository import JobRepository
    job_repo = JobRepository()
    job = job_repo.get_job_by_workflow_run_id(run.id)
    job_id = job.job_id if job else None

    logger.info("Retrieved workflow run", extra={"run_id": run_id, "job_id": job_id, "user_id": user.id, "status": run.status})

    # Handle both old data (JSON strings) and new data (Python objects)
    document_ids = run.document_ids
    if isinstance(document_ids, str):
        document_ids = json.loads(document_ids)
    document_ids = document_ids or []

    variables = run.variables
    if isinstance(variables, str):
        variables = json.loads(variables)
    variables = variables or {}

    artifact = run.artifact
    if isinstance(artifact, str):
        artifact = json.loads(artifact) if artifact else None

    return WorkflowRunOut(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_name=run.workflow.name if run.workflow else None,
        status=run.status,
        mode=run.mode,
        strategy=run.strategy,
        output_format=run.output_format,
        version=run.version,
        document_ids=document_ids,
        variables=variables,
        artifact_json=artifact,
        error_message=run.error_message,
        job_id=job_id,
    )


@router.get("/runs", response_model=List[WorkflowRunListItem])
def list_workflow_runs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    """List user's workflow runs (paginated)."""
    logger.info("Listing workflow runs", extra={"user_id": user.id, "limit": limit, "offset": offset})
    repo = WorkflowRepository(db)
    runs = repo.list_runs_for_user(user.id, limit=limit, offset=offset)

    result = []
    for run in runs:
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
def list_available_documents(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    collection_id: Optional[str] = None,
):
    """List documents available for workflows (from user's collections)."""
    logger.info("Listing available documents for workflows", extra={"user_id": user.id, "collection_id": collection_id})
    # Query canonical Document table, joining through CollectionDocument to filter by user's collections
    query = db.query(
        Document.id,
        Document.filename,
        Document.page_count,
        Document.status,
        Document.created_at,
        func.count(DocumentChunk.id.distinct()).label("chunk_count"),
        func.count(DocumentChunk.embedding).label("embeddings_count")
    ).join(
        CollectionDocument, Document.id == CollectionDocument.document_id
    ).join(
        Collection, CollectionDocument.collection_id == Collection.id
    ).outerjoin(
        DocumentChunk, Document.id == DocumentChunk.document_id
    ).filter(
        Collection.user_id == user.id,
        Document.status == "completed"
    )

    if collection_id:
        query = query.filter(Collection.id == collection_id)

    query = query.group_by(
        Document.id,
        Document.filename,
        Document.page_count,
        Document.status,
        Document.created_at
    ).order_by(Document.created_at.desc())

    results = query.all()
    
    for r in results:
        logger.info(
            "document chunk/embedding counts",
            extra={
                "user_id": user.id,
                "collection_id": collection_id,
                "document_id": r.id,
                "document_name": getattr(r, "filename", None),
                "chunk_count": int(r.chunk_count or 0),
                "embeddings_count": int(r.embeddings_count or 0),
            },
        )

    return [
        DocumentSummary(
            id=r.id,
            filename=r.filename,
            page_count=r.page_count,
            status=r.status,
            has_embeddings=r.chunk_count > 0 and r.embeddings_count > 0,
            created_at=r.created_at,
        )
        for r in results
    ]


@router.get("/runs/{run_id}/artifact")
def get_workflow_artifact(
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get workflow run artifact (parsed JSON output)."""
    repo = WorkflowRepository(db)
    run = repo.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this run")

    logger.info("Retrieving workflow artifact", extra={"run_id": run_id, "user_id": user.id})

    if not run.artifact:
        raise HTTPException(status_code=404, detail="No artifact available")

    # Artifact is already a Python object (JSON column), no need to parse
    artifact_data = run.artifact

    # If artifact is a pointer to R2, load from storage
    from app.services.artifacts import load_artifact
    try:
        full_artifact = load_artifact(artifact_data)
    except Exception as e:
        logger.exception("Failed to load artifact from storage", extra={"run_id": run_id, "user_id": user.id})
        raise HTTPException(status_code=500, detail=f"Failed to load artifact: {str(e)}")

    return {
        "run_id": run.id,
        "workflow_name": run.workflow.name if run.workflow else None,  # FIXED: Access workflow relationship
        "status": run.status,
        "artifact": full_artifact,
        "cost_usd": run.cost_usd,
        "token_usage": run.token_usage,
        "latency_ms": run.latency_ms,
        "citations_count": run.citations_count,
    }


@router.delete("/runs/{run_id}")
def delete_workflow_run(
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a workflow run and its associated job state."""
    repo = WorkflowRepository(db)
    run = repo.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this run")

    logger.info("Deleting workflow run", extra={"run_id": run_id, "user_id": user.id})

    # Delete artifact from R2 if it exists
    if run.artifact:
        from app.services.artifacts import delete_artifact
        delete_artifact(run.artifact)

    # Delete associated job state (cascade should handle this, but be explicit)
    from app.repositories.job_repository import JobRepository
    job_repo = JobRepository()
    job = job_repo.get_job_by_workflow_run_id(run.id)
    if job:
        job_repo.delete_job(job.job_id)

    # Delete the run (cascade will delete job_state if FK is set up correctly)
    db.delete(run)
    db.commit()

    logger.info("Workflow run deleted", extra={"run_id": run_id, "user_id": user.id})
    return {"message": "Run deleted successfully", "run_id": run_id}


@router.post("/runs/{run_id}/rerun", response_model=WorkflowRunOut)
def rerun_workflow(
    run_id: str,
    payload: RerunWorkflowRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Re-run a workflow with optionally modified variables and prompt.

    Creates a new run based on the original run's configuration, but allows
    overriding variables and custom_prompt.
    """
    repo = WorkflowRepository(db)
    original_run = repo.get_run(run_id)
    if not original_run:
        raise HTTPException(status_code=404, detail="Original run not found")
    if original_run.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this run")

    logger.info("Re-running workflow", extra={
        "original_run_id": run_id,
        "user_id": user.id,
        "workflow_id": original_run.workflow_id
    })

    # Use original run's document_ids and collection_id if not provided
    collection_id = payload.collection_id if payload.collection_id else original_run.collection_id

    # Parse original document_ids (handle both old and new formats)
    original_doc_ids = original_run.document_ids
    if isinstance(original_doc_ids, str):
        original_doc_ids = json.loads(original_doc_ids or "[]")
    else:
        original_doc_ids = original_doc_ids or []

    doc_ids = payload.document_ids if payload.document_ids else original_doc_ids

    # Merge variables: start with original, override with new
    original_vars = original_run.variables
    if isinstance(original_vars, str):
        original_vars = json.loads(original_vars or "{}")
    else:
        original_vars = original_vars or {}

    merged_variables = {**original_vars, **payload.variables}

    # Determine mode and strategy (same logic as create run)
    workflow = original_run.workflow
    if not workflow:
        raise HTTPException(status_code=404, detail="Associated workflow template not found")

    mode = "single_doc" if len(doc_ids) == 1 else "multi_doc"
    strategy = payload.strategy or ("full_context" if mode == "single_doc" else "retrieval")

    # Create new run
    run = repo.create_run(
        workflow=workflow,
        user_id=user.id,
        collection_id=collection_id,
        document_ids=doc_ids,
        variables=merged_variables,
        mode=mode,
        strategy=strategy,
    )

    # Create job state for progress tracking
    from app.repositories.job_repository import JobRepository
    job_repo = JobRepository()
    job = job_repo.create_job(
        workflow_run_id=run.id,
        status="queued",
        current_stage="queued",
        progress_percent=0,
        message="Queued for processing..."
    )
    job_id = job.job_id if job else None

    logger.info("Workflow re-run created", extra={
        "original_run_id": run_id,
        "new_run_id": run.id,
        "workflow_id": workflow.id,
        "user_id": user.id,
        "job_id": job_id
    })

    # Kick off workflow chain
    from app.services.tasks.workflows import start_workflow_chain
    start_workflow_chain(run.id, job_id, custom_prompt=payload.custom_prompt)

    # Return response
    return WorkflowRunOut(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_name=workflow.name,
        status=run.status,
        mode=run.mode,
        strategy=run.strategy,
        output_format=run.output_format,
        version=run.version,
        document_ids=doc_ids,
        variables=merged_variables,
        artifact_json=None,
        error_message=run.error_message,
        job_id=job_id,
    )
