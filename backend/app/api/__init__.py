from fastapi import APIRouter
from app.api import health, extractions, feedback, analytics


api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(extractions.router)
api_router.include_router(feedback.router)
api_router.include_router(analytics.router)

__all__ = ["api_router"]

