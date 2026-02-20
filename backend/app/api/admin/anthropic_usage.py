"""Admin-only endpoints for Anthropic usage and cost data.

Provides access to ground-truth usage/cost from Anthropic Admin API,
comparison with internal tracking, and manual sync triggering.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timedelta, date, timezone
from typing import Optional
from pydantic import BaseModel, Field
import asyncio

from app.database import get_db
from app.auth import require_admin
from app.config import settings
from app.db_models import AnthropicUsageSnapshot
from app.db_models_workflows import WorkflowRun
from app.db_models_templates import TemplateFillRun
from app.db_models_chat import ChatMessage
from app.db_models import Extraction
from app.utils.logging import logger

router = APIRouter(prefix="/anthropic-usage", tags=["anthropic-usage"])


# -------------------- Response Models --------------------

class AnthropicUsageSummary(BaseModel):
    """Anthropic-reported usage summary."""
    time_window_days: int
    snapshots: list[dict] = Field(description="Daily snapshots from Anthropic API")
    totals: dict = Field(description="Aggregated totals across all models")


class UsageComparison(BaseModel):
    """Comparison between internal tracking and Anthropic-reported data."""
    time_window_days: int
    internal: dict = Field(description="Usage from our internal tracking")
    anthropic: dict = Field(description="Usage reported by Anthropic Admin API")
    drift: dict = Field(description="Drift metrics (difference and percentage)")


# -------------------- Helper Functions --------------------

def _get_date_range(days: int) -> tuple[date, date]:
    """Get date range for queries (end_date is yesterday, start_date is N days before)."""
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    start_date = yesterday - timedelta(days=days - 1)
    return start_date, yesterday


# -------------------- Endpoints --------------------

@router.get("/summary", response_model=AnthropicUsageSummary)
def get_anthropic_usage_summary(
    days: int = Query(7, ge=1, le=30, description="Number of days to fetch"),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Get Anthropic-reported usage summary for the last N days.

    Returns daily snapshots from the anthropic_usage_snapshots table,
    along with aggregated totals across all models.

    Args:
        days: Number of days to include (1-30)

    Returns:
        AnthropicUsageSummary with daily snapshots and totals
    """
    start_date, end_date = _get_date_range(days)

    logger.info(
        "Fetching Anthropic usage summary",
        extra={"days": days, "start_date": str(start_date), "end_date": str(end_date)}
    )

    # Query snapshots
    snapshots = (
        db.query(AnthropicUsageSnapshot)
        .filter(
            AnthropicUsageSnapshot.snapshot_date >= start_date,
            AnthropicUsageSnapshot.snapshot_date <= end_date,
        )
        .order_by(desc(AnthropicUsageSnapshot.snapshot_date))
        .all()
    )

    # Format snapshots
    snapshot_data = []
    for snap in snapshots:
        snapshot_data.append({
            "date": snap.snapshot_date.isoformat() if snap.snapshot_date else None,
            "model": snap.model,
            "input_tokens": snap.input_tokens,
            "output_tokens": snap.output_tokens,
            "cache_read_input_tokens": snap.cache_read_input_tokens,
            "cache_creation_input_tokens": snap.cache_creation_input_tokens,
            "cost_usd": float(snap.cost_usd) if snap.cost_usd else 0.0,
            "fetched_at": snap.fetched_at.isoformat() if snap.fetched_at else None,
        })

    # Calculate totals
    totals = {
        "input_tokens": sum(s["input_tokens"] for s in snapshot_data),
        "output_tokens": sum(s["output_tokens"] for s in snapshot_data),
        "cache_read_input_tokens": sum(s["cache_read_input_tokens"] for s in snapshot_data),
        "cache_creation_input_tokens": sum(s["cache_creation_input_tokens"] for s in snapshot_data),
        "cost_usd": sum(s["cost_usd"] for s in snapshot_data),
        "snapshot_count": len(snapshot_data),
    }

    return AnthropicUsageSummary(
        time_window_days=days,
        snapshots=snapshot_data,
        totals=totals,
    )


