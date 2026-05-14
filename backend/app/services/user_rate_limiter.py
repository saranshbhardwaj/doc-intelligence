"""Per-user Redis sliding-window rate limiter.

Industry-standard pattern used by large-scale APIs:
- Each user gets an independent counter, not shared with other users behind the same IP
- Sliding window (not fixed window) prevents burst-at-boundary abuse
- Atomic Lua script: ZREMRANGEBYSCORE + ZCARD + ZADD in one round-trip, no TOCTOU race
- Fail-open: if Redis is unreachable the request is allowed through; log for monitoring

Usage in a FastAPI endpoint:

    from app.services.user_rate_limiter import enforce_fill_run_rate_limit

    @router.post("/{template_id}/fill")
    async def start_fill(user: User = Depends(get_current_user), ...):
        enforce_fill_run_rate_limit(user.id)
        ...
"""
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, status

from app.utils.logging import logger

# Atomic sliding-window script.
# Prunes entries older than the window, checks the count, and records
# the request only if allowed — all in a single Redis round-trip.
_SLIDING_WINDOW_LUA = """
local key          = KEYS[1]
local now          = tonumber(ARGV[1])
local window_start = tonumber(ARGV[2])
local limit        = tonumber(ARGV[3])
local member       = ARGV[4]
local ttl          = tonumber(ARGV[5])

redis.call('ZREMRANGEBYSCORE', key, 0, window_start)
local count = redis.call('ZCARD', key)

if count >= limit then
    return {0, 0}
end

redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, ttl)
return {1, limit - count - 1}
"""


@dataclass
class _LimitResult:
    allowed: bool
    remaining: int


class UserRateLimiter:
    """Sliding-window rate limiter backed by Redis sorted sets.

    Thread-safe across multiple processes (each process shares the same Redis key).
    Falls back to allow-all if Redis is unavailable.
    """

    def __init__(self, scope: str, limit: int, window_seconds: int) -> None:
        self.scope = scope
        self.limit = limit
        self.window_seconds = window_seconds

    def _key(self, user_id: str) -> str:
        return f"ratelimit:{self.scope}:{user_id}"

    def _client(self):
        from app.core.redis_client import get_redis_client
        return get_redis_client(decode_responses=True)

    def check(self, user_id: str) -> _LimitResult:
        """Record a request attempt and return whether it is allowed."""
        try:
            client = self._client()
            now = time.time()
            result = client.eval(
                _SLIDING_WINDOW_LUA,
                1,                              # numkeys
                self._key(user_id),             # KEYS[1]
                str(now),                       # ARGV[1] — current timestamp
                str(now - self.window_seconds), # ARGV[2] — window start
                str(self.limit),                # ARGV[3] — max requests
                f"{now}:{uuid.uuid4().hex}",    # ARGV[4] — unique member
                str(self.window_seconds),       # ARGV[5] — key TTL
            )
            return _LimitResult(allowed=bool(result[0]), remaining=int(result[1]))
        except Exception as exc:
            # Classify the failure so ops can distinguish Redis being down
            # (ConnectionError/TimeoutError) from unexpected bugs (other types).
            exc_type = type(exc).__name__
            is_connection_issue = isinstance(exc, (ConnectionError, TimeoutError, OSError))

            log_extra = {
                "scope": self.scope,
                "user_id": user_id,
                "error_type": exc_type,
                "error": str(exc),
                "fail_open": True,
            }

            if is_connection_issue:
                # Redis is unreachable — rate limiting is fully disabled until
                # connectivity is restored. Warn loudly so alerting picks it up.
                logger.warning(
                    "UserRateLimiter: Redis unreachable — rate limiting disabled (fail-open). "
                    "Check Redis connectivity.",
                    extra=log_extra,
                )
            else:
                # Unexpected error (script bug, auth failure, etc.) — log with
                # full traceback so it can be diagnosed.
                logger.error(
                    "UserRateLimiter: unexpected error — rate limiting disabled (fail-open).",
                    extra=log_extra,
                    exc_info=True,
                )

            return _LimitResult(allowed=True, remaining=self.limit)


# ── Singleton limiters (lazy-initialized so settings are available) ────────────

_fill_run_limiter: Optional[UserRateLimiter] = None


def _get_fill_run_limiter() -> UserRateLimiter:
    global _fill_run_limiter
    if _fill_run_limiter is None:
        from app.config import settings
        _fill_run_limiter = UserRateLimiter(
            scope="fill_run",
            limit=settings.template_fill_rate_limit_per_minute,
            window_seconds=60,
        )
    return _fill_run_limiter


# ── Public enforcement helpers (call directly in route handlers) ───────────────

def enforce_fill_run_rate_limit(user_id: str) -> None:
    """Raise HTTP 429 if the user exceeds the per-minute fill run rate limit.

    Designed to be called at the start of the start_fill endpoint, after
    authentication and before any DB writes or Celery task enqueues.
    """
    limiter = _get_fill_run_limiter()
    result = limiter.check(user_id)
    if not result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Rate limit exceeded: you may start at most "
                f"{limiter.limit} fill runs per minute. Please wait before retrying."
            ),
            headers={"Retry-After": str(limiter.window_seconds)},
        )
