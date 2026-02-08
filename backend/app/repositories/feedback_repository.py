"""Repository for feedback database operations.

Data Access Layer for unified feedback system across all operation types.

Pattern:
- All database queries go through repositories
- Endpoints/services call repositories (never SessionLocal directly)
- Repositories handle session management and error handling
"""
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
from contextlib import contextmanager
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, select, and_, desc

from app.database import SessionLocal
from app.db_models_feedback import Feedback
from app.db_models_chat import ChatMessage, ChatSession
from app.db_models_workflows import WorkflowRun
from app.db_models_templates import TemplateFillRun
from app.db_models import Extraction
from app.utils.logging import logger
from app.utils.id_generator import generate_id


class FeedbackRepository:
    """Repository for feedback CRUD operations.

    Encapsulates all database access for feedback across all operation types.
    Provides clean interface for CRUD operations and analytics.
    """

    @contextmanager
    def _get_session(self) -> Session:
        """Context manager for database sessions.

        Ensures sessions are properly closed even on errors.

        Yields:
            Session: SQLAlchemy database session
        """
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def validate_entity_access(
        self,
        operation_type: str,
        entity_id: str,
        org_id: str
    ) -> bool:
        """Validate entity exists and belongs to organization.

        Args:
            operation_type: Type of operation (chat, workflow, template_fill, extraction)
            entity_id: ID of the entity
            org_id: Organization ID to validate against

        Returns:
            True if entity exists and belongs to org, False otherwise
        """
        with self._get_session() as db:
            try:
                if operation_type == "chat":
                    # Chat messages need to be joined through session for org_id
                    msg = db.query(ChatMessage).filter(ChatMessage.id == entity_id).first()
                    if not msg:
                        return False
                    session = db.query(ChatSession).filter(ChatSession.id == msg.session_id).first()
                    return session and session.org_id == org_id

                elif operation_type == "workflow":
                    run = db.query(WorkflowRun).filter(WorkflowRun.id == entity_id).first()
                    return run and run.org_id == org_id

                elif operation_type == "template_fill":
                    run = db.query(TemplateFillRun).filter(TemplateFillRun.id == entity_id).first()
                    return run and run.org_id == org_id

                elif operation_type == "extraction":
                    extraction = db.query(Extraction).filter(Extraction.id == entity_id).first()
                    return extraction and extraction.org_id == org_id

                return False

            except SQLAlchemyError as e:
                logger.error(f"Failed to validate entity access: {e}", exc_info=True)
                return False

    def create_feedback(
        self,
        org_id: str,
        user_id: str,
        operation_type: str,
        rating_type: str,
        rating_value: int,
        chat_message_id: Optional[str] = None,
        workflow_run_id: Optional[str] = None,
        template_fill_run_id: Optional[str] = None,
        extraction_id: Optional[str] = None,
        comment: Optional[str] = None,
        feedback_category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        context_snapshot: Optional[dict] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Optional[str]:
        """Create new feedback record.

        Args:
            org_id: Organization ID
            user_id: User ID
            operation_type: Type of operation (chat, workflow, template_fill, extraction)
            rating_type: Type of rating (thumbs, stars)
            rating_value: Rating value (-1/1 for thumbs, 1-5 for stars)
            chat_message_id: Optional chat message ID
            workflow_run_id: Optional workflow run ID
            template_fill_run_id: Optional template fill run ID
            extraction_id: Optional extraction ID
            comment: Optional comment text
            feedback_category: Optional category
            tags: Optional list of tags
            context_snapshot: Optional context snapshot
            client_ip: Optional client IP
            user_agent: Optional user agent string

        Returns:
            Feedback ID if successful, None otherwise
        """
        with self._get_session() as db:
            try:
                feedback_id = generate_id()

                # Determine if response is needed (negative feedback with comment)
                requires_response = (
                    (rating_type == "thumbs" and rating_value == -1) or
                    (rating_type == "stars" and rating_value <= 2)
                ) and comment is not None and len(comment.strip()) > 0

                feedback = Feedback(
                    id=feedback_id,
                    org_id=org_id,
                    user_id=user_id,
                    operation_type=operation_type,
                    chat_message_id=chat_message_id,
                    workflow_run_id=workflow_run_id,
                    template_fill_run_id=template_fill_run_id,
                    extraction_id=extraction_id,
                    rating_type=rating_type,
                    rating_value=rating_value,
                    comment=comment,
                    feedback_category=feedback_category,
                    tags=tags or [],
                    context_snapshot=context_snapshot,
                    requires_response=requires_response,
                    response_status="pending" if requires_response else "none",
                    client_ip=client_ip,
                    user_agent=user_agent,
                )

                db.add(feedback)
                db.commit()

                logger.info(
                    f"Created feedback: {feedback_id}",
                    extra={
                        "feedback_id": feedback_id,
                        "operation_type": operation_type,
                        "rating_value": rating_value,
                        "org_id": org_id
                    }
                )

                return feedback_id

            except SQLAlchemyError as e:
                db.rollback()
                logger.error(f"Failed to create feedback: {e}", exc_info=True)
                return None

    def list_feedback(
        self,
        operation_type: Optional[str] = None,
        org_id: Optional[str] = None,
        rating_min: Optional[int] = None,
        rating_max: Optional[int] = None,
        requires_response: Optional[bool] = None,
        response_status: Optional[str] = None,
        hours: int = 168,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Feedback], int]:
        """List feedback with filters.

        Args:
            operation_type: Optional filter by operation type
            org_id: Optional filter by organization
            rating_min: Optional minimum rating
            rating_max: Optional maximum rating
            requires_response: Optional filter by requires_response flag
            response_status: Optional filter by response status
            hours: Time window in hours
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            Tuple of (list of feedback, total count)
        """
        with self._get_session() as db:
            try:
                time_filter = datetime.utcnow() - timedelta(hours=hours)

                query = db.query(Feedback).filter(Feedback.created_at >= time_filter)

                if operation_type:
                    query = query.filter(Feedback.operation_type == operation_type)
                if org_id:
                    query = query.filter(Feedback.org_id == org_id)
                if rating_min is not None:
                    query = query.filter(Feedback.rating_value >= rating_min)
                if rating_max is not None:
                    query = query.filter(Feedback.rating_value <= rating_max)
                if requires_response is not None:
                    query = query.filter(Feedback.requires_response == requires_response)
                if response_status:
                    query = query.filter(Feedback.response_status == response_status)

                # Count total
                total = query.count()

                # Fetch page
                items = query.order_by(desc(Feedback.created_at)).offset(offset).limit(limit).all()

                return items, total

            except SQLAlchemyError as e:
                logger.error(f"Failed to list feedback: {e}", exc_info=True)
                return [], 0

    def get_feedback_by_id(self, feedback_id: str) -> Optional[Feedback]:
        """Get feedback by ID.

        Args:
            feedback_id: Feedback ID

        Returns:
            Feedback object if found, None otherwise
        """
        with self._get_session() as db:
            try:
                return db.query(Feedback).filter(Feedback.id == feedback_id).first()
            except SQLAlchemyError as e:
                logger.error(f"Failed to get feedback by ID: {e}", exc_info=True)
                return None

    def add_response(
        self,
        feedback_id: str,
        response_text: str,
        responded_by: str,
    ) -> bool:
        """Add admin response to feedback.

        Args:
            feedback_id: Feedback ID
            response_text: Response text
            responded_by: User ID of responder

        Returns:
            True if successful, False otherwise
        """
        with self._get_session() as db:
            try:
                feedback = db.query(Feedback).filter(Feedback.id == feedback_id).first()
                if not feedback:
                    return False

                feedback.response_text = response_text
                feedback.response_status = "responded"
                feedback.responded_at = datetime.utcnow()
                feedback.responded_by = responded_by

                db.commit()
                logger.info(f"Added response to feedback: {feedback_id}")
                return True

            except SQLAlchemyError as e:
                db.rollback()
                logger.error(f"Failed to add response: {e}", exc_info=True)
                return False

    def get_feedback_stats(
        self,
        hours: int = 168,
        operation_type: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> dict:
        """Get aggregated statistics.

        Args:
            hours: Time window in hours
            operation_type: Optional filter by operation type
            org_id: Optional filter by organization

        Returns:
            Dictionary with aggregated statistics
        """
        with self._get_session() as db:
            try:
                time_filter = datetime.utcnow() - timedelta(hours=hours)

                base_query = db.query(Feedback).filter(Feedback.created_at >= time_filter)
                if operation_type:
                    base_query = base_query.filter(Feedback.operation_type == operation_type)
                if org_id:
                    base_query = base_query.filter(Feedback.org_id == org_id)

                # Total count
                total = base_query.count()

                # By operation type
                by_op_type = (
                    db.query(Feedback.operation_type, func.count())
                    .filter(Feedback.created_at >= time_filter)
                    .group_by(Feedback.operation_type)
                    .all()
                )

                # By rating
                by_rating = (
                    db.query(Feedback.rating_value, func.count())
                    .filter(Feedback.created_at >= time_filter)
                    .group_by(Feedback.rating_value)
                    .all()
                )

                # Average rating for stars only
                avg_rating = (
                    db.query(func.avg(Feedback.rating_value))
                    .filter(and_(
                        Feedback.created_at >= time_filter,
                        Feedback.rating_type == "stars"
                    ))
                    .scalar()
                )

                # Response rate
                requires_response_count = (
                    db.query(func.count())
                    .filter(and_(
                        Feedback.created_at >= time_filter,
                        Feedback.requires_response == True
                    ))
                    .scalar() or 0
                )

                responded_count = (
                    db.query(func.count())
                    .filter(and_(
                        Feedback.created_at >= time_filter,
                        Feedback.requires_response == True,
                        Feedback.response_status == "responded"
                    ))
                    .scalar() or 0
                )

                response_rate = (responded_count / requires_response_count * 100) if requires_response_count > 0 else 0.0

                return {
                    "time_window_hours": hours,
                    "total_feedback": total,
                    "by_operation_type": {op: count for op, count in by_op_type},
                    "by_rating": {str(rating): count for rating, count in by_rating if rating is not None},
                    "average_rating": round(avg_rating or 0, 2),
                    "response_rate": round(response_rate, 2),
                }

            except SQLAlchemyError as e:
                logger.error(f"Failed to get feedback stats: {e}", exc_info=True)
                return {
                    "time_window_hours": hours,
                    "total_feedback": 0,
                    "by_operation_type": {},
                    "by_rating": {},
                    "average_rating": 0.0,
                    "response_rate": 0.0,
                }
