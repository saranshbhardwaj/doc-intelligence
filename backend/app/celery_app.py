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
# (Autodiscover could be used instead if package layout expands)
try:
    import app.services.celery_tasks  # noqa: F401
except Exception as e:
    # Avoid hard failure if tasks module temporarily missing; log later after logging init.
    pass

@celery_app.task(bind=True)
def ping(self):  # simple health check task
    return {"status": "ok"}
