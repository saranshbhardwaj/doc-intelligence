# app/api/feedback.py
"""User-facing feedback API endpoints.

Allows authenticated users to submit feedback on any operation type:
- Chat messages (thumbs up/down)
- Workflow runs (star ratings)
- Template fills (star ratings)
- Extractions (star ratings)
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.db_models_users import User
from app.repositories.feedback_repository import FeedbackRepository
from app.models import SubmitFeedbackRequest, FeedbackResponse
from app.api.dependencies import get_client_ip
from app.utils.logging import logger

router = APIRouter(tags=["feedback"])


@router.post("/api/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    feedback: SubmitFeedbackRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Submit feedback for any operation type.

    Supports:
    - Chat messages (thumbs up/down)
    - Workflow runs (star rating)
    - Template fills (star rating)
    - Extractions (star rating)

    Args:
        feedback: Feedback submission data
        request: FastAPI request object
        user: Current authenticated user
        db: Database session

    Returns:
        FeedbackResponse with success status and feedback ID
    """
    # Determine operation type from which entity ID is set
    operation_type = None
    entity_id = None

    if feedback.chat_message_id:
        operation_type = "chat"
        entity_id = feedback.chat_message_id
    elif feedback.workflow_run_id:
        operation_type = "workflow"
        entity_id = feedback.workflow_run_id
    elif feedback.template_fill_run_id:
        operation_type = "template_fill"
        entity_id = feedback.template_fill_run_id
    elif feedback.extraction_id:
        operation_type = "extraction"
        entity_id = feedback.extraction_id
    else:
        raise HTTPException(
            status_code=400,
            detail="Exactly one entity reference must be provided"
        )

    repo = FeedbackRepository()

    # Validate entity exists and belongs to user's org
    entity_valid = repo.validate_entity_access(
        operation_type=operation_type,
        entity_id=entity_id,
        org_id=user.org_id
    )

    if not entity_valid:
        raise HTTPException(
            status_code=404,
            detail="Entity not found or access denied"
        )

    # Create feedback
    feedback_id = repo.create_feedback(
        org_id=user.org_id,
        user_id=user.id,
        operation_type=operation_type,
        chat_message_id=feedback.chat_message_id,
        workflow_run_id=feedback.workflow_run_id,
        template_fill_run_id=feedback.template_fill_run_id,
        extraction_id=feedback.extraction_id,
        rating_type=feedback.rating_type.value,
        rating_value=feedback.rating_value,
        comment=feedback.comment,
        feedback_category=feedback.feedback_category.value if feedback.feedback_category else None,
        tags=feedback.tags,
        context_snapshot=feedback.context_snapshot,
        client_ip=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )

    if not feedback_id:
        raise HTTPException(
            status_code=500,
            detail="Failed to save feedback"
        )

    logger.info("Feedback submitted", extra={
        "feedback_id": feedback_id,
        "operation_type": operation_type,
        "rating_value": feedback.rating_value,
        "org_id": user.org_id,
    })

    return FeedbackResponse(
        success=True,
        message="Thank you for your feedback!",
        feedback_id=feedback_id
    )
