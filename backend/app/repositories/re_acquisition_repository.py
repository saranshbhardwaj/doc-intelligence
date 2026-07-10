"""Repository for Real Estate acquisition candidates."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.db_models_re import AcquisitionCandidate, AcquisitionCandidateDocument

logger = logging.getLogger(__name__)


class AcquisitionCandidateRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user_id: str, org_id: str | None, payload: dict[str, Any]) -> AcquisitionCandidate:
        try:
            candidate = AcquisitionCandidate(
                user_id=user_id,
                org_id=org_id,
                name=payload["name"],
                address=payload.get("address"),
                market=payload.get("market"),
                asset_class=payload.get("asset_class") or "self_storage",
                asset_class_confidence=payload.get("asset_class_confidence"),
                source_type=payload.get("source_type") or "manual",
                source_name=payload.get("source_name"),
                source_status=payload.get("source_status"),
                source_metadata=payload.get("source_metadata") or {},
                status=payload.get("status") or "new",
                priority=payload.get("priority") or "medium",
                readiness_score=payload.get("readiness_score"),
                facts=payload.get("facts") or {},
                evidence=payload.get("evidence") or [],
                missing_items=payload.get("missing_items") or [],
            )
            self.db.add(candidate)
            self.db.commit()
            self.db.refresh(candidate)
            return candidate
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("Failed to create acquisition candidate for user %s", user_id)
            raise

    def list(self, user_id: str, limit: int = 100, offset: int = 0) -> list[AcquisitionCandidate]:
        stmt = (
            select(AcquisitionCandidate)
            .options(selectinload(AcquisitionCandidate.documents).joinedload(AcquisitionCandidateDocument.document))
            .where(AcquisitionCandidate.user_id == user_id)
            .order_by(AcquisitionCandidate.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())

    def get(self, candidate_id: str, user_id: str) -> AcquisitionCandidate | None:
        stmt = (
            select(AcquisitionCandidate)
            .options(selectinload(AcquisitionCandidate.documents).joinedload(AcquisitionCandidateDocument.document))
            .where(AcquisitionCandidate.id == candidate_id)
            .where(AcquisitionCandidate.user_id == user_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def update(self, candidate_id: str, user_id: str, payload: dict[str, Any]) -> AcquisitionCandidate | None:
        candidate = self.get(candidate_id, user_id)
        if not candidate:
            return None
        allowed = {"name", "address", "market", "status", "priority", "facts", "evidence", "missing_items"}
        try:
            for key, value in payload.items():
                if key in allowed and value is not None:
                    setattr(candidate, key, value)
            self.db.commit()
            self.db.refresh(candidate)
            return candidate
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("Failed to update acquisition candidate %s", candidate_id)
            raise

    def attach_document(
        self,
        candidate_id: str,
        user_id: str,
        document_id: str,
        doc_type: str,
        source: str = "library",
    ) -> AcquisitionCandidateDocument | None:
        candidate = self.get(candidate_id, user_id)
        if not candidate:
            return None
        try:
            for existing in candidate.documents:
                if existing.doc_type == doc_type and existing.status == "attached":
                    existing.status = "detached"
            link = AcquisitionCandidateDocument(
                candidate_id=candidate.id,
                document_id=document_id,
                doc_type=doc_type,
                status="attached",
                source=source,
            )
            candidate.missing_items = [
                item for item in (candidate.missing_items or [])
                if item != doc_type
            ]
            self.db.add(link)
            self.db.commit()
            self.db.refresh(link)
            return link
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("Failed to attach document %s to candidate %s", document_id, candidate_id)
            raise

    def detach_document(self, candidate_id: str, user_id: str, document_id: str) -> bool:
        candidate = self.get(candidate_id, user_id)
        if not candidate:
            return False
        try:
            changed = False
            for existing in candidate.documents:
                if existing.document_id == document_id and existing.status == "attached":
                    existing.status = "detached"
                    if existing.doc_type in {"om", "rent_roll", "t12"}:
                        missing_items = list(candidate.missing_items or [])
                        if existing.doc_type not in missing_items:
                            candidate.missing_items = [*missing_items, existing.doc_type]
                    changed = True
            if changed:
                self.db.commit()
            return changed
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("Failed to detach document %s from candidate %s", document_id, candidate_id)
            raise