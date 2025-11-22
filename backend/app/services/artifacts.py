"""Artifact persistence/retrieval service.

Responsibilities:
- Persist workflow artifact dicts to storage (Cloudflare R2) when enabled
- Return a compact pointer object to store in DB
- Load full artifact JSON given a pointer-or-inline object
"""
from __future__ import annotations
from typing import Dict, Any
import json
from datetime import datetime

from app.config import settings
from app.utils.logging import logger
from app.utils.metrics import ARTIFACT_PERSIST_SECONDS, ARTIFACT_PERSIST_FAILURES

try:
    from app.services.storage.cloudflare_r2 import get_r2_storage
except Exception:
    get_r2_storage = None  # type: ignore


def _now_ts() -> str:
    return datetime.utcnow().isoformat()


def persist_artifact(run_id: str, artifact: Dict[str, Any]) -> Dict[str, Any]:
    """Persist artifact to storage (if enabled) and return pointer JSON for DB.

    If storage disabled, returns the original artifact dict (inline store in DB).
    Pointer structure (R2):
    {
        "backend": "r2",
        "bucket": <bucket>,
        "key": "artifacts/<run_id>/artifact.json",
        "size_bytes": <int>,
        "created_at": <iso8601>
    }
    """
    timer = ARTIFACT_PERSIST_SECONDS.time()
    try:
        if settings.exports_use_r2 and get_r2_storage is not None:
            try:
                storage = get_r2_storage()
                key = f"workflow-artifacts/{run_id}/artifact.json"
                data = json.dumps(artifact, ensure_ascii=False).encode("utf-8")
                storage.store_bytes(key, data, "application/json")
                pointer = {
                    "backend": "r2",
                    "bucket": settings.r2_bucket,
                    "key": key,
                    "size_bytes": len(data),
                    "created_at": _now_ts(),
                }
                logger.info("Artifact persisted to R2", extra={"run_id": run_id, "key": key, "size": len(data)})
                return pointer
            except Exception:
                ARTIFACT_PERSIST_FAILURES.inc()
                logger.exception("Artifact persistence to R2 failed — storing inline in DB", extra={"run_id": run_id})
                return artifact
        return artifact
    finally:
        try:
            timer.__exit__(None, None, None)
        except Exception:
            pass
    # storage disabled -> inline
    return artifact


def load_artifact(pointer_or_inline: Dict[str, Any]) -> Dict[str, Any]:
    """Load full artifact dict given a pointer or inline object.

    If object contains keys {backend: 'r2', key: '...'}, fetch from R2 and decode JSON.
    Otherwise, return the object itself.
    """
    if isinstance(pointer_or_inline, dict) and pointer_or_inline.get("backend") == "r2":
        if get_r2_storage is None:
            raise RuntimeError("R2 storage not available to load artifact")
        key = pointer_or_inline.get("key")
        if not key:
            raise ValueError("Artifact pointer missing key")
        storage = get_r2_storage()
        try:
            data = storage.get_bytes(key)
            return json.loads(data.decode("utf-8"))
        except Exception as e:
            logger.exception("Failed to load artifact from R2", extra={"key": key})
            raise
    # inline
    return pointer_or_inline


def delete_artifact(pointer_or_inline: Dict[str, Any]) -> bool:
    """Delete artifact from storage if it's stored in R2.

    Args:
        pointer_or_inline: Artifact pointer or inline object from DB

    Returns:
        True if deleted from R2, False if inline (nothing to delete)
    """
    if isinstance(pointer_or_inline, dict) and pointer_or_inline.get("backend") == "r2":
        if get_r2_storage is None:
            logger.warning("R2 storage not available to delete artifact")
            return False

        key = pointer_or_inline.get("key")
        if not key:
            logger.warning("Artifact pointer missing key, cannot delete")
            return False

        storage = get_r2_storage()
        try:
            storage.delete(key)
            logger.info("Artifact deleted from R2", extra={"key": key})
            return True
        except Exception as e:
            logger.exception("Failed to delete artifact from R2", extra={"key": key, "error": str(e)})
            # Don't raise - allow DB deletion to proceed even if R2 deletion fails
            return False

    # inline artifact - nothing to delete from storage
    return False


def persist_extraction_artifact(extraction_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Persist extraction result to storage (if enabled) and return pointer JSON for DB.

    Similar to persist_artifact but specifically for extraction results.
    Uses different R2 key pattern: extractions/{extraction_id}/result.json

    Args:
        extraction_id: Extraction ID
        result: Extraction result data (normalized LLM output)

    Returns:
        Pointer dict (if R2) or inline result (if storage disabled/small)

    Pointer structure (R2):
    {
        "backend": "r2",
        "bucket": <bucket>,
        "key": "extractions/<extraction_id>/result.json",
        "size_bytes": <int>,
        "created_at": <iso8601>
    }
    """
    timer = ARTIFACT_PERSIST_SECONDS.time()
    try:
        if settings.exports_use_r2 and get_r2_storage is not None:
            try:
                storage = get_r2_storage()
                key = f"extractions/{extraction_id}/result.json"
                data = json.dumps(result, ensure_ascii=False).encode("utf-8")
                storage.store_bytes(key, data, "application/json")
                pointer = {
                    "backend": "r2",
                    "bucket": settings.r2_bucket,
                    "key": key,
                    "size_bytes": len(data),
                    "created_at": _now_ts(),
                }
                logger.info("Extraction artifact persisted to R2", extra={
                    "extraction_id": extraction_id,
                    "key": key,
                    "size": len(data)
                })
                return pointer
            except Exception:
                ARTIFACT_PERSIST_FAILURES.inc()
                logger.exception("Extraction artifact persistence to R2 failed — storing inline in DB", extra={
                    "extraction_id": extraction_id
                })
                return result
        # storage disabled -> inline
        return result
    finally:
        try:
            timer.__exit__(None, None, None)
        except Exception:
            pass


def load_extraction_artifact(extraction_id: str, pointer_or_inline: Dict[str, Any]) -> Dict[str, Any]:
    """Load extraction result given a pointer or inline object.

    Convenience wrapper around load_artifact with extraction-specific logging.

    Args:
        extraction_id: Extraction ID (for logging)
        pointer_or_inline: Artifact pointer or inline data from DB

    Returns:
        Full extraction result dict
    """
    try:
        result = load_artifact(pointer_or_inline)
        logger.debug("Extraction artifact loaded", extra={"extraction_id": extraction_id})
        return result
    except Exception as e:
        logger.exception("Failed to load extraction artifact", extra={
            "extraction_id": extraction_id,
            "error": str(e)
        })
        raise


__all__ = [
    "persist_artifact",
    "load_artifact",
    "delete_artifact",
    "persist_extraction_artifact",
    "load_extraction_artifact"
]