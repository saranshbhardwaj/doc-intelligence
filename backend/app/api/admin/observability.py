"""Admin-only observability endpoints for aggregated stats and metrics."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, case
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, Field

from app.database import get_db
from app.auth import require_admin
from app.db_models_users import User
from app.db_models_workflows import WorkflowRun
from app.db_models_templates import TemplateFillRun
from app.db_models_chat import ChatMessage
from app.db_models import Extraction

router = APIRouter(prefix="/observability", tags=["observability"])


# -------------------- Response Models --------------------

class ObservabilitySummary(BaseModel):
    """Aggregated summary of operations in the specified time window."""
    time_window_hours: int
    workflow_runs: dict = Field(description="Workflow run stats (total, completed, failed, success_rate)")
    template_fills: dict = Field(description="Template fill stats (total, completed, failed, success_rate)")
    chat_messages: dict = Field(description="Chat message stats (total, assistant_messages)")
    extractions: dict = Field(description="Extraction stats (total, completed, failed)")
    costs: dict = Field(description="Cost breakdown (total_usd, by_operation_type)")
    tokens: dict = Field(description="Token usage breakdown (total, input, output, cache_read, cache_write)")
    latency: dict = Field(description="Latency percentiles in milliseconds (p50, p95, p99)")


class OrgCostBreakdown(BaseModel):
    """Cost breakdown by organization."""
    org_id: str
    total_cost_usd: float
    workflow_cost_usd: float
    template_fill_cost_usd: float
    chat_cost_usd: float
    extraction_cost_usd: float
    operation_count: int


class WorkflowCostBreakdown(BaseModel):
    """Cost breakdown by workflow type."""
    workflow_name: str
    workflow_id: Optional[str]
    run_count: int
    total_cost_usd: float
    avg_cost_usd: float
    total_tokens: int
    avg_latency_ms: Optional[float]


class OperationCostBreakdown(BaseModel):
    """Cost breakdown by operation type (workflow, template_fill, chat, extraction)."""
    operation_type: str
    operation_count: int
    total_cost_usd: float
    avg_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_write_tokens: int


class TemplateFillSummary(BaseModel):
    """Template filling specific statistics."""
    total_runs: int
    completed_runs: int
    failed_runs: int
    success_rate: float
    total_fields_detected: int
    total_fields_mapped: int
    avg_auto_mapped_count: Optional[float]
    avg_cache_hit_rate: Optional[float]
    total_llm_batches: int
    avg_llm_batches_per_run: Optional[float]


class ErrorSummary(BaseModel):
    """Common error types and counts."""
    error_type: str
    error_count: int
    sample_message: Optional[str]


class LatencyHistogram(BaseModel):
    """Latency distribution histogram."""
    bucket_label: str
    count: int


# -------------------- Helper Functions --------------------

def _get_time_filter(hours: int):
    """Generate datetime filter for queries."""
    return datetime.utcnow() - timedelta(hours=hours)


def _calculate_percentile(values: list, percentile: float) -> Optional[float]:
    """Calculate percentile from sorted list of values."""
    if not values:
        return None
    values = sorted(values)
    index = int(len(values) * percentile)
    return float(values[min(index, len(values) - 1)])


# -------------------- Endpoints --------------------

@router.get("/summary", response_model=ObservabilitySummary)
def get_observability_summary(
    hours: int = Query(24, ge=1, le=720, description="Time window in hours"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Get aggregated observability summary for all operations.

    Includes workflow runs, template fills, chat messages, extractions,
    costs, token usage, and latency percentiles.
    """
    time_filter = _get_time_filter(hours)

    # Workflow runs stats
    workflow_total = db.query(func.count(WorkflowRun.id)).filter(
        WorkflowRun.created_at >= time_filter
    ).scalar() or 0
    workflow_completed = db.query(func.count(WorkflowRun.id)).filter(
        WorkflowRun.created_at >= time_filter,
        WorkflowRun.status == "completed"
    ).scalar() or 0
    workflow_failed = db.query(func.count(WorkflowRun.id)).filter(
        WorkflowRun.created_at >= time_filter,
        WorkflowRun.status == "failed"
    ).scalar() or 0

    # Template fill stats
    template_total = db.query(func.count(TemplateFillRun.id)).filter(
        TemplateFillRun.created_at >= time_filter
    ).scalar() or 0
    template_completed = db.query(func.count(TemplateFillRun.id)).filter(
        TemplateFillRun.created_at >= time_filter,
        TemplateFillRun.status == "completed"
    ).scalar() or 0
    template_failed = db.query(func.count(TemplateFillRun.id)).filter(
        TemplateFillRun.created_at >= time_filter,
        TemplateFillRun.status == "failed"
    ).scalar() or 0

    # Chat message stats
    chat_total = db.query(func.count(ChatMessage.id)).filter(
        ChatMessage.created_at >= time_filter
    ).scalar() or 0
    chat_assistant = db.query(func.count(ChatMessage.id)).filter(
        ChatMessage.created_at >= time_filter,
        ChatMessage.role == "assistant"
    ).scalar() or 0

    # Extraction stats
    extraction_total = db.query(func.count(Extraction.id)).filter(
        Extraction.created_at >= time_filter
    ).scalar() or 0
    extraction_completed = db.query(func.count(Extraction.id)).filter(
        Extraction.created_at >= time_filter,
        Extraction.status == "completed"
    ).scalar() or 0
    extraction_failed = db.query(func.count(Extraction.id)).filter(
        Extraction.created_at >= time_filter,
        Extraction.status == "failed"
    ).scalar() or 0

    # Cost aggregation
    workflow_cost = db.query(func.coalesce(func.sum(WorkflowRun.cost_usd), 0)).filter(
        WorkflowRun.created_at >= time_filter
    ).scalar() or 0.0
    template_cost = db.query(func.coalesce(func.sum(TemplateFillRun.cost_usd), 0)).filter(
        TemplateFillRun.created_at >= time_filter
    ).scalar() or 0.0
    chat_cost = db.query(func.coalesce(func.sum(ChatMessage.cost_usd), 0)).filter(
        ChatMessage.created_at >= time_filter
    ).scalar() or 0.0
    extraction_cost = db.query(func.coalesce(func.sum(Extraction.llm_cost_usd), 0)).filter(
        Extraction.created_at >= time_filter
    ).scalar() or 0.0

    total_cost = workflow_cost + template_cost + chat_cost + extraction_cost

    # Token aggregation (workflow runs)
    workflow_tokens = db.query(
        func.coalesce(func.sum(WorkflowRun.input_tokens), 0).label("input"),
        func.coalesce(func.sum(WorkflowRun.output_tokens), 0).label("output"),
        func.coalesce(func.sum(WorkflowRun.cache_read_tokens), 0).label("cache_read"),
        func.coalesce(func.sum(WorkflowRun.cache_write_tokens), 0).label("cache_write")
    ).filter(WorkflowRun.created_at >= time_filter).first()

    # Token aggregation (template fills)
    template_tokens = db.query(
        func.coalesce(func.sum(TemplateFillRun.input_tokens), 0).label("input"),
        func.coalesce(func.sum(TemplateFillRun.output_tokens), 0).label("output"),
        func.coalesce(func.sum(TemplateFillRun.cache_read_tokens), 0).label("cache_read"),
        func.coalesce(func.sum(TemplateFillRun.cache_write_tokens), 0).label("cache_write")
    ).filter(TemplateFillRun.created_at >= time_filter).first()

    # Token aggregation (chat messages)
    chat_tokens = db.query(
        func.coalesce(func.sum(ChatMessage.input_tokens), 0).label("input"),
        func.coalesce(func.sum(ChatMessage.output_tokens), 0).label("output"),
        func.coalesce(func.sum(ChatMessage.cache_read_tokens), 0).label("cache_read"),
        func.coalesce(func.sum(ChatMessage.cache_write_tokens), 0).label("cache_write")
    ).filter(ChatMessage.created_at >= time_filter).first()

    # Token aggregation (extractions)
    extraction_tokens = db.query(
        func.coalesce(func.sum(Extraction.llm_input_tokens), 0).label("input"),
        func.coalesce(func.sum(Extraction.llm_output_tokens), 0).label("output")
    ).filter(Extraction.created_at >= time_filter).first()

    # Aggregate tokens
    total_input = (workflow_tokens.input + template_tokens.input +
                   chat_tokens.input + extraction_tokens.input)
    total_output = (workflow_tokens.output + template_tokens.output +
                    chat_tokens.output + extraction_tokens.output)
    total_cache_read = (workflow_tokens.cache_read + template_tokens.cache_read +
                        chat_tokens.cache_read)
    total_cache_write = (workflow_tokens.cache_write + template_tokens.cache_write +
                         chat_tokens.cache_write)

    # Latency percentiles (workflow runs + template fills)
    workflow_latencies = db.query(WorkflowRun.latency_ms).filter(
        WorkflowRun.created_at >= time_filter,
        WorkflowRun.latency_ms.isnot(None)
    ).all()
    template_latencies = db.query(TemplateFillRun.processing_time_ms).filter(
        TemplateFillRun.created_at >= time_filter,
        TemplateFillRun.processing_time_ms.isnot(None)
    ).all()

    all_latencies = [l[0] for l in workflow_latencies if l[0]] + [l[0] for l in template_latencies if l[0]]

    return ObservabilitySummary(
        time_window_hours=hours,
        workflow_runs={
            "total": workflow_total,
            "completed": workflow_completed,
            "failed": workflow_failed,
            "success_rate": round(workflow_completed / workflow_total * 100, 2) if workflow_total > 0 else 0.0
        },
        template_fills={
            "total": template_total,
            "completed": template_completed,
            "failed": template_failed,
            "success_rate": round(template_completed / template_total * 100, 2) if template_total > 0 else 0.0
        },
        chat_messages={
            "total": chat_total,
            "assistant_messages": chat_assistant
        },
        extractions={
            "total": extraction_total,
            "completed": extraction_completed,
            "failed": extraction_failed
        },
        costs={
            "total_usd": round(total_cost, 4),
            "by_operation_type": {
                "workflow": round(workflow_cost, 4),
                "template_fill": round(template_cost, 4),
                "chat": round(chat_cost, 4),
                "extraction": round(extraction_cost, 4)
            }
        },
        tokens={
            "total": total_input + total_output,
            "input": total_input,
            "output": total_output,
            "cache_read": total_cache_read,
            "cache_write": total_cache_write
        },
        latency={
            "p50": _calculate_percentile(all_latencies, 0.50),
            "p95": _calculate_percentile(all_latencies, 0.95),
            "p99": _calculate_percentile(all_latencies, 0.99)
        }
    )


