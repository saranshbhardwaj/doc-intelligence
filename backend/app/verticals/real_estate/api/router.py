"""Real Estate API routes.

Main router that aggregates all RE vertical endpoints.
Routes: /api/v1/re/*
"""
from fastapi import APIRouter, Depends
from app.auth import require_vertical

# Import routers from sub-modules
from .templates import router as templates_router
from .underwriting import router as underwriting_router
from .memos import router as memos_router
from .acquisitions import router as acquisitions_router

router = APIRouter(
    prefix="/re",
    tags=["real_estate"],
    dependencies=[Depends(require_vertical("real_estate"))]
)

# Include sub-routers
router.include_router(templates_router)
router.include_router(underwriting_router)
router.include_router(memos_router)
router.include_router(acquisitions_router)


@router.get("/health")
async def health_check():
    """Health check endpoint for RE vertical."""
    return {"status": "healthy", "vertical": "real_estate"}
