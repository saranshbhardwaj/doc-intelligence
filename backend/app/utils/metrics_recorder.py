"""Centralized metric recording helpers with error handling.

This module provides safe wrappers for recording Prometheus metrics with:
- Automatic error handling (metrics failures shouldn't crash the app)
- Consistent label handling
- Clear naming conventions

Note: org_id is NOT a Prometheus label (high-cardinality anti-pattern).
Per-org analytics come from the database, not Prometheus.

Usage:
    from app.utils.metrics_recorder import record_workflow_completed

    record_workflow_completed(workflow_name="Investment Memo")
"""
from app.utils.metrics import (
    WORKFLOW_RUNS_COMPLETED,
    WORKFLOW_RUNS_FAILED,
    CHAT_MESSAGES_TOTAL,
    EXTRACTIONS_COMPLETED,
    EXTRACTIONS_FAILED,
    TEMPLATE_FILLS_COMPLETED,
    TEMPLATE_FILLS_FAILED,
)
from app.utils.logging import logger


def record_workflow_completed(workflow_name: str, **kwargs) -> None:
    """Record a successful workflow completion.

    Args:
        workflow_name: Name of the workflow (e.g., "Investment Memo")
    """
    try:
        WORKFLOW_RUNS_COMPLETED.labels(
            workflow_name=workflow_name or "unknown"
        ).inc()
    except Exception as e:
        logger.warning(f"Failed to record workflow completion metric: {e}")


def record_workflow_failed(workflow_name: str, **kwargs) -> None:
    """Record a failed workflow execution.

    Args:
        workflow_name: Name of the workflow (e.g., "Investment Memo")
    """
    try:
        WORKFLOW_RUNS_FAILED.labels(
            workflow_name=workflow_name or "unknown"
        ).inc()
    except Exception as e:
        logger.warning(f"Failed to record workflow failure metric: {e}")


def record_chat_message(role: str, **kwargs) -> None:
    """Record a chat message.

    Args:
        role: Message role ("user" or "assistant")
    """
    try:
        CHAT_MESSAGES_TOTAL.labels(
            role=role or "unknown",
        ).inc()
    except Exception as e:
        logger.warning(f"Failed to record chat message metric: {e}")


def record_extraction_completed(**kwargs) -> None:
    """Record a successful extraction."""
    try:
        EXTRACTIONS_COMPLETED.inc()
    except Exception as e:
        logger.warning(f"Failed to record extraction completion metric: {e}")


def record_extraction_failed(**kwargs) -> None:
    """Record a failed extraction."""
    try:
        EXTRACTIONS_FAILED.inc()
    except Exception as e:
        logger.warning(f"Failed to record extraction failure metric: {e}")


def record_template_fill_completed(**kwargs) -> None:
    """Record a successful template fill."""
    try:
        TEMPLATE_FILLS_COMPLETED.inc()
    except Exception as e:
        logger.warning(f"Failed to record template fill completion metric: {e}")


def record_template_fill_failed(**kwargs) -> None:
    """Record a failed template fill."""
    try:
        TEMPLATE_FILLS_FAILED.inc()
    except Exception as e:
        logger.warning(f"Failed to record template fill failure metric: {e}")


__all__ = [
    "record_workflow_completed",
    "record_workflow_failed",
    "record_chat_message",
    "record_extraction_completed",
    "record_extraction_failed",
    "record_template_fill_completed",
    "record_template_fill_failed",
]
