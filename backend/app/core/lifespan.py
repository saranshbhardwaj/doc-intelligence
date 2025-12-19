# app/core/lifespan.py
import asyncio
import os
import time
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from app.config import settings
from app.utils.logging import logger
from app.api.dependencies import cache
from app.database import get_db
from app.services.workflows.seeding import seed_workflows
from app.core.embeddings.factory import get_embedding_provider
from app.services.service_locator import get_reranker

# Retention settings (could later move to settings)
UPLOAD_RETENTION_HOURS = 6  # Delete uploaded source PDFs older than this
UPLOAD_SCAN_INTERVAL_SECONDS = 1800  # 30 minutes
SHARED_UPLOAD_ROOT = os.getenv("SHARED_UPLOAD_ROOT", "/shared_uploads")


@asynccontextmanager
async def lifespan(app):
    """Run setup and teardown logic for the app lifecycle."""

    # ---------- Startup ----------
    logger.info("Application starting", extra={
        "environment": settings.environment,
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

    # Seed workflow templates (idempotent)
    try:
        db = next(get_db())
        created = seed_workflows(db)
        if created:
            logger.info("Seeded workflows", extra={"count": len(created), "names": created})
        else:
            logger.info("No new workflows seeded (already present)")
        db.close()
    except Exception as e:
        logger.error("Workflow seeding failed", extra={"error": str(e)})

    # Start background cleanup task (cache + uploaded file pruning)
    cleanup_task = asyncio.create_task(periodic_cleanup())
    
    get_embedding_provider()
    if settings.rag_use_reranker:
        get_reranker()  # Preload reranker
    
    logger.info("✅ Models ready")

    # yield control to the running app
    yield

    # ---------- Shutdown ----------

    cleanup_task.cancel()  # Stop background task
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    logger.info("Application shutting down")


async def periodic_cleanup():
    """Run periodic cleanup of cache + stale uploaded files"""
    while True:
        try:
            await asyncio.sleep(UPLOAD_SCAN_INTERVAL_SECONDS)
            logger.info("Running periodic maintenance cleanup...")

            # Cache cleanup
            removed = cache.clear_expired()
            logger.info(f"Cache cleanup: removed {removed} expired entries")

            # Uploaded file pruning
            if os.path.isdir(SHARED_UPLOAD_ROOT):
                cutoff = time.time() - (UPLOAD_RETENTION_HOURS * 3600)
                deleted = 0
                scanned = 0
                for name in os.listdir(SHARED_UPLOAD_ROOT):
                    path = os.path.join(SHARED_UPLOAD_ROOT, name)
                    if not os.path.isfile(path):
                        continue
                    scanned += 1
                    try:
                        st = os.stat(path)
                        if st.st_mtime < cutoff:
                            os.remove(path)
                            deleted += 1
                    except FileNotFoundError:
                        continue
                    except Exception as e:  # log and continue
                        logger.warning("Failed to evaluate uploaded file for cleanup", extra={"file": path, "error": str(e)})
                logger.info(
                    "Upload cleanup complete",
                    extra={"scanned": scanned, "deleted": deleted, "retention_hours": UPLOAD_RETENTION_HOURS}
                )
            else:
                logger.debug("Shared upload root does not exist yet", extra={"path": SHARED_UPLOAD_ROOT})
        except asyncio.CancelledError:
            logger.info("Cleanup task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}", exc_info=True)
            # Continue loop after logging