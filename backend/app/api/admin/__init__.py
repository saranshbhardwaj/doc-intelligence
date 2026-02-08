"""Admin API router - admin-only endpoints for observability and management."""
from fastapi import APIRouter
from . import observability

# Create admin router with prefix
router = APIRouter(prefix="/api/admin", tags=["admin"])

# Include sub-routers
router.include_router(observability.router)
