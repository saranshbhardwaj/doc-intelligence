"""Repository for PE diligence investigation entities."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.db_models_chat import DocumentChunk
from app.db_models_pe_diligence import (
    PEDiligenceAnalysisRun,
    PEDiligenceAuditEvent,
    PEDiligenceEvidenceSpan,
    PEDiligenceInvestigation,
    PEDiligenceInvestigationClaim,
    PEDiligenceInvestigationRun,
    PEDiligenceRoom,
    PEDiligenceRoomDocument,
)


class PEDiligenceInvestigationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_room(self, *, room_id: str, org_id: str, user_id: str) -> Optional[PEDiligenceRoom]:
        return self.db.query(PEDiligenceRoom).filter(
            PEDiligenceRoom.id == room_id,
            PEDiligenceRoom.org_id == org_id,
            PEDiligenceRoom.user_id == user_id,
        ).first()

    def list_room_documents(self, *, room_id: str) -> List[PEDiligenceRoomDocument]:
        return self.db.query(PEDiligenceRoomDocument).filter(
            PEDiligenceRoomDocument.room_id == room_id,
            PEDiligenceRoomDocument.document_id.isnot(None),
        ).order_by(PEDiligenceRoomDocument.created_at.asc()).all()

    def list_investigations(self, *, room_id: str) -> List[PEDiligenceInvestigation]:
        return self.db.query(PEDiligenceInvestigation).filter(
            PEDiligenceInvestigation.room_id == room_id,
        ).order_by(PEDiligenceInvestigation.created_at.desc()).all()

    def get_investigation(
        self,
        *,
        investigation_id: str,
        room_id: str,
        org_id: str,
        user_id: str,
    ) -> Optional[PEDiligenceInvestigation]:
        return self.db.query(PEDiligenceInvestigation).filter(
            PEDiligenceInvestigation.id == investigation_id,
            PEDiligenceInvestigation.room_id == room_id,
            PEDiligenceInvestigation.org_id == org_id,
            PEDiligenceInvestigation.user_id == user_id,
        ).first()

    def create_investigation(
        self,
        *,
        room_id: str,
        org_id: str,
        user_id: str,
        investigation_type: str,
        title: str,
        question: Optional[str],
        metadata: Optional[dict] = None,
    ) -> PEDiligenceInvestigation:
        row = PEDiligenceInvestigation(
            room_id=room_id,
            org_id=org_id,
            user_id=user_id,
            investigation_type=investigation_type,
            title=title,
            question=question,
            status="queued",
            metadata_json=metadata or {},
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_investigation(
        self,
        *,
        investigation_id: str,
        status: Optional[str] = None,
        conclusion_markdown: Optional[str] = None,
        confidence: Optional[float] = None,
        coverage_score: Optional[float] = None,
        coverage_status: Optional[str] = None,
        metadata_patch: Optional[dict] = None,
        completed_at: Optional[datetime] = None,
    ) -> Optional[PEDiligenceInvestigation]:
        row = self.db.query(PEDiligenceInvestigation).filter(
            PEDiligenceInvestigation.id == investigation_id,
        ).first()
        if not row:
            return None

        if status is not None:
            row.status = status
        if conclusion_markdown is not None:
            row.conclusion_markdown = conclusion_markdown
        if confidence is not None:
            row.confidence = confidence
        if coverage_score is not None:
            row.coverage_score = coverage_score
        if coverage_status is not None:
            row.coverage_status = coverage_status
        if metadata_patch:
            existing = row.metadata_json or {}
            row.metadata_json = {**existing, **metadata_patch}
        if completed_at is not None:
            row.completed_at = completed_at

        self.db.commit()
        self.db.refresh(row)
        return row

    def create_run(
        self,
        *,
        investigation_id: str,
        room_id: str,
        org_id: str,
        user_id: str,
        metadata: Optional[dict] = None,
    ) -> PEDiligenceInvestigationRun:
        run = PEDiligenceInvestigationRun(
            investigation_id=investigation_id,
            room_id=room_id,
            org_id=org_id,
            user_id=user_id,
            status="queued",
            progress_percent=0,
            metadata_json=metadata or {},
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def get_run(
        self,
        *,
        run_id: str,
        investigation_id: str,
    ) -> Optional[PEDiligenceInvestigationRun]:
        return self.db.query(PEDiligenceInvestigationRun).filter(
            PEDiligenceInvestigationRun.id == run_id,
            PEDiligenceInvestigationRun.investigation_id == investigation_id,
        ).first()

    def get_latest_run(self, *, investigation_id: str) -> Optional[PEDiligenceInvestigationRun]:
        return self.db.query(PEDiligenceInvestigationRun).filter(
            PEDiligenceInvestigationRun.investigation_id == investigation_id,
        ).order_by(PEDiligenceInvestigationRun.created_at.desc()).first()

    def get_active_run(self, *, investigation_id: str) -> Optional[PEDiligenceInvestigationRun]:
        return self.db.query(PEDiligenceInvestigationRun).filter(
            PEDiligenceInvestigationRun.investigation_id == investigation_id,
            PEDiligenceInvestigationRun.status.in_(["queued", "running"]),
        ).order_by(PEDiligenceInvestigationRun.created_at.desc()).first()

    def update_run(
        self,
        *,
        run_id: str,
        status: Optional[str] = None,
        current_stage: Optional[str] = None,
        progress_percent: Optional[int] = None,
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        metadata_patch: Optional[dict] = None,
    ) -> Optional[PEDiligenceInvestigationRun]:
        run = self.db.query(PEDiligenceInvestigationRun).filter(
            PEDiligenceInvestigationRun.id == run_id
        ).first()
        if not run:
            return None

        if status is not None:
            run.status = status
        if current_stage is not None:
            run.current_stage = current_stage
        if progress_percent is not None:
            run.progress_percent = progress_percent
        if error_message is not None:
            run.error_message = error_message
        if started_at is not None:
            run.started_at = started_at
        if completed_at is not None:
            run.completed_at = completed_at
        if metadata_patch:
            existing = run.metadata_json or {}
            run.metadata_json = {**existing, **metadata_patch}

        self.db.commit()
        self.db.refresh(run)
        return run

    def replace_claims(
        self,
        *,
        investigation_id: str,
        run_id: str,
        room_id: str,
        claims: Sequence[dict],
    ) -> List[PEDiligenceInvestigationClaim]:
        # Load existing active (non-archived) claims for lineage tracking.
        existing_active = self.db.query(PEDiligenceInvestigationClaim).filter(
            PEDiligenceInvestigationClaim.investigation_id == investigation_id,
            PEDiligenceInvestigationClaim.status != "archived",
        ).all()

        # Build lookup maps from the previous run.
        prev_by_key: Dict[str, PEDiligenceInvestigationClaim] = {
            row.claim_key: row for row in existing_active
        }

        # Soft-archive all previous active claims (preserve history, do not delete).
        for row in existing_active:
            row.status = "archived"
        if existing_active:
            self.db.flush()

        created: List[PEDiligenceInvestigationClaim] = []
        for claim in claims:
            claim_payload = dict(claim)
            source_workers = claim.get("source_workers")
            if source_workers is None:
                source_workers = ["rule"]

            confidence_history = claim.get("confidence_history")
            if confidence_history is None:
                base_conf = claim.get("interpretation_confidence")
                if base_conf is None:
                    base_conf = claim.get("confidence")
                confidence_history = [float(base_conf)] if base_conf is not None else []

            # Determine lineage from previous run's claim with same key.
            claim_key = claim.get("claim_key", "")
            prev = prev_by_key.get(claim_key)
            supersedes_claim_id = prev.id if prev else claim.get("supersedes_claim_id")

            # Carry-forward verification_status only when a reviewer has explicitly
            # overridden it (override_history present) AND the claim stance hasn't
            # changed (a stance flip invalidates the previous reviewer decision).
            verification_status = claim.get("verification_status") or "needs_review"
            if prev is not None:
                prev_meta = prev.metadata_json or {}
                has_override = bool(prev_meta.get("override_history"))
                stance_unchanged = (prev.stance == claim.get("stance"))
                if has_override and stance_unchanged:
                    verification_status = prev.verification_status

            for key in [
                "status",
                "supersedes_claim_id",
                "interpretation_confidence",
                "coverage_score",
                "source_workers",
                "confidence_history",
                "verification_status",
            ]:
                claim_payload.pop(key, None)

            row = PEDiligenceInvestigationClaim(
                investigation_id=investigation_id,
                run_id=run_id,
                room_id=room_id,
                status=claim.get("status") or "proposed",
                supersedes_claim_id=supersedes_claim_id,
                interpretation_confidence=claim.get("interpretation_confidence"),
                coverage_score=claim.get("coverage_score"),
                source_workers=source_workers,
                confidence_history=confidence_history,
                verification_status=verification_status,
                **claim_payload,
            )
            self.db.add(row)
            created.append(row)

        self.db.commit()
        for row in created:
            self.db.refresh(row)
        return created

    def override_claim(
        self,
        *,
        claim_id: str,
        investigation_id: str,
        verification_status: str,
        override_reason: Optional[str],
        reviewer_notes: Optional[str],
        actor_user_id: str,
    ) -> Optional[PEDiligenceInvestigationClaim]:
        """Override the verification status of an active claim."""
        claim = self.db.query(PEDiligenceInvestigationClaim).filter(
            PEDiligenceInvestigationClaim.id == claim_id,
            PEDiligenceInvestigationClaim.investigation_id == investigation_id,
        ).first()
        if not claim:
            return None
        if claim.status == "archived":
            # Archived claims are immutable history — callers should 409.
            raise ValueError("Cannot override an archived claim")

        meta = dict(claim.metadata_json or {})
        history = list(meta.get("override_history") or [])
        history.append({
            "previous_status": claim.verification_status,
            "new_status": verification_status,
            "reason": override_reason,
            "reviewer_notes": reviewer_notes,
            "overridden_by": actor_user_id,
            "overridden_at": datetime.utcnow().isoformat(),
        })
        meta["override_history"] = history
        claim.verification_status = verification_status
        claim.metadata_json = meta
        self.db.commit()
        self.db.refresh(claim)
        return claim

    def list_claims(self, *, investigation_id: str) -> List[PEDiligenceInvestigationClaim]:
        return self.db.query(PEDiligenceInvestigationClaim).filter(
            PEDiligenceInvestigationClaim.investigation_id == investigation_id
        ).order_by(PEDiligenceInvestigationClaim.created_at.asc()).all()

    def delete_investigation_evidence(self, *, room_id: str, entity_ids: Sequence[str]) -> None:
        if not entity_ids:
            return
        self.db.query(PEDiligenceEvidenceSpan).filter(
            PEDiligenceEvidenceSpan.room_id == room_id,
            PEDiligenceEvidenceSpan.entity_id.in_(list(entity_ids)),
            PEDiligenceEvidenceSpan.entity_type.in_(["investigation_claim", "investigation_conclusion"]),
        ).delete(synchronize_session=False)
        self.db.commit()

    def create_evidence_spans(self, *, room_id: str, spans: Sequence[dict]) -> List[PEDiligenceEvidenceSpan]:
        created: List[PEDiligenceEvidenceSpan] = []
        for span in spans:
            row = PEDiligenceEvidenceSpan(
                room_id=room_id,
                analysis_run_id=None,
                **span,
            )
            self.db.add(row)
            created.append(row)
        self.db.commit()
        for row in created:
            self.db.refresh(row)
        return created

    def get_evidence_for_entities(
        self,
        *,
        room_id: str,
        entity_type: str,
        entity_ids: Sequence[str],
    ) -> List[PEDiligenceEvidenceSpan]:
        if not entity_ids:
            return []
        return self.db.query(PEDiligenceEvidenceSpan).filter(
            PEDiligenceEvidenceSpan.room_id == room_id,
            PEDiligenceEvidenceSpan.entity_type == entity_type,
            PEDiligenceEvidenceSpan.entity_id.in_(list(entity_ids)),
        ).order_by(PEDiligenceEvidenceSpan.created_at.asc()).all()

    def get_latest_completed_analysis_run(self, *, room_id: str) -> Optional[PEDiligenceAnalysisRun]:
        return self.db.query(PEDiligenceAnalysisRun).filter(
            PEDiligenceAnalysisRun.room_id == room_id,
            PEDiligenceAnalysisRun.status == "completed",
        ).order_by(PEDiligenceAnalysisRun.completed_at.desc()).first()

    def get_active_analysis_run(self, *, room_id: str) -> Optional[PEDiligenceAnalysisRun]:
        return self.db.query(PEDiligenceAnalysisRun).filter(
            PEDiligenceAnalysisRun.room_id == room_id,
            PEDiligenceAnalysisRun.status.in_(["queued", "running"]),
        ).order_by(PEDiligenceAnalysisRun.created_at.desc()).first()

    def add_audit_event(
        self,
        *,
        room_id: str,
        event_type: str,
        actor_user_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> PEDiligenceAuditEvent:
        row = PEDiligenceAuditEvent(
            room_id=room_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload or {},
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_document_chunk_count(self, *, document_ids: Sequence[str]) -> Dict[str, int]:
        if not document_ids:
            return {}
        rows = self.db.query(
            DocumentChunk.document_id,
            DocumentChunk.id,
        ).filter(DocumentChunk.document_id.in_(list(document_ids))).all()
        counts: Dict[str, int] = {}
        for doc_id, _ in rows:
            counts[doc_id] = counts.get(doc_id, 0) + 1
        return counts
