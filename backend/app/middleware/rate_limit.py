"""Rate limiting middleware to prevent abuse and security scanning attacks."""
import time
from collections import defaultdict
from typing import Callable
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.utils.logging import logger
from app.utils.metrics import (
    HTTP_REQUESTS_RATE_LIMITED,
    HTTP_SUSPICIOUS_REQUESTS
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware with security scanning detection.

    Features:
    - Per-IP rate limiting (requests per minute)
    - Suspicious pattern detection (XSS, path traversal)
    - Prometheus metrics for monitoring
    - Auto-blocking of repeated offenders
    """

    def __init__(
        self,
        app,
        requests_per_minute: int = 60,
        burst_limit: int = 100,
        block_duration: int = 300  # 5 minutes
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.burst_limit = burst_limit
        self.block_duration = block_duration

        # Tracking structures
        self.request_counts = defaultdict(list)  # IP -> [timestamp, timestamp, ...]
        self.blocked_ips = {}  # IP -> block_until_timestamp
        self.suspicious_patterns = [
            '<script',
            'javascript:',
            'alert(',
            '../',
            'WEB-INF',
            'META-INF',
            '.nasl',
            '%3cscript',
            '%3e%3c',
        ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting and security checks."""
        client_ip = self._get_client_ip(request)
        current_time = time.time()

        # Check if IP is blocked
        if client_ip in self.blocked_ips:
            if current_time < self.blocked_ips[client_ip]:
                logger.warning(
                    f"Blocked request from rate-limited IP",
                    extra={"client_ip": client_ip, "path": request.url.path}
                )
                HTTP_REQUESTS_RATE_LIMITED.labels(
                    client_ip=client_ip,
                    path=request.url.path
                ).inc()
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please try again later."
                )
            else:
                # Unblock IP after duration expires
                del self.blocked_ips[client_ip]

        # Check for suspicious patterns
        if self._is_suspicious(request):
            logger.warning(
                f"Suspicious request detected",
                extra={
                    "client_ip": client_ip,
                    "path": request.url.path,
                    "user_agent": request.headers.get("user-agent", "unknown")
                }
            )
            HTTP_SUSPICIOUS_REQUESTS.labels(
                client_ip=client_ip,
                pattern="xss_or_scan"
            ).inc()

            # Auto-block IPs sending suspicious requests
            self.blocked_ips[client_ip] = current_time + self.block_duration

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden"
            )

        # Rate limiting check
        request_times = self.request_counts[client_ip]

        # Remove old timestamps (outside the 1-minute window)
        cutoff_time = current_time - 60
        request_times = [t for t in request_times if t > cutoff_time]

        # Check burst limit
        if len(request_times) >= self.burst_limit:
            logger.warning(
                f"Rate limit exceeded (burst)",
                extra={"client_ip": client_ip, "request_count": len(request_times)}
            )
            HTTP_REQUESTS_RATE_LIMITED.labels(
                client_ip=client_ip,
                path=request.url.path
            ).inc()

            # Block IP temporarily
            self.blocked_ips[client_ip] = current_time + self.block_duration

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {self.burst_limit} requests/minute"
            )

        # Check per-minute limit
        if len(request_times) >= self.requests_per_minute:
            logger.info(
                f"Rate limit warning",
                extra={"client_ip": client_ip, "request_count": len(request_times)}
            )

        # Record this request
        request_times.append(current_time)
        self.request_counts[client_ip] = request_times

        # Cleanup old entries periodically (every 1000 requests)
        if len(self.request_counts) > 1000:
            self._cleanup_old_entries(current_time)

        # Process request
        response = await call_next(request)
        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        # Check X-Forwarded-For header (if behind proxy)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()

        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"

    def _is_suspicious(self, request: Request) -> bool:
        """Check if request contains suspicious patterns."""
        path = request.url.path.lower()
        query = str(request.url.query).lower()

        for pattern in self.suspicious_patterns:
            if pattern in path or pattern in query:
                return True

        return False

    def _cleanup_old_entries(self, current_time: float):
        """Remove old tracking entries to prevent memory bloat."""
        cutoff = current_time - 120  # Keep last 2 minutes

        # Cleanup request counts
        for ip in list(self.request_counts.keys()):
            self.request_counts[ip] = [
                t for t in self.request_counts[ip] if t > cutoff
            ]
            if not self.request_counts[ip]:
                del self.request_counts[ip]

        # Cleanup expired blocks
        for ip in list(self.blocked_ips.keys()):
            if current_time >= self.blocked_ips[ip]:
                del self.blocked_ips[ip]
