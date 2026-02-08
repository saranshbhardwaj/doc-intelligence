"""Centralized metric recording helpers with error handling.

This module provides safe wrappers for recording Prometheus metrics with:
- Automatic error handling (metrics failures shouldn't crash the app)
- Consistent label handling
- Clear naming conventions

Usage:
    from app.utils.metrics_recorder import record_workflow_completed

    record_workflow_completed(org_id="org_123", workflow_name="Investment Memo")
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


def record_workflow_completed(org_id: str, workflow_name: str) -> None:
    """Record a successful workflow completion.

    Args:
        org_id: Organization/tenant ID (Clerk org ID)
        workflow_name: Name of the workflow (e.g., "Investment Memo")
    """
    try:
        WORKFLOW_RUNS_COMPLETED.labels(
            org_id=org_id or "unknown",
            workflow_name=workflow_name or "unknown"
        ).inc()
    except Exception as e:
        logger.warning(f"Failed to record workflow completion metric: {e}")


def record_workflow_failed(org_id: str, workflow_name: str) -> None:
    """Record a failed workflow execution.

    Args:
        org_id: Organization/tenant ID (Clerk org ID)
        workflow_name: Name of the workflow (e.g., "Investment Memo")
    """
    try:
        WORKFLOW_RUNS_FAILED.labels(
            org_id=org_id or "unknown",
            workflow_name=workflow_name or "unknown"
        ).inc()
    except Exception as e:
        logger.warning(f"Failed to record workflow failure metric: {e}")


def record_chat_message(role: str, org_id: str) -> None:
    """Record a chat message.

    Args:
        role: Message role ("user" or "assistant")
        org_id: Organization/tenant ID
    """
    try:
        CHAT_MESSAGES_TOTAL.labels(
            role=role or "unknown",
            org_id=org_id or "unknown"
        ).inc()
    except Exception as e:
        logger.warning(f"Failed to record chat message metric: {e}")


def record_extraction_completed(org_id: str) -> None:
    """Record a successful extraction.

    Args:
        org_id: Organization/tenant ID
    """
    try:
        EXTRACTIONS_COMPLETED.labels(org_id=org_id or "unknown").inc()
    except Exception as e:
        logger.warning(f"Failed to record extraction completion metric: {e}")


def record_extraction_failed(org_id: str) -> None:
    """Record a failed extraction.

    Args:
        org_id: Organization/tenant ID
    """
    try:
        EXTRACTIONS_FAILED.labels(org_id=org_id or "unknown").inc()
    except Exception as e:
        logger.warning(f"Failed to record extraction failure metric: {e}")


def record_template_fill_completed(org_id: str) -> None:
    """Record a successful template fill.

    Args:
        org_id: Organization/tenant ID
    """
    try:
        TEMPLATE_FILLS_COMPLETED.labels(org_id=org_id or "unknown").inc()
    except Exception as e:
        logger.warning(f"Failed to record template fill completion metric: {e}")


def record_template_fill_failed(org_id: str) -> None:
    """Record a failed template fill.

    Args:
        org_id: Organization/tenant ID
    """
    try:
        TEMPLATE_FILLS_FAILED.labels(org_id=org_id or "unknown").inc()
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
