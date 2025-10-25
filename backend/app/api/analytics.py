# app/api/analytics.py
from app.services import analytics
from fastapi import APIRouter

router = APIRouter()

@router.get("/api/analytics/stats")
async def get_analytics_stats(days: int = 7):
    """
    Get basic analytics stats (for internal use).
    In production, protect this endpoint with auth.
    """
    stats = analytics.get_stats(days=days)
    return {
        "period_days": days,
        "stats": stats
    }