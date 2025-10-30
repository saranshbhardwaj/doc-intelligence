# backend/app/services/db_rate_limiter.py
"""Database-backed rate limiter with per-user customization"""
from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.db_models import RateLimit
from app.models import RateLimitInfo
from app.config import settings
from app.utils.logging import logger


class DatabaseRateLimiter:
    """Rate limiter using database for persistence and customization

    Features:
    - Per-user/per-IP rate limits
    - Persistent across restarts
    - Customizable limits per user
    - Automatic daily/monthly resets

    Rate limits are now configurable via environment variables.
    See config.py for rate_limit_*_daily and rate_limit_*_monthly settings.
    """

    def __init__(self, db: Session):
        """Initialize rate limiter with database session

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def _get_default_limits(self, tier: str) -> dict:
        """Get default limits for a tier from settings

        Args:
            tier: User tier ('free', 'pro', 'enterprise')

        Returns:
            Dict with 'daily' and 'monthly' limits
        """
        if tier == "free":
            return {
                "daily": settings.rate_limit_free_daily,
                "monthly": settings.rate_limit_free_monthly
            }
        elif tier == "pro":
            return {
                "daily": settings.rate_limit_pro_daily,
                "monthly": settings.rate_limit_pro_monthly
            }
        elif tier == "enterprise":
            return {
                "daily": settings.rate_limit_enterprise_daily,
                "monthly": settings.rate_limit_enterprise_monthly
            }
        else:
            # Unknown tier - default to free
            logger.warning(f"Unknown tier '{tier}', defaulting to free tier limits")
            return {
                "daily": settings.rate_limit_free_daily,
                "monthly": settings.rate_limit_free_monthly
            }

    def check_rate_limit(self, identifier: str, identifier_type: str = "ip") -> RateLimitInfo:
        """Check if user/IP has remaining quota

        Args:
            identifier: IP address or user ID
            identifier_type: 'ip' or 'user'

        Returns:
            RateLimitInfo with current limits and remaining quota

        Raises:
            Exception: If rate limit exceeded
        """
        # Get or create rate limit entry
        rate_limit = self._get_or_create_rate_limit(identifier, identifier_type)

        # Reset counts if needed
        rate_limit = self._reset_if_needed(rate_limit)

        # Check if limit exceeded
        if rate_limit.daily_limit > 0:  # -1 means unlimited
            if rate_limit.current_daily_count >= rate_limit.daily_limit:
                logger.warning(f"Rate limit exceeded for {identifier} (daily limit: {rate_limit.daily_limit})")
                raise Exception(
                    f"Daily upload limit reached ({rate_limit.daily_limit} uploads per day). "
                    f"Limit resets in {self._hours_until_next_day()} hours. "
                    f"Upgrade to Pro for higher limits."
                )

        # Return rate limit info
        remaining = max(0, rate_limit.daily_limit - rate_limit.current_daily_count)
        if rate_limit.daily_limit == -1:
            remaining = -1  # Unlimited

        return RateLimitInfo(
            remaining_uploads=remaining,
            reset_in_hours=self._hours_until_next_day(),
            limit_per_window=rate_limit.daily_limit
        )

    def increment_count(self, identifier: str, identifier_type: str = "ip"):
        """Increment usage count for user/IP

        Args:
            identifier: IP address or user ID
            identifier_type: 'ip' or 'user'
        """
        rate_limit = self._get_or_create_rate_limit(identifier, identifier_type)
        rate_limit = self._reset_if_needed(rate_limit)

        # Increment counts
        rate_limit.current_daily_count += 1
        rate_limit.current_monthly_count += 1

        self.db.commit()
        logger.info(f"Rate limit incremented for {identifier}: {rate_limit.current_daily_count}/{rate_limit.daily_limit}")

    def set_custom_limit(
        self,
        identifier: str,
        daily_limit: int,
        monthly_limit: int,
        tier: str = "custom",
        notes: str = None
    ):
        """Set custom rate limit for specific user/IP

        Args:
            identifier: IP address or user ID
            daily_limit: Daily upload limit (-1 for unlimited)
            monthly_limit: Monthly upload limit (-1 for unlimited)
            tier: User tier
            notes: Admin notes (e.g., "Beta tester")
        """
        rate_limit = self._get_or_create_rate_limit(identifier, "user")

        rate_limit.daily_limit = daily_limit
        rate_limit.monthly_limit = monthly_limit
        rate_limit.tier = tier
        if notes:
            rate_limit.notes = notes

        self.db.commit()
        logger.info(f"Custom rate limit set for {identifier}: {daily_limit}/day, {monthly_limit}/month")

    def get_tier(self, identifier: str) -> str:
        """Get user tier

        Args:
            identifier: IP address or user ID

        Returns:
            User tier ('free', 'pro', 'enterprise')
        """
        rate_limit = self.db.query(RateLimit).filter(RateLimit.identifier == identifier).first()
        return rate_limit.tier if rate_limit else "free"

    def _get_or_create_rate_limit(self, identifier: str, identifier_type: str) -> RateLimit:
        """Get existing rate limit or create new one

        Args:
            identifier: IP address or user ID
            identifier_type: 'ip' or 'user'

        Returns:
            RateLimit database object
        """
        # Try to get existing
        rate_limit = self.db.query(RateLimit).filter(RateLimit.identifier == identifier).first()

        if rate_limit:
            return rate_limit

        # Create new with default limits for 'free' tier
        defaults = self._get_default_limits("free")
        rate_limit = RateLimit(
            identifier=identifier,
            identifier_type=identifier_type,
            tier="free",
            daily_limit=defaults["daily"],
            monthly_limit=defaults["monthly"],
            current_daily_count=0,
            current_monthly_count=0,
            last_daily_reset=date.today(),
            last_monthly_reset=date.today()
        )

        self.db.add(rate_limit)
        self.db.commit()
        self.db.refresh(rate_limit)

        logger.info(f"Created new rate limit entry for {identifier} (tier: free)")
        return rate_limit

    def _reset_if_needed(self, rate_limit: RateLimit) -> RateLimit:
        """Reset counts if day/month has changed

        Args:
            rate_limit: RateLimit object

        Returns:
            Updated RateLimit object
        """
        today = date.today()
        needs_commit = False

        # Reset daily count if new day
        if rate_limit.last_daily_reset < today:
            rate_limit.current_daily_count = 0
            rate_limit.last_daily_reset = today
            needs_commit = True
            logger.info(f"Daily count reset for {rate_limit.identifier}")

        # Reset monthly count if new month
        if rate_limit.last_monthly_reset.month != today.month or rate_limit.last_monthly_reset.year != today.year:
            rate_limit.current_monthly_count = 0
            rate_limit.last_monthly_reset = today
            needs_commit = True
            logger.info(f"Monthly count reset for {rate_limit.identifier}")

        if needs_commit:
            self.db.commit()
            self.db.refresh(rate_limit)

        return rate_limit

    def _hours_until_next_day(self) -> int:
        """Calculate hours until next day (for reset time)

        Returns:
            Hours until midnight
        """
        from datetime import datetime
        now = datetime.now()
        tomorrow = datetime(now.year, now.month, now.day) + timedelta(days=1)
        hours_remaining = (tomorrow - now).seconds // 3600
        return max(1, hours_remaining)  # At least 1 hour
