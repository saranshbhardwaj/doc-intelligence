"""Prometheus multiprocess mode setup for API + Celery worker metrics.

This module configures Prometheus to collect metrics from multiple processes:
- API process (HTTP requests, system metrics)
- Celery worker processes (workflow runs, LLM metrics)
- Celery beat process (periodic task scheduler)

Without this, worker metrics won't show up in the API's /metrics endpoint.

Docker note: All containers run as PID 1, so we use a combination of
container type offset + HOSTNAME hash to give each container a unique
process identifier. This ensures separate .db files per container
(no clobbering) while preserving the {type}_{integer}.db format that
MultiProcessCollector can parse.

Example: worker1 → counter_234567.db, worker2 → counter_278901.db
"""
import os
import time
import hashlib
from pathlib import Path
import prometheus_client.values
from app.utils.logging import logger

# Base offsets per container type to group .db files by range.
# API: 100000-199999, Workers: 200000-299999, Beat: 300000-399999
PID_OFFSETS = {'api': 100000, 'worker': 200000, 'beat': 300000}

TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def _get_process_identifier(container_type: str) -> int:
    """Generate a unique process identifier per process instance.

    Uses container_type to select the base offset range, then combines
    HOSTNAME (Docker container ID) with real PID to differentiate:
    - Multiple containers of the same type (worker1, worker2, worker3)
    - Multiple processes within a container (uvicorn workers in API)

    Result: Each process gets unique ID:
    - API uvicorn worker PID 8 → ~155818
    - API uvicorn worker PID 9 → ~167234
    - worker1 container PID 1 → ~261124
    - worker2 container PID 1 → ~279892

    Each process gets its own .db files — no clobbering.
    """
    base_offset = PID_OFFSETS.get(container_type, 200000)

    # Combine HOSTNAME + PID for truly unique identifier
    # This handles both multi-container AND multi-process scenarios
    hostname = os.environ.get('HOSTNAME', '')
    pid = os.getpid()

    if hostname:
        # Hash "hostname:pid" to get unique ID per process
        unique_str = f"{hostname}:{pid}"
        host_hash = int(hashlib.md5(unique_str.encode()).hexdigest()[:8], 16) % 99999
        return base_offset + host_hash + 1  # +1 to avoid offset+0

    # Fallback for local dev (no Docker): use real PID + offset
    return pid + base_offset


def _cleanup_stale_files(metrics_dir: str, proc_id: int) -> int:
    """Clean only THIS container's stale prometheus files on startup.

    Uses the exact proc_id to match files (e.g., counter_234567.db),
    so restarting one container never wipes another container's metrics.

    Returns:
        Number of files cleaned
    """
    cleaned = 0
    metrics_path = Path(metrics_dir)

    if not metrics_path.exists():
        return 0

    # Only delete files with our specific proc_id suffix
    for db_file in metrics_path.glob(f"*_{proc_id}.db"):
        try:
            db_file.unlink(missing_ok=True)
            cleaned += 1
            logger.debug(f"Cleaned stale prometheus file: {db_file.name}")
        except Exception as e:
            logger.warning(f"Failed to clean prometheus file {db_file}: {e}")

    return cleaned


def _cleanup_retention_files(metrics_dir: str, container_type: str) -> int:
    """Apply retention rules to multiprocess files.

    Configurable via environment variables:
      - PROMETHEUS_MULTIPROC_GC_ENABLED (default: true)
      - PROMETHEUS_MULTIPROC_GC_LEADER_ONLY (default: true)
      - PROMETHEUS_MULTIPROC_GC_MAX_AGE_DAYS (default: 3)
      - PROMETHEUS_MULTIPROC_GC_MAX_FILES (default: 25000)
      - PROMETHEUS_MULTIPROC_GC_MAX_SIZE_MB (default: 512)
      - PROMETHEUS_MULTIPROC_GC_MIN_AGE_SECONDS (default: 3600)
    """
    if not _env_bool("PROMETHEUS_MULTIPROC_GC_ENABLED", True):
        return 0

    leader_only = _env_bool("PROMETHEUS_MULTIPROC_GC_LEADER_ONLY", True)
    if leader_only and container_type != "api":
        return 0

    metrics_path = Path(metrics_dir)
    if not metrics_path.exists():
        return 0

    max_age_days = _env_int("PROMETHEUS_MULTIPROC_GC_MAX_AGE_DAYS", 3, minimum=0)
    max_files = _env_int("PROMETHEUS_MULTIPROC_GC_MAX_FILES", 25_000, minimum=0)
    max_size_mb = _env_int("PROMETHEUS_MULTIPROC_GC_MAX_SIZE_MB", 512, minimum=0)
    min_age_seconds = _env_int("PROMETHEUS_MULTIPROC_GC_MIN_AGE_SECONDS", 3_600, minimum=0)
    max_size_bytes = max_size_mb * 1024 * 1024

    now = time.time()
    deleted = 0

    candidates: list[tuple[Path, float, int]] = []
    for file_path in metrics_path.glob("*.db"):
        try:
            stat = file_path.stat()
            candidates.append((file_path, stat.st_mtime, stat.st_size))
        except OSError:
            continue

    if not candidates:
        return 0

    # Step 1: hard age-based cleanup
    if max_age_days > 0:
        age_cutoff = now - (max_age_days * 86400)
        for file_path, mtime, _size in list(candidates):
            if mtime < age_cutoff:
                try:
                    file_path.unlink(missing_ok=True)
                    deleted += 1
                    candidates.remove((file_path, mtime, _size))
                except OSError:
                    continue

    # Step 2: enforce size/file caps for "old enough" files only
    total_size = sum(size for _path, _mtime, size in candidates)
    removable = sorted(
        [item for item in candidates if (now - item[1]) >= min_age_seconds],
        key=lambda item: item[1],  # oldest first
    )

    while removable and (
        (max_files > 0 and len(candidates) > max_files) or
        (max_size_bytes > 0 and total_size > max_size_bytes)
    ):
        file_path, mtime, size = removable.pop(0)
        try:
            file_path.unlink(missing_ok=True)
            deleted += 1
            total_size -= size
            candidates.remove((file_path, mtime, size))
        except OSError:
            continue

    if deleted > 0:
        logger.info(
            "Prometheus multiprocess retention cleanup completed",
            extra={
                "deleted_files": deleted,
                "remaining_files": len(candidates),
                "remaining_size_mb": round(total_size / (1024 * 1024), 2),
                "max_age_days": max_age_days,
                "max_files": max_files,
                "max_size_mb": max_size_mb,
            },
        )

    return deleted