@router.get("/comparison", response_model=UsageComparison)
def get_usage_comparison(
    days: int = Query(7, ge=1, le=30, description="Number of days to compare"),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """Compare internal tracking vs Anthropic-reported data.

    Queries internal database for token usage from workflows, template fills,
    chat messages, and extractions, then compares with Anthropic snapshots.

    Args:
        days: Number of days to compare (1-30)

    Returns:
        UsageComparison with internal, Anthropic, and drift data
    """
    start_date, end_date = _get_date_range(days)
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())

    logger.info(
        "Fetching usage comparison",
        extra={"days": days, "start_date": str(start_date), "end_date": str(end_date)}
    )

    # Internal tracking: aggregate from all sources
    internal_tokens = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "cost_usd": 0.0,
    }

    # Workflow runs
    workflow_agg = (
        db.query(
            func.sum(WorkflowRun.input_tokens).label("input"),
            func.sum(WorkflowRun.output_tokens).label("output"),
            func.sum(WorkflowRun.cache_read_tokens).label("cache_read"),
            func.sum(WorkflowRun.cache_write_tokens).label("cache_write"),
            func.sum(WorkflowRun.cost_usd).label("cost"),
        )
        .filter(WorkflowRun.created_at >= start_datetime, WorkflowRun.created_at <= end_datetime)
        .first()
    )
    if workflow_agg:
        internal_tokens["input_tokens"] += workflow_agg.input or 0
        internal_tokens["output_tokens"] += workflow_agg.output or 0
        internal_tokens["cache_read_tokens"] += workflow_agg.cache_read or 0
        internal_tokens["cache_write_tokens"] += workflow_agg.cache_write or 0
        internal_tokens["cost_usd"] += workflow_agg.cost or 0.0

    # Template fill runs
    template_agg = (
        db.query(
            func.sum(TemplateFillRun.input_tokens).label("input"),
            func.sum(TemplateFillRun.output_tokens).label("output"),
            func.sum(TemplateFillRun.cache_read_tokens).label("cache_read"),
            func.sum(TemplateFillRun.cache_write_tokens).label("cache_write"),
            func.sum(TemplateFillRun.cost_usd).label("cost"),
        )
        .filter(TemplateFillRun.created_at >= start_datetime, TemplateFillRun.created_at <= end_datetime)
        .first()
    )
    if template_agg:
        internal_tokens["input_tokens"] += template_agg.input or 0
        internal_tokens["output_tokens"] += template_agg.output or 0
        internal_tokens["cache_read_tokens"] += template_agg.cache_read or 0
        internal_tokens["cache_write_tokens"] += template_agg.cache_write or 0
        internal_tokens["cost_usd"] += template_agg.cost or 0.0

    # Chat messages
    chat_agg = (
        db.query(
            func.sum(ChatMessage.input_tokens).label("input"),
            func.sum(ChatMessage.output_tokens).label("output"),
            func.sum(ChatMessage.cache_read_tokens).label("cache_read"),
            func.sum(ChatMessage.cache_write_tokens).label("cache_write"),
            func.sum(ChatMessage.cost_usd).label("cost"),
        )
        .filter(ChatMessage.created_at >= start_datetime, ChatMessage.created_at <= end_datetime)
        .first()
    )
    if chat_agg:
        internal_tokens["input_tokens"] += chat_agg.input or 0
        internal_tokens["output_tokens"] += chat_agg.output or 0
        internal_tokens["cache_read_tokens"] += chat_agg.cache_read or 0
        internal_tokens["cache_write_tokens"] += chat_agg.cache_write or 0
        internal_tokens["cost_usd"] += chat_agg.cost or 0.0

    # Extractions (older data model - no cache tokens)
    extraction_agg = (
        db.query(
            func.sum(Extraction.llm_input_tokens).label("input"),
            func.sum(Extraction.llm_output_tokens).label("output"),
            func.sum(Extraction.llm_cost_usd).label("cost"),
        )
        .filter(Extraction.created_at >= start_datetime, Extraction.created_at <= end_datetime)
        .first()
    )
    if extraction_agg:
        internal_tokens["input_tokens"] += extraction_agg.input or 0
        internal_tokens["output_tokens"] += extraction_agg.output or 0
        internal_tokens["cost_usd"] += extraction_agg.cost or 0.0

    # Anthropic snapshots
    snapshots = (
        db.query(AnthropicUsageSnapshot)
        .filter(
            AnthropicUsageSnapshot.snapshot_date >= start_date,
            AnthropicUsageSnapshot.snapshot_date <= end_date,
        )
        .all()
    )

    anthropic_tokens = {
        "input_tokens": sum(s.input_tokens for s in snapshots),
        "output_tokens": sum(s.output_tokens for s in snapshots),
        "cache_read_tokens": sum(s.cache_read_input_tokens for s in snapshots),
        "cache_write_tokens": sum(s.cache_creation_input_tokens for s in snapshots),
        "cost_usd": sum(float(s.cost_usd) if s.cost_usd else 0.0 for s in snapshots),
    }

    # Calculate drift
    def calc_drift(internal: float, anthropic: float) -> dict:
        if anthropic == 0:
            return {"absolute": internal, "percent": 0.0 if internal == 0 else 100.0}
        diff = internal - anthropic
        pct = (diff / anthropic) * 100
        return {"absolute": diff, "percent": round(pct, 2)}

    drift = {
        "input_tokens": calc_drift(internal_tokens["input_tokens"], anthropic_tokens["input_tokens"]),
        "output_tokens": calc_drift(internal_tokens["output_tokens"], anthropic_tokens["output_tokens"]),
        "cache_read_tokens": calc_drift(internal_tokens["cache_read_tokens"], anthropic_tokens["cache_read_tokens"]),
        "cache_write_tokens": calc_drift(internal_tokens["cache_write_tokens"], anthropic_tokens["cache_write_tokens"]),
        "cost_usd": calc_drift(internal_tokens["cost_usd"], anthropic_tokens["cost_usd"]),
    }

    return UsageComparison(
        time_window_days=days,
        internal=internal_tokens,
        anthropic=anthropic_tokens,
        drift=drift,
    )


