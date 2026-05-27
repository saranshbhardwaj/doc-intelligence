"""Credit memo API: create, list, and download IC credit memos for underwriting runs."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.db_models_users import User
from app.repositories.job_repository import JobRepository
from app.repositories.re_memo_repository import ReMemoRepository
from app.repositories.re_underwriting_repo import UnderwritingRunRepository
from app.core.storage.storage_factory import get_storage_backend
from app.utils.id_generator import generate_id
from app.utils.logging import logger
from app.verticals.real_estate.underwriting.memo.filenames import build_memo_filename
from app.verticals.real_estate.underwriting.memo.tasks import generate_credit_memo_task

router = APIRouter(prefix="/underwriting", tags=["re_underwriting_memos"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateMemoRequest(BaseModel):
    cover_data: dict = Field(default_factory=dict)
    sponsor_data: dict = Field(default_factory=dict)
    market_notes: Optional[str] = None
    # Analyst inputs from "Thesis & Strategy" modal tab. Free-form JSON so
    # adding fields later doesn't require a migration. Recognized keys:
    #   thesis_text, strategy_type, hold_period_years,
    #   verdict_override, verdict_override_reason,
    #   custom_conditions (list[str]),
    #   sourcing_type, sourcing_detail
    thesis_data: dict = Field(default_factory=dict)


class CreateMemoResponse(BaseModel):
    memo_id: str
    job_id: str
    version: int


class MemoSummary(BaseModel):
    id: str
    version: int
    status: str
    created_at: str
    completed_at: Optional[str] = None
    section_warnings: list[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    cover_data: dict = Field(default_factory=dict)
    sponsor_data: dict = Field(default_factory=dict)
    market_notes: Optional[str] = None
    thesis_data: dict = Field(default_factory=dict)


class ListMemosResponse(BaseModel):
    memos: list[MemoSummary]


class DownloadMemoResponse(BaseModel):
    url: str
    filename: Optional[str] = None


class DeleteMemoResponse(BaseModel):
    success: bool
    message: str
    storage_deleted: bool = False
    warnings: list[str] = Field(default_factory=list)


class MemoReadinessResponse(BaseModel):
    """Pre-flight check shown in the Generate Memo modal so the analyst knows
    whether the OM is indexed (and the memo will have source citations)."""
    om_indexed: bool
    document_count: int
    indexed_chunk_count: int
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Storage helper
# ---------------------------------------------------------------------------


def _presign_r2(r2_key: str, expiry_seconds: int = 900, filename: Optional[str] = None) -> str:
    storage = get_storage_backend()
    return storage.generate_presigned_url(
        r2_key,
        expiry_seconds=expiry_seconds,
        filename=filename,
    )


def _memo_download_filename(memo) -> str:
    deal_name = None
    if isinstance(memo.cover_data, dict):
        deal_name = memo.cover_data.get("deal_name")
    if not deal_name and getattr(memo, "run", None) is not None:
        deal_name = getattr(memo.run, "name", None)
    return build_memo_filename(deal_name or "IC_Memo", memo.version)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/runs/{run_id}/memos", response_model=CreateMemoResponse)
def create_memo(
    run_id: str,
    body: CreateMemoRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new IC credit memo for a completed underwriting run and dispatch generation."""
    run_repo = UnderwritingRunRepository(db)
    run = run_repo.get(run_id, user.id)
    if run is None:
        raise HTTPException(status_code=404, detail="Underwriting run not found")
    if not run.result_artifact:
        raise HTTPException(
            status_code=400,
            detail="Run must be completed before generating a memo",
        )

    repo = ReMemoRepository(db)
    memo = repo.create(
        run_id=run_id,
        user_id=user.id,
        cover_data=body.cover_data,
        sponsor_data=body.sponsor_data,
        market_notes=body.market_notes,
        thesis_data=body.thesis_data,
    )

    # Pre-create the JobState row with a known task_id so that JobProgressTracker
    # inside the Celery task can look it up via job_id == task_id.
    task_id = generate_id()
    job_repo = JobRepository()
    job = job_repo.create_job(
        entity_type="underwriting_memo",
        entity_id=memo.id,
        status="queued",
        current_stage="queued",
        progress_percent=0,
        message="Memo generation queued…",
        job_id=task_id,
    )
    if not job:
        raise HTTPException(status_code=500, detail="Failed to create job for memo generation")

    generate_credit_memo_task.apply_async(
        args=[memo.id, run_id, user.id],
        task_id=task_id,
    )
    repo.update_status(memo.id, "pending", job_id=task_id)

    logger.info(
        "Credit memo creation queued",
        extra={"memo_id": memo.id, "run_id": run_id, "user_id": user.id, "task_id": task_id},
    )
    return CreateMemoResponse(memo_id=memo.id, job_id=task_id, version=memo.version)


