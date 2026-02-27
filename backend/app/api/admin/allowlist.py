# backend/app/api/admin/allowlist.py
"""Admin endpoints for managing the email allowlist (invite-only access control)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from typing import Optional
from app.auth import require_admin
from app.db_models_users import User, AllowedEmail, ShadowCreditLog
from app.services.beta_limits import get_usage_snapshot
from app.database import SessionLocal
from app.utils.logging import logger
import uuid

router = APIRouter()


class AllowEmailRequest(BaseModel):
    emails: list[str]


class ActivateUserRequest(BaseModel):
    user_id: str


class UpdateUserLimitsRequest(BaseModel):
    pages_limit: Optional[int] = None
    workflow_runs_limit: Optional[int] = None
    extractions_limit: Optional[int] = None
    template_fill_runs_limit: Optional[int] = None
    chat_messages_limit: Optional[int] = None


@router.get("/allowed-emails")
def list_allowed_emails(admin: User = Depends(require_admin)):
    """List all emails in the allowlist."""
    db = SessionLocal()
    try:
        entries = db.query(AllowedEmail).order_by(AllowedEmail.created_at.desc()).all()
        return {
            "allowed_emails": [
                {"id": e.id, "email": e.email, "added_by": e.added_by, "created_at": e.created_at.isoformat() if e.created_at else None}
                for e in entries
            ],
            "total": len(entries),
        }
    finally:
        db.close()


@router.post("/allowed-emails")
def add_allowed_emails(body: AllowEmailRequest, admin: User = Depends(require_admin)):
    """Add one or more emails to the allowlist.

    Also activates any existing users with matching emails.
    """
    db = SessionLocal()
    added = []
    activated = []
    try:
        for email in body.emails:
            email_lower = email.lower()
            # Check if already in allowlist
            existing = db.query(AllowedEmail).filter(
                func.lower(AllowedEmail.email) == email_lower
            ).first()
            if existing:
                continue

            entry = AllowedEmail(
                id=str(uuid.uuid4()),
                email=email_lower,
                added_by=admin.id,
            )
            db.add(entry)
            added.append(email_lower)

            # Activate any existing user with this email
            user = db.query(User).filter(
                func.lower(User.email) == email_lower
            ).first()
            if user and user.status != "active":
                user.status = "active"
                activated.append(email_lower)

        db.commit()
        logger.info("Allowlist updated", extra={"added": added, "activated": activated, "by": admin.id})
        return {"added": added, "activated": activated}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.delete("/allowed-emails/{email}")
def remove_allowed_email(email: str, deactivate_user: bool = False, admin: User = Depends(require_admin)):
    """Remove an email from the allowlist.

    Pass ?deactivate_user=true to also set the matching active user's status back to pending_approval.
    """
    db = SessionLocal()
    try:
        entry = db.query(AllowedEmail).filter(
            func.lower(AllowedEmail.email) == email.lower()
        ).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Email not in allowlist")
        db.delete(entry)

        deactivated_user_id = None
        if deactivate_user:
            user = db.query(User).filter(func.lower(User.email) == email.lower()).first()
            if user and user.status == "active":
                user.status = "pending_approval"
                deactivated_user_id = user.id

        db.commit()
        logger.info(
            "Removed from allowlist",
            extra={"email": email, "by": admin.id, "deactivated_user": deactivated_user_id}
        )
        return {"removed": email, "deactivated_user": deactivated_user_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.post("/activate-user")
def activate_user(body: ActivateUserRequest, admin: User = Depends(require_admin)):
    """Manually activate a user (bypass allowlist)."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == body.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.status = "active"
        db.commit()
        logger.info("User activated manually", extra={"user_id": body.user_id, "by": admin.id})
        return {"activated": user.id, "email": user.email}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/pending-users")
def list_pending_users(admin: User = Depends(require_admin)):
    """List all users with pending_approval status."""
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.status == "pending_approval").order_by(User.created_at.desc()).all()
        return {
            "pending_users": [
                {"id": u.id, "email": u.email, "org_id": u.org_id, "created_at": u.created_at.isoformat() if u.created_at else None}
                for u in users
            ],
            "total": len(users),
        }
    finally:
        db.close()


@router.get("/users/{user_id}/limits")
def get_user_limits(user_id: str, admin: User = Depends(require_admin)):
    """Get current per-user limits and usage snapshot."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "tier": user.tier,
                "status": user.status,
            },
            "limits": {
                "pages_limit": user.pages_limit,
                "workflow_runs_limit": user.workflow_runs_limit,
                "extractions_limit": user.extractions_limit,
                "template_fill_runs_limit": user.template_fill_runs_limit,
                "chat_messages_limit": user.chat_messages_limit,
            },
            "usage": get_usage_snapshot(user),
        }
    finally:
        db.close()


@router.patch("/users/{user_id}/limits")
def update_user_limits(user_id: str, body: UpdateUserLimitsRequest, admin: User = Depends(require_admin)):
    """Update per-user closed-beta limits (0 = unlimited)."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        updates = {}
        for field in (
            "pages_limit",
            "workflow_runs_limit",
            "extractions_limit",
            "template_fill_runs_limit",
            "chat_messages_limit",
        ):
            value = getattr(body, field)
            if value is None:
                continue
            if value < 0:
                raise HTTPException(status_code=400, detail=f"{field} must be >= 0")
            setattr(user, field, int(value))
            updates[field] = int(value)

        if not updates:
            raise HTTPException(status_code=400, detail="No limit fields provided")

        db.commit()
        db.refresh(user)

        logger.info(
            "Updated user limits",
            extra={"user_id": user.id, "updated_fields": updates, "admin_id": admin.id},
        )

        return {
            "updated": updates,
            "usage": get_usage_snapshot(user),
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.get("/users/{user_id}/shadow-credits")
def list_user_shadow_credits(user_id: str, limit: int = 100, admin: User = Depends(require_admin)):
    """List recent shadow-credit ledger entries for a user."""
    db = SessionLocal()
    try:
        safe_limit = max(1, min(limit, 500))
        entries = (
            db.query(ShadowCreditLog)
            .filter(ShadowCreditLog.user_id == user_id)
            .order_by(ShadowCreditLog.created_at.desc())
            .limit(safe_limit)
            .all()
        )
        committed_credits = sum(float(e.shadow_credits or 0.0) for e in entries if e.status == "committed")
        reserved_credits = sum(float(e.shadow_credits or 0.0) for e in entries if e.status == "reserved")
        reversed_credits = sum(float(e.shadow_credits or 0.0) for e in entries if e.status == "reversed")

        return {
            "user_id": user_id,
            "count": len(entries),
            "totals": {
                "committed_shadow_credits": round(committed_credits, 3),
                "reserved_shadow_credits": round(reserved_credits, 3),
                "reversed_shadow_credits": round(reversed_credits, 3),
                "net_committed_minus_reversed": round(committed_credits - reversed_credits, 3),
            },
            "items": [
                {
                    "id": e.id,
                    "operation_type": e.operation_type,
                    "reference_id": e.reference_id,
                    "units": e.units,
                    "shadow_credits": e.shadow_credits,
                    "status": e.status,
                    "reversed_at": e.reversed_at.isoformat() if e.reversed_at else None,
                    "reverse_reason": e.reverse_reason,
                    "metadata": e.shadow_metadata,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in entries
            ],
        }
    finally:
        db.close()
