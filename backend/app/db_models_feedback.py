# backend/app/db_models_feedback.py
"""SQLAlchemy database model for unified feedback system."""
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, Index, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base
import uuid


class Feedback(Base):
    """
    Unified feedback model supporting all operation types.

    Uses polymorphic pattern (same as JobState) where exactly one
    entity reference must be set.

    Operation types:
    - chat: Feedback on chat messages (thumbs up/down)
    - workflow: Feedback on workflow runs (star rating)
    - template_fill: Feedback on template fill runs (star rating)
    - extraction: Feedback on extractions (star rating)
    """
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(
            "operation_type IN ('chat', 'workflow', 'template_fill', 'extraction')",
            name='feedback_operation_type_check'
        ),
        CheckConstraint(
            "rating_type IN ('thumbs', 'stars')",
            name='feedback_rating_type_check'
        ),
        Index("idx_feedback_org_id", "org_id"),
        Index("idx_feedback_user_id", "user_id"),
        Index("idx_feedback_operation_type", "operation_type"),
        Index("idx_feedback_created_at", "created_at"),
        Index("idx_feedback_org_type_created", "org_id", "operation_type", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Multi-tenant
    org_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)

    # Polymorphic entity references (exactly one must be set)
    chat_message_id = Column(String(36), ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True)
    workflow_run_id = Column(String(36), ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True)
    template_fill_run_id = Column(String(36), ForeignKey("template_fill_runs.id", ondelete="SET NULL"), nullable=True)
    extraction_id = Column(String(36), ForeignKey("extractions.id", ondelete="SET NULL"), nullable=True)

    # Operation type (denormalized for query efficiency)
    operation_type = Column(String(20), nullable=False)

    # Rating
    rating_type = Column(String(20), nullable=False, default="thumbs")
    rating_value = Column(Integer, nullable=True)  # -1/1 for thumbs, 1-5 for stars

    # Free text
    comment = Column(Text, nullable=True)

    # Categorization
    feedback_category = Column(String(50), nullable=True)
    tags = Column(JSONB, default=list)

    # Response tracking
    requires_response = Column(Boolean, default=False)
    response_status = Column(String(20), default="none")
    response_text = Column(Text, nullable=True)
    responded_at = Column(DateTime(timezone=True), nullable=True)
    responded_by = Column(String(100), nullable=True)

    # Context snapshot
    context_snapshot = Column(JSONB, nullable=True)

    # Metadata
    client_ip = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships (optional - helps with joins)
    chat_message = relationship("ChatMessage", foreign_keys=[chat_message_id], uselist=False)
    workflow_run = relationship("WorkflowRun", foreign_keys=[workflow_run_id], uselist=False)
    template_fill_run = relationship("TemplateFillRun", foreign_keys=[template_fill_run_id], uselist=False)
    extraction = relationship("Extraction", foreign_keys=[extraction_id], uselist=False)
