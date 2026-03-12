"""Service layer for PE diligence."""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.db_models_pe_diligence import PEDiligenceAnalysisRun
from app.verticals.private_equity.diligence.repository import PEDiligenceRepository
from app.verticals.private_equity.diligence.tasks import run_diligence_analysis_task


class PEDiligenceService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = PEDiligenceRepository(db)

    def create_room(self, *, org_id: str, user_id: str, name: str, target_company: Optional[str], notes: Optional[str]):
        room = self.repo.create_room(
            org_id=org_id,
            user_id=user_id,
            name=name,
            target_company=target_company,
            notes=notes,
        )
        self.repo.add_audit_event(
            room_id=room.id,
            event_type="room.created",
            actor_user_id=user_id,
            entity_type="room",
            entity_id=room.id,
        )
        return room

    def attach_documents(self, *, room_id: str, org_id: str, user_id: str, document_ids: List[str]):
        links = self.repo.attach_documents_to_room(
            room_id=room_id,
            org_id=org_id,
            document_ids=document_ids,
        )
        self.repo.add_audit_event(
            room_id=room_id,
            event_type="room.documents.attached",
            actor_user_id=user_id,
            entity_type="room_documents",
            payload={"document_ids": [row.document_id for row in links if row.document_id]},
        )
        return links

    def start_analysis(self, *, room_id: str, org_id: str, user_id: str, force_reanalyze: bool) -> PEDiligenceAnalysisRun:
        run = self.repo.create_analysis_run(
            room_id=room_id,
            org_id=org_id,
            user_id=user_id,
            metadata={"force_reanalyze": force_reanalyze},
        )
        self.repo.mark_room_status(room_id=room_id, status="analyzing")
        self.repo.add_audit_event(
            room_id=room_id,
            analysis_run_id=run.id,
            actor_user_id=user_id,
            event_type="analysis.started",
            entity_type="analysis_run",
            entity_id=run.id,
            payload={"force_reanalyze": force_reanalyze},
        )

        payload = {
            "room_id": room_id,
            "analysis_run_id": run.id,
            "org_id": org_id,
            "user_id": user_id,
            "force_reanalyze": force_reanalyze,
        }
        run_diligence_analysis_task.apply_async(args=[payload], queue="critical")
        return run