@router.post("/sync")
async def trigger_sync(_: None = Depends(require_admin)):
    """Manually trigger an Anthropic usage sync (admin only).

    Runs the sync immediately in the background, bypassing the daily schedule.
    Useful for debugging or when you need fresh data on-demand.

    Returns:
        Status message indicating sync was triggered
    """
    if not settings.anthropic_admin_api_key:
        return {
            "status": "error",
            "message": "Anthropic Admin API key not configured (ANTHROPIC_ADMIN_API_KEY)",
        }

    logger.info("Manual Anthropic usage sync triggered by admin")

    # Import here to avoid circular dependency
    from app.services.anthropic_usage_service import AnthropicUsageService
    from app.utils.metrics import (
        ANTHROPIC_REPORTED_TOKENS,
        ANTHROPIC_REPORTED_COST_USD,
        ANTHROPIC_USAGE_LAST_SYNC
    )
    from app.database import get_db
    import time

    try:
        service = AnthropicUsageService(settings.anthropic_admin_api_key)
        starting_at, ending_at = service.get_yesterday_time_range()
        yesterday_date = datetime.strptime(starting_at, "%Y-%m-%dT%H:%M:%SZ").date()

        # Fetch reports
        usage_report = await service.fetch_usage_report(
            starting_at, ending_at, bucket_width="1d", group_by=["model"]
        )
        cost_report = await service.fetch_cost_report(
            starting_at, ending_at, group_by=["description"]
        )

        # Parse costs by model
        costs_by_model = {}
        for bucket in cost_report.get("data", []):
            description = bucket.get("description", "")
            model = service.parse_model_from_description(description)
            cost_str = bucket.get("cost", "0")
            cost_usd = float(cost_str) if cost_str else 0.0
            costs_by_model[model] = costs_by_model.get(model, 0.0) + cost_usd

        # Update metrics and database
        db = next(get_db())
        try:
            synced_models = []
            model_records = AnthropicUsageService.flatten_usage_data(usage_report)

            for record in model_records:
                model = record["model"]
                input_tokens = record["input_tokens"]
                output_tokens = record["output_tokens"]
                cache_read = record["cache_read_input_tokens"]
                cache_write = record["cache_creation_input_tokens"]
                cost_usd = costs_by_model.get(model, 0.0)

                # Update gauges
                ANTHROPIC_REPORTED_TOKENS.labels(model=model, token_type="input").set(input_tokens)
                ANTHROPIC_REPORTED_TOKENS.labels(model=model, token_type="output").set(output_tokens)
                ANTHROPIC_REPORTED_TOKENS.labels(model=model, token_type="cache_read").set(cache_read)
                ANTHROPIC_REPORTED_TOKENS.labels(model=model, token_type="cache_write").set(cache_write)
                ANTHROPIC_REPORTED_COST_USD.labels(model=model).set(cost_usd)

                # Upsert snapshot
                snapshot = db.query(AnthropicUsageSnapshot).filter_by(
                    snapshot_date=yesterday_date,
                    model=model
                ).first()

                if snapshot:
                    snapshot.input_tokens = input_tokens
                    snapshot.output_tokens = output_tokens
                    snapshot.cache_read_input_tokens = cache_read
                    snapshot.cache_creation_input_tokens = cache_write
                    snapshot.cost_usd = cost_usd
                    snapshot.fetched_at = datetime.now(timezone.utc)
                    snapshot.raw_usage_response = bucket
                    snapshot.raw_cost_response = costs_by_model
                else:
                    snapshot = AnthropicUsageSnapshot(
                        snapshot_date=yesterday_date,
                        model=model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cache_read_input_tokens=cache_read,
                        cache_creation_input_tokens=cache_write,
                        cost_usd=cost_usd,
                        fetched_at=datetime.now(timezone.utc),
                        raw_usage_response=record,
                        raw_cost_response=costs_by_model,
                    )
                    db.add(snapshot)

                synced_models.append(model)

            db.commit()
            ANTHROPIC_USAGE_LAST_SYNC.set(time.time())

            return {
                "status": "success",
                "message": f"Synced {len(synced_models)} model(s) for {yesterday_date}",
                "date": str(yesterday_date),
                "models": synced_models,
            }

        except Exception as e:
            db.rollback()
            logger.error("Manual sync failed during database persist", exc_info=True)
            raise
        finally:
            db.close()

    except Exception as e:
        logger.error("Manual Anthropic usage sync failed", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
        }
