# app/api/feedback.py
from datetime import datetime
import json
import uuid
from app.api.dependencies import get_client_ip
from fastapi import APIRouter, HTTPException, Request
from app.models import FeedbackRequest, FeedbackResponse
from app.utils.logging import logger
from app.utils.notifications import send_feedback_notification
from app.config import settings

router = APIRouter()

@router.post("/api/feedback", response_model=FeedbackResponse)
async def submit_feedback(feedback: FeedbackRequest, request: Request):
    """
    Submit feedback on document extraction.
    Users can rate accuracy and provide comments.
    """
    feedback_id = str(uuid.uuid4())
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("User-Agent")
    
    logger.info("Feedback received", extra={
        "feedback_id": feedback_id,
        "request_id": feedback.request_id,
        "rating": feedback.rating,
        "has_comment": bool(feedback.comment),
        "client_ip": client_ip
    })
    
    try:
        # Save feedback to file
        feedback_data = {
            "feedback_id": feedback_id,
            "request_id": feedback.request_id,
            "rating": feedback.rating,
            "accuracy_rating": feedback.accuracy_rating,
            "would_pay": feedback.would_pay,
            "comment": feedback.comment,
            "email": feedback.email,
            "client_ip": client_ip,
            "timestamp": feedback.timestamp.isoformat(),
            "user_agent": user_agent,
        }
        
        # Create feedback directory if doesn't exist
        settings.feedback_dir.mkdir(parents=True, exist_ok=True)
        
        # Save with timestamp + feedback_id
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        feedback_file = settings.feedback_dir / f"{timestamp}_{feedback_id[:8]}.json"
        feedback_file.write_text(json.dumps(feedback_data, indent=2))

        logger.info("Feedback saved", extra={"feedback_id": feedback_id})

        # Send notification (Slack/email) - runs in background, won't block response
        try:
            await send_feedback_notification(feedback_data)
        except Exception as e:
            # Don't fail feedback submission if notification fails
            logger.warning(f"Notification failed but feedback saved: {e}")

        return FeedbackResponse(
            success=True,
            message="Thank you for your feedback! It helps us improve.",
            feedback_id=feedback_id
        )
        
    except Exception as e:
        logger.exception("Failed to save feedback", extra={"error": str(e)})
        raise HTTPException(
            status_code=500,
            detail="Failed to save feedback. Please try again."
        )