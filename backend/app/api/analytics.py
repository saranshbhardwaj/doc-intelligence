# app/api/analytics.py
from app.services import analytics
from fastapi import APIRouter, Header, HTTPException
from app.config import settings

router = APIRouter()

@router.get("/api/analytics/stats")
async def get_analytics_stats(
    days: int = 7,
    x_admin_key: str = Header(None, description="Admin API key for authentication")
):
    """
    Get basic analytics stats (for internal use).
    Requires admin API key in X-Admin-Key header.
    """
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized - Invalid or missing admin API key"
        )

    stats = analytics.get_stats(days=days)
    return {
        "period_days": days,
        "stats": stats
    }