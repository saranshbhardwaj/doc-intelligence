# backend/app/db_models_users.py
"""Database models for user management and authentication"""
from sqlalchemy import Boolean, Column, String, Integer, DateTime, Float, ForeignKey
from datetime import datetime
from app.database import Base


class User(Base):
    """User accounts synced from Clerk"""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True)  # Clerk user ID
    org_id = Column(String(64), nullable=False, index=True)  # Clerk org ID (tenant)
    email = Column(String(255), unique=True, nullable=False, index=True)
    tier = Column(String(20), default="free")  # free, standard, pro, admin
    vertical = Column(String(50), default="private_equity", nullable=False, index=True)  # Vertical/domain

    # Usage tracking
    total_pages_processed = Column(Integer, default=0)
    pages_this_month = Column(Integer, default=0)
    pages_limit = Column(Integer, default=100)  # Based on tier

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
    """Track per-extraction usage for billing and analytics"""
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
