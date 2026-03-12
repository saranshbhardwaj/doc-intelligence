"""Repository for PE diligence domain entities."""
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db_models_documents import Document
from app.db_models_chat import DocumentChunk
from app.db_models_pe_diligence import (
    PEDiligenceAnalysisRun,
    PEDiligenceAuditEvent,
    PEDiligenceChecklistItem,
    PEDiligenceClause,
    PEDiligenceContractFamily,
    PEDiligenceEvidenceSpan,
    PEDiligenceFinding,
    PEDiligencePlaybook,
    PEDiligenceRoom,
    PEDiligenceRoomDocument,
    PEDiligenceSummary,
)


class PEDiligenceRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_room(
        self,
        *,
        org_id: str,
        user_id: str,
        name: str,
        target_company: Optional[str],
        notes: Optional[str],
    ) -> PEDiligenceRoom:
        room = PEDiligenceRoom(
            org_id=org_id,
            user_id=user_id,
            name=name,
            target_company=target_company,
            notes=notes,
            status="draft",
        )
        self.db.add(room)
        self.db.commit()
        self.db.refresh(room)
        return room

    def list_rooms(
        self,
        *,
        org_id: str,
        user_id: str,
        limit: int,
        offset: int,
        status: Optional[str],
    ) -> List[PEDiligenceRoom]:
        q = self.db.query(PEDiligenceRoom).filter(
            PEDiligenceRoom.org_id == org_id,
            PEDiligenceRoom.user_id == user_id,
        )
        if status:
            q = q.filter(PEDiligenceRoom.status == status)
        return q.order_by(PEDiligenceRoom.created_at.desc()).offset(offset).limit(limit).all()

    def get_room(self, *, room_id: str, org_id: str, user_id: str) -> Optional[PEDiligenceRoom]:
        return self.db.query(PEDiligenceRoom).filter(
            PEDiligenceRoom.id == room_id,
            PEDiligenceRoom.org_id == org_id,
            PEDiligenceRoom.user_id == user_id,
        ).first()

    def get_room_counts(self, *, room_id: str) -> Tuple[int, int, float]:
        docs_count = self.db.query(func.count(PEDiligenceRoomDocument.id)).filter(
            PEDiligenceRoomDocument.room_id == room_id
        ).scalar() or 0

        open_flags = self.db.query(func.count(PEDiligenceFinding.id)).filter(
            PEDiligenceFinding.room_id == room_id,
            PEDiligenceFinding.status.in_(["open", "acknowledged"]),
        ).scalar() or 0

        total_items = self.db.query(func.count(PEDiligenceChecklistItem.id)).filter(
            PEDiligenceChecklistItem.room_id == room_id
        ).scalar() or 0
        covered_items = self.db.query(func.count(PEDiligenceChecklistItem.id)).filter(
            PEDiligenceChecklistItem.room_id == room_id,
            PEDiligenceChecklistItem.status.in_(["covered", "partial"]),
        ).scalar() or 0

        completion = 0.0 if total_items == 0 else round(float(covered_items) * 100.0 / float(total_items), 2)
        return int(docs_count), int(open_flags), completion

    def list_documents_in_room(self, *, room_id: str) -> List[PEDiligenceRoomDocument]:
        return self.db.query(PEDiligenceRoomDocument).filter(
            PEDiligenceRoomDocument.room_id == room_id
        ).order_by(PEDiligenceRoomDocument.created_at.asc()).all()

    def remove_document_from_room(self, *, room_id: str, room_document_id: str) -> bool:
        row = self.db.query(PEDiligenceRoomDocument).filter(
            PEDiligenceRoomDocument.id == room_document_id,
            PEDiligenceRoomDocument.room_id == room_id,
        ).first()
        if not row:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    def get_room_document(
        self, *, room_id: str, room_document_id: str
    ) -> Optional[PEDiligenceRoomDocument]:
        return self.db.query(PEDiligenceRoomDocument).filter(
            PEDiligenceRoomDocument.id == room_document_id,
            PEDiligenceRoomDocument.room_id == room_id,
        ).first()

    def attach_documents_to_room(
        self,
        *,
        room_id: str,
        org_id: str,
        document_ids: Sequence[str],
    ) -> List[PEDiligenceRoomDocument]:
        documents = self.db.query(Document).filter(
            Document.id.in_(list(document_ids)),
            Document.org_id == org_id,
        ).all()
        found_ids = {d.id for d in documents}

        results = []
        for doc_id in document_ids:
            if doc_id not in found_ids:
                continue
            link = self.db.query(PEDiligenceRoomDocument).filter(
                PEDiligenceRoomDocument.room_id == room_id,
                PEDiligenceRoomDocument.document_id == doc_id,
            ).first()
            if not link:
                link = PEDiligenceRoomDocument(
                    room_id=room_id,
                    document_id=doc_id,
                    ingest_status="linked",
                )
                self.db.add(link)
            results.append(link)

        self.db.commit()
        for row in results:
            self.db.refresh(row)
        return results


    def update_room_document_metadata(
        self,
        *,
        room_id: str,
        document_id: str,
        ingest_status: Optional[str] = None,
        metadata_patch: Optional[dict] = None,
    ) -> Optional[PEDiligenceRoomDocument]:
        row = self.db.query(PEDiligenceRoomDocument).filter(
            PEDiligenceRoomDocument.room_id == room_id,
            PEDiligenceRoomDocument.document_id == document_id,
        ).first()
        if not row:
            return None

        if ingest_status is not None:
            row.ingest_status = ingest_status

        if metadata_patch:
            existing = row.metadata_json or {}
            merged = {**existing, **metadata_patch}
            row.metadata_json = merged

        self.db.commit()
        self.db.refresh(row)
        return row
    def create_analysis_run(self, *, room_id: str, org_id: str, user_id: str, metadata: Optional[dict] = None) -> PEDiligenceAnalysisRun:
        run = PEDiligenceAnalysisRun(
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

    def get_analysis_run(self, *, room_id: str, run_id: str, org_id: str, user_id: str) -> Optional[PEDiligenceAnalysisRun]:
        return self.db.query(PEDiligenceAnalysisRun).filter(
            PEDiligenceAnalysisRun.id == run_id,
            PEDiligenceAnalysisRun.room_id == room_id,
            PEDiligenceAnalysisRun.org_id == org_id,
            PEDiligenceAnalysisRun.user_id == user_id,
        ).first()

    def update_analysis_run(
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
    ) -> Optional[PEDiligenceAnalysisRun]:
        run = self.db.query(PEDiligenceAnalysisRun).filter(PEDiligenceAnalysisRun.id == run_id).first()
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

    def get_run_verification_stats(self, *, room_id: str, run_id: str) -> Dict[str, int]:
        rows = self.db.query(PEDiligenceFinding.metadata_json).filter(
            PEDiligenceFinding.room_id == room_id,
            PEDiligenceFinding.analysis_run_id == run_id,
        ).all()

        verified = 0
        needs_review = 0
        for (metadata_json,) in rows:
            metadata = metadata_json or {}
            verification = metadata.get("verification") if isinstance(metadata, dict) else {}
            status = verification.get("status") if isinstance(verification, dict) else None
            if status == "verified":
                verified += 1
            else:
                needs_review += 1

        total = len(rows)
        return {
            "total": total,
            "verified": verified,
            "needs_review": needs_review,
        }

    def list_checklist_items(self, *, room_id: str) -> List[PEDiligenceChecklistItem]:
        return self.db.query(PEDiligenceChecklistItem).filter(
            PEDiligenceChecklistItem.room_id == room_id
        ).order_by(PEDiligenceChecklistItem.priority.asc(), PEDiligenceChecklistItem.title.asc()).all()

    def replace_checklist_items(self, *, room_id: str, items: Sequence[dict]) -> List[PEDiligenceChecklistItem]:
        self.db.query(PEDiligenceChecklistItem).filter(
            PEDiligenceChecklistItem.room_id == room_id
        ).delete()
        created: List[PEDiligenceChecklistItem] = []
        for item in items:
            row = PEDiligenceChecklistItem(room_id=room_id, **item)
            self.db.add(row)
            created.append(row)
        self.db.commit()
        for row in created:
            self.db.refresh(row)
        return created

    def list_findings(
        self,
        *,
        room_id: str,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[PEDiligenceFinding]:
        q = self.db.query(PEDiligenceFinding).filter(PEDiligenceFinding.room_id == room_id)
        if status:
            q = q.filter(PEDiligenceFinding.status == status)
        if severity:
            q = q.filter(PEDiligenceFinding.severity == severity)
        if category:
            q = q.filter(PEDiligenceFinding.category == category)
        return q.order_by(PEDiligenceFinding.created_at.desc()).all()

    def replace_findings(self, *, room_id: str, run_id: str, findings: Sequence[dict]) -> List[PEDiligenceFinding]:
        self.db.query(PEDiligenceFinding).filter(
            PEDiligenceFinding.room_id == room_id
        ).delete()
        created: List[PEDiligenceFinding] = []
        for row in findings:
            finding = PEDiligenceFinding(room_id=room_id, analysis_run_id=run_id, **row)
            self.db.add(finding)
            created.append(finding)
        self.db.commit()
        for row in created:
            self.db.refresh(row)
        return created

    def update_finding(
        self,
        *,
        room_id: str,
        finding_id: str,
        status: str,
        resolution_note: Optional[str],
        actor_user_id: str,
    ) -> Optional[PEDiligenceFinding]:
        finding = self.db.query(PEDiligenceFinding).filter(
            PEDiligenceFinding.id == finding_id,
            PEDiligenceFinding.room_id == room_id,
        ).first()
        if not finding:
            return None
        finding.status = status
        finding.resolution_note = resolution_note
        finding.resolved_by_user_id = actor_user_id if status in {"resolved", "dismissed"} else None
        finding.resolved_at = datetime.utcnow() if status in {"resolved", "dismissed"} else None
        self.db.commit()
        self.db.refresh(finding)
        return finding

    def upsert_summary(
        self,
        *,
        room_id: str,
        run_id: Optional[str],
        summary_type: str,
        status: str,
        content_markdown: Optional[str],
        citations: Optional[list],
        confidence: Optional[float],
        metadata: Optional[dict] = None,
        actor_user_id: Optional[str] = None,
    ) -> PEDiligenceSummary:
        summary = self.db.query(PEDiligenceSummary).filter(
            PEDiligenceSummary.room_id == room_id,
            PEDiligenceSummary.summary_type == summary_type,
        ).first()
        if not summary:
            summary = PEDiligenceSummary(room_id=room_id, summary_type=summary_type)
            self.db.add(summary)

        summary.analysis_run_id = run_id
        summary.status = status
        summary.content_markdown = content_markdown
        summary.citations = citations
        summary.confidence = confidence
        summary.metadata_json = metadata or {}
        if actor_user_id:
            summary.created_by_user_id = actor_user_id
        self.db.commit()
        self.db.refresh(summary)
        return summary

    def get_summary(self, *, room_id: str, summary_type: str = "diligence_overview") -> Optional[PEDiligenceSummary]:
        return self.db.query(PEDiligenceSummary).filter(
            PEDiligenceSummary.room_id == room_id,
            PEDiligenceSummary.summary_type == summary_type,
        ).first()

    def replace_evidence_spans(
        self,
        *,
        room_id: str,
        run_id: Optional[str],
        spans: Sequence[dict],
    ) -> List[PEDiligenceEvidenceSpan]:
        q = self.db.query(PEDiligenceEvidenceSpan).filter(
            PEDiligenceEvidenceSpan.room_id == room_id
        )
        if run_id:
            q = q.filter(PEDiligenceEvidenceSpan.analysis_run_id == run_id)
        q.delete()

        created: List[PEDiligenceEvidenceSpan] = []
        for span in spans:
            row = PEDiligenceEvidenceSpan(
                room_id=room_id,
                analysis_run_id=run_id,
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

    def add_audit_event(
        self,
        *,
        room_id: str,
        event_type: str,
        actor_user_id: Optional[str] = None,
        analysis_run_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        payload: Optional[dict] = None,
    ) -> PEDiligenceAuditEvent:
        event = PEDiligenceAuditEvent(
            room_id=room_id,
            analysis_run_id=analysis_run_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload or {},
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def list_audit_events(self, *, room_id: str, limit: int, offset: int) -> List[PEDiligenceAuditEvent]:
        return self.db.query(PEDiligenceAuditEvent).filter(
            PEDiligenceAuditEvent.room_id == room_id
        ).order_by(PEDiligenceAuditEvent.created_at.desc()).offset(offset).limit(limit).all()


    def get_room_documents_and_chunks(self, *, room_id: str) -> List[tuple]:
        return self.db.query(
            PEDiligenceRoomDocument.document_id,
            Document.filename,
            DocumentChunk.id,
            DocumentChunk.chunk_index,
            DocumentChunk.page_number,
            DocumentChunk.section_type,
            DocumentChunk.chunk_metadata,
            DocumentChunk.text,
        ).join(
            Document,
            PEDiligenceRoomDocument.document_id == Document.id,
        ).outerjoin(
            DocumentChunk,
            DocumentChunk.document_id == Document.id,
        ).filter(
            PEDiligenceRoomDocument.room_id == room_id,
            PEDiligenceRoomDocument.document_id.isnot(None),
        ).all()

    def mark_room_status(self, *, room_id: str, status: str, last_analyzed_at: Optional[datetime] = None) -> None:
        room = self.db.query(PEDiligenceRoom).filter(PEDiligenceRoom.id == room_id).first()
        if not room:
            return
        room.status = status
        if last_analyzed_at is not None:
            room.last_analyzed_at = last_analyzed_at
        self.db.commit()

    # ─── Clauses ──────────────────────────────────────────────────────────────

    def save_clauses(self, *, room_id: str, run_id: str, clauses: List[dict]) -> List[PEDiligenceClause]:
        """Replace clauses for this run and persist new ones."""
        self.db.query(PEDiligenceClause).filter(
            PEDiligenceClause.room_id == room_id,
            PEDiligenceClause.analysis_run_id == run_id,
        ).delete()

        created: List[PEDiligenceClause] = []
        for c in clauses:
            row = PEDiligenceClause(
                room_id=room_id,
                analysis_run_id=run_id,
                source_document_id=c.get("source_document_id"),
                source_chunk_id=c.get("source_chunk_id"),
                source_page_number=c.get("source_page_number"),
                clause_type=c.get("clause_type", ""),
                playbook_id=c.get("playbook_id"),
                extracted_fields=c.get("extracted_fields") or {},
                raw_quote=c.get("raw_quote"),
                interpretation=c.get("interpretation"),
                confidence=c.get("confidence"),
                engine=c.get("engine", "llm_v1"),
                metadata_json=c.get("metadata_json"),
            )
            self.db.add(row)
            created.append(row)

        self.db.commit()
        for row in created:
            self.db.refresh(row)
        return created

    def list_clauses(
        self,
        *,
        room_id: str,
        document_id: Optional[str] = None,
        clause_type: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[PEDiligenceClause]:
        q = self.db.query(PEDiligenceClause).filter(PEDiligenceClause.room_id == room_id)
        if document_id:
            q = q.filter(PEDiligenceClause.source_document_id == document_id)
        if clause_type:
            q = q.filter(PEDiligenceClause.clause_type == clause_type)
        return q.order_by(PEDiligenceClause.created_at.desc()).offset(offset).limit(limit).all()

    # ─── Contract Families ────────────────────────────────────────────────────

    def list_contract_families(self, *, room_id: str) -> List[PEDiligenceContractFamily]:
        return self.db.query(PEDiligenceContractFamily).filter(
            PEDiligenceContractFamily.room_id == room_id
        ).order_by(PEDiligenceContractFamily.created_at.asc()).all()

    # ─── Playbooks ────────────────────────────────────────────────────────────

    def list_playbooks(self, *, is_system: Optional[bool] = None) -> List[PEDiligencePlaybook]:
        q = self.db.query(PEDiligencePlaybook)
        if is_system is not None:
            q = q.filter(PEDiligencePlaybook.is_system == is_system)
        return q.order_by(PEDiligencePlaybook.slug.asc()).all()

    def get_playbooks_for_extraction(self) -> List[dict]:
        """Return all system playbooks as dicts for the clause extractor."""
        rows = self.list_playbooks(is_system=True)
        return [
            {
                "slug": r.slug,
                "title": r.title,
                "clause_types": r.clause_types or [],
                "prompt_template": r.prompt_template,
                "output_schema": r.output_schema,
            }
            for r in rows
        ]


