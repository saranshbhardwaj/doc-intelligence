from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class WorkflowDomain(str, Enum):
    """Workflow domain enum for PE vs RE workflows."""
    PRIVATE_EQUITY = "private_equity"
    REAL_ESTATE = "real_estate"


class WorkflowTemplateListItem(BaseModel):
    """Workflow template summary for listing."""
    id: str
    name: str
    domain: str = "private_equity"
    category: Optional[str]
    description: Optional[str]
    prompt_template: str
    user_prompt_template: Optional[str] = None
    user_prompt_max_length: Optional[int] = None
    variables_schema: Optional[str]
    output_format: str
    min_documents: int
    max_documents: Optional[int]
    version: int
    active: bool


class WorkflowVariableSchema(BaseModel):
    """Variable definition in workflow template schema."""
    name: str
    type: str
    required: bool = False
    default: Optional[Any] = None
    choices: Optional[List[Any]] = None
    min: Optional[float] = None
    max: Optional[float] = None


class WorkflowTemplateDetail(WorkflowTemplateListItem):
    """Full workflow template with variable schema."""
    variables_schema: Optional[List[WorkflowVariableSchema]] = None


class WorkflowRunCreate(BaseModel):
    """Request to create a new workflow run."""
    workflow_id: str = Field(..., description="ID of workflow template")
    collection_id: Optional[str] = Field(None, description="Collection to draw documents from")
    document_ids: Optional[List[str]] = Field(None, description="Specific document IDs (override collection)")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Template variables")
    strategy: Optional[str] = Field(None, description="Context assembly strategy override")


class WorkflowRunListItem(BaseModel):
    """Workflow run summary for listing."""
    id: str
    workflow_id: Optional[str] = None
    workflow_name: Optional[str] = None
    status: str
    mode: str
    output_format: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime] = None
    latency_ms: Optional[int] = None
    cost_usd: Optional[float] = None
    error_message: Optional[str] = None
    artifact_json: Optional[Dict[str, Any]] = None  # Include artifact for preview in results panel


class WorkflowRunDetail(BaseModel):
    """Full workflow run details."""
    id: str
    workflow_id: str
    workflow_name: Optional[str] = None
    status: str
    mode: str
    strategy: Optional[str]
    output_format: Optional[str]
    version: int
    document_ids: List[str]
    variables: Dict[str, Any]
    artifact_json: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    token_usage: Optional[int] = None
    cost_usd: Optional[float] = None
    latency_ms: Optional[int] = None
    citations_count: Optional[int] = None
    attempts: Optional[int] = None
    job_id: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class WorkflowRunResponse(BaseModel):
    id: str
    status: str
    artifact: Optional[Dict[str, Any]] = None
    cost_usd: Optional[float] = None
    token_usage: Optional[int] = None
    partial: Optional[bool] = False
    salvage_reason: Optional[str] = None


class ExportRequest(BaseModel):
    run_id: str
    format: str = 'pdf'


class DocumentSummary(BaseModel):
    """Document summary for selection in workflow UI."""
    id: str
    filename: str
    page_count: Optional[int]
    status: str
    has_embeddings: bool
    created_at: datetime


__all__ = [
    'WorkflowDomain',
    'WorkflowTemplateListItem',
    'WorkflowTemplateDetail',
    'WorkflowVariableSchema',
    'WorkflowRunCreate',
    'WorkflowRunListItem',
    'WorkflowRunDetail',
    'WorkflowRunResponse',
    'ExportRequest',
    'DocumentSummary',
]
