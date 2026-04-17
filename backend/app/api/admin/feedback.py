# backend/app/api/admin/feedback.py
"""Platform admin feedback endpoints.

Internal admin endpoints for reviewing and responding to user feedback
across all organizations.

Access: Requires admin API key or admin role
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.auth import require_admin
from app.db_models_users import User
from app.repositories.feedback_repository import FeedbackRepository
from app.models import (
    FeedbackItem,
    FeedbackListResponse,
    FeedbackStatsResponse,
    UpdateFeedbackResponseRequest,
    OperationType
)
from app.utils.logging import logger

router = APIRouter(prefix="/feedback", tags=["platform-admin-feedback"])


@router.get("", response_model=FeedbackListResponse)
async def list_feedback(
    operation_type: Optional[OperationType] = None,
    org_id: Optional[str] = None,
    rating_min: Optional[int] = Query(None, ge=-1, le=10),
    rating_max: Optional[int] = Query(None, ge=-1, le=10),
    requires_response: Optional[bool] = None,
    response_status: Optional[str] = Query(None, pattern="^(none|pending|responded)$"),
    hours: int = Query(168, ge=1, le=720, description="Time window in hours (default 7 days)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    List and filter feedback (admin only).

    Supports filtering by:
    - Operation type (chat, workflow, template_fill, extraction)
    - Organization ID
    - Rating range
    - Response status
    - Time window

    Returns:
        Paginated list of feedback items
    """
    repo = FeedbackRepository()

    items, total = repo.list_feedback(
        operation_type=operation_type.value if operation_type else None,
        org_id=org_id,
        rating_min=rating_min,
        rating_max=rating_max,
        requires_response=requires_response,
        response_status=response_status,
        hours=hours,
        limit=limit,
        offset=offset,
    )

    return FeedbackListResponse(
        items=[FeedbackItem.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats(
    hours: int = Query(168, ge=1, le=720, description="Time window in hours"),
    operation_type: Optional[OperationType] = None,
    org_id: Optional[str] = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Get aggregated feedback statistics for admin dashboard.

    Args:
        hours: Time window in hours
        operation_type: Optional filter by operation type
        org_id: Optional filter by organization

    Returns:
        Aggregated statistics including counts, averages, and response rates
    """
    repo = FeedbackRepository()

    stats = repo.get_feedback_stats(
        hours=hours,
        operation_type=operation_type.value if operation_type else None,
        org_id=org_id,
    )

    return FeedbackStatsResponse(**stats)


@router.get("/{feedback_id}", response_model=FeedbackItem)
async def get_feedback_detail(
    feedback_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Get detailed feedback item by ID.

    Args:
        feedback_id: Feedback ID

    Returns:
        Detailed feedback item
    """
    repo = FeedbackRepository()
    feedback = repo.get_feedback_by_id(feedback_id)

    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    return FeedbackItem.model_validate(feedback)


@router.post("/{feedback_id}/respond")
async def respond_to_feedback(
    feedback_id: str,
    response: UpdateFeedbackResponseRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Add admin response to feedback.

    Args:
        feedback_id: Feedback ID
        response: Response text
        admin: Admin user making the response

    Returns:
        Success message
    """
    repo = FeedbackRepository()

    success = repo.add_response(
        feedback_id=feedback_id,
        response_text=response.response_text,
        responded_by=admin.id,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Feedback not found")

    logger.info(f"Admin response added to feedback: {feedback_id} by {admin.id}")

    return {"success": True, "message": "Response added"}
