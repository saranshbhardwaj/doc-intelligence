# backend/app/api/users.py
"""User profile and extraction history endpoints"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.auth import get_current_user
from app.db_models_users import User
from app.db_models import Extraction
from app.database import get_db

router = APIRouter()


@router.get("/api/users/me")
def get_current_user_info(user: User = Depends(get_current_user)):
    """Get current user's profile and usage stats"""
    # For free tier, use total pages (one-time limit)
    # For paid tiers, use monthly pages (recurring limit)
    if user.tier == "free":
        pages_used = user.total_pages_processed
        pages_remaining = max(0, user.pages_limit - user.total_pages_processed)
    else:
        pages_used = user.pages_this_month
        pages_remaining = max(0, user.pages_limit - user.pages_this_month)

    percentage_used = (pages_used / user.pages_limit * 100) if user.pages_limit > 0 else 0

    return {
        "id": user.id,
        "email": user.email,
        "tier": user.tier,
        "usage": {
            "pages_used": pages_used,
            "pages_remaining": pages_remaining,
            "pages_limit": user.pages_limit,
            "total_pages_processed": user.total_pages_processed,
            "pages_this_month": user.pages_this_month,
            "percentage_used": round(percentage_used, 1)
        },
        "subscription": {
            "status": user.subscription_status,
            "billing_period_end": user.billing_period_end.isoformat() if user.billing_period_end else None
        }
    }


@router.get("/api/users/me/extractions")
def get_user_extractions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's extraction history"""
    extractions = db.query(Extraction).filter(
        Extraction.user_id == user.id
    ).order_by(Extraction.created_at.desc()).limit(100).all()

    return {
        "extractions": [
            {
                "id": e.id,
                "filename": e.filename,
                "page_count": e.page_count,
                "status": e.status,
                "created_at": e.created_at.isoformat(),
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                "pdf_type": e.pdf_type,
                "from_cache": e.from_cache
            }
            for e in extractions
        ]
    }
