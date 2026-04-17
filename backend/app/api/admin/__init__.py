"""Admin API router - admin-only endpoints for observability and management."""
from fastapi import APIRouter
from . import observability, anthropic_usage, task_management, allowlist, template_fill_analytics

# Create admin router with prefix
router = APIRouter(prefix="/api/admin", tags=["admin"])

# Include sub-routers
router.include_router(observability.router)
router.include_router(anthropic_usage.router)
router.include_router(task_management.router)
router.include_router(allowlist.router)
router.include_router(template_fill_analytics.router)
