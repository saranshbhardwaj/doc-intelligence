# app/core/lifespan.py
import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from app.config import settings
from app.utils.logging import logger
from app.api.dependencies import cache
from app.database import get_db, async_engine
from app.verticals.private_equity.workflows.seeding import seed_workflows
from app.core.embeddings.factory import get_embedding_provider
from app.services.service_locator import get_reranker

# Retention settings (could later move to settings)
UPLOAD_RETENTION_HOURS = 6  # Delete uploaded source PDFs older than this
UPLOAD_SCAN_INTERVAL_SECONDS = 1800  # 30 minutes
SHARED_UPLOAD_ROOT = os.getenv("SHARED_UPLOAD_ROOT", "/shared_uploads")

# Anthropic usage sync settings
ANTHROPIC_USAGE_SYNC_INTERVAL = 86400  # 24 hours (daily)


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

    # Seed workflow templates (idempotent) — retry for Railway IPv6→IPv4 fallback
    for attempt in range(3):
        try:
            db = next(get_db())
            created = seed_workflows(db)
            if created:
                logger.info("Seeded workflows", extra={"count": len(created), "names": created})
            else:
                logger.info("No new workflows seeded (already present)")
            db.close()
            break
        except Exception as e:
            if attempt < 2:
                logger.warning("Workflow seeding retry", extra={"attempt": attempt + 1, "error": str(e)})
                await asyncio.sleep(5)
            else:
                logger.error("Workflow seeding failed after 3 attempts", extra={"error": str(e)})

    # Start background cleanup task (cache + uploaded file pruning)
    cleanup_task = asyncio.create_task(periodic_cleanup())

    # Start background Anthropic usage sync task (if admin key configured)
    usage_sync_task = asyncio.create_task(periodic_anthropic_usage_sync())

    get_embedding_provider()
    if settings.rag_use_reranker:
        get_reranker()  # Preload reranker

    logger.info("✅ Models ready")

    # yield control to the running app
    yield

    # ---------- Shutdown ----------

    cleanup_task.cancel()  # Stop background task
    usage_sync_task.cancel()  # Stop usage sync task
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    try:
        await usage_sync_task
    except asyncio.CancelledError:
        pass

    # Dispose async engine to release connection pool (prevents memory leak)
    await async_engine.dispose()
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


async def periodic_anthropic_usage_sync():
    """Fetch Anthropic usage/cost data daily and update metrics.

    Runs in background, fetching yesterday's complete data from Anthropic Admin API.
    Updates Prometheus gauges and persists snapshots to database.
    """
    from datetime import datetime
    from app.services.anthropic_usage_service import AnthropicUsageService
    from app.utils.metrics import (
        ANTHROPIC_REPORTED_TOKENS,
        ANTHROPIC_REPORTED_COST_USD,
        ANTHROPIC_USAGE_LAST_SYNC
    )
    from app.db_models import AnthropicUsageSnapshot

    # Wait 60s on startup to let the app settle
    await asyncio.sleep(60)

    while True:
        try:
            # Check if admin API key is configured
            if not settings.anthropic_admin_api_key:
                logger.debug("Anthropic Admin API key not configured, skipping usage sync")
                await asyncio.sleep(ANTHROPIC_USAGE_SYNC_INTERVAL)
                continue

            logger.info("Starting Anthropic usage sync...")

            # Initialize service
            service = AnthropicUsageService(settings.anthropic_admin_api_key)

            # Fetch yesterday's data (complete day in UTC)
            starting_at, ending_at = service.get_yesterday_time_range()
            yesterday_date = datetime.strptime(starting_at, "%Y-%m-%dT%H:%M:%SZ").date()

            logger.info(
                "Fetching Anthropic usage for yesterday",
                extra={
                    "date": str(yesterday_date),
                    "starting_at": starting_at,
                    "ending_at": ending_at,
                }
            )

            # Fetch usage and cost reports
            usage_report = await service.fetch_usage_report(
                starting_at, ending_at, bucket_width="1d", group_by=["model"]
            )
            cost_report = await service.fetch_cost_report(
                starting_at, ending_at, group_by=["description"]
            )

            logger.info(
                "Fetched Anthropic reports",
                extra={
                    "usage_time_buckets": len(usage_report.get("data", [])),
                    "cost_buckets": len(cost_report.get("data", [])),
                }
            )

            # Parse cost data by model
            costs_by_model = {}
            for bucket in cost_report.get("data", []):
                description = bucket.get("description", "")
                model = service.parse_model_from_description(description)
                cost_str = bucket.get("cost", "0")
                # Cost is in USD string format (cents precision)
                cost_usd = float(cost_str) if cost_str else 0.0
                costs_by_model[model] = costs_by_model.get(model, 0.0) + cost_usd

            # Update Prometheus gauges and persist to database
            db = next(get_db())
            try:
                model_records = AnthropicUsageService.flatten_usage_data(usage_report)

                for record in model_records:
                    model = record["model"]
                    input_tokens = record["input_tokens"]
                    output_tokens = record["output_tokens"]
                    cache_read = record["cache_read_input_tokens"]
                    cache_write = record["cache_creation_input_tokens"]
                    cost_usd = costs_by_model.get(model, 0.0)

                    # Update Prometheus gauges
                    ANTHROPIC_REPORTED_TOKENS.labels(model=model, token_type="input").set(input_tokens)
                    ANTHROPIC_REPORTED_TOKENS.labels(model=model, token_type="output").set(output_tokens)
                    ANTHROPIC_REPORTED_TOKENS.labels(model=model, token_type="cache_read").set(cache_read)
                    ANTHROPIC_REPORTED_TOKENS.labels(model=model, token_type="cache_write").set(cache_write)
                    ANTHROPIC_REPORTED_COST_USD.labels(model=model).set(cost_usd)

                    # Upsert snapshot to database
                    snapshot = db.query(AnthropicUsageSnapshot).filter_by(
                        snapshot_date=yesterday_date,
                        model=model
                    ).first()

                    if snapshot:
                        # Update existing
                        snapshot.input_tokens = input_tokens
                        snapshot.output_tokens = output_tokens
                        snapshot.cache_read_input_tokens = cache_read
                        snapshot.cache_creation_input_tokens = cache_write
                        snapshot.cost_usd = cost_usd
                        snapshot.fetched_at = datetime.now(timezone.utc)
                        snapshot.raw_usage_response = record
                        snapshot.raw_cost_response = costs_by_model
                    else:
                        # Create new
                        snapshot = AnthropicUsageSnapshot(
                            snapshot_date=yesterday_date,
                            model=model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cache_read_input_tokens=cache_read,
                            cache_creation_input_tokens=cache_write,
                            cost_usd=cost_usd,
                            fetched_at=datetime.now(timezone.utc),
                            raw_usage_response=record,
                            raw_cost_response=costs_by_model,
                        )
                        db.add(snapshot)

                db.commit()

                # Update last sync timestamp
                ANTHROPIC_USAGE_LAST_SYNC.set(time.time())

                logger.info(
                    "Anthropic usage sync complete",
                    extra={
                        "date": str(yesterday_date),
                        "models_synced": len(model_records),
                    }
                )

            except Exception as e:
                db.rollback()
                logger.error("Failed to persist Anthropic usage snapshots", exc_info=True)
                raise
            finally:
                db.close()

        except asyncio.CancelledError:
            logger.info("Anthropic usage sync task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in Anthropic usage sync: {e}", exc_info=True)
            # Continue loop after logging error

        # Wait for next sync (24 hours)
        await asyncio.sleep(ANTHROPIC_USAGE_SYNC_INTERVAL)