from pathlib import Path
from typing import Optional
from app.config import settings

# Lazy import to avoid heavy dependencies at module import time
try:
    from .redis_cache import RedisDocumentCache
except Exception:
    RedisDocumentCache = None  # type: ignore

from .file_cache import DocumentCache


def create_cache(cache_dir: Optional[Path] = None, cache_ttl_hours: int = 24):
    """Factory: return Redis-backed cache if configured, else file-backed cache."""
    if getattr(settings, "use_redis_cache", False) and RedisDocumentCache is not None:
        try:
            return RedisDocumentCache(cache_ttl_hours=cache_ttl_hours, redis_url=getattr(settings, "redis_url", None))
        except Exception:
            # Fall back to file cache
            pass
    return DocumentCache(cache_dir or settings.cache_dir, cache_ttl_hours=cache_ttl_hours)

__all__ = ["create_cache", "DocumentCache", "RedisDocumentCache"]
