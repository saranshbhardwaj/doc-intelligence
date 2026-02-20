"""User-facing dashboard API endpoints.

Provides analytics and insights for authenticated users, automatically scoped to org_id.

Endpoints:
- GET /api/dashboard/overview?days=30 - High-level stats
- GET /api/dashboard/activity?days=30 - Daily activity breakdown
- GET /api/dashboard/template-fills?days=30 - Template fill insights

Note: LLM costs (cost_usd) are internal operational data and NOT exposed to users.
"""
from fastapi import APIRouter, Depends, Query
from app.auth import get_current_user
from app.db_models_users import User
from app.repositories.dashboard_repository import DashboardRepository
from app.utils.logging import logger

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard/overview")
async def get_dashboard_overview(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to include in stats"),
    user: User = Depends(get_current_user),
):
    """
    Get high-level dashboard overview for the organization.

    Automatically scoped to user's org_id. Includes:
    - Document counts (total, period)
    - Chat activity (sessions, messages)
    - Template fill stats (total, completed, failed, success rate)
    - Extraction stats (total, completed, failed)
    - Workflow stats (total, completed, failed)
    - Active users count

    Args:
        days: Number of days to include in period stats (default 30, max 365)
        user: Current authenticated user (injected by dependency)

    Returns:
        Dict with overview stats:
        {
            "period_days": 30,
            "documents": {"total": 47, "period": 12},
            "chat": {"sessions": 23, "messages": 156},
            "template_fills": {"total": 18, "completed": 15, "failed": 3, "success_rate": 0.83},
            "extractions": {"total": 31, "completed": 28, "failed": 3},
            "workflows": {"total": 8, "completed": 7, "failed": 1},
            "active_users": 5
        }
    """
    repo = DashboardRepository()
    overview = repo.get_overview(org_id=user.org_id, days=days)

    logger.info(
        f"Dashboard overview requested",
        extra={
            "user_id": user.id,
            "org_id": user.org_id,
            "days": days,
            "total_documents": overview.get("documents", {}).get("total", 0)
        }
    )

    return overview


@router.get("/api/dashboard/activity")
async def get_dashboard_activity(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to include in breakdown"),
    user: User = Depends(get_current_user),
):
    """
    Get daily activity breakdown for charts.

    Automatically scoped to user's org_id. Returns daily counts for:
    - Chat messages
    - Template fills
    - Extractions

    Args:
        days: Number of days to include (default 30, max 365)
        user: Current authenticated user (injected by dependency)

    Returns:
        Dict with daily activity:
        {
            "daily": [
                {"date": "2026-02-01", "chat_messages": 12, "template_fills": 3, "extractions": 5},
                {"date": "2026-02-02", "chat_messages": 8, "template_fills": 1, "extractions": 2}
            ]
        }
    """
    repo = DashboardRepository()
    daily = repo.get_daily_activity(org_id=user.org_id, days=days)

    logger.info(
        f"Dashboard activity requested",
        extra={
            "user_id": user.id,
            "org_id": user.org_id,
            "days": days,
            "activity_days_returned": len(daily)
        }
    )

    return {"daily": daily}


@router.get("/api/dashboard/template-fills")
async def get_dashboard_template_fills(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to include in stats"),
    user: User = Depends(get_current_user),
):
    """
    Get template fill insights and statistics.

    Automatically scoped to user's org_id. Includes:
    - Status breakdown (completed, failed, running)
    - Average fields filled per run
    - Average auto-mapping success rate
    - Average processing time
    - Top templates by usage

    Args:
        days: Number of days to include (default 30, max 365)
        user: Current authenticated user (injected by dependency)

    Returns:
        Dict with template fill stats:
        {
            "by_status": {"completed": 15, "failed": 3, "running": 0},
            "avg_fields_filled": 24.5,
            "avg_auto_map_rate": 0.85,
            "avg_processing_time_seconds": 45.2,
            "top_templates": [
                {"template_name": "Rent Roll v1", "fill_count": 8},
                {"template_name": "Operating Statement", "fill_count": 5}
            ]
        }
    """
    repo = DashboardRepository()
    stats = repo.get_template_fill_stats(org_id=user.org_id, days=days)

    logger.info(
        f"Dashboard template fill stats requested",
        extra={
            "user_id": user.id,
            "org_id": user.org_id,
            "days": days,
            "total_fills": sum(stats.get("by_status", {}).values())
        }
    )

    return stats


__all__ = ["router"]
