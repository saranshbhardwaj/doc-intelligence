# app/api/cache.py
from fastapi import APIRouter, Depends
from app.api.dependencies import cache
from app.auth import require_org_role

router = APIRouter()

@router.get("/list")
async def list_cache():
    """List all cached entries"""
    return cache.list_entries()

@router.delete("/clear")
async def clear_cache(_role: str = Depends(require_org_role(["admin"]))):
    """Clear all cache"""
    cache.clear_all()
    return {"success": True, "message": "Cache cleared"}