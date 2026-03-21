"""Private Equity Diligence API."""
from collections import defaultdict
import hashlib
import os
import shutil
import uuid
from io import BytesIO
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.db_models import JobState
from app.db_models_users import User
from app.repositories.document_repository import DocumentRepository
from app.repositories.job_repository import JobRepository
from app.services.beta_limits import enforce_page_limit
from app.services.tasks import start_document_indexing_chain
from app.utils.document_uploads import SUPPORTED_UPLOAD_EXTENSIONS, validate_uploaded_file_signature
from app.utils.logging import logger
from app.verticals.private_equity.diligence.repository import PEDiligenceRepository
from app.verticals.private_equity.diligence.schemas import (
    AnalysisRunOut,
    AttachRoomDocumentsRequest,
    AuditEventOut,
    ChecklistItemOut,
    ClauseOut,
    ClauseReviewIn,
    ContractFamilyOut,
    DiligenceRoomCreateRequest,
    DiligenceRoomOut,
    EvidenceSpanOut,
    FindingOut,
    GenerateICMemoResponse,
    PlaybookOut,
    RoomDocumentOut,
    StartAnalysisRequest,
    SummaryOut,
    UploadRoomDocumentOut,
    UpdateAmendmentLinkRequest,
    UpdateFindingRequest,
    UpdateFolderRequest,
)
from app.verticals.private_equity.diligence.service import PEDiligenceService


router = APIRouter(prefix="/diligence", tags=["pe_diligence"])

MAX_FILE_SIZE_MB = 50
MAX_FILENAME_LENGTH = 255
ALLOWED_EXTENSIONS = SUPPORTED_UPLOAD_EXTENSIONS


def _build_evidence_map(spans) -> dict:
    out = defaultdict(list)
    for span in spans:
        out[span.entity_id].append(
            EvidenceSpanOut.model_validate(
                {
                    **span.__dict__,
                    "metadata": span.metadata_json,
                }
            )
        )
    return out


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _extract_document_classification_fields(metadata: Optional[dict]) -> dict:
    meta = metadata if isinstance(metadata, dict) else {}
    classification = meta.get("document_classification")
    classification = classification if isinstance(classification, dict) else {}

    confidence = classification.get("confidence")
    try:
        confidence = float(confidence) if confidence is not None else None
    except Exception:
        confidence = None

    signals = classification.get("signals")
    if not isinstance(signals, list):
        signals = []
    signals = [str(s) for s in signals if s is not None][:12]

    needs_review = classification.get("needs_review")
    if not isinstance(needs_review, bool):
        needs_review = None

    return {
        "document_type": classification.get("document_type"),
        "classification_confidence": confidence,
        "classification_needs_review": needs_review,
        "classification_signals": signals,
    }


def _summarize_document_classification_for_room(repo: PEDiligenceRepository, room_id: str) -> Dict[str, int]:
    rows = repo.list_documents_in_room(room_id=room_id)
    doc_type_counts: Dict[str, int] = {}
    needs_review = 0
    total = 0
    for row in rows:
        fields = _extract_document_classification_fields(row.metadata_json)
        doc_type = fields["document_type"]
        if not doc_type:
            continue
        total += 1
        doc_type_counts[doc_type] = doc_type_counts.get(doc_type, 0) + 1
        if fields["classification_needs_review"] is True:
            needs_review += 1

    return {
        "total": total,
        "needs_review": needs_review,
        "document_type_counts": doc_type_counts,
    }


