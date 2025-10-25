# backend/app/rate_limiter.py
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Tuple
from app.utils.logging import logger

class RateLimiter:
    """
    In-memory rate limiter.
    In production, use Redis for distributed rate limiting.
    """
    
    def __init__(self, max_uploads: int, window_hours: int):
        self.max_uploads = max_uploads
        self.window = timedelta(hours=window_hours)
        self.storage = defaultdict(list)  # ip -> [timestamps]
    
    def _clean_old_entries(self, ip: str):
        """Remove timestamps outside the window"""
        cutoff = datetime.now() - self.window
        self.storage[ip] = [
            ts for ts in self.storage[ip]
            if ts > cutoff
        ]
    
    def check_limit(self, ip: str) -> Tuple[bool, int]:
        """
        Check if IP is within rate limit.
        Returns: (is_allowed, remaining_uploads)
        """
        self._clean_old_entries(ip)
        
        current_count = len(self.storage[ip])
        remaining = max(0, self.max_uploads - current_count)
        is_allowed = current_count < self.max_uploads
        
        logger.info(
            f"Rate limit check for {ip}: "
            f"{current_count}/{self.max_uploads} used, "
            f"allowed={is_allowed}"
        )
        
        return is_allowed, remaining
    
    def record_upload(self, ip: str):
        """Record an upload for the IP"""
        self.storage[ip].append(datetime.now())
        logger.info(f"Recorded upload for {ip}")
    
    def get_reset_time(self, ip: str) -> datetime:
        """Get when the rate limit resets for this IP"""
        self._clean_old_entries(ip)
        if not self.storage[ip]:
            return datetime.now()
        
        oldest = min(self.storage[ip])
        return oldest + self.window
    
    def clear_expired(self):
        """Clean up expired entries from all IPs"""
        before_count = sum(len(v) for v in self.storage.values())
        
        for ip in list(self.storage.keys()):
            self._clean_old_entries(ip)
            if not self.storage[ip]:
                del self.storage[ip]
        
        after_count = sum(len(v) for v in self.storage.values())
        removed = before_count - after_count
        
        if removed > 0:
            logger.info(f"Cleaned {removed} expired rate limit entries")