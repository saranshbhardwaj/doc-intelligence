# backend/app/api/admin/allowlist.py
"""Admin endpoints for managing the email allowlist (invite-only access control)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from app.auth import require_admin
from app.db_models_users import User, AllowedEmail
from app.database import SessionLocal
from app.utils.logging import logger
import uuid

router = APIRouter()


class AllowEmailRequest(BaseModel):
    emails: list[str]


class ActivateUserRequest(BaseModel):
    user_id: str


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
def remove_allowed_email(email: str, admin: User = Depends(require_admin)):
    """Remove an email from the allowlist."""
    db = SessionLocal()
    try:
        entry = db.query(AllowedEmail).filter(
            func.lower(AllowedEmail.email) == email.lower()
        ).first()
        if not entry:
            raise HTTPException(status_code=404, detail="Email not in allowlist")
        db.delete(entry)
        db.commit()
        logger.info("Removed from allowlist", extra={"email": email, "by": admin.id})
        return {"removed": email}
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