def _build_analysis_run_out(repo: PEDiligenceRepository, run) -> AnalysisRunOut:
    metadata = run.metadata_json if isinstance(run.metadata_json, dict) else {}

    verification = metadata.get("verification")
    if isinstance(verification, dict):
        verification_stats = {
            "total": _safe_int(verification.get("total")),
            "verified": _safe_int(verification.get("verified")),
            "needs_review": _safe_int(verification.get("needs_review")),
        }
    elif run.status in {"completed", "failed"}:
        verification_stats = repo.get_run_verification_stats(room_id=run.room_id, run_id=run.id)
    else:
        verification_stats = {"total": 0, "verified": 0, "needs_review": 0}

    classification_summary = metadata.get("document_classification_summary")
    if isinstance(classification_summary, dict):
        doc_type_counts = classification_summary.get("document_type_counts")
        doc_type_counts = doc_type_counts if isinstance(doc_type_counts, dict) else {}
        class_stats = {
            "total": _safe_int(classification_summary.get("total")),
            "needs_review": _safe_int(classification_summary.get("needs_review")),
            "document_type_counts": {str(k): _safe_int(v) for k, v in doc_type_counts.items()},
        }
    elif run.status in {"completed", "failed"}:
        class_stats = _summarize_document_classification_for_room(repo, run.room_id)
    else:
        class_stats = {"total": 0, "needs_review": 0, "document_type_counts": {}}

    return AnalysisRunOut.model_validate(
        {
            **run.__dict__,
            "verification_total": verification_stats.get("total", 0),
            "verification_verified": verification_stats.get("verified", 0),
            "verification_needs_review": verification_stats.get("needs_review", 0),
            "document_classification_total": class_stats.get("total", 0),
            "document_classification_needs_review": class_stats.get("needs_review", 0),
            "document_type_counts": class_stats.get("document_type_counts", {}),
            "metadata": metadata,
        }
    )


def _link_document_to_room(
    *,
    db: Session,
    room_id: str,
    org_id: str,
    user_id: str,
    document_id: str,
    folder: Optional[str] = None,
):
    service = PEDiligenceService(db)
    rows = service.attach_documents(
        room_id=room_id,
        org_id=org_id,
        user_id=user_id,
        document_ids=[document_id],
    )
    link = rows[0] if rows else None
    if link and folder:
        link.folder = folder
        db.commit()
    return link


