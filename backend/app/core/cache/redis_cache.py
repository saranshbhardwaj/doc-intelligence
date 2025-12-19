from typing import Optional
from app.config import settings
from app.utils.logging import logger

try:
    import redis
except Exception:
    redis = None


class RedisDocumentCache:
    """
    Redis-backed cache for processed documents. Uses content-hash keys and TTL.
    """

    def __init__(self, cache_ttl_hours: int = 24, redis_url: Optional[str] = None):
        if redis is None:
            raise RuntimeError("redis package not available")
        self.client = redis.Redis.from_url(redis_url or settings.redis_url)
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
                return None
            logger.info(f"Redis cache HIT for {key}")
            import json

            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Redis cache error on get: {e}")
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
