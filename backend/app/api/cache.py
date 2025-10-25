# app/api/cache.py
from fastapi import APIRouter
from app.api.dependencies import cache

router = APIRouter()

@router.get("/list")
async def list_cache():
    """List all cached entries"""
    return cache.list_entries()

@router.delete("/clear")
async def clear_cache():
    """Clear all cache"""
    cache.clear_all()
    return {"success": True, "message": "Cache cleared"}