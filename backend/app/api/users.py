# backend/app/api/users.py
"""User profile and extraction history endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.auth import get_current_user
from app.db_models_users import User
from app.db_models import Extraction
from app.database import get_db
from app.utils.logging import logger
import os
from pathlib import Path
from app.config import settings

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
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100, description="Number of extractions to return"),
    offset: int = Query(0, ge=0, description="Number of extractions to skip"),
    status: str = Query(None, description="Filter by status (completed, processing, failed)")
):
    """Get user's extraction history with pagination and filtering

    Args:
        limit: Maximum number of results (1-100, default 50)
        offset: Number of results to skip for pagination
        status: Optional status filter

    Returns:
        extractions: List of extraction records
        total: Total count of extractions matching filters
        limit: Applied limit
        offset: Applied offset
    """
    # Base query
    query = db.query(Extraction).filter(Extraction.user_id == user.id)

    # Apply status filter if provided
    if status:
        query = query.filter(Extraction.status == status)

    # Get total count before pagination
    total = query.count()

    # Apply pagination and ordering
    extractions = query.order_by(
        Extraction.created_at.desc()
    ).limit(limit).offset(offset).all()

    return {
        "extractions": [
            {
                "id": e.id,
                "filename": e.filename,
                "page_count": e.page_count,
                "status": e.status,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                "pdf_type": e.pdf_type,
                "parser_used": e.parser_used,
                "cost_usd": e.cost_usd,
                "processing_time_ms": e.processing_time_ms,
                "error_message": e.error_message,
                "from_cache": e.from_cache,
                "context": e.context  # User-provided context
            }
            for e in extractions
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + len(extractions)) < total
    }


@router.delete("/api/extractions/{extraction_id}")
def delete_extraction(
    extraction_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an extraction and its associated files

    Requires authentication - users can only delete their own extractions.

    Args:
        extraction_id: ID of the extraction to delete

    Returns:
        success: Boolean indicating success
        message: Confirmation message
    """
    # Get extraction
    extraction = db.query(Extraction).filter(
        Extraction.id == extraction_id
    ).first()

    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")

    # Verify ownership
    if extraction.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to delete this extraction"
        )

    # Delete associated files (raw text, parsed result, etc.)
    try:
        # Define file patterns to delete
        file_patterns = [
            settings.raw_dir / f"*_{extraction_id[:8]}.txt",
            settings.parsed_dir / f"*_{extraction_id[:8]}.json",
            settings.llm_output_dir / f"*_{extraction_id[:8]}.json",
        ]

        files_deleted = 0
        for pattern in file_patterns:
            for file_path in Path(pattern.parent).glob(pattern.name):
                try:
                    file_path.unlink()
                    files_deleted += 1
                    logger.info(f"Deleted file: {file_path}", extra={
                        "extraction_id": extraction_id,
                        "user_id": user.id
                    })
                except Exception as e:
                    logger.warning(f"Failed to delete file {file_path}: {e}", extra={
                        "extraction_id": extraction_id
                    })

        logger.info(f"Deleted {files_deleted} files for extraction {extraction_id}", extra={
            "extraction_id": extraction_id,
            "user_id": user.id
        })

    except Exception as e:
        logger.error(f"Error deleting files: {e}", extra={
            "extraction_id": extraction_id,
            "user_id": user.id
        })
        # Continue with DB deletion even if file deletion fails

    # Delete from database
    db.delete(extraction)
    db.commit()

    logger.info(f"Extraction deleted successfully", extra={
        "extraction_id": extraction_id,
        "user_id": user.id,
        "filename": extraction.filename
    })

    return {
        "success": True,
        "message": f"Extraction '{extraction.filename}' deleted successfully"
    }