@router.get("/costs/by-org", response_model=list[OrgCostBreakdown])
def get_costs_by_org(
    hours: int = Query(24, ge=1, le=720, description="Time window in hours"),
    limit: int = Query(50, ge=1, le=500, description="Max orgs to return"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Get cost breakdown by organization.

    Returns top organizations by total cost in the specified time window.
    """
    time_filter = _get_time_filter(hours)

    # Query workflow costs by org
    workflow_costs = db.query(
        WorkflowRun.org_id,
        func.coalesce(func.sum(WorkflowRun.cost_usd), 0).label("workflow_cost"),
        func.count(WorkflowRun.id).label("workflow_count")
    ).filter(
        WorkflowRun.created_at >= time_filter
    ).group_by(WorkflowRun.org_id).subquery()

    # Query template fill costs by org
    template_costs = db.query(
        TemplateFillRun.org_id,
        func.coalesce(func.sum(TemplateFillRun.cost_usd), 0).label("template_cost"),
        func.count(TemplateFillRun.id).label("template_count")
    ).filter(
        TemplateFillRun.created_at >= time_filter
    ).group_by(TemplateFillRun.org_id).subquery()

    # Query extraction costs by org
    extraction_costs = db.query(
        Extraction.org_id,
        func.coalesce(func.sum(Extraction.llm_cost_usd), 0).label("extraction_cost"),
        func.count(Extraction.id).label("extraction_count")
    ).filter(
        Extraction.created_at >= time_filter
    ).group_by(Extraction.org_id).subquery()

    # Union all org_ids and aggregate (chat doesn't have org_id in current schema, so skipping)
    # Note: If chat had org_id, we'd add it here

    # Get all unique org_ids from all tables
    all_orgs = set()
    workflow_orgs = db.query(WorkflowRun.org_id).filter(
        WorkflowRun.created_at >= time_filter
    ).distinct().all()
    template_orgs = db.query(TemplateFillRun.org_id).filter(
        TemplateFillRun.created_at >= time_filter
    ).distinct().all()
    extraction_orgs = db.query(Extraction.org_id).filter(
        Extraction.created_at >= time_filter
    ).distinct().all()

    all_orgs.update([o[0] for o in workflow_orgs])
    all_orgs.update([o[0] for o in template_orgs])
    all_orgs.update([o[0] for o in extraction_orgs])

    # Build result for each org
    results = []
    for org_id in all_orgs:
        workflow_data = db.query(
            func.coalesce(func.sum(WorkflowRun.cost_usd), 0),
            func.count(WorkflowRun.id)
        ).filter(
            WorkflowRun.org_id == org_id,
            WorkflowRun.created_at >= time_filter
        ).first()

        template_data = db.query(
            func.coalesce(func.sum(TemplateFillRun.cost_usd), 0),
            func.count(TemplateFillRun.id)
        ).filter(
            TemplateFillRun.org_id == org_id,
            TemplateFillRun.created_at >= time_filter
        ).first()

        extraction_data = db.query(
            func.coalesce(func.sum(Extraction.llm_cost_usd), 0),
            func.count(Extraction.id)
        ).filter(
            Extraction.org_id == org_id,
            Extraction.created_at >= time_filter
        ).first()

        workflow_cost = workflow_data[0] or 0.0
        template_cost = template_data[0] or 0.0
        extraction_cost = extraction_data[0] or 0.0

        total_cost = workflow_cost + template_cost + extraction_cost
        operation_count = (workflow_data[1] or 0) + (template_data[1] or 0) + (extraction_data[1] or 0)

        results.append(OrgCostBreakdown(
            org_id=org_id,
            total_cost_usd=round(total_cost, 4),
            workflow_cost_usd=round(workflow_cost, 4),
            template_fill_cost_usd=round(template_cost, 4),
            chat_cost_usd=0.0,  # Chat doesn't track org_id in current schema
            extraction_cost_usd=round(extraction_cost, 4),
            operation_count=operation_count
        ))

    # Sort by total cost descending and limit
    results.sort(key=lambda x: x.total_cost_usd, reverse=True)
    return results[:limit]


@router.get("/costs/by-workflow", response_model=list[WorkflowCostBreakdown])
def get_costs_by_workflow(
    hours: int = Query(24, ge=1, le=720, description="Time window in hours"),
    limit: int = Query(50, ge=1, le=500, description="Max workflows to return"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Get cost breakdown by workflow type.

    Returns top workflows by total cost in the specified time window.
    """
    time_filter = _get_time_filter(hours)

    # Join workflow_runs with workflows to get workflow names
    from app.db_models_workflows import Workflow

    results = db.query(
        Workflow.name.label("workflow_name"),
        Workflow.id.label("workflow_id"),
        func.count(WorkflowRun.id).label("run_count"),
        func.coalesce(func.sum(WorkflowRun.cost_usd), 0).label("total_cost"),
        func.coalesce(func.avg(WorkflowRun.cost_usd), 0).label("avg_cost"),
        func.coalesce(
            func.sum(
                func.coalesce(WorkflowRun.input_tokens, 0) +
                func.coalesce(WorkflowRun.output_tokens, 0)
            ), 0
        ).label("total_tokens"),
        func.avg(WorkflowRun.latency_ms).label("avg_latency")
    ).join(
        Workflow, WorkflowRun.workflow_id == Workflow.id
    ).filter(
        WorkflowRun.created_at >= time_filter
    ).group_by(
        Workflow.name, Workflow.id
    ).order_by(
        desc("total_cost")
    ).limit(limit).all()

    return [
        WorkflowCostBreakdown(
            workflow_name=r.workflow_name,
            workflow_id=r.workflow_id,
            run_count=r.run_count,
            total_cost_usd=round(r.total_cost, 4),
            avg_cost_usd=round(r.avg_cost, 4),
            total_tokens=r.total_tokens,
            avg_latency_ms=round(r.avg_latency, 2) if r.avg_latency else None
        )
        for r in results
    ]


@router.get("/costs/by-operation", response_model=list[OperationCostBreakdown])
def get_costs_by_operation(
    hours: int = Query(24, ge=1, le=720, description="Time window in hours"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Get cost breakdown by operation type (workflow, template_fill, chat, extraction).

    Aggregates costs and token usage across all operation types.
    """
    time_filter = _get_time_filter(hours)

    results = []

    # Workflow operations
    workflow_stats = db.query(
        func.count(WorkflowRun.id),
        func.coalesce(func.sum(WorkflowRun.cost_usd), 0),
        func.coalesce(func.avg(WorkflowRun.cost_usd), 0),
        func.coalesce(func.sum(WorkflowRun.input_tokens), 0),
        func.coalesce(func.sum(WorkflowRun.output_tokens), 0),
        func.coalesce(func.sum(WorkflowRun.cache_read_tokens), 0),
        func.coalesce(func.sum(WorkflowRun.cache_write_tokens), 0)
    ).filter(WorkflowRun.created_at >= time_filter).first()

    if workflow_stats and workflow_stats[0] > 0:
        results.append(OperationCostBreakdown(
            operation_type="workflow",
            operation_count=workflow_stats[0],
            total_cost_usd=round(workflow_stats[1], 4),
            avg_cost_usd=round(workflow_stats[2], 4),
            total_input_tokens=workflow_stats[3],
            total_output_tokens=workflow_stats[4],
            total_cache_read_tokens=workflow_stats[5],
            total_cache_write_tokens=workflow_stats[6]
        ))

    # Template fill operations
    template_stats = db.query(
        func.count(TemplateFillRun.id),
        func.coalesce(func.sum(TemplateFillRun.cost_usd), 0),
        func.coalesce(func.avg(TemplateFillRun.cost_usd), 0),
        func.coalesce(func.sum(TemplateFillRun.input_tokens), 0),
        func.coalesce(func.sum(TemplateFillRun.output_tokens), 0),
        func.coalesce(func.sum(TemplateFillRun.cache_read_tokens), 0),
        func.coalesce(func.sum(TemplateFillRun.cache_write_tokens), 0)
    ).filter(TemplateFillRun.created_at >= time_filter).first()

    if template_stats and template_stats[0] > 0:
        results.append(OperationCostBreakdown(
            operation_type="template_fill",
            operation_count=template_stats[0],
            total_cost_usd=round(template_stats[1], 4),
            avg_cost_usd=round(template_stats[2], 4),
            total_input_tokens=template_stats[3],
            total_output_tokens=template_stats[4],
            total_cache_read_tokens=template_stats[5],
            total_cache_write_tokens=template_stats[6]
        ))

    # Chat operations
    chat_stats = db.query(
        func.count(ChatMessage.id),
        func.coalesce(func.sum(ChatMessage.cost_usd), 0),
        func.coalesce(func.avg(ChatMessage.cost_usd), 0),
        func.coalesce(func.sum(ChatMessage.input_tokens), 0),
        func.coalesce(func.sum(ChatMessage.output_tokens), 0),
        func.coalesce(func.sum(ChatMessage.cache_read_tokens), 0),
        func.coalesce(func.sum(ChatMessage.cache_write_tokens), 0)
    ).filter(ChatMessage.created_at >= time_filter).first()

    if chat_stats and chat_stats[0] > 0:
        results.append(OperationCostBreakdown(
            operation_type="chat",
            operation_count=chat_stats[0],
            total_cost_usd=round(chat_stats[1], 4),
            avg_cost_usd=round(chat_stats[2], 4),
            total_input_tokens=chat_stats[3],
            total_output_tokens=chat_stats[4],
            total_cache_read_tokens=chat_stats[5],
            total_cache_write_tokens=chat_stats[6]
        ))

    # Extraction operations
    extraction_stats = db.query(
        func.count(Extraction.id),
        func.coalesce(func.sum(Extraction.llm_cost_usd), 0),
        func.coalesce(func.avg(Extraction.llm_cost_usd), 0),
        func.coalesce(func.sum(Extraction.llm_input_tokens), 0),
        func.coalesce(func.sum(Extraction.llm_output_tokens), 0)
    ).filter(Extraction.created_at >= time_filter).first()

    if extraction_stats and extraction_stats[0] > 0:
        results.append(OperationCostBreakdown(
            operation_type="extraction",
            operation_count=extraction_stats[0],
            total_cost_usd=round(extraction_stats[1], 4),
            avg_cost_usd=round(extraction_stats[2], 4),
            total_input_tokens=extraction_stats[3],
            total_output_tokens=extraction_stats[4],
            total_cache_read_tokens=0,  # Extractions don't track cache tokens
            total_cache_write_tokens=0
        ))

    return results


@router.get("/template-fills/summary", response_model=TemplateFillSummary)
def get_template_fill_summary(
    hours: int = Query(24, ge=1, le=720, description="Time window in hours"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Get template filling specific statistics.

    Includes field detection/mapping stats, cache hit rate, and LLM batch counts.
    """
    time_filter = _get_time_filter(hours)

    # Basic stats
    total_runs = db.query(func.count(TemplateFillRun.id)).filter(
        TemplateFillRun.created_at >= time_filter
    ).scalar() or 0

    completed_runs = db.query(func.count(TemplateFillRun.id)).filter(
        TemplateFillRun.created_at >= time_filter,
        TemplateFillRun.status == "completed"
    ).scalar() or 0

    failed_runs = db.query(func.count(TemplateFillRun.id)).filter(
        TemplateFillRun.created_at >= time_filter,
        TemplateFillRun.status == "failed"
    ).scalar() or 0

    # Aggregated field stats
    field_stats = db.query(
        func.coalesce(func.sum(TemplateFillRun.total_fields_detected), 0),
        func.coalesce(func.sum(TemplateFillRun.total_fields_filled), 0),
        func.avg(TemplateFillRun.auto_mapped_count)
    ).filter(TemplateFillRun.created_at >= time_filter).first()

    # Cache hit rate and batch counts
    cache_stats = db.query(
        func.avg(TemplateFillRun.cache_hit_rate),
        func.coalesce(func.sum(TemplateFillRun.llm_batches_count), 0),
        func.avg(TemplateFillRun.llm_batches_count)
    ).filter(TemplateFillRun.created_at >= time_filter).first()

    return TemplateFillSummary(
        total_runs=total_runs,
        completed_runs=completed_runs,
        failed_runs=failed_runs,
        success_rate=round(completed_runs / total_runs * 100, 2) if total_runs > 0 else 0.0,
        total_fields_detected=field_stats[0] or 0,
        total_fields_mapped=field_stats[1] or 0,
        avg_auto_mapped_count=round(field_stats[2], 2) if field_stats[2] else None,
        avg_cache_hit_rate=round(cache_stats[0], 4) if cache_stats[0] else None,
        total_llm_batches=cache_stats[1] or 0,
        avg_llm_batches_per_run=round(cache_stats[2], 2) if cache_stats[2] else None
    )


@router.get("/errors/summary", response_model=list[ErrorSummary])
def get_error_summary(
    hours: int = Query(24, ge=1, le=720, description="Time window in hours"),
    limit: int = Query(20, ge=1, le=100, description="Max error types to return"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Get common error types and counts across all operations.

    Aggregates errors from workflow runs, template fills, and extractions.
    """
    time_filter = _get_time_filter(hours)

    errors = []

    # Workflow errors
    workflow_errors = db.query(
        WorkflowRun.error_message,
        func.count(WorkflowRun.id).label("count")
    ).filter(
        WorkflowRun.created_at >= time_filter,
        WorkflowRun.status == "failed",
        WorkflowRun.error_message.isnot(None)
    ).group_by(WorkflowRun.error_message).order_by(desc("count")).limit(limit).all()

    for error_msg, count in workflow_errors:
        errors.append(ErrorSummary(
            error_type=f"workflow: {error_msg[:100]}",
            error_count=count,
            sample_message=error_msg[:200]
        ))

    # Template fill errors
    template_errors = db.query(
        TemplateFillRun.error_message,
        func.count(TemplateFillRun.id).label("count")
    ).filter(
        TemplateFillRun.created_at >= time_filter,
        TemplateFillRun.status == "failed",
        TemplateFillRun.error_message.isnot(None)
    ).group_by(TemplateFillRun.error_message).order_by(desc("count")).limit(limit).all()

    for error_msg, count in template_errors:
        errors.append(ErrorSummary(
            error_type=f"template_fill: {error_msg[:100]}",
            error_count=count,
            sample_message=error_msg[:200]
        ))

    # Extraction errors
    extraction_errors = db.query(
        Extraction.error_message,
        func.count(Extraction.id).label("count")
    ).filter(
        Extraction.created_at >= time_filter,
        Extraction.status == "failed",
        Extraction.error_message.isnot(None)
    ).group_by(Extraction.error_message).order_by(desc("count")).limit(limit).all()

    for error_msg, count in extraction_errors:
        errors.append(ErrorSummary(
            error_type=f"extraction: {error_msg[:100]}",
            error_count=count,
            sample_message=error_msg[:200]
        ))

    # Sort by count and limit
    errors.sort(key=lambda x: x.error_count, reverse=True)
    return errors[:limit]


@router.get("/latency/histogram", response_model=list[LatencyHistogram])
def get_latency_histogram(
    hours: int = Query(24, ge=1, le=720, description="Time window in hours"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Get latency distribution histogram.

    Buckets: <1s, 1-5s, 5-10s, 10-30s, 30-60s, >60s
    """
    time_filter = _get_time_filter(hours)

    # Define buckets (in milliseconds)
    buckets = [
        ("< 1s", 0, 1000),
        ("1-5s", 1000, 5000),
        ("5-10s", 5000, 10000),
        ("10-30s", 10000, 30000),
        ("30-60s", 30000, 60000),
        ("> 60s", 60000, float('inf'))
    ]

    results = []

    for label, min_ms, max_ms in buckets:
        # Count workflow runs in bucket
        workflow_count = db.query(func.count(WorkflowRun.id)).filter(
            WorkflowRun.created_at >= time_filter,
            WorkflowRun.latency_ms >= min_ms,
            WorkflowRun.latency_ms < max_ms if max_ms != float('inf') else True
        ).scalar() or 0

        # Count template fills in bucket
        template_count = db.query(func.count(TemplateFillRun.id)).filter(
            TemplateFillRun.created_at >= time_filter,
            TemplateFillRun.processing_time_ms >= min_ms,
            TemplateFillRun.processing_time_ms < max_ms if max_ms != float('inf') else True
        ).scalar() or 0

        total_count = workflow_count + template_count

        results.append(LatencyHistogram(
            bucket_label=label,
            count=total_count
        ))

    return results
