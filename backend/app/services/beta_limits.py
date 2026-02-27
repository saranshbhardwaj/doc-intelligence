"""Centralized beta-limit enforcement and shadow-credit logging."""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Generator, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.db_models import Extraction
from app.db_models_chat import ChatMessage, ChatSession
from app.db_models_templates import TemplateFillRun
from app.db_models_users import ShadowCreditLog, User
from app.db_models_workflows import WorkflowRun
from app.utils.logging import logger


SHADOW_CREDIT_RATES: Dict[str, float] = {
    "document_index_page": 1.0,
    "workflow_run": 12.0,
    "extraction_run": 16.0,
    "template_fill_run": 14.0,
    "chat_message": 0.8,
}


@contextmanager
def _get_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _pages_used(user: User) -> int:
    return int(user.total_pages_processed or 0) if user.tier == "free" else int(user.pages_this_month or 0)


def _count_user_workflow_runs(db: Session, user: User) -> int:
    return (
        db.query(func.count(WorkflowRun.id))
        .filter(WorkflowRun.user_id == user.id, WorkflowRun.org_id == user.org_id)
        .scalar()
        or 0
    )


def _count_user_extractions(db: Session, user: User) -> int:
    return (
        db.query(func.count(Extraction.id))
        .filter(Extraction.user_id == user.id, Extraction.org_id == user.org_id)
        .scalar()
        or 0
    )


def _count_user_template_fills(db: Session, user: User) -> int:
    return (
        db.query(func.count(TemplateFillRun.id))
        .filter(
            TemplateFillRun.user_id == user.id,
            TemplateFillRun.org_id == user.org_id,
            TemplateFillRun.status != "failed",
        )
        .scalar()
        or 0
    )


def _count_user_chat_messages(db: Session, user: User) -> int:
    return (
        db.query(func.count(ChatMessage.id))
        .join(ChatSession, ChatSession.id == ChatMessage.session_id)
        .filter(
            ChatSession.user_id == user.id,
            ChatSession.org_id == user.org_id,
            ChatMessage.role == "user",
        )
        .scalar()
        or 0
    )


def get_usage_snapshot(user: User) -> Dict[str, Any]:
    with _get_session() as db:
        workflow_runs_used = int(_count_user_workflow_runs(db, user))
        extractions_used = int(_count_user_extractions(db, user))
        template_fill_runs_used = int(_count_user_template_fills(db, user))
        chat_messages_used = int(_count_user_chat_messages(db, user))

    pages_used = _pages_used(user)
    pages_remaining = max(0, int(user.pages_limit or 0) - pages_used) if (user.pages_limit or 0) > 0 else None

    return {
        "pages": {
            "used": pages_used,
            "limit": user.pages_limit,
            "remaining": pages_remaining,
            "window": "lifetime" if user.tier == "free" else "monthly",
        },
        "workflow_runs": {"used": workflow_runs_used, "limit": user.workflow_runs_limit},
        "extractions": {"used": extractions_used, "limit": user.extractions_limit},
        "template_fill_runs": {"used": template_fill_runs_used, "limit": user.template_fill_runs_limit},
        "chat_messages": {"used": chat_messages_used, "limit": user.chat_messages_limit},
    }


def _raise_limit_error(error_code: str, message: str, used: int, limit: int, **extra: Any) -> None:
    detail = {"error": error_code, "message": message, "used": used, "limit": limit}
    detail.update(extra)
    raise HTTPException(status_code=403, detail=detail)


def _enforce_counter_limit(limit: Optional[int], used: int, error_code: str, message: str) -> None:
    # All operation counters (workflows, extractions, template fills, chat messages) are LIFETIME
    # totals — there is no time-window reset. A user who hits their limit is locked out until an
    # admin manually increases their limit via PATCH /admin/users/{id}/limits (0 = unlimited).
    if limit is None or int(limit) <= 0:
        return
    if used >= int(limit):
        _raise_limit_error(error_code=error_code, message=message, used=used, limit=int(limit))


def enforce_page_limit(user: User, pages_to_add: int = 0) -> None:
    limit = int(user.pages_limit or 0)
    if user.tier == "admin" or limit <= 0:
        return

    used = _pages_used(user)
    projected = used + max(0, int(pages_to_add or 0))

    if projected > limit:
        window = "total" if user.tier == "free" else "monthly"
        _raise_limit_error(
            error_code="page_limit_exceeded",
            message=f"Page limit reached ({limit} {window} pages).",
            used=used,
            limit=limit,
            requested=max(0, int(pages_to_add or 0)),
            projected=projected,
            tier=user.tier,
        )


def enforce_workflow_limit(user: User) -> None:
    if user.tier == "admin":
        return
    with _get_session() as db:
        used = int(_count_user_workflow_runs(db, user))
    _enforce_counter_limit(
        user.workflow_runs_limit,
        used,
        "workflow_limit_exceeded",
        "Workflow run limit reached for this beta account.",
    )


