from fastapi import APIRouter
from app.api import health, extract, feedback, analytics
from app.api import export


api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(extract.router)
api_router.include_router(feedback.router)
api_router.include_router(analytics.router)
api_router.include_router(export.router)

__all__ = ["api_router"]