@router.post("/rooms", response_model=DiligenceRoomOut)
def create_room(
    payload: DiligenceRoomCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = PEDiligenceService(db)
    repo = PEDiligenceRepository(db)
    room = service.create_room(
        org_id=user.org_id,
        user_id=user.id,
        name=payload.name,
        target_company=payload.target_company,
        notes=payload.notes,
    )
    docs_count, open_flags, completion = repo.get_room_counts(room_id=room.id)
    return DiligenceRoomOut.model_validate(
        {
            **room.__dict__,
            "documents_count": docs_count,
            "open_flags_count": open_flags,
            "checklist_completion_pct": completion,
        }
    )


@router.get("/rooms", response_model=List[DiligenceRoomOut])
def list_rooms(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = PEDiligenceRepository(db)
    rooms = repo.list_rooms(
        org_id=user.org_id,
        user_id=user.id,
        limit=limit,
        offset=offset,
        status=status,
    )
    results = []
    for room in rooms:
        docs_count, open_flags, completion = repo.get_room_counts(room_id=room.id)
        results.append(
            DiligenceRoomOut.model_validate(
                {
                    **room.__dict__,
                    "documents_count": docs_count,
                    "open_flags_count": open_flags,
                    "checklist_completion_pct": completion,
                }
            )
        )
    return results


@router.get("/rooms/{room_id}", response_model=DiligenceRoomOut)
def get_room(
    room_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")
    docs_count, open_flags, completion = repo.get_room_counts(room_id=room.id)
    return DiligenceRoomOut.model_validate(
        {
            **room.__dict__,
            "documents_count": docs_count,
            "open_flags_count": open_flags,
            "checklist_completion_pct": completion,
        }
    )


@router.post("/rooms/{room_id}/documents", response_model=List[RoomDocumentOut])
def attach_room_documents(
    room_id: str,
    payload: AttachRoomDocumentsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")

    service = PEDiligenceService(db)
    rows = service.attach_documents(
        room_id=room_id,
        org_id=user.org_id,
        user_id=user.id,
        document_ids=payload.document_ids,
    )
    return [
        RoomDocumentOut.model_validate(
            {
                **row.__dict__,
                **_extract_document_classification_fields(row.metadata_json),
                "metadata": row.metadata_json,
            }
        )
        for row in rows
    ]


@router.post("/rooms/{room_id}/documents/upload", response_model=UploadRoomDocumentOut)
async def upload_room_document(
    room_id: str,
    file: UploadFile = File(...),
    folder: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    if len(file.filename) > MAX_FILENAME_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Filename too long (max {MAX_FILENAME_LENGTH} characters)",
        )

    safe_filename = os.path.basename(file.filename)
    file_ext = os.path.splitext(safe_filename.lower())[1]
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file_ext}' not supported. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    try:
        file_bytes = await file.read()
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to read uploaded file")

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    file_size_mb = len(file_bytes) / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({file_size_mb:.1f}MB). Maximum size is {MAX_FILE_SIZE_MB}MB",
        )

    validation_error = validate_uploaded_file_signature(file_ext, file_bytes)
    if validation_error:
        raise HTTPException(status_code=400, detail=validation_error)

    content_hash = hashlib.sha256(file_bytes).hexdigest()
    doc_repo = DocumentRepository()
    job_repo = JobRepository()
    existing_doc = doc_repo.get_by_hash(content_hash, user.org_id)

    if existing_doc and existing_doc.is_ready():
        link = _link_document_to_room(
            db=db,
            room_id=room_id,
            org_id=user.org_id,
            user_id=user.id,
            document_id=existing_doc.id,
            folder=folder,
        )
        classification_fields = _extract_document_classification_fields(link.metadata_json if link else None)
        existing_job = job_repo.get_job_by_document_id(existing_doc.id)
        return UploadRoomDocumentOut.model_validate(
            {
                "document_id": existing_doc.id,
                "room_document_id": link.id if link else None,
                "job_id": existing_job.job_id if existing_job else None,
                "filename": safe_filename,
                "status": "completed",
                "reuse": True,
                "attached": True,
                "message": "Reused existing indexed document and attached it to diligence room.",
                "ingest_status": link.ingest_status if link else None,
                **classification_fields,
            }
        )

    if file_ext == ".pdf" and not existing_doc:
        estimated_pages = 0
        try:
            from PyPDF2 import PdfReader

            estimated_pages = len(PdfReader(BytesIO(file_bytes)).pages)
        except Exception as e:
            logger.warning(
                "Failed to estimate PDF page count before diligence upload; deferring to pipeline check",
                extra={"filename": safe_filename, "error": str(e)},
            )
        if estimated_pages > 0:
            enforce_page_limit(user, pages_to_add=estimated_pages)

    temp_id = str(uuid.uuid4())
    temp_path = os.path.join("/tmp", f"upload_{temp_id}_{safe_filename}")
    created_new_document = False
    document = existing_doc
    file_path = None

    try:
        with open(temp_path, "wb") as f:
            f.write(file_bytes)

        if document is None:
            document = doc_repo.create_document(
                org_id=user.org_id,
                user_id=user.id,
                filename=safe_filename,
                file_path="",
                file_size_bytes=len(file_bytes),
                content_hash=content_hash,
                page_count=0,
                status="processing",
            )
            if not document:
                raise HTTPException(status_code=500, detail="Failed to create document record")
            created_new_document = True

        if not created_new_document and document.status == "processing":
            # Only skip re-indexing if a job is genuinely still active.
            # If the job failed or disappeared the document is stuck in "processing"
            # and we must fall through to re-upload and re-trigger the chain.
            processing_job = job_repo.get_job_by_document_id(document.id)
            job_is_active = (
                processing_job is not None
                and processing_job.status not in ("failed", "completed")
            )
            if job_is_active:
                link = _link_document_to_room(
                    db=db,
                    room_id=room_id,
                    org_id=user.org_id,
                    user_id=user.id,
                    document_id=document.id,
                    folder=folder,
                )
                classification_fields = _extract_document_classification_fields(link.metadata_json if link else None)
                return UploadRoomDocumentOut.model_validate(
                    {
                        "document_id": document.id,
                        "room_document_id": link.id if link else None,
                        "job_id": processing_job.job_id,
                        "filename": safe_filename,
                        "status": "processing",
                        "reuse": True,
                        "attached": True,
                        "message": "Document is already processing; attached to diligence room.",
                        "ingest_status": link.ingest_status if link else "linked",
                        **classification_fields,
                    }
                )
            # Job is gone or failed — fall through to re-upload and re-index.

        # Upload fresh source file and (re)index with existing shared pipeline.
        from app.core.storage.storage_factory import get_storage_backend

        storage = get_storage_backend()
        try:
            from datetime import datetime as _dt

            _now = _dt.utcnow()
            storage_key = (
                f"documents/{_now.year}/{_now.month:02d}/{_now.day:02d}"
                f"/{document.id}_{safe_filename}"
            )
            storage.upload(temp_path, storage_key)
            file_path = storage_key
        except Exception:
            # Local fallback mirrors existing document upload behavior.
            upload_dir = os.path.join("uploads", "diligence", room_id)
            os.makedirs(upload_dir, exist_ok=True)
            fallback_path = os.path.join(upload_dir, f"{document.id}_{safe_filename}")
            shutil.move(temp_path, fallback_path)
            file_path = fallback_path

        doc_repo.update_file_path(document.id, file_path)
        doc_repo.update_document(
            document_id=document.id,
            status="processing",
            error_message=None,
        )

        link = _link_document_to_room(
            db=db,
            room_id=room_id,
            org_id=user.org_id,
            user_id=user.id,
            document_id=document.id,
            folder=folder,
        )

        job = job_repo.create_job(
            entity_type="document",
            entity_id=document.id,
            status="queued",
            current_stage="queued",
            progress_percent=0,
            message="Queued for processing...",
        )
        if not job:
            raise HTTPException(status_code=500, detail="Failed to create job tracking record")

        task_id = start_document_indexing_chain(
            file_path=file_path,
            filename=safe_filename,
            job_id=job.job_id,
            document_id=document.id,
            collection_id=None,
            user_id=user.id,
            content_hash=content_hash,
        )

        classification_fields = _extract_document_classification_fields(link.metadata_json if link else None)
        return UploadRoomDocumentOut.model_validate(
            {
                "document_id": document.id,
                "room_document_id": link.id if link else None,
                "job_id": job.job_id,
                "task_id": task_id,
                "filename": safe_filename,
                "status": "processing",
                "reuse": existing_doc is not None,
                "attached": True,
                "message": "Document indexing started and attached to diligence room.",
                "ingest_status": link.ingest_status if link else "linked",
                **classification_fields,
            }
        )

    except HTTPException:
        # Keep existing documents; cleanup only truly new document records.
        if created_new_document and document is not None:
            doc_repo.delete_document(document.id)
        raise
    except Exception as e:
        if created_new_document and document is not None:
            doc_repo.delete_document(document.id)
        logger.error(
            "Diligence room upload failed",
            extra={"room_id": room_id, "filename": safe_filename, "error": str(e)},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


@router.get("/rooms/{room_id}/documents", response_model=List[RoomDocumentOut])
def list_room_documents(
    room_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.db_models_documents import Document  # local import to avoid circular deps
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")
    rows = repo.list_documents_in_room(room_id=room_id)
    # Batch-fetch filenames from the documents table
    doc_ids = [r.document_id for r in rows if r.document_id]
    filename_map: Dict[str, str] = {}
    page_count_map: Dict[str, int] = {}
    job_state_map: Dict[str, JobState] = {}
    if doc_ids:
        docs = db.query(Document.id, Document.filename, Document.page_count).filter(Document.id.in_(doc_ids)).all()
        filename_map = {d.id: d.filename for d in docs}
        page_count_map = {d.id: d.page_count for d in docs if d.page_count}
        jobs = (
            db.query(JobState)
            .filter(
                JobState.entity_type == "document",
                JobState.entity_id.in_(doc_ids),
            )
            .all()
        )
        for job in jobs:
            current = job_state_map.get(job.entity_id)
            if current is None or (job.updated_at or job.created_at) > (current.updated_at or current.created_at):
                job_state_map[job.entity_id] = job
    result = []
    for row in rows:
        job = job_state_map.get(row.document_id) if row.document_id else None
        is_active = job is not None and job.status not in ("completed", "failed")
        result.append(RoomDocumentOut.model_validate({
            **row.__dict__,
            **_extract_document_classification_fields(row.metadata_json),
            "metadata": row.metadata_json,
            "filename": filename_map.get(row.document_id) if row.document_id else None,
            "job_id": job.job_id if job else None,
            "progress_percent": job.progress_percent if is_active else None,
            "status_detail": (job.message or job.current_stage) if is_active else None,
            "page_count": page_count_map.get(row.document_id) if row.document_id else None,
            "ingest_status": "processing" if is_active else row.ingest_status,
        }))
    return result


@router.delete("/rooms/{room_id}/documents/{room_document_id}", status_code=204)
def delete_room_document(
    room_id: str,
    room_document_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")
    removed = repo.remove_document_from_room(
        room_id=room_id,
        room_document_id=room_document_id,
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Document not found in this room")
    repo.add_audit_event(
        room_id=room_id,
        actor_user_id=user.id,
        event_type="document.removed",
        entity_type="room_document",
        entity_id=room_document_id,
        payload={},
    )


@router.patch("/rooms/{room_id}/documents/{room_document_id}/amendment-link")
def update_amendment_link(
    room_id: str,
    room_document_id: str,
    payload: UpdateAmendmentLinkRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update or remove the amendment link for a room document."""
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")

    doc = repo.get_room_document(room_id=room_id, room_document_id=room_document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found in this room")

    if payload.parent_document_id:
        amendment_link = {
            "parent_document_id": payload.parent_document_id,
            "amendment_type": payload.amendment_type or "modifies",
            "confidence": 1.0,  # user-set = full confidence
            "rationale": "Manually set by user",
        }
    else:
        amendment_link = None

    repo.update_room_document_metadata(
        room_document_id=room_document_id,
        metadata_patch={"amendment_link": amendment_link},
    )
    repo.add_audit_event(
        room_id=room_id,
        actor_user_id=user.id,
        event_type="amendment.linked" if amendment_link else "amendment.unlinked",
        entity_type="room_document",
        entity_id=room_document_id,
        payload={"amendment_link": amendment_link},
    )
    return {"ok": True}


@router.patch("/rooms/{room_id}/documents/{room_document_id}/folder")
def update_document_folder(
    room_id: str,
    room_document_id: str,
    payload: UpdateFolderRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the folder label for a room document."""
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")

    doc = repo.get_room_document(room_id=room_id, room_document_id=room_document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found in this room")

    doc.folder = payload.folder
    db.commit()
    db.refresh(doc)

    repo.add_audit_event(
        room_id=room_id,
        actor_user_id=user.id,
        event_type="document.folder_updated",
        entity_type="room_document",
        entity_id=room_document_id,
        payload={"folder": payload.folder},
    )
    return {"ok": True}


@router.get("/rooms/{room_id}/analysis-status")
def get_analysis_status(
    room_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get delta (added/removed docs) since last completed analysis run."""
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")

    last_run = repo.get_latest_completed_run(room_id=room_id)
    if not last_run:
        return {
            "has_completed_run": False,
            "last_run_completed_at": None,
            "added_doc_count": 0,
            "removed_doc_count": 0,
            "has_delta": False,
        }

    prev_doc_ids = set((last_run.metadata_json or {}).get("document_classification", {}).keys())
    current_doc_ids = set(repo.get_room_document_ids(room_id=room_id))
    added = current_doc_ids - prev_doc_ids
    removed = prev_doc_ids - current_doc_ids

    return {
        "has_completed_run": True,
        "last_run_completed_at": last_run.completed_at,
        "added_doc_count": len(added),
        "removed_doc_count": len(removed),
        "has_delta": bool(added or removed),
    }


@router.post("/rooms/{room_id}/analyze", response_model=AnalysisRunOut)
def start_room_analysis(
    room_id: str,
    payload: StartAnalysisRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")

    service = PEDiligenceService(db)
    run = service.start_analysis(
        room_id=room_id,
        org_id=user.org_id,
        user_id=user.id,
        force_reanalyze=payload.force_reanalyze,
        incremental=payload.incremental,
    )
    return _build_analysis_run_out(repo, run)


@router.get("/rooms/{room_id}/analysis-runs/{run_id}", response_model=AnalysisRunOut)
def get_room_analysis_run(
    room_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = PEDiligenceRepository(db)
    run = repo.get_analysis_run(
        room_id=room_id,
        run_id=run_id,
        org_id=user.org_id,
        user_id=user.id,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return _build_analysis_run_out(repo, run)


@router.get("/rooms/{room_id}/active-analysis-run", response_model=Optional[AnalysisRunOut])
def get_active_analysis_run(
    room_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the most recent in-progress analysis run for a room, or null if none active."""
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    run = repo.get_latest_active_analysis_run(room_id=room_id)
    if not run:
        return None
    return _build_analysis_run_out(repo, run)


@router.get("/rooms/{room_id}/checklist", response_model=List[ChecklistItemOut])
def get_room_checklist(
    room_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")
    rows = repo.list_checklist_items(room_id=room_id)
    spans = repo.get_evidence_for_entities(
        room_id=room_id,
        entity_type="checklist_item",
        entity_ids=[row.id for row in rows],
    )
    evidence_map = _build_evidence_map(spans)
    return [
        ChecklistItemOut.model_validate(
            {
                **row.__dict__,
                "metadata": row.metadata_json,
                "evidence_spans": evidence_map.get(row.id, []),
            }
        )
        for row in rows
    ]


@router.get("/rooms/{room_id}/findings", response_model=List[FindingOut])
def get_room_findings(
    room_id: str,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    category: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")
    rows = repo.list_findings(room_id=room_id, status=status, severity=severity, category=category)
    spans = repo.get_evidence_for_entities(
        room_id=room_id,
        entity_type="finding",
        entity_ids=[row.id for row in rows],
    )
    evidence_map = _build_evidence_map(spans)
    return [
        FindingOut.model_validate(
            {
                **row.__dict__,
                "metadata": row.metadata_json,
                "evidence_spans": evidence_map.get(row.id, []),
            }
        )
        for row in rows
    ]


@router.patch("/rooms/{room_id}/findings/{finding_id}", response_model=FindingOut)
def update_room_finding(
    room_id: str,
    finding_id: str,
    payload: UpdateFindingRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")

    row = repo.update_finding(
        room_id=room_id,
        finding_id=finding_id,
        status=payload.status,
        resolution_note=payload.resolution_note,
        actor_user_id=user.id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Finding not found")

    repo.add_audit_event(
        room_id=room_id,
        actor_user_id=user.id,
        event_type="finding.updated",
        entity_type="finding",
        entity_id=finding_id,
        payload={"status": payload.status},
    )
    spans = repo.get_evidence_for_entities(
        room_id=room_id,
        entity_type="finding",
        entity_ids=[row.id],
    )
    evidence_map = _build_evidence_map(spans)
    return FindingOut.model_validate(
        {
            **row.__dict__,
            "metadata": row.metadata_json,
            "evidence_spans": evidence_map.get(row.id, []),
        }
    )


@router.get("/rooms/{room_id}/summary", response_model=SummaryOut)
def get_room_summary(
    room_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")
    summary = repo.get_summary(room_id=room_id, summary_type="diligence_overview")
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    spans = repo.get_evidence_for_entities(
        room_id=room_id,
        entity_type="summary",
        entity_ids=[summary.id],
    )
    evidence_map = _build_evidence_map(spans)
    metadata = summary.metadata_json or {}
    return SummaryOut.model_validate(
        {
            **summary.__dict__,
            "overview": metadata.get("overview"),
            "triage": metadata.get("triage"),
            "coverage": metadata.get("coverage"),
            "top_risks": metadata.get("top_risks") or [],
            "contradictions": metadata.get("contradictions") or [],
            "valuation_signals": metadata.get("valuation_signals") or [],
            "deal_blockers": metadata.get("deal_blockers") or [],
            "management_questions": metadata.get("management_questions") or [],
            "follow_up_requests": metadata.get("follow_up_requests") or [],
            "missing_key_documents": metadata.get("missing_key_documents") or [],
            "document_gap_register": metadata.get("document_gap_register") or [],
            "ic_memo_inputs": metadata.get("ic_memo_inputs"),
            "ic_readiness": metadata.get("ic_readiness"),
            "suggested_investigations": metadata.get("suggested_investigations") or [],
            "data_quality_assessment": metadata.get("data_quality_assessment"),
            "metadata": metadata,
            "evidence_spans": evidence_map.get(summary.id, []),
        }
    )


@router.post("/rooms/{room_id}/summary/regenerate", response_model=AnalysisRunOut)
def regenerate_room_summary(
    room_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = PEDiligenceService(db)
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")
    run = service.start_analysis(room_id=room_id, org_id=user.org_id, user_id=user.id, force_reanalyze=True)
    return _build_analysis_run_out(repo, run)


@router.get("/rooms/{room_id}/audit", response_model=List[AuditEventOut])
def list_room_audit_events(
    room_id: str,
    limit: int = 100,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")
    rows = repo.list_audit_events(room_id=room_id, limit=limit, offset=offset)
    return [AuditEventOut.model_validate(row) for row in rows]


# ─── Clauses ──────────────────────────────────────────────────────────────────

@router.get("/rooms/{room_id}/clauses", response_model=List[ClauseOut])
def list_room_clauses(
    room_id: str,
    document_id: Optional[str] = None,
    clause_type: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List structured clauses extracted for a room, optionally filtered by document or clause type."""
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")
    rows = repo.list_clauses(
        room_id=room_id,
        document_id=document_id,
        clause_type=clause_type,
        limit=limit,
        offset=offset,
    )
    return [
        ClauseOut.model_validate({**row.__dict__, "metadata": row.metadata_json})
        for row in rows
    ]


@router.patch("/rooms/{room_id}/clauses/{clause_id}/review", response_model=ClauseOut)
def review_clause(
    room_id: str,
    clause_id: str,
    payload: ClauseReviewIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set review status on a clause (approve / flag / edit)."""
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")
    clause = repo.review_clause(
        room_id=room_id,
        clause_id=clause_id,
        review_status=payload.status,
        reviewed_by=user.id,
        corrected_fields=payload.corrected_fields,
    )
    if not clause:
        raise HTTPException(status_code=404, detail="Clause not found")
    # Serialize BEFORE audit event — add_audit_event calls db.commit() which expires ORM attributes
    result = ClauseOut.model_validate({**clause.__dict__, "metadata": clause.metadata_json})
    repo.add_audit_event(
        room_id=room_id,
        event_type=f"clause.reviewed.{payload.status}",
        actor_user_id=user.id,
        entity_type="clause",
        entity_id=clause_id,
        payload={"review_status": payload.status},
    )
    return result


# ─── Contract Families ────────────────────────────────────────────────────────

@router.get("/rooms/{room_id}/contract-families", response_model=List[ContractFamilyOut])
def list_contract_families(
    room_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List contract families (base doc + amendments) for a room."""
    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")
    rows = repo.list_contract_families(room_id=room_id)
    return [
        ContractFamilyOut.model_validate({**row.__dict__, "metadata": row.metadata_json})
        for row in rows
    ]


# ─── Playbooks ────────────────────────────────────────────────────────────────

@router.get("/playbooks", response_model=List[PlaybookOut])
def list_playbooks(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all available investigation playbooks."""
    repo = PEDiligenceRepository(db)
    rows = repo.list_playbooks()
    return [
        PlaybookOut.model_validate({**row.__dict__, "clause_types": row.clause_types or []})
        for row in rows
    ]


# ─── Room Financials ─────────────────────────────────────────────────────────

@router.get("/rooms/{room_id}/financials")
def get_room_financials(
    room_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return llm_financials and numeric_signals from the latest completed analysis run."""
    repo = PEDiligenceRepository(db)
    run = repo.get_latest_completed_run(room_id=room_id)
    if not run:
        return {"llm_financials": None, "numeric_signals": None}
    meta = run.metadata_json or {}
    return {
        "llm_financials": meta.get("llm_financials"),
        "numeric_signals": meta.get("numeric_signals"),
    }


# ─── IC Memo Generation ───────────────────────────────────────────────────────

@router.post("/rooms/{room_id}/generate-ic-memo", response_model=GenerateICMemoResponse)
def generate_ic_memo(
    room_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Kick off an Investment Memo workflow run using this diligence room's documents.

    Returns the workflow_run_id and job_id for SSE polling. The frontend can redirect
    to the existing workflow results page (/pe/workflows/{workflow_run_id}).
    """
    from app.repositories.workflow_repository import WorkflowRepository
    from app.api.workflows import CreateWorkflowRunRequest, create_workflow_run

    repo = PEDiligenceRepository(db)
    room = repo.get_room(room_id=room_id, org_id=user.org_id, user_id=user.id)
    if not room:
        raise HTTPException(status_code=404, detail="Diligence room not found")

    # Collect canonical document IDs from room
    room_docs = repo.list_documents_in_room(room_id=room_id)
    doc_ids = [rd.document_id for rd in room_docs if rd.document_id]
    if not doc_ids:
        raise HTTPException(status_code=400, detail="No documents in this diligence room")

    # Find the active Investment Memo workflow
    wf_repo = WorkflowRepository(db)
    pe_workflows = wf_repo.list_workflows(active_only=True, domain="private_equity")
    memo_workflow = next(
        (wf for wf in pe_workflows if "Investment Memo" in (wf.name or "")),
        None,
    )
    if not memo_workflow:
        raise HTTPException(
            status_code=404,
            detail="Investment Memo workflow not found. Contact your administrator.",
        )

    # Inject diligence context as custom prompt suffix
    custom_prompt = (
        f"This investment memo is being generated from the diligence room: "
        f"'{room.name}'"
        + (f" (target: {room.target_company})" if room.target_company else "")
        + ". Focus on the deal-critical risks identified during diligence review."
    )

    payload = CreateWorkflowRunRequest(
        workflow_id=memo_workflow.id,
        document_ids=doc_ids,
        variables={},
        custom_prompt=custom_prompt,
    )

    try:
        run_out = create_workflow_run(payload, user, db)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "IC memo generation failed",
            extra={"room_id": room_id, "user_id": user.id, "error": str(exc)},
        )
        raise HTTPException(status_code=500, detail="Failed to start IC memo workflow")

    return GenerateICMemoResponse(
        workflow_run_id=run_out.id,
        job_id=run_out.job_id if hasattr(run_out, "job_id") else None,
        message=f"Investment memo workflow started for room '{room.name}'.",
    )
