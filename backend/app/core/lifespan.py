# app/core/lifespan.py
import asyncio
from contextlib import asynccontextmanager
from app.config import settings
from app.utils.logging import logger
from app.api.dependencies import cache


@asynccontextmanager
async def lifespan(app):
    """Run setup and teardown logic for the app lifecycle."""

    # ---------- Startup ----------
    logger.info("Application starting", extra={
        "environment": settings.environment,
        "rate_limit": f"{settings.rate_limit_uploads} uploads per {settings.rate_limit_window_hours}h",
        "max_pages": settings.max_pages,
        "max_file_size_mb": settings.max_file_size_mb
    })

    # Warn loudly if mock mode is enabled
    if settings.mock_mode:
        logger.warning("=" * 60)
        logger.warning("MOCK MODE ENABLED - RETURNING TEST DATA ONLY")
        logger.warning("Set MOCK_MODE=false in .env to use real API")
        logger.warning("=" * 60)

    # Clean up cache on startup
    removed = cache.clear_expired()
    logger.info(f"Cache cleanup on startup: removed {removed} expired entries")

    # Start background cleanup task
    # cleanup_task = asyncio.create_task(periodic_cleanup())

    # yield control to the running app
    yield

    # ---------- Shutdown ----------

    # cleanup_task.cancel()  # Stop background task
    # try:
    #     await cleanup_task
    # except asyncio.CancelledError:
    #     pass
    # logger.info("Application shutting down")


async def periodic_cleanup():
    """Run cleanup every hour"""
    while True:
        try:
            await asyncio.sleep(3600)  # 1 hour = 3600 seconds
            logger.info("Running periodic cleanup...")
            # Clean cache
            removed = cache.clear_expired()
            logger.info(f"Cache cleanup: removed {removed} expired entries")
        except asyncio.CancelledError:
            logger.info("Cleanup task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}", exc_info=True)
            # Continue running even if cleanup fails