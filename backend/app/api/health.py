# app/api/health.py
from datetime import datetime
from fastapi import APIRouter
from app.config import settings

router = APIRouter()

@router.get("/api/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "environment": settings.environment,
        "anthropic_configured": bool(settings.anthropic_api_key),
        "cache_entries": len(list(settings.parsed_dir.glob("*.json")))
    }