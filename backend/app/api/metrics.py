import os
import logging
from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry
from prometheus_client.multiprocess import MultiProcessCollector

_metrics_logger = logging.getLogger("app.metrics_debug")

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", summary="Prometheus metrics scrape endpoint")
def metrics_root():
    """Expose Prometheus metrics from all processes (API + Celery workers).

    Uses multiprocess mode to aggregate metrics from all .db files in the
    shared PROMETHEUS_MULTIPROC_DIR directory. Each container type uses a
    PID offset to avoid filename collisions (see metrics_setup.py).
    """
    multiproc_dir = os.environ.get('PROMETHEUS_MULTIPROC_DIR')

    if multiproc_dir and os.path.exists(multiproc_dir):
        registry = CollectorRegistry()
        MultiProcessCollector(registry, path=multiproc_dir)
        data = generate_latest(registry)
    else:
        data = generate_latest()

    # METRICS_DEBUG: log workflow-related lines from scrape output
    workflow_lines = [l for l in data.decode().split('\n') if 'workflow_runs' in l]
    if workflow_lines:
        _metrics_logger.info(f"METRICS_DEBUG /metrics scrape: {workflow_lines}")
    else:
        _metrics_logger.info("METRICS_DEBUG /metrics scrape: NO workflow_runs lines found")

    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