def enforce_extraction_limit(user: User) -> None:
    if user.tier == "admin":
        return
    with _get_session() as db:
        used = int(_count_user_extractions(db, user))
    _enforce_counter_limit(
        user.extractions_limit,
        used,
        "extraction_limit_exceeded",
        "Extraction limit reached for this beta account.",
    )


def enforce_template_fill_limit(user: User) -> None:
    if user.tier == "admin":
        return
    with _get_session() as db:
        used = int(_count_user_template_fills(db, user))
    _enforce_counter_limit(
        user.template_fill_runs_limit,
        used,
        "template_fill_limit_exceeded",
        "Template-fill limit reached for this beta account.",
    )


def enforce_chat_message_limit(user: User) -> None:
    if user.tier == "admin":
        return
    with _get_session() as db:
        used = int(_count_user_chat_messages(db, user))
    _enforce_counter_limit(
        user.chat_messages_limit,
        used,
        "chat_limit_exceeded",
        "Chat message limit reached for this beta account.",
    )


def log_shadow_credits(
    *,
    user: User,
    operation_type: str,
    units: int = 1,
    reference_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    _create_shadow_credit_entry(
        user=user,
        operation_type=operation_type,
        units=units,
        reference_id=reference_id,
        metadata=metadata,
        status="committed",
    )


def reserve_shadow_credits(
    *,
    user: User,
    operation_type: str,
    units: int = 1,
    reference_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    return _create_shadow_credit_entry(
        user=user,
        operation_type=operation_type,
        units=units,
        reference_id=reference_id,
        metadata=metadata,
        status="reserved",
    )


def commit_shadow_credits(operation_type: str, reference_id: str) -> bool:
    with _get_session() as db:
        try:
            entry = _find_latest_shadow_entry(
                db=db,
                operation_type=operation_type,
                reference_id=reference_id,
                statuses=("reserved",),
            )
            if not entry:
                return False

            entry.status = "committed"
            entry.reversed_at = None
            entry.reverse_reason = None
            db.commit()
            return True
        except SQLAlchemyError as e:
            db.rollback()
            logger.warning(
                "Failed to commit shadow credits",
                extra={"operation_type": operation_type, "reference_id": reference_id, "error": str(e)},
            )
            return False


def reverse_shadow_credits(
    operation_type: str,
    reference_id: str,
    reason: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    with _get_session() as db:
        try:
            entry = _find_latest_shadow_entry(
                db=db,
                operation_type=operation_type,
                reference_id=reference_id,
                statuses=("reserved", "committed"),
            )
            if not entry:
                return False

            entry.status = "reversed"
            entry.reversed_at = datetime.utcnow()
            entry.reverse_reason = reason[:1000]

            merged_meta = dict(entry.shadow_metadata or {})
            if metadata:
                merged_meta["reversal_metadata"] = metadata
            entry.shadow_metadata = merged_meta

            db.commit()
            return True
        except SQLAlchemyError as e:
            db.rollback()
            logger.warning(
                "Failed to reverse shadow credits",
                extra={"operation_type": operation_type, "reference_id": reference_id, "error": str(e)},
            )
            return False


def _create_shadow_credit_entry(
    *,
    user: User,
    operation_type: str,
    units: int,
    reference_id: Optional[str],
    metadata: Optional[Dict[str, Any]],
    status: str,
) -> Optional[str]:
    units = max(1, int(units or 1))
    per_unit = float(SHADOW_CREDIT_RATES.get(operation_type, 1.0))
    total_credits = per_unit * units

    with _get_session() as db:
        try:
            entry_id = str(uuid.uuid4())
            entry = ShadowCreditLog(
                id=entry_id,
                user_id=user.id,
                org_id=user.org_id,
                operation_type=operation_type,
                reference_id=reference_id,
                units=units,
                shadow_credits=total_credits,
                status=status,
                shadow_metadata=metadata or {},
            )
            db.add(entry)
            db.commit()
            return entry_id
        except SQLAlchemyError as e:
            db.rollback()
            logger.warning(
                "Failed to log shadow credits",
                extra={
                    "user_id": user.id,
                    "org_id": user.org_id,
                    "operation_type": operation_type,
                    "error": str(e),
                },
            )
            return None


def _find_latest_shadow_entry(
    *,
    db: Session,
    operation_type: str,
    reference_id: str,
    statuses: tuple[str, ...],
) -> Optional[ShadowCreditLog]:
    return (
        db.query(ShadowCreditLog)
        .filter(
            ShadowCreditLog.operation_type == operation_type,
            ShadowCreditLog.reference_id == reference_id,
            ShadowCreditLog.status.in_(statuses),
        )
        .order_by(ShadowCreditLog.created_at.desc())
        .first()
    )
