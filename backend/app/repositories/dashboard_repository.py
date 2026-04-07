"""Repository for dashboard analytics.

Data Access Layer for user-facing admin dashboard.

All queries are scoped to org_id. Data comes from database (NOT Prometheus).
LLM costs (cost_usd) are internal operational data and NOT exposed to users.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Any
from contextlib import contextmanager
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func, and_

from app.database import SessionLocal
from app.db_models_chat import ChatMessage, ChatSession
from app.db_models_documents import Document
from app.db_models_templates import TemplateFillRun, ExcelTemplate
from app.db_models import Extraction
from app.db_models_workflows import WorkflowRun
from app.utils.logging import logger


class DashboardRepository:
    """Repository for dashboard analytics queries.

    Provides org-scoped aggregations for:
    - Overview stats (documents, chat, template fills, extractions, workflows)
    - Daily activity breakdown
    - Template fill insights
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

    def get_overview(self, org_id: str, days: int) -> Dict[str, Any]:
        """Get high-level stats for the organization.

        Args:
            org_id: Organization ID
            days: Number of days to include in period stats (default 30)

        Returns:
            Dict with overview stats:
            - period_days: Number of days in the period
            - documents: {total, period}
            - chat: {sessions, messages}
            - template_fills: {total, completed, failed, success_rate}
            - extractions: {total, completed, failed}
            - workflows: {total, completed, failed}
            - active_users: Count of distinct users with activity in period
        """
        with self._get_session() as db:
            try:
                period_start = datetime.utcnow() - timedelta(days=days)

                # Documents
                doc_total = db.query(func.count(Document.id)).filter(
                    Document.org_id == org_id
                ).scalar() or 0

                doc_period = db.query(func.count(Document.id)).filter(
                    and_(
                        Document.org_id == org_id,
                        Document.created_at >= period_start
                    )
                ).scalar() or 0

                # Chat sessions and messages
                chat_sessions = db.query(func.count(ChatSession.id)).filter(
                    and_(
                        ChatSession.org_id == org_id,
                        ChatSession.created_at >= period_start
                    )
                ).scalar() or 0

                chat_messages = db.query(func.count(ChatMessage.id)).join(
                    ChatSession, ChatMessage.session_id == ChatSession.id
                ).filter(
                    and_(
                        ChatSession.org_id == org_id,
                        ChatMessage.created_at >= period_start
                    )
                ).scalar() or 0

                # Template fills
                tf_total = db.query(func.count(TemplateFillRun.id)).filter(
                    and_(
                        TemplateFillRun.org_id == org_id,
                        TemplateFillRun.created_at >= period_start
                    )
                ).scalar() or 0

                tf_completed = db.query(func.count(TemplateFillRun.id)).filter(
                    and_(
                        TemplateFillRun.org_id == org_id,
                        TemplateFillRun.status == "completed",
                        TemplateFillRun.created_at >= period_start
                    )
                ).scalar() or 0

                tf_failed = db.query(func.count(TemplateFillRun.id)).filter(
                    and_(
                        TemplateFillRun.org_id == org_id,
                        TemplateFillRun.status == "failed",
                        TemplateFillRun.created_at >= period_start
                    )
                ).scalar() or 0

                tf_success_rate = round(tf_completed / tf_total, 2) if tf_total > 0 else 0.0

                # Extractions
                ext_total = db.query(func.count(Extraction.id)).filter(
                    and_(
                        Extraction.org_id == org_id,
                        Extraction.created_at >= period_start
                    )
                ).scalar() or 0

                ext_completed = db.query(func.count(Extraction.id)).filter(
                    and_(
                        Extraction.org_id == org_id,
                        Extraction.status == "completed",
                        Extraction.created_at >= period_start
                    )
                ).scalar() or 0

                ext_failed = db.query(func.count(Extraction.id)).filter(
                    and_(
                        Extraction.org_id == org_id,
                        Extraction.status == "failed",
                        Extraction.created_at >= period_start
                    )
                ).scalar() or 0

                # Pages analyzed (sum of page_count from documents uploaded in period)
                pages_analyzed = db.query(
                    func.coalesce(func.sum(Document.page_count), 0)
                ).filter(
                    and_(
                        Document.org_id == org_id,
                        Document.created_at >= period_start
                    )
                ).scalar() or 0

                # Total fields auto-filled across all completed template fill runs
                total_fields_populated = db.query(
                    func.coalesce(func.sum(TemplateFillRun.total_fields_filled), 0)
                ).filter(
                    and_(
                        TemplateFillRun.org_id == org_id,
                        TemplateFillRun.status == "completed",
                        TemplateFillRun.created_at >= period_start
                    )
                ).scalar() or 0

                # Workflows
                wf_total = db.query(func.count(WorkflowRun.id)).filter(
                    and_(
                        WorkflowRun.org_id == org_id,
                        WorkflowRun.created_at >= period_start
                    )
                ).scalar() or 0

                wf_completed = db.query(func.count(WorkflowRun.id)).filter(
                    and_(
                        WorkflowRun.org_id == org_id,
                        WorkflowRun.status == "completed",
                        WorkflowRun.created_at >= period_start
                    )
                ).scalar() or 0

                wf_failed = db.query(func.count(WorkflowRun.id)).filter(
                    and_(
                        WorkflowRun.org_id == org_id,
                        WorkflowRun.status == "failed",
                        WorkflowRun.created_at >= period_start
                    )
                ).scalar() or 0

                # Active users (distinct users with any activity in period)
                # Count users who created chat messages, template fills, or extractions
                active_users_from_chat = db.query(ChatSession.user_id).join(
                    ChatMessage, ChatMessage.session_id == ChatSession.id
                ).filter(
                    and_(
                        ChatSession.org_id == org_id,
                        ChatMessage.created_at >= period_start
                    )
                ).distinct().count()

                active_users_from_tf = db.query(TemplateFillRun.user_id).filter(
                    and_(
                        TemplateFillRun.org_id == org_id,
                        TemplateFillRun.created_at >= period_start,
                        TemplateFillRun.user_id.isnot(None)
                    )
                ).distinct().count()

                active_users_from_ext = db.query(Extraction.user_id).filter(
                    and_(
                        Extraction.org_id == org_id,
                        Extraction.created_at >= period_start,
                        Extraction.user_id.isnot(None)
                    )
                ).distinct().count()

                # Union of distinct user IDs
                active_users = len(set(
                    [uid for uid in [active_users_from_chat, active_users_from_tf, active_users_from_ext] if uid]
                ))

                return {
                    "period_days": days,
                    "documents": {
                        "total": doc_total,
                        "period": doc_period,
                        "pages_analyzed": int(pages_analyzed)
                    },
                    "chat": {
                        "sessions": chat_sessions,
                        "messages": chat_messages
                    },
                    "template_fills": {
                        "total": tf_total,
                        "completed": tf_completed,
                        "failed": tf_failed,
                        "success_rate": tf_success_rate,
                        "total_fields_populated": int(total_fields_populated)
                    },
                    "extractions": {
                        "total": ext_total,
                        "completed": ext_completed,
                        "failed": ext_failed
                    },
                    "workflows": {
                        "total": wf_total,
                        "completed": wf_completed,
                        "failed": wf_failed
                    },
                    "active_users": active_users
                }

            except SQLAlchemyError as e:
                logger.error(f"Failed to get dashboard overview: {e}", exc_info=True)
                return {
                    "period_days": days,
                    "documents": {"total": 0, "period": 0, "pages_analyzed": 0},
                    "chat": {"sessions": 0, "messages": 0},
                    "template_fills": {"total": 0, "completed": 0, "failed": 0, "success_rate": 0.0, "total_fields_populated": 0},
                    "extractions": {"total": 0, "completed": 0, "failed": 0},
                    "workflows": {"total": 0, "completed": 0, "failed": 0},
                    "active_users": 0
                }

    def get_daily_activity(self, org_id: str, days: int) -> List[Dict[str, Any]]:
        """Get daily activity breakdown for charts.

        Args:
            org_id: Organization ID
            days: Number of days to include

        Returns:
            List of daily activity dicts:
            [
                {
                    "date": "2026-02-01",
                    "chat_messages": 12,
                    "template_fills": 3,
                    "extractions": 5
                },
                ...
            ]
        """
        with self._get_session() as db:
            try:
                period_start = datetime.utcnow() - timedelta(days=days)

                # Chat messages by date
                chat_by_date = db.query(
                    func.date(ChatMessage.created_at).label('date'),
                    func.count(ChatMessage.id).label('count')
                ).join(
                    ChatSession, ChatMessage.session_id == ChatSession.id
                ).filter(
                    and_(
                        ChatSession.org_id == org_id,
                        ChatMessage.created_at >= period_start
                    )
                ).group_by(func.date(ChatMessage.created_at)).all()

                # Template fills by date
                tf_by_date = db.query(
                    func.date(TemplateFillRun.created_at).label('date'),
                    func.count(TemplateFillRun.id).label('count')
                ).filter(
                    and_(
                        TemplateFillRun.org_id == org_id,
                        TemplateFillRun.created_at >= period_start
                    )
                ).group_by(func.date(TemplateFillRun.created_at)).all()

                # Extractions by date
                ext_by_date = db.query(
                    func.date(Extraction.created_at).label('date'),
                    func.count(Extraction.id).label('count')
                ).filter(
                    and_(
                        Extraction.org_id == org_id,
                        Extraction.created_at >= period_start
                    )
                ).group_by(func.date(Extraction.created_at)).all()

                # Workflow runs by date
                wf_by_date = db.query(
                    func.date(WorkflowRun.created_at).label('date'),
                    func.count(WorkflowRun.id).label('count')
                ).filter(
                    and_(
                        WorkflowRun.org_id == org_id,
                        WorkflowRun.created_at >= period_start
                    )
                ).group_by(func.date(WorkflowRun.created_at)).all()

                # Merge into daily breakdown
                def empty_day(d):
                    return {"date": d, "chat_messages": 0, "template_fills": 0, "extractions": 0, "workflow_runs": 0}
                daily_map: Dict[str, Dict[str, int]] = {}

                for date_obj, count in chat_by_date:
                    date_str = date_obj.strftime('%Y-%m-%d')
                    if date_str not in daily_map:
                        daily_map[date_str] = empty_day(date_str)
                    daily_map[date_str]["chat_messages"] = count

                for date_obj, count in tf_by_date:
                    date_str = date_obj.strftime('%Y-%m-%d')
                    if date_str not in daily_map:
                        daily_map[date_str] = empty_day(date_str)
                    daily_map[date_str]["template_fills"] = count

                for date_obj, count in ext_by_date:
                    date_str = date_obj.strftime('%Y-%m-%d')
                    if date_str not in daily_map:
                        daily_map[date_str] = empty_day(date_str)
                    daily_map[date_str]["extractions"] = count

                for date_obj, count in wf_by_date:
                    date_str = date_obj.strftime('%Y-%m-%d')
                    if date_str not in daily_map:
                        daily_map[date_str] = empty_day(date_str)
                    daily_map[date_str]["workflow_runs"] = count

                # Fill zero-days so chart is continuous (no gaps between active days)
                today = datetime.utcnow().date()
                for i in range(days):
                    day = today - timedelta(days=days - 1 - i)
                    date_str = day.strftime('%Y-%m-%d')
                    if date_str not in daily_map:
                        daily_map[date_str] = empty_day(date_str)

                # Sort by date
                daily = sorted(daily_map.values(), key=lambda x: x["date"])

                return daily

            except SQLAlchemyError as e:
                logger.error(f"Failed to get daily activity: {e}", exc_info=True)
                return []

    def get_template_fill_stats(self, org_id: str, days: int) -> Dict[str, Any]:
        """Get template fill insights.

        Args:
            org_id: Organization ID
            days: Number of days to include

        Returns:
            Dict with template fill stats:
            {
                "by_status": {"completed": 15, "failed": 3, "running": 0},
                "avg_fields_filled": 24.5,
                "avg_auto_map_rate": 0.85,
                "avg_processing_time_seconds": 45.2,
                "top_templates": [
                    {"template_name": "Rent Roll v1", "fill_count": 8},
                    {"template_name": "Operating Statement", "fill_count": 5}
                ]
            }
        """
        with self._get_session() as db:
            try:
                period_start = datetime.utcnow() - timedelta(days=days)

                # Status breakdown
                status_counts = db.query(
                    TemplateFillRun.status,
                    func.count(TemplateFillRun.id).label('count')
                ).filter(
                    and_(
                        TemplateFillRun.org_id == org_id,
                        TemplateFillRun.created_at >= period_start
                    )
                ).group_by(TemplateFillRun.status).all()

                by_status = {status: count for status, count in status_counts}

                # Average fields filled (only for completed runs)
                avg_fields_result = db.query(
                    func.avg(TemplateFillRun.total_fields_filled).label('avg_filled')
                ).filter(
                    and_(
                        TemplateFillRun.org_id == org_id,
                        TemplateFillRun.status == "completed",
                        TemplateFillRun.created_at >= period_start,
                        TemplateFillRun.total_fields_filled.isnot(None)
                    )
                ).scalar()

                avg_fields_filled = round(float(avg_fields_result), 1) if avg_fields_result else 0.0

                # Average auto-map rate (auto_mapped_count / total_fields_detected)
                # Only for completed runs with non-zero fields
                auto_map_data = db.query(
                    func.sum(TemplateFillRun.auto_mapped_count).label('total_auto'),
                    func.sum(TemplateFillRun.total_fields_detected).label('total_detected')
                ).filter(
                    and_(
                        TemplateFillRun.org_id == org_id,
                        TemplateFillRun.status == "completed",
                        TemplateFillRun.created_at >= period_start,
                        TemplateFillRun.total_fields_detected > 0
                    )
                ).first()

                total_auto = auto_map_data[0] or 0
                total_detected = auto_map_data[1] or 0
                avg_auto_map_rate = round(total_auto / total_detected, 2) if total_detected > 0 else 0.0

                # Average processing time (convert ms to seconds)
                avg_time_ms = db.query(
                    func.avg(TemplateFillRun.processing_time_ms).label('avg_time')
                ).filter(
                    and_(
                        TemplateFillRun.org_id == org_id,
                        TemplateFillRun.status == "completed",
                        TemplateFillRun.created_at >= period_start,
                        TemplateFillRun.processing_time_ms.isnot(None)
                    )
                ).scalar()

                avg_processing_time_seconds = round(float(avg_time_ms) / 1000, 1) if avg_time_ms else 0.0

                # Top templates by fill count
                top_templates_query = db.query(
                    ExcelTemplate.name.label('template_name'),
                    func.count(TemplateFillRun.id).label('fill_count')
                ).join(
                    TemplateFillRun, TemplateFillRun.template_id == ExcelTemplate.id
                ).filter(
                    and_(
                        TemplateFillRun.org_id == org_id,
                        TemplateFillRun.created_at >= period_start
                    )
                ).group_by(ExcelTemplate.name).order_by(func.count(TemplateFillRun.id).desc()).limit(10).all()

                top_templates = [
                    {"template_name": name, "fill_count": count}
                    for name, count in top_templates_query
                ]

                return {
                    "by_status": by_status,
                    "avg_fields_filled": avg_fields_filled,
                    "avg_auto_map_rate": avg_auto_map_rate,
                    "avg_processing_time_seconds": avg_processing_time_seconds,
                    "top_templates": top_templates
                }

            except SQLAlchemyError as e:
                logger.error(f"Failed to get template fill stats: {e}", exc_info=True)
                return {
                    "by_status": {},
                    "avg_fields_filled": 0.0,
                    "avg_auto_map_rate": 0.0,
                    "avg_processing_time_seconds": 0.0,
                    "top_templates": []
                }


__all__ = ["DashboardRepository"]