@router.get("/runs/{run_id}/memo-readiness", response_model=MemoReadinessResponse)
def memo_readiness(
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pre-flight check the modal hits when it opens.

    Returns whether the OM is indexed (memo will have source citations) so the
    analyst can decide whether to proceed.
    """
    from sqlalchemy import select, func
    from app.db_models_chat import DocumentChunk

    run_repo = UnderwritingRunRepository(db)
    run = run_repo.get(run_id, user.id)
    if run is None:
        raise HTTPException(status_code=404, detail="Underwriting run not found")

    raw_docs = run.document_ids or []
    om_doc_ids = [
        d.get("document_id")
        for d in raw_docs
        if isinstance(d, dict) and d.get("document_id") and (d.get("doc_type") or "").lower() == "om"
    ]
    document_count = len(om_doc_ids)

    indexed_chunk_count = 0
    if om_doc_ids:
        stmt = select(func.count()).select_from(DocumentChunk).where(
            DocumentChunk.document_id.in_(om_doc_ids)
        )
        indexed_chunk_count = int(db.execute(stmt).scalar() or 0)

    om_indexed = indexed_chunk_count > 0
    warnings: list[str] = []
    if document_count == 0:
        warnings.append(
            "No offering memorandum attached to this run. Memo will have no source citations."
        )
    elif not om_indexed:
        warnings.append(
            "Offering memorandum is not indexed for retrieval. "
            "The memo will narrate from structured data only — Property Description and "
            "Market Overview sections will have no OM-backed citations."
        )

    return MemoReadinessResponse(
        om_indexed=om_indexed,
        document_count=document_count,
        indexed_chunk_count=indexed_chunk_count,
        warnings=warnings,
    )


@router.get("/runs/{run_id}/memos", response_model=ListMemosResponse)
def list_memos(
    run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all credit memos for a run, newest version first."""
    repo = ReMemoRepository(db)
    memos = repo.list_by_run(run_id, user.id)
    return ListMemosResponse(
        memos=[
            MemoSummary(
                id=m.id,
                version=m.version,
                status=m.status,
                created_at=m.created_at.isoformat() if m.created_at else "",
                completed_at=m.completed_at.isoformat() if m.completed_at else None,
                section_warnings=list(m.section_warnings or []),
                error_message=m.error_message,
                cover_data=dict(m.cover_data or {}),
                sponsor_data=dict(m.sponsor_data or {}),
                market_notes=m.market_notes,
                thesis_data=dict(m.thesis_data or {}),
            )
            for m in memos
        ]
    )


@router.get("/memos/{memo_id}/download", response_model=DownloadMemoResponse)
def download_memo(
    memo_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return a presigned download URL for a completed credit memo DOCX."""
    repo = ReMemoRepository(db)
    memo = repo.get(memo_id, user.id)
    if memo is None:
        raise HTTPException(status_code=404, detail="Memo not found")
    if memo.status != "complete":
        raise HTTPException(
            status_code=409,
            detail=f"Memo is not ready (status={memo.status})",
        )
    if not memo.r2_key:
        raise HTTPException(status_code=500, detail="Memo has no r2_key — internal error")
    filename = _memo_download_filename(memo)
    return DownloadMemoResponse(
        url=_presign_r2(memo.r2_key, filename=filename),
        filename=filename,
    )


@router.delete("/memos/{memo_id}", response_model=DeleteMemoResponse)
def delete_memo(
    memo_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a terminal credit memo and best-effort clean up its generated DOCX."""
    repo = ReMemoRepository(db)
    try:
        result = repo.delete_terminal(memo_id, user.id)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to delete memo from database")

    if not result.deleted:
        raise HTTPException(status_code=result.status_code or 400, detail=result.error or "Memo not deleted")

    warnings: list[str] = []
    storage_deleted = False
    if result.storage_key:
        try:
            storage = get_storage_backend()
            storage.delete(result.storage_key)
            storage_deleted = True
            logger.info(
                "Deleted credit memo file from storage",
                extra={"memo_id": memo_id, "r2_key": result.storage_key},
            )
        except Exception as exc:
            warning = "Memo deleted, but file cleanup failed."
            warnings.append(warning)
            logger.warning(
                "Credit memo storage cleanup failed",
                extra={"memo_id": memo_id, "r2_key": result.storage_key, "error": str(exc)},
            )

    return DeleteMemoResponse(
        success=True,
        message="Memo deleted",
        storage_deleted=storage_deleted,
        warnings=warnings,
    )
