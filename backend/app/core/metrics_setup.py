"""Prometheus multiprocess mode setup for API + Celery worker metrics.

This module configures Prometheus to collect metrics from multiple processes:
- API process (HTTP requests, system metrics)
- Celery worker process (workflow runs, LLM metrics)

Without this, worker metrics won't show up in the API's /metrics endpoint.
"""
import os
import atexit
from pathlib import Path
from app.utils.logging import logger


def _cleanup_stale_files(metrics_dir: str) -> int:
    """Clean stale prometheus multiprocess files.

    Uses PID-based detection to identify and remove files from dead processes,
    with fallback to direct file deletion for corrupted files.

    Returns:
        Number of files cleaned
    """
    cleaned = 0
    metrics_path = Path(metrics_dir)

    if not metrics_path.exists():
        return 0

    # Get all .db files
    db_files = list(metrics_path.glob("*.db"))

    for db_file in db_files:
        try:
            # Try to extract PID from filename (format: type_pid.db)
            parts = db_file.stem.split("_")
            if len(parts) >= 2:
                pid_str = parts[-1]
                try:
                    pid = int(pid_str)
                    # Check if process is still alive
                    try:
                        os.kill(pid, 0)  # Signal 0 = check if process exists
                        # Process alive, skip
                        continue
                    except OSError:
                        # Process dead, safe to remove
                        pass
                except ValueError:
                    # Not a valid PID, remove anyway
                    pass

            # Remove the file
            db_file.unlink(missing_ok=True)
            cleaned += 1
            logger.debug(f"Cleaned stale prometheus file: {db_file.name}")

        except Exception as e:
            # If we can't process the file, try to remove it anyway
            try:
                db_file.unlink(missing_ok=True)
                cleaned += 1
            except Exception:
                logger.warning(f"Failed to clean prometheus file {db_file}: {e}")

    return cleaned


def setup_prometheus_multiproc_dir(clear_on_startup: bool = True):
    """Initialize Prometheus multiprocess directory.

    Args:
        clear_on_startup: If True, clean stale metric files on startup (recommended for API)
    """
    # Get or set multiprocess directory
    metrics_dir = os.environ.get('PROMETHEUS_MULTIPROC_DIR')

    if not metrics_dir:
        # Default to /tmp/prometheus_multiproc in production, or temp dir locally
        metrics_dir = '/tmp/prometheus_multiproc'
        os.environ['PROMETHEUS_MULTIPROC_DIR'] = metrics_dir

    metrics_path = Path(metrics_dir)

    # Create directory first
    metrics_path.mkdir(parents=True, exist_ok=True)

    # Clean stale files from dead processes
    if clear_on_startup:
        try:
            cleaned = _cleanup_stale_files(metrics_dir)
            if cleaned > 0:
                logger.info(f"Cleaned {cleaned} stale Prometheus metric file(s)")
        except Exception as e:
            # If cleanup fails, try full wipe as fallback
            logger.warning(f"Stale file cleanup failed, performing full wipe: {e}")
            try:
                import shutil
                shutil.rmtree(metrics_path, ignore_errors=True)
                metrics_path.mkdir(parents=True, exist_ok=True)
            except Exception as e2:
                logger.error(f"Failed to wipe prometheus dir: {e2}")

    logger.info(f"Prometheus multiprocess directory: {metrics_dir}")

    # Register cleanup on process exit (graceful shutdown)
    def _cleanup_on_exit():
        try:
            pid = os.getpid()
            for pattern in ["counter", "gauge", "histogram", "summary"]:
                filepath = metrics_path / f"{pattern}_{pid}.db"
                if filepath.exists():
                    filepath.unlink(missing_ok=True)
        except Exception:
            pass  # Best effort cleanup

    atexit.register(_cleanup_on_exit)

    return metrics_dir
