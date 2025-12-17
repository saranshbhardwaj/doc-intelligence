"""Private Equity API routes.

Main router that aggregates all PE vertical endpoints.
Routes: /api/v1/pe/*
"""
from fastapi import APIRouter

# Import routers from sub-modules (to be created)
# from .workflows import router as workflows_router
# from .extraction import router as extraction_router
# from .comparison import router as comparison_router

router = APIRouter(prefix="/pe", tags=["private_equity"])

# Include sub-routers (uncomment as modules are created)
# router.include_router(workflows_router)
# router.include_router(extraction_router)
# router.include_router(comparison_router)


@router.get("/health")
async def health_check():
    """Health check endpoint for PE vertical."""
    return {"status": "healthy", "vertical": "private_equity"}
