"""Repository for IC credit memos generated from underwriting runs."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db_models_re_memos import UnderwritingMemo

logger = logging.getLogger(__name__)


@dataclass
class DeleteMemoResult:
    deleted: bool
    storage_key: Optional[str] = None
    error: Optional[str] = None
    status_code: Optional[int] = None


class ReMemoRepository:
    def __init__(self, db: Session):
        self.db = db

    def _next_version(self, run_id: str) -> int:
        stmt = select(func.coalesce(func.max(UnderwritingMemo.version), 0)).where(
            UnderwritingMemo.run_id == run_id
        )
        return int(self.db.execute(stmt).scalar_one()) + 1

    def create(
        self,
        run_id: str,
        user_id: str,
        cover_data: dict,
        sponsor_data: dict,
        market_notes: Optional[str],
        thesis_data: Optional[dict] = None,
    ) -> UnderwritingMemo:
        try:
            memo = UnderwritingMemo(
                run_id=run_id,
                user_id=user_id,
                version=self._next_version(run_id),
                status="pending",
                cover_data=cover_data,
                sponsor_data=sponsor_data,
                market_notes=market_notes,
                thesis_data=thesis_data or {},
                section_warnings=[],
            )
            self.db.add(memo)
            self.db.commit()
            self.db.refresh(memo)
            return memo
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("Failed to create memo for run %s", run_id)
            raise

    def get(self, memo_id: str, user_id: str) -> Optional[UnderwritingMemo]:
        stmt = (
            select(UnderwritingMemo)
            .where(UnderwritingMemo.id == memo_id)
            .where(UnderwritingMemo.user_id == user_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_run(self, run_id: str, user_id: str) -> List[UnderwritingMemo]:
        stmt = (
            select(UnderwritingMemo)
            .where(UnderwritingMemo.run_id == run_id)
            .where(UnderwritingMemo.user_id == user_id)
            .order_by(UnderwritingMemo.version.desc())
        )
        return list(self.db.execute(stmt).scalars())

    def update_status(self, memo_id: str, status: str, job_id: Optional[str] = None) -> None:
        memo = self.db.get(UnderwritingMemo, memo_id)
        if memo is None:
            return
        memo.status = status
        if job_id is not None:
            memo.job_id = job_id
        self.db.commit()

    def mark_complete(self, memo_id: str, r2_key: str, file_size_bytes: int) -> None:
        memo = self.db.get(UnderwritingMemo, memo_id)
        if memo is None:
            return
        memo.status = "complete"
        memo.r2_key = r2_key
        memo.file_size_bytes = file_size_bytes
        memo.completed_at = datetime.now(timezone.utc)
        self.db.commit()

    def mark_failed(self, memo_id: str, error_message: str) -> None:
        memo = self.db.get(UnderwritingMemo, memo_id)
        if memo is None:
            return
        memo.status = "failed"
        memo.error_message = error_message[:5000]
        memo.completed_at = datetime.now(timezone.utc)
        self.db.commit()

    def append_warning(self, memo_id: str, warning: str) -> None:
        memo = self.db.get(UnderwritingMemo, memo_id)
        if memo is None:
            return
        warnings = list(memo.section_warnings or [])
        warnings.append(warning)
        memo.section_warnings = warnings
        self.db.commit()

    def set_metadata(self, memo_id: str, metadata: dict) -> None:
        """Replace ``metadata_json`` blob (e.g., token usage / cost totals)."""
        memo = self.db.get(UnderwritingMemo, memo_id)
        if memo is None:
            return
        memo.metadata_json = dict(metadata)
        self.db.commit()

    def delete_pending(self, memo_id: str, user_id: str) -> bool:
        """Delete a pending memo that has not been handed to a worker yet."""
        memo = self.db.get(UnderwritingMemo, memo_id)
        if memo is None or memo.user_id != user_id or memo.status != "pending":
            return False
        try:
            self.db.delete(memo)
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            logger.exception("Failed to delete pending memo", extra={"memo_id": memo_id})
            raise

    def has_active(self, run_id: str) -> bool:
        """Return True if any memo on this run is currently generating."""
        stmt = (
            select(func.count())
            .select_from(UnderwritingMemo)
            .where(UnderwritingMemo.run_id == run_id)
            .where(UnderwritingMemo.status.in_(("pending", "generating")))
        )
        return int(self.db.execute(stmt).scalar_one()) > 0

    def delete_terminal(self, memo_id: str, user_id: str) -> DeleteMemoResult:
        """Delete a terminal memo row and return its storage key for cleanup.

        Only terminal memos may be deleted. Active memo jobs can still update the
        row, so they must remain visible until the generation task finishes.
        """
        memo = self.db.get(UnderwritingMemo, memo_id)
        if memo is None or memo.user_id != user_id:
            return DeleteMemoResult(deleted=False, error="Memo not found", status_code=404)

        if memo.status not in {"complete", "failed"}:
            return DeleteMemoResult(
                deleted=False,
                error="Memo is still generating",
                status_code=409,
            )

        storage_key = memo.r2_key
        try:
            self.db.delete(memo)
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("Failed to delete memo from database", extra={"memo_id": memo_id})
            raise

        logger.info("Deleted underwriting memo row", extra={"memo_id": memo_id})
        return DeleteMemoResult(deleted=True, storage_key=storage_key)
