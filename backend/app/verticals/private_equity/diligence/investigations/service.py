"""Service layer for PE diligence investigations."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.repositories.document_repository import DocumentRepository
from app.verticals.private_equity.diligence.investigations.repository import (
    PEDiligenceInvestigationRepository,
)
from app.verticals.private_equity.diligence.investigations.retriever import (
    search_evidence_chunks,
    to_evidence_search_rows,
)
from app.verticals.private_equity.diligence.investigations.tasks import (
    run_diligence_investigation_task,
)
from app.verticals.private_equity.diligence.investigations.templates import get_template


class PEDiligenceInvestigationService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = PEDiligenceInvestigationRepository(db)
        self.doc_repo = DocumentRepository()

    def create_investigation(
        self,
        *,
        room_id: str,
        org_id: str,
        user_id: str,
        investigation_type: str,
        title: Optional[str],
        question: Optional[str],
    ) -> Tuple[object, object, bool]:
        room = self.repo.get_room(room_id=room_id, org_id=org_id, user_id=user_id)
        if not room:
            raise ValueError("Diligence room not found")

        template = get_template(investigation_type)
        effective_title = (title or template.get("title") or investigation_type).strip()
        effective_question = (question or template.get("default_question") or "").strip() or None

        investigation = self.repo.create_investigation(
            room_id=room_id,
            org_id=org_id,
            user_id=user_id,
            investigation_type=investigation_type,
            title=effective_title,
            question=effective_question,
            metadata={
                "template_type": investigation_type,
                "created_via": "api",
            },
        )

        run = self.repo.create_run(
            investigation_id=investigation.id,
            room_id=room_id,
            org_id=org_id,
            user_id=user_id,
            metadata={
                "trigger": "create",
            },
        )

        self.repo.add_audit_event(
            room_id=room_id,
            actor_user_id=user_id,
            event_type="investigation.created",
            entity_type="investigation",
            entity_id=investigation.id,
            payload={
                "investigation_type": investigation_type,
                "run_id": run.id,
            },
        )

        payload = {
            "room_id": room_id,
            "investigation_id": investigation.id,
            "run_id": run.id,
            "org_id": org_id,
            "user_id": user_id,
        }
        run_diligence_investigation_task.apply_async(args=[payload], queue="critical")
        return investigation, run, False

    def rerun_investigation(
        self,
        *,
        room_id: str,
        investigation_id: str,
        org_id: str,
        user_id: str,
    ) -> Tuple[object, object, bool]:
        investigation = self.repo.get_investigation(
            investigation_id=investigation_id,
            room_id=room_id,
            org_id=org_id,
            user_id=user_id,
        )
        if not investigation:
            raise ValueError("Investigation not found")

        active_run = self.repo.get_active_run(investigation_id=investigation_id)
        if active_run:
            return investigation, active_run, True

        self.repo.update_investigation(
            investigation_id=investigation_id,
            status="queued",
            metadata_patch={"rerun_requested": True},
        )
        investigation = self.repo.get_investigation(
            investigation_id=investigation_id,
            room_id=room_id,
            org_id=org_id,
            user_id=user_id,
        )

        run = self.repo.create_run(
            investigation_id=investigation_id,
            room_id=room_id,
            org_id=org_id,
            user_id=user_id,
            metadata={
                "trigger": "rerun",
            },
        )

        self.repo.add_audit_event(
            room_id=room_id,
            actor_user_id=user_id,
            event_type="investigation.rerun_requested",
            entity_type="investigation",
            entity_id=investigation_id,
            payload={"run_id": run.id},
        )

        payload = {
            "room_id": room_id,
            "investigation_id": investigation_id,
            "run_id": run.id,
            "org_id": org_id,
            "user_id": user_id,
        }
        run_diligence_investigation_task.apply_async(args=[payload], queue="critical")
        return investigation, run, False

    def list_investigations(self, *, room_id: str, org_id: str, user_id: str) -> List[object]:
        room = self.repo.get_room(room_id=room_id, org_id=org_id, user_id=user_id)
        if not room:
            raise ValueError("Diligence room not found")
        return self.repo.list_investigations(room_id=room_id)

    def get_investigation_detail(
        self,
        *,
        room_id: str,
        investigation_id: str,
        org_id: str,
        user_id: str,
    ) -> Tuple[object, List[object], List[object], Optional[object], List[object]]:
        investigation = self.repo.get_investigation(
            investigation_id=investigation_id,
            room_id=room_id,
            org_id=org_id,
            user_id=user_id,
        )
        if not investigation:
            raise ValueError("Investigation not found")

        claims = self.repo.list_claims(investigation_id=investigation_id)
        claim_ids = [row.id for row in claims]
        claim_spans = self.repo.get_evidence_for_entities(
            room_id=room_id,
            entity_type="investigation_claim",
            entity_ids=claim_ids,
        )
        conclusion_spans = self.repo.get_evidence_for_entities(
            room_id=room_id,
            entity_type="investigation_conclusion",
            entity_ids=[investigation_id],
        )
        latest_run = self.repo.get_latest_run(investigation_id=investigation_id)
        return investigation, claims, claim_spans, latest_run, conclusion_spans

    def override_claim(
        self,
        *,
        room_id: str,
        investigation_id: str,
        claim_id: str,
        verification_status: str,
        override_reason: Optional[str],
        reviewer_notes: Optional[str],
        actor_user_id: str,
        org_id: str,
        user_id: str,
    ) -> object:
        investigation = self.repo.get_investigation(
            investigation_id=investigation_id,
            room_id=room_id,
            org_id=org_id,
            user_id=user_id,
        )
        if not investigation:
            raise ValueError("Investigation not found")

        try:
            claim = self.repo.override_claim(
                claim_id=claim_id,
                investigation_id=investigation_id,
                verification_status=verification_status,
                override_reason=override_reason,
                reviewer_notes=reviewer_notes,
                actor_user_id=actor_user_id,
            )
        except ValueError:
            raise

        if claim is None:
            raise ValueError("Claim not found")

        return claim

    def search_evidence(
        self,
        *,
        room_id: str,
        org_id: str,
        user_id: str,
        query: str,
        document_ids: Optional[List[str]],
        top_k: int,
    ) -> List[Dict]:
        room = self.repo.get_room(room_id=room_id, org_id=org_id, user_id=user_id)
        if not room:
            raise ValueError("Diligence room not found")

        room_docs = self.repo.list_room_documents(room_id=room_id)
        room_doc_ids = [row.document_id for row in room_docs if row.document_id]
        if not room_doc_ids:
            return []

        if document_ids:
            allowed_ids = set(room_doc_ids)
            candidate_doc_ids = [doc_id for doc_id in document_ids if doc_id in allowed_ids]
        else:
            candidate_doc_ids = room_doc_ids

        if not candidate_doc_ids:
            return []

        chunks = search_evidence_chunks(
            db=self.db,
            queries=[query],
            document_ids=candidate_doc_ids,
            top_k_per_query=max(20, top_k),
            max_results=max(40, top_k),
        )
        return to_evidence_search_rows(chunks, top_k=top_k)
