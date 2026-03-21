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

    def start_analysis(
        self,
        *,
        room_id: str,
        org_id: str,
        user_id: str,
        force_reanalyze: bool,
        incremental: bool = False,
    ) -> PEDiligenceAnalysisRun:
        import uuid
        from app.repositories.job_repository import JobRepository

        # Delta detection for incremental mode
        incremental_payload = {}
        if incremental and not force_reanalyze:
            last_run = self.repo.get_latest_completed_run(room_id=room_id)
            if last_run:
                prev_doc_ids = set(
                    (last_run.metadata_json or {}).get("document_classification", {}).keys()
                )
                current_doc_ids = set(self.repo.get_room_document_ids(room_id=room_id))
                added = list(current_doc_ids - prev_doc_ids)
                removed = list(prev_doc_ids - current_doc_ids)
                if not added and not removed:
                    # Nothing changed — return existing run
                    return last_run
                incremental_payload = {
                    "incremental": True,
                    "added_doc_ids": added,
                    "removed_doc_ids": removed,
                    "previous_run_id": last_run.id,
                }

        # Create analysis run
        run = self.repo.create_analysis_run(
            room_id=room_id,
            org_id=org_id,
            user_id=user_id,
            metadata={"force_reanalyze": force_reanalyze, **incremental_payload},
        )

        # Create JobState for SSE real-time progress
        job_id = str(uuid.uuid4())
        job_repo = JobRepository()
        job = job_repo.create_job(
            entity_type="analysis_run",
            entity_id=run.id,
            status="running",
            current_stage="initialization",
            message="Starting analysis...",
            job_id=job_id,
        )

        # Store job_id on analysis run
        if job:
            self.repo.update_analysis_run(run_id=run.id, job_id=job_id)

        self.repo.mark_room_status(room_id=room_id, status="analyzing")
        self.repo.add_audit_event(
            room_id=room_id,
            analysis_run_id=run.id,
            actor_user_id=user_id,
            event_type="analysis.started",
            entity_type="analysis_run",
            entity_id=run.id,
            payload={"force_reanalyze": force_reanalyze, "job_id": job_id, **incremental_payload},
        )

        payload = {
            "room_id": room_id,
            "analysis_run_id": run.id,
            "job_id": job_id,
            "org_id": org_id,
            "user_id": user_id,
            "force_reanalyze": force_reanalyze,
            **incremental_payload,
        }
        run_diligence_analysis_task.apply_async(args=[payload], queue="critical")
        return run

