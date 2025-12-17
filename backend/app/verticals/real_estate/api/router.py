"""Real Estate API routes.

Main router that aggregates all RE vertical endpoints.
Routes: /api/v1/re/*
"""
from fastapi import APIRouter

# Import routers from sub-modules (to be created)
# from .excel_templates import router as templates_router
# from .template_filling import router as filling_router

router = APIRouter(prefix="/re", tags=["real_estate"])

# Include sub-routers (uncomment as modules are created)
# router.include_router(templates_router)
# router.include_router(filling_router)


@router.get("/health")
async def health_check():
    """Health check endpoint for RE vertical."""
    return {"status": "healthy", "vertical": "real_estate"}
