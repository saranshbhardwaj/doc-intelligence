# backend/app/celery_app.py
"""Celery application initialization.

Loads broker/backend from settings. Import this in worker startup and tasks.
Run worker locally:
  celery -A app.celery_app.celery_app worker --loglevel=info --pool=solo
"""
import os
import sys

# Debug configuration - attach debugpy if DEBUG is truthy
def _is_debug_enabled() -> bool:
    return os.getenv("DEBUG", "").strip().lower() in {"1", "true", "yes", "y", "on"}

def _should_wait_for_debugger() -> bool:
    return os.getenv("DEBUG_WAIT", "").strip().lower() in {"1", "true", "yes", "y", "on"}

if _is_debug_enabled():
    try:
        import debugpy
        debugpy.listen(("0.0.0.0", 5679))
        print("⏸️  Celery worker debugger listening on 0.0.0.0:5679", file=sys.stderr)
        if _should_wait_for_debugger():
            print("⏳ Waiting for debugger to attach (Celery)...", file=sys.stderr)
            debugpy.wait_for_client()
    except Exception as e:
        print(f"Failed to initialize debugpy for Celery: {e}", file=sys.stderr)

# Initialize Prometheus multiprocess mode for worker metrics
# This MUST happen before any metrics are imported/created
from app.core.metrics_setup import setup_prometheus_multiproc_dir
setup_prometheus_multiproc_dir(clear_on_startup=True)  # Safe: only cleans our PID range

from celery import Celery
from app.config import settings

celery_app = Celery(
    "doc_intelligence",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Recommended explicit JSON serializer settings
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    task_time_limit=900,             # Hard kill after 15 min (prevents stuck worker slots)
    task_soft_time_limit=840,        # Raise SoftTimeLimitExceeded after 14 min
    task_default_queue="default",    # Fallback queue for unrouted tasks
    result_expires=3600,             # Task results expire after 1 hour (prevents stuck task bloat)
    result_extended=True,            # Store full traceback for debugging failed tasks
)

# Priority queue routing: business-critical tasks → "critical" queue,
# background indexing → "default" queue.
# Workers subscribe to specific queues via -Q flag in docker-compose.
celery_app.conf.task_routes = {
    # Critical: user-facing, revenue-impacting tasks get dedicated workers
    "app.verticals.private_equity.workflows.tasks.tasks.*": {"queue": "critical"},
    "app.verticals.private_equity.extraction.tasks.tasks.*": {"queue": "critical"},
    "app.verticals.private_equity.diligence.tasks.*": {"queue": "critical"},
    "app.verticals.private_equity.diligence.investigations.tasks.*": {"queue": "critical"},
    "app.verticals.real_estate.template_filling.tasks.*": {"queue": "critical"},
    # Default: document indexing runs in background, can wait
    "app.services.tasks.document_processor.*": {"queue": "default"},
    "app.services.tasks.stuck_task_monitor.*": {"queue": "default"},
}

# Celery Beat schedule for periodic tasks
# Run `celery -A app.celery_app.celery_app beat` to start the scheduler
from celery.schedules import crontab
celery_app.conf.beat_schedule = {
    "cleanup-stuck-tasks": {
        "task": "app.services.tasks.stuck_task_monitor.cleanup_stuck_tasks",
        "schedule": crontab(minute="*/10"),  # Run every 10 minutes
        "options": {"queue": "default"},  # Low-priority maintenance task
    },
}

# Explicitly import task modules so worker registers them.
# Ensure all model modules are imported first so SQLAlchemy MetaData knows about
# every table (especially workflow_runs) before any task code performs DB writes.
try:
    import app.db_models  # noqa: F401 - Extraction, ParserOutput, CacheEntry, JobState
    import app.db_models_users  # noqa: F401 - User
    import app.db_models_chat  # noqa: F401 - Collection, CollectionDocument, DocumentChunk, ChatSession, ChatMessage
    import app.db_models_workflows  # noqa: F401 - Workflow, WorkflowRun
    import app.db_models_documents  # noqa: F401 - Document, DocumentChunk
    import app.db_models_templates  # noqa: F401 - ExcelTemplate, TemplateFillRun
    import app.db_models_pe_diligence  # noqa: F401 - PE diligence domain models
except Exception:
    # Non-fatal here; if imports fail the worker will likely fail later when using DB.
    pass

# Tasks are organized in app/services/tasks/ and app/verticals/
try:
        import app.services.tasks.document_processor  # noqa: F401 - Document indexing pipeline tasks
        import app.services.tasks.stuck_task_monitor  # noqa: F401 - Background cleanup of stuck tasks
        import app.verticals.private_equity.extraction.tasks  # noqa: F401 - PE extraction pipeline tasks
        import app.verticals.private_equity.workflows.tasks.tasks  # noqa: F401 - PE workflow execution pipeline tasks (explicit import to ensure registration)
        import app.verticals.private_equity.diligence.tasks  # noqa: F401 - PE diligence analysis tasks
        import app.verticals.private_equity.diligence.investigations.tasks  # noqa: F401 - PE diligence investigation tasks
        import app.verticals.real_estate.template_filling.tasks  # noqa: F401 - RE template filling tasks
except Exception as e:
    # Log task import failures so we can debug worker registration issues
    import sys
    print(f"WARNING: Failed to import task modules: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)

# With pool=solo, each worker is a single process.
# No forking complexity, no need for per-child Prometheus reinitialization.
# Metrics work correctly with the initial setup_prometheus_multiproc_dir() call above.


@celery_app.task(bind=True)
def ping(self):  # simple health check task
    return {"status": "ok"}