def setup_prometheus_multiproc_dir(clear_on_startup: bool = True):
    """Initialize Prometheus multiprocess directory with PID offset.

    Uses integer PID offsets to avoid PID collisions in Docker where both
    API and worker containers run as PID 1. This keeps the standard
    {type}_{integer}.db filename format that MultiProcessCollector can parse.

    Args:
        clear_on_startup: If True, clean stale metric files from our PID range
    """
    # Get metrics directory — keep it FLAT (no subdirectories)
    metrics_dir = os.environ.get('PROMETHEUS_MULTIPROC_DIR', '/tmp/prometheus_multiproc')
    os.environ['PROMETHEUS_MULTIPROC_DIR'] = metrics_dir

    metrics_path = Path(metrics_dir)
    metrics_path.mkdir(parents=True, exist_ok=True)

    # Generate unique process identifier per container instance
    container_type = os.environ.get('CONTAINER_TYPE', 'app')
    proc_id = _get_process_identifier(container_type)

    # Set custom process identifier BEFORE any metrics are created
    # Each container gets a unique ID → separate .db files → no clobbering
    prometheus_client.values.ValueClass = prometheus_client.values.MultiProcessValue(
        process_identifier=lambda: proc_id
    )

    # Clean only THIS container's stale files (not other containers')
    if clear_on_startup:
        try:
            cleaned = _cleanup_stale_files(metrics_dir, proc_id)
            if cleaned > 0:
                logger.debug(f"Cleaned {cleaned} stale Prometheus metric file(s)")
        except Exception as e:
            logger.warning(f"Stale file cleanup failed: {e}")

        try:
            _cleanup_retention_files(metrics_dir, container_type)
        except Exception as e:
            logger.warning(f"Retention cleanup failed: {e}")

    logger.info(
        f"Prometheus multiprocess directory: {metrics_dir} "
        f"(container_type={container_type}, pid={os.getpid()}, "
        f"proc_id={proc_id})"
    )

    # Initialize a gauge on startup so /metrics always returns at least one metric
    try:
        from prometheus_client import Gauge
        startup_gauge = Gauge(
            'docint_process_info',
            'Active process heartbeat (1 = alive)',
            ['container_type', 'pid'],
            multiprocess_mode='liveall'
        )
        startup_gauge.labels(
            container_type=container_type,
            pid=str(os.getpid())
        ).set(1)
        logger.info(f"Initialized docint_process_info gauge (container={container_type}, pid={os.getpid()})")
    except Exception as e:
        logger.debug(f"Startup gauge already registered: {e}")

    # Pre-register labeled metrics so they appear in /metrics immediately
    try:
        from app.utils.metrics import init_labeled_metrics
        init_labeled_metrics()
        logger.info("Initialized labeled Prometheus metrics")
    except Exception as e:
        logger.warning(f"Failed to initialize labeled metrics: {e}")

    # METRICS_DEBUG: log .db files in multiproc dir at startup
    try:
        import glob as glob_mod
        db_files = glob_mod.glob(os.path.join(metrics_dir, "*.db"))
        logger.info(
            f"METRICS_DEBUG: {len(db_files)} .db files in {metrics_dir}: "
            f"{[os.path.basename(f) for f in db_files[:20]]}"
        )
    except Exception as e:
        logger.warning(f"METRICS_DEBUG: failed to list .db files: {e}")

    return metrics_dir


def start_worker_metrics_server(port: int = 9091) -> None:
    """Expose worker Prometheus metrics over HTTP (background daemon thread).

    Workers have no FastAPI app. This starts a minimal HTTP server that
    serves MultiProcessCollector output from the local PROMETHEUS_MULTIPROC_DIR.

    On Railway, each worker service has an isolated filesystem, so the API
    cannot read worker .db files directly. This endpoint lets the Railway
    Prometheus service scrape each worker independently.

    Call once per worker process, after setup_prometheus_multiproc_dir().
    """
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from prometheus_client import CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
    from prometheus_client.multiprocess import MultiProcessCollector

    metrics_port = int(os.environ.get("METRICS_PORT", str(port)))
    metrics_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR", "")

    if not metrics_port or not metrics_dir:
        logger.info("Worker metrics server disabled (METRICS_PORT or PROMETHEUS_MULTIPROC_DIR not set)")
        return

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            registry = CollectorRegistry()
            MultiProcessCollector(registry, path=metrics_dir)
            output = generate_latest(registry)
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(output)

        def log_message(self, *args):
            pass  # Suppress per-request access log noise

    def _serve():
        HTTPServer(("", metrics_port), _Handler).serve_forever()

    threading.Thread(target=_serve, daemon=True, name="prometheus-metrics").start()
    logger.info(f"Worker Prometheus metrics server started on :{metrics_port}")
