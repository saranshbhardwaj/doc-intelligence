from __future__ import annotations

from pydantic import BaseModel, Field


class WorkflowFinding(BaseModel):
    id: str
    severity: str = "warning"
    message: str
    source: str | None = None
    related_section: str | None = None


class WorkflowPhase(BaseModel):
    id: str
    label: str
    status: str
    summary: str | None = None
    related_sections: list[str] = Field(default_factory=list)


class WorkflowGate(BaseModel):
    id: str
    label: str
    status: str
    severity: str = "info"
    can_override: bool = True
    findings: list[WorkflowFinding] = Field(default_factory=list)


class MemoGenerationState(BaseModel):
    allowed: bool
    requires_override: bool = False
    blocking_gate_ids: list[str] = Field(default_factory=list)
    disabled_reason: str | None = None


class UnderwritingWorkflowState(BaseModel):
    workflow_name: str
    workflow_key: str
    asset_type: str | None = None
    overall_status: str
    memo_generation: MemoGenerationState
    phases: list[WorkflowPhase]
    gates: list[WorkflowGate]