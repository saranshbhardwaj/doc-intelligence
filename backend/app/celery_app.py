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
setup_prometheus_multiproc_dir(clear_on_startup=False)  # Don't clear - API already did

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
    worker_max_tasks_per_child=100,  # recycle to avoid memory leaks
    broker_connection_retry_on_startup=True,
)

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
except Exception:
    # Non-fatal here; if imports fail the worker will likely fail later when using DB.
    pass

# Tasks are organized in app/services/tasks/ and app/verticals/
try:
        import app.services.tasks.document_processor  # noqa: F401 - Document indexing pipeline tasks
        import app.verticals.private_equity.extraction.tasks  # noqa: F401 - PE extraction pipeline tasks
        import app.verticals.private_equity.workflows.tasks  # noqa: F401 - PE workflow execution pipeline tasks
        import app.verticals.real_estate.template_filling.tasks  # noqa: F401 - RE template filling tasks
except Exception:
    # Avoid hard failure if tasks module temporarily missing; log later after logging init.
    pass

@celery_app.task(bind=True)
def ping(self):  # simple health check task
    return {"status": "ok"}
