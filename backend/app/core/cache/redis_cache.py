from typing import Optional, List, Dict, Any
from app.config import settings
from app.utils.logging import logger
from app.utils.metrics import DOC_CACHE_HITS, DOC_CACHE_MISSES

try:
    import redis
except Exception:
    redis = None

# Import centralized Redis connection pool
from app.core.redis_client import get_redis_pool


class RedisDocumentCache:
    """
    Redis-backed cache for processed documents. Uses content-hash keys and TTL.
    Features connection pooling and Prometheus metrics.
    """

    def __init__(self, cache_ttl_hours: int = 24, redis_url: Optional[str] = None):
        if redis is None:
            raise RuntimeError("redis package not available")
        # Use centralized connection pool with decode_responses=False for binary data
        pool = get_redis_pool(redis_url or settings.redis_url, decode_responses=False)
        self.client = redis.Redis(connection_pool=pool)
        self.cache_ttl_seconds = int(cache_ttl_hours * 3600)

    def _get_content_hash(self, content: bytes) -> str:
        import hashlib

        return hashlib.sha256(content).hexdigest()

    def get(self, content: bytes) -> Optional[dict]:
        key = f"doccache:{self._get_content_hash(content)}"
        try:
            raw = self.client.get(key)
            if not raw:
                logger.info(f"Redis cache MISS for {key}")
                DOC_CACHE_MISSES.labels(cache_type="redis").inc()
                return None
            logger.info(f"Redis cache HIT for {key}")
            DOC_CACHE_HITS.labels(cache_type="redis").inc()
            import json

            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Redis cache error on get: {e}")
            DOC_CACHE_MISSES.labels(cache_type="redis").inc()
            return None

    def set(self, content: bytes, result: dict):
        key = f"doccache:{self._get_content_hash(content)}"
        try:
            import json

            self.client.setex(key, self.cache_ttl_seconds, json.dumps(result, ensure_ascii=False))
            logger.info(f"Redis cache SET for {key}")
        except Exception as e:
            logger.warning(f"Redis cache error on set: {e}")

    def clear_expired(self):
        # Redis TTL handles eviction automatically
        return 0

    def list_entries(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all cached document keys (for admin)."""
        try:
            keys = self.client.keys("doccache:*")
            entries = []
            for key in keys[:limit]:
                key_str = key.decode() if isinstance(key, bytes) else key
                ttl = self.client.ttl(key)
                entries.append({
                    "key": key_str,
                    "ttl_seconds": ttl if ttl > 0 else None
                })
            return entries
        except Exception as e:
            logger.warning(f"Failed to list cache entries: {e}")
            return []

    def clear_all(self) -> int:
        """Clear all document cache entries."""
        try:
            keys = self.client.keys("doccache:*")
            if keys:
                deleted = self.client.delete(*keys)
                logger.info(f"Cleared {deleted} Redis cache entries")
                return deleted
            return 0
        except Exception as e:
            logger.warning(f"Failed to clear cache: {e}")
            return 0
