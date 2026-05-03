# backend/app/db_models_users.py
"""Database models for user management and authentication."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class User(Base):
    """User accounts managed via WorkOS AuthKit."""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True)  # WorkOS user ID
    org_id = Column(String(64), nullable=False, index=True)  # WorkOS org ID (tenant)
    email = Column(String(255), unique=True, nullable=False, index=True)
    tier = Column(String(20), default="free")  # free, standard, pro, admin
    status = Column(String(20), default="active", nullable=False)  # active, pending_approval
    vertical = Column(String(50), default="real_estate", nullable=False, index=True)  # Deprecated — use allowed_verticals
    allowed_verticals = Column(JSONB, default=lambda: ["real_estate"], server_default='["real_estate"]', nullable=False)

    # Usage tracking
    total_pages_processed = Column(Integer, default=0)
    pages_this_month = Column(Integer, default=0)
    pages_limit = Column(Integer, default=100)  # Based on tier
    workflow_runs_limit = Column(Integer, default=2)  # Closed beta cap (0 = unlimited)
    extractions_limit = Column(Integer, default=1)  # Closed beta cap (0 = unlimited)
    template_fill_runs_limit = Column(Integer, default=100)  # Closed beta cap (0 = unlimited)
    chat_messages_limit = Column(Integer, default=100)  # Closed beta cap (0 = unlimited)

    # Per-user underwriting threshold overrides (sparse JSONB blob)
    underwriting_thresholds = Column(JSONB, nullable=True)

    # Billing
    subscription_id = Column(String(255), nullable=True)
    subscription_status = Column(String(20), default="inactive")  # inactive, active, canceled
    billing_period_start = Column(DateTime, nullable=True)
    billing_period_end = Column(DateTime, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    last_login = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class UsageLog(Base):
    """Track per-extraction usage for billing and analytics."""
    __tablename__ = "usage_logs"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    org_id = Column(String(64), nullable=False, index=True)
    extraction_id = Column(String(36), ForeignKey("extractions.id", ondelete="SET NULL"), nullable=True)
    
    filename = Column(String(255), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    pages_processed = Column(Integer, nullable=False)
    operation_type = Column(String(50), default="extraction")  # parsing, extraction
    cost_usd = Column(Float, default=0.0)  # Actual cost (Azure + Claude)

    created_at = Column(DateTime, default=datetime.now, nullable=False)


class AllowedEmail(Base):
    """Pre-approved emails that can use the app (invite-only access control)."""
    __tablename__ = "allowed_emails"

    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    added_by = Column(String(36), nullable=True)  # admin user_id who added this
    created_at = Column(DateTime, default=datetime.now, nullable=False)


class ShadowCreditLog(Base):
    """Best-effort shadow credit ledger for pricing simulation (not enforced)."""
    __tablename__ = "shadow_credit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id = Column(String(64), nullable=False, index=True)
    operation_type = Column(String(50), nullable=False, index=True)
    reference_id = Column(String(64), nullable=True, index=True)  # run/extraction/session/document id
    units = Column(Integer, nullable=False, default=1)  # e.g., pages for indexing
    shadow_credits = Column(Float, nullable=False, default=0.0)
    status = Column(String(20), nullable=False, default="committed", index=True)  # reserved | committed | reversed
    reversed_at = Column(DateTime, nullable=True)
    reverse_reason = Column(Text, nullable=True)
    shadow_metadata = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)
