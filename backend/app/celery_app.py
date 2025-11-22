# backend/app/celery_app.py
"""Celery application initialization.

Loads broker/backend from settings. Import this in worker startup and tasks.
Run worker locally:
  celery -A app.celery_app.celery_app worker --loglevel=info --pool=solo
"""
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
except Exception:
    # Non-fatal here; if imports fail the worker will likely fail later when using DB.
    pass

# Tasks are organized in app/services/tasks/
try:
    import app.services.tasks.extraction  # noqa: F401 - Extraction pipeline tasks
    import app.services.tasks.document_processor  # noqa: F401 - Document indexing pipeline tasks
    import app.services.tasks.workflows  # noqa: F401 - Workflow execution pipeline tasks
except Exception:
    # Avoid hard failure if tasks module temporarily missing; log later after logging init.
    pass

@celery_app.task(bind=True)
def ping(self):  # simple health check task
    return {"status": "ok"}
