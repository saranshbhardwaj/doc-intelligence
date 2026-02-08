import os
from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry
from prometheus_client.multiprocess import MultiProcessCollector

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", summary="Prometheus metrics scrape endpoint")
def metrics_root():
    """Expose Prometheus metrics from all processes (API + Celery workers).

    Uses multiprocess mode to aggregate metrics from:
    - API process (HTTP requests, system metrics)
    - Celery worker processes (workflow runs, LLM metrics)
    """
    # Check if multiprocess mode is enabled
    multiproc_dir = os.environ.get('PROMETHEUS_MULTIPROC_DIR')

    if multiproc_dir and os.path.exists(multiproc_dir):
        # Multiprocess mode: collect from all processes
        registry = CollectorRegistry()
        MultiProcessCollector(registry)
        data = generate_latest(registry)
    else:
        # Single process mode (fallback)
        data = generate_latest()

    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
