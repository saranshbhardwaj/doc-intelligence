"""Repository for LLM I/O log entries (eval/debugging capture)."""
import json
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.db_models_io_logs import LLMIOLog
from app.utils.logging import logger


class IOLogRepository:
    """CRUD operations for llm_io_logs table."""

    def __init__(self, db: Optional[Session] = None):
        self._db = db
        self._owns_session = db is None

    def _get_db(self) -> Session:
        if self._db is not None:
            return self._db
        return SessionLocal()

    def save_io_log(
        self,
        source_type: str,
        source_id: str,
        stage: str,
        system_prompt: Optional[str] = None,
        user_message: Optional[str] = None,
        output: Optional[Any] = None,
        prompt_version: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_creation_tokens: int = 0,
        cache_read_tokens: int = 0,
        duration_ms: Optional[int] = None,
    ) -> Optional[str]:
        """Insert a single io_log entry. Returns the new row ID, or None on failure."""
        db = self._get_db()
        try:
            output_str = (
                json.dumps(output, ensure_ascii=False)
                if output is not None and not isinstance(output, str)
                else output
            )
            entry = LLMIOLog(
                id=str(uuid.uuid4()),
                source_type=source_type,
                source_id=source_id,
                stage=stage,
                prompt_version=prompt_version,
                system_prompt=system_prompt,
                user_message=user_message,
                output=output_str,
                metadata_=metadata,
                input_tokens=input_tokens or 0,
                output_tokens=output_tokens or 0,
                cache_creation_tokens=cache_creation_tokens or 0,
                cache_read_tokens=cache_read_tokens or 0,
                duration_ms=duration_ms,
            )
            db.add(entry)
            db.commit()
            return entry.id
        except Exception as e:
            db.rollback()
            logger.warning(f"Failed to save io_log entry ({source_type}/{stage}): {e}")
            return None
        finally:
            if self._owns_session:
                db.close()

    def save_io_logs_batch(self, entries: List[Dict[str, Any]]) -> int:
        """Bulk insert multiple io_log entries. Returns count saved."""
        if not entries:
            return 0
        db = self._get_db()
        saved = 0
        try:
            for entry_data in entries:
                output = entry_data.get("output")
                output_str = (
                    json.dumps(output, ensure_ascii=False)
                    if output is not None and not isinstance(output, str)
                    else output
                )
                entry = LLMIOLog(
                    id=str(uuid.uuid4()),
                    source_type=entry_data["source_type"],
                    source_id=entry_data["source_id"],
                    stage=entry_data["stage"],
                    prompt_version=entry_data.get("prompt_version"),
                    system_prompt=entry_data.get("system_prompt"),
                    user_message=entry_data.get("user_message"),
                    output=output_str,
                    metadata_=entry_data.get("metadata"),
                    input_tokens=entry_data.get("input_tokens", 0) or 0,
                    output_tokens=entry_data.get("output_tokens", 0) or 0,
                    cache_creation_tokens=entry_data.get("cache_creation_tokens", 0) or 0,
                    cache_read_tokens=entry_data.get("cache_read_tokens", 0) or 0,
                    duration_ms=entry_data.get("duration_ms"),
                )
                db.add(entry)
                saved += 1
            db.commit()
            return saved
        except Exception as e:
            db.rollback()
            logger.warning(f"Failed to bulk-save io_log entries: {e}")
            return 0
        finally:
            if self._owns_session:
                db.close()

    def get_io_logs(
        self,
        source_type: str,
        source_id: str,
    ) -> List[LLMIOLog]:
        """Fetch all io_log entries for a given source."""
        db = self._get_db()
        try:
            return (
                db.query(LLMIOLog)
                .filter(
                    LLMIOLog.source_type == source_type,
                    LLMIOLog.source_id == source_id,
                )
                .order_by(LLMIOLog.created_at)
                .all()
            )
        finally:
            if self._owns_session:
                db.close()

    def query_io_logs(
        self,
        stage: Optional[str] = None,
        source_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[LLMIOLog]:
        """Query io_log entries by stage/source_type for export."""
        db = self._get_db()
        try:
            q = db.query(LLMIOLog)
            if stage:
                q = q.filter(LLMIOLog.stage == stage)
            if source_type:
                q = q.filter(LLMIOLog.source_type == source_type)
            return (
                q.order_by(LLMIOLog.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
        finally:
            if self._owns_session:
                db.close()
