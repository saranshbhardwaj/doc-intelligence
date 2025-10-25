# app/core/lifespan.py
import asyncio
from contextlib import asynccontextmanager
from app.config import settings
from app.utils.logging import logger
from app.api.dependencies import rate_limiter


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
    # cache.clear_expired()
    rate_limiter.clear_expired()

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

            # cache_removed = cache.clear_expired()
            # logger.info(f"Cache cleanup: removed {cache_removed} expired entries")
            
            # Clean rate limiter
            rate_limiter.clear_expired()
            logger.info("Rate limiter cleanup completed")
            
        except asyncio.CancelledError:
            logger.info("Cleanup task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}", exc_info=True)
            # Continue running even if cleanup fails