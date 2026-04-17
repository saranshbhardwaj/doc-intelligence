"""
Centralized Redis client for both API and worker contexts.

Provides singleton Redis clients with connection pooling.
Used by:
- Cache system (RedisDocumentCache, ConversationSummaryCache)
- SSE streaming (job progress events)
- Stuck task monitor (SSE notifications)
- Auth (Clerk webhook deduplication)
"""
from typing import Optional
import logging

try:
    import redis
    from redis import ConnectionPool, Redis
except ImportError:
    redis = None
    ConnectionPool = None
    Redis = None

logger = logging.getLogger(__name__)

# Module-level connection pools (singletons)
_redis_pool: Optional["ConnectionPool"] = None  # For binary data (cache)
_redis_pool_decode: Optional["ConnectionPool"] = None  # For text data (SSE, auth)


def get_redis_pool(redis_url: str, max_connections: int = 10, decode_responses: bool = False) -> "ConnectionPool":
    """
    Get or create a Redis connection pool (singleton).

    Args:
        redis_url: Redis connection URL
        max_connections: Maximum connections in pool
        decode_responses: If True, decode bytes to strings automatically

    Returns:
        Redis connection pool
    """
    global _redis_pool, _redis_pool_decode

    if redis is None or ConnectionPool is None:
        raise RuntimeError("redis package not available")

    # Use separate pools for binary vs text to avoid decode_responses conflicts
    if decode_responses:
        if _redis_pool_decode is None:
            _redis_pool_decode = ConnectionPool.from_url(
                redis_url,
                max_connections=max_connections,
                decode_responses=True
            )
            logger.info(f"Created Redis connection pool (decode=True): max_connections={max_connections}")
        return _redis_pool_decode
    else:
        if _redis_pool is None:
            _redis_pool = ConnectionPool.from_url(
                redis_url,
                max_connections=max_connections,
                decode_responses=False
            )
            logger.info(f"Created Redis connection pool (decode=False): max_connections={max_connections}")
        return _redis_pool


def get_redis_client(redis_url: Optional[str] = None, decode_responses: bool = True) -> "Redis":
    """
    Get a Redis client with connection pooling.

    This is the main function to use throughout the codebase.

    Args:
        redis_url: Redis connection URL (uses settings.redis_url if None)
        decode_responses: If True, decode bytes to strings (for SSE, auth)
                         If False, keep as bytes (for cache)

    Returns:
        Redis client instance

    Raises:
        RuntimeError: If redis package is not available

    Example:
        # For SSE/auth (strings)
        client = get_redis_client()
        client.publish("channel", "message")

        # For cache (bytes)
        client = get_redis_client(decode_responses=False)
        client.set("key", b"binary_data")
    """
    if redis is None or Redis is None:
        raise RuntimeError("redis package not available - install with: pip install redis")

    # Get Redis URL from settings if not provided
    if redis_url is None:
        from app.config import settings
        redis_url = settings.redis_url

    # Get connection pool
    pool = get_redis_pool(redis_url, decode_responses=decode_responses)

    # Return client using pool
    return redis.Redis(connection_pool=pool)


# Convenience alias for common SSE/auth use case
def get_redis_client_for_sse() -> "Redis":
    """
    Get Redis client for SSE streaming (strings, decode_responses=True).

    This is a convenience wrapper for the most common use case.
    """
    return get_redis_client(decode_responses=True)


# Convenience alias for cache use case
def get_redis_client_for_cache() -> "Redis":
    """
    Get Redis client for caching (bytes, decode_responses=False).

    This is a convenience wrapper for cache implementations.
    """
    return get_redis_client(decode_responses=False)
