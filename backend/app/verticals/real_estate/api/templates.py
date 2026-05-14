"""Real Estate Excel Templates API - Template management and filling endpoints.

Routes: /api/v1/re/templates/*

Provides Excel template upload, management, and filling functionality.
"""

import os
import shutil
from datetime import datetime, timezone

import openpyxl
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_org_role, is_admin_role
from app.config import settings
from app.database import get_db
from app.db_models_users import User
from app.repositories.document_repository import DocumentRepository
from app.repositories.job_repository import JobRepository
from app.repositories.template_repository import TemplateRepository
from app.core.storage.storage_factory import get_storage_backend
from app.services.beta_limits import (
    enforce_fill_run_concurrency_limit,
    enforce_template_fill_limit,
    reserve_shadow_credits,
)
from app.services.user_rate_limiter import enforce_fill_run_rate_limit
from app.utils.logging import logger
from app.utils.id_generator import generate_id
from app.verticals.real_estate.template_filling.excel_handler import ExcelHandler
from app.verticals.real_estate.template_filling.tasks import (
    continue_fill_run_chain,
    start_fill_run_chain,
)
from app.verticals.real_estate.template_filling.schema_planner import (
    compute_schema_counts as _compute_schema_counts,
)
from app.verticals.real_estate.template_filling.excel.mapping_coordinator import MappingCoordinator

router = APIRouter(prefix="/templates", tags=["re_templates"])


# ==================== Pydantic Models ====================


class TemplateUploadResponse(BaseModel):
    """Response for template upload."""

    id: str
    name: str
    description: Optional[str]
    file_path: str
    file_size_bytes: int
    schema_metadata: Optional[Dict[str, Any]]
    total_sheets: int = 0
    total_fields: int = 0
    usage_count: int = 0
    created_at: datetime
    job_id: Optional[str] = None  # For progress tracking


class TemplateListItem(BaseModel):
    """Template list item."""

    id: str
    name: str
    description: Optional[str]
    category: Optional[str]
    usage_count: int
    total_fields: int
    total_sheets: int
    created_at: datetime
    last_used_at: Optional[datetime]


class TemplateDetail(BaseModel):
    """Detailed template information."""

    id: str
    name: str
    description: Optional[str]
    category: Optional[str]
    file_path: str
    file_size_bytes: int
    schema_metadata: Dict[str, Any]
    usage_count: int
    created_at: datetime
    last_used_at: Optional[datetime]


class StartFillRequest(BaseModel):
    """Request to start a fill run."""

    document_id: str = Field(..., description="PDF document ID to extract data from")
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Optional user-defined fill run name")

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class StartFillResponse(BaseModel):
    """Response for starting a fill run."""

    fill_run_id: str
    job_id: str
    status: str


class FillRunStatus(BaseModel):
    """Fill run status information."""

    id: str
    name: Optional[str] = None
    template_id: Optional[str]  # Can be null if template deleted
    document_id: Optional[str]  # Can be null if document deleted
    status: str
    current_stage: Optional[str]
    field_mapping: Dict[str, Any]
    extracted_data: Dict[str, Any]
    artifact: Optional[Dict[str, Any]]
    total_fields_detected: Optional[int]
    total_fields_mapped: Optional[int]
    total_fields_filled: Optional[int]
    total_template_fields: Optional[int]
    auto_mapped_count: Optional[int]
    user_edited_count: Optional[int]
    created_at: datetime
    completed_at: Optional[datetime]
    document_metadata: Optional[Dict[str, Any]]  # PDF metadata for viewer
    citation_context: Optional[Dict[str, Any]] = None  # S{n}→{bbox,page,filename} lookup for PDF highlighting


class FillRunListItem(BaseModel):
    """Fill run list item (simplified)."""

    id: str
    name: Optional[str] = None
    template_id: Optional[str]  # Can be null if template deleted
    template_snapshot: Optional[Dict[str, Any]]  # Template metadata snapshot
    document_id: Optional[str]  # Can be null if document deleted
    document_metadata: Optional[Dict[str, Any]]  # Document metadata
    status: str
    total_fields_detected: Optional[int]
    total_fields_mapped: Optional[int]
    total_fields_filled: Optional[int]
    created_at: datetime
    completed_at: Optional[datetime]


class UpdateMappingRequest(BaseModel):
    """Request to update field mapping."""

    mappings: List[Dict[str, Any]] = Field(
        ...,
        description="Updated list of PDF field to Excel cell mappings"
    )


class ContinueFillRequest(BaseModel):
    """Request to continue fill run after user review."""

    pass  # No additional data needed


class UpdateTemplateRequest(BaseModel):
    """Request to rename a template."""

    name: str = Field(..., min_length=1, max_length=255)


class UpdateFillRunRequest(BaseModel):
    """Request to rename a fill run."""

    name: str = Field(..., min_length=1, max_length=255)


# ==================== Helper Functions ====================


def _compute_correction_counts(extracted_data: dict) -> dict:
    """
    Compute user correction counts from a flat extracted_data dict.

    Counts:
    - user_corrected_count: user_edited=True, 'original_value' key present, value is not None
    - user_filled_blank_count: user_edited=True, 'original_value' key present, value is None
    - user_edited_count: all fields where user_edited=True (includes legacy edits without original_value)
    """
    user_corrected = 0
    user_filled_blank = 0
    user_edited_total = 0

    for key, data in extracted_data.items():
        if key == "manual_edits":
            continue
        if not isinstance(data, dict):
            continue
        if not data.get("user_edited"):
            continue
        user_edited_total += 1
        if "original_value" in data:
            if data["original_value"] is not None:
                user_corrected += 1
            else:
                user_filled_blank += 1

    return {
        "user_corrected_count": user_corrected,
        "user_filled_blank_count": user_filled_blank,
        "user_edited_count": user_edited_total,
    }


# ==================== Template Management Endpoints ====================


@router.post("", response_model=TemplateUploadResponse)
async def upload_template(
    file: UploadFile = File(...),
    name: str = Form(None),
    description: str = Form(None),
    category: str = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload a new Excel template.

    The template will be analyzed to detect fillable cells, formulas, and sheets.
    """
    logger.info(f"Uploading Excel template: {file.filename}", extra={"user_id": user.id})

    # Validate file type
    if not file.filename.endswith((".xlsx", ".xlsm")):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only .xlsx and .xlsm files are supported."
        )

    try:
        repo = TemplateRepository(db)
        handler = ExcelHandler()
        storage = get_storage_backend()

        # Extract file extension (.xlsx or .xlsm)
        file_ext = Path(file.filename).suffix.lower()  # e.g., ".xlsx" or ".xlsm"

        # Use filename as name if not provided
        template_name = name or Path(file.filename).stem

        # Save to temporary file WITH CORRECT EXTENSION
        temp_path = f"/tmp/upload_{user.id}_{template_name}{file_ext}"
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Compute file hash and size
        content_hash = handler.compute_file_hash(temp_path)
        file_size = handler.get_file_size(temp_path)
        max_template_bytes = settings.template_fill_max_template_mb * 1024 * 1024
        if file_size > max_template_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Excel templates up to {settings.template_fill_max_template_mb} MB are supported. "
                    "Remove unused sheets, images, or excess formatting and try again."
                ),
            )

        # Validate fingerprint — only the known RE Investment Model is supported for beta.
        # This is synchronous but fast (reads only 3 cells).
        coordinator = MappingCoordinator()
        try:
            wb = openpyxl.load_workbook(temp_path, read_only=True, data_only=True)
            schema_id = coordinator.identify_template(wb)
            wb.close()
        except Exception as fp_err:
            logger.warning(f"Fingerprint check failed: {fp_err}")
            schema_id = None

        if not schema_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "This file doesn't match the supported RE Investment Model template. "
                    "Please upload the correct master template file. "
                    "Contact your admin if you need a different template type."
                ),
            )

        # Build schema_metadata from YAML counts — no heavy analyzer needed.
        schema_obj = coordinator.schema_loader.load_schema(schema_id)
        schema_summary = _compute_schema_counts(schema_obj) if schema_obj else {}
        schema_metadata = {
            "schema_summary": schema_summary,
            "total_yaml_fields": schema_summary.get("total_yaml_fields", 0),
            "total_sheets": getattr(schema_obj, "total_sheets", 0),
        }

        # Create template record FIRST to get the real ID
        template = repo.create_template(
            org_id=user.org_id,
            user_id=user.id,
            name=template_name,
            file_path="",  # Placeholder, will update after upload
            file_extension=file_ext,  # Store the extension!
            file_size_bytes=file_size,
            content_hash=content_hash,
            description=description,
            category=category,
        )

        # Generate storage key: templates/{YYYY}/{MM}/{DD}/{template_id}_{filename}
        # Date-partitioned, consistent with workflow-artifacts. Readable in R2 browser.
        _now = datetime.now(timezone.utc)
        safe_template_filename = file.filename.replace("/", "_").replace("\\", "_")
        storage_key = (
            f"templates/{_now.year}/{_now.month:02d}/{_now.day:02d}"
            f"/{template.id}_{safe_template_filename}"
        )
        storage.upload(temp_path, storage_key)

        # Update template with file path and pre-built schema_metadata (no async analysis needed)
        template = repo.update_template(template.id, file_path=storage_key, schema_metadata=schema_metadata)

        logger.info(f"Template uploaded successfully: {template.id}")

        return TemplateUploadResponse(
            id=template.id,
            name=template.name,
            description=template.description,
            file_path=template.file_path,
            file_size_bytes=template.file_size_bytes,
            schema_metadata=template.schema_metadata,
            total_sheets=schema_metadata.get("total_sheets", 0),
            total_fields=schema_metadata.get("total_yaml_fields", 0),
            created_at=template.created_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Template upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Template upload failed: {str(e)}")


@router.get("", response_model=List[TemplateListItem])
async def list_templates(
    category: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List user's Excel templates.

    Optionally filter by category.
    """
    logger.info("Listing Excel templates", extra={"user_id": user.id, "category": category})

    try:
        repo = TemplateRepository(db)
        templates = repo.list_user_templates(
            user_id=user.id,
            org_id=user.org_id,
            active_only=True,
            category=category,
        )

        return [
            TemplateListItem(
                id=t.id,
                name=t.name,
                description=t.description,
                category=t.category,
                usage_count=t.usage_count,
                # Prefer YAML schema target fields when available, fallback to all detected fillables
                total_fields=(
                    (
                        (t.schema_metadata.get("schema_summary") or {}).get("total_yaml_fields")
                        or t.schema_metadata.get("total_yaml_fields")
                    )
                    if t.schema_metadata and (
                        (t.schema_metadata.get("schema_summary") or {}).get("total_yaml_fields") is not None
                        or t.schema_metadata.get("total_yaml_fields") is not None
                    )
                    else (
                        t.schema_metadata.get("total_key_value_fields", 0) +
                        sum(
                            table.get("total_fillable_cells", 0)
                            for sheet in t.schema_metadata.get("sheets", [])
                            for table in sheet.get("tables", [])
                        )
                    )
                ) if t.schema_metadata else 0,
                total_sheets=(
                    t.schema_metadata.get("total_sheets") or
                    len(t.schema_metadata.get("sheets", []))
                ) if t.schema_metadata else 0,
                created_at=t.created_at,
                last_used_at=t.last_used_at,
            )
            for t in templates
        ]

    except Exception as e:
        logger.error(f"Failed to list templates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list templates")


@router.get("/fills", response_model=List[FillRunListItem])
async def list_fills(
    limit: int = 20,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List fill runs for the current user with pagination."""
    logger.info(f"Listing fill runs (limit={limit}, offset={offset})", extra={"user_id": user.id})

    try:
        repo = TemplateRepository(db)
        fill_runs = repo.list_user_fill_runs(user_id=user.id, org_id=user.org_id, limit=limit, offset=offset)

        # Batch fetch documents to avoid N+1 queries
        document_ids = [fr.document_id for fr in fill_runs if fr.document_id]
        documents_map = {}
        if document_ids:
            document_repo = DocumentRepository()
            documents = document_repo.get_doc_metadata_by_ids(document_ids, user.org_id)
            documents_map = {doc["id"]: doc for doc in documents}

        # Build response with template and document metadata
        result = []
        for fill_run in fill_runs:
            # Use template_snapshot if available, otherwise use eager-loaded template
            template_snapshot = fill_run.template_snapshot
            if not template_snapshot and fill_run.template:
                template_snapshot = {
                    "name": fill_run.template.name,
                    "description": fill_run.template.description,
                }

            # Get document metadata from batch-fetched map
            document_metadata = None
            if fill_run.document_id and fill_run.document_id in documents_map:
                doc = documents_map[fill_run.document_id]
                document_metadata = {
                    "filename": doc.get("filename"),
                    "page_count": doc.get("page_count"),
                    "file_size_bytes": doc.get("file_size_bytes"),
                }

            result.append(FillRunListItem(
                id=fill_run.id,
                name=fill_run.name,
                template_id=fill_run.template_id,
                template_snapshot=template_snapshot,
                document_id=fill_run.document_id,
                document_metadata=document_metadata,
                status=fill_run.status,
                total_fields_detected=fill_run.total_fields_detected,
                total_fields_mapped=fill_run.total_fields_mapped,
                total_fields_filled=fill_run.total_fields_filled,
                created_at=fill_run.created_at,
                completed_at=fill_run.completed_at,
            ))

        logger.info(f"Found {len(result)} fill runs", extra={"user_id": user.id})
        return result

    except Exception as e:
        logger.error(f"Failed to list fill runs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list fill runs")


@router.get("/fills/count")
async def count_fills(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return total fill run count for the current user (cheap COUNT query for badge display)."""
    repo = TemplateRepository(db)
    count = repo.count_user_fill_runs(user_id=user.id, org_id=user.org_id)
    return {"count": count}


@router.get("/{template_id}", response_model=TemplateDetail)
async def get_template(
    template_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get detailed template information."""
    logger.info(f"Getting template: {template_id}", extra={"user_id": user.id})

    try:
        repo = TemplateRepository(db)
        template = repo.get_template(template_id, user.org_id)

        if not template or template.user_id != user.id:
            raise HTTPException(status_code=404, detail="Template not found")

        return TemplateDetail(
            id=template.id,
            name=template.name,
            description=template.description,
            category=template.category,
            file_path=template.file_path,
            file_size_bytes=template.file_size_bytes,
            schema_metadata=template.schema_metadata or {},
            usage_count=template.usage_count,
            created_at=template.created_at,
            last_used_at=template.last_used_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get template")


@router.patch("/{template_id}")
async def rename_template(
    template_id: str,
    request: UpdateTemplateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rename a template."""
    repo = TemplateRepository(db)
    template = repo.get_template(template_id, user.org_id)
    if not template or template.user_id != user.id:
        raise HTTPException(status_code=404, detail="Template not found")
    updated = repo.update_template(template_id, name=request.name)
    return {"id": updated.id, "name": updated.name}


@router.get("/{template_id}/usage")
async def get_template_usage(
    template_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get template usage statistics before deletion."""
    logger.info(f"Checking template usage: {template_id}", extra={"user_id": user.id})

    try:
        repo = TemplateRepository(db)
        template = repo.get_template(template_id, user.org_id)

        if not template or template.user_id != user.id:
            raise HTTPException(status_code=404, detail="Template not found")

        usage = repo.get_template_usage(template_id)
        if not usage:
            raise HTTPException(status_code=404, detail="Template not found")

        return usage

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get template usage: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get template usage")


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    user: User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    Hard delete a template.

    Prevents deletion if any fill runs are in progress.
    Fill runs with completed/failed status will be preserved with template_id=NULL.
    """
    logger.info(f"Deleting template: {template_id}", extra={"user_id": user.id})

    try:
        repo = TemplateRepository(db)
        template = repo.get_template(template_id, user.org_id)

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        if template.user_id != user.id:
            role = get_current_org_role(request)
            if not is_admin_role(role):
                raise HTTPException(status_code=403, detail="Not authorized to delete this template")

        result = repo.delete_template(template_id)

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])

        response = {
            "message": result["message"],
            "affected_fill_runs": result["affected_fill_runs"],
        }
        if result.get("warnings"):
            response["warnings"] = result["warnings"]

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete template")


@router.get("/{template_id}/download")
async def download_template(
    template_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Download the Excel template file.

    When storage is R2, returns a presigned URL as JSON so the browser can fetch
    directly without a redirect (redirects cause Origin: null which breaks CORS).
    When storage is local, streams the file through the API (dev mode).
    """
    logger.info(f"Downloading template: {template_id}", extra={"user_id": user.id})

    try:
        repo = TemplateRepository(db)
        template = repo.get_template(template_id, user.org_id)

        if not template or template.user_id != user.id:
            raise HTTPException(status_code=404, detail="Template not found")

        storage = get_storage_backend()

        # R2: return presigned URL as JSON — frontend fetches directly to avoid the
        # Origin: null CORS issue that occurs when browsers follow cross-origin redirects.
        if storage.get_storage_type() == "r2":
            presigned_url = storage.generate_presigned_url(template.file_path, expiry_seconds=3600)
            return {"url": presigned_url, "storage_backend": "r2", "expires_in": 3600}

        # Local filesystem: stream through API (dev mode)
        file_ext = template.file_extension or ".xlsx"
        temp_path = f"/tmp/{template_id}{file_ext}"
        try:
            storage.download(template.file_path, temp_path)
            with open(temp_path, "rb") as f:
                file_bytes = f.read()
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        return StreamingResponse(
            BytesIO(file_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'inline; filename="{template.name}{file_ext}"',
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to download template")


# ==================== Fill Run Endpoints ====================


@router.post("/{template_id}/fill", response_model=StartFillResponse)
async def start_fill(
    template_id: str,
    request: StartFillRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Start a template fill run.

    This will:
    1. Detect fields from the PDF
    2. Auto-map fields to Excel cells
    3. Pause for user review

    After reviewing the mappings, call POST /fills/{fill_run_id}/continue
    """
    logger.info(
        f"Starting fill run: template={template_id}, document={request.document_id}",
        extra={"user_id": user.id}
    )

    try:
        repo = TemplateRepository(db)

        # Layer 1: per-user rate limit (Redis sliding window, fail-open)
        enforce_fill_run_rate_limit(user.id)

        # Layer 2: template ownership
        template = repo.get_template(template_id, user.org_id)
        if not template or template.user_id != user.id:
            raise HTTPException(status_code=404, detail="Template not found")

        # Layer 3: document ownership (cross-org access guard)
        document_repo = DocumentRepository()
        document = document_repo.get_by_id(request.document_id, user.org_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        # Layer 4: per-user concurrency cap (tighter filters, cheaper query)
        enforce_fill_run_concurrency_limit(user, db)

        # Layer 5: monthly quota
        enforce_template_fill_limit(user)

        fill_run_id = start_fill_run_chain.delay(
            template_id=template_id,
            document_id=request.document_id,
            user_id=user.id,
            fill_run_name=request.name,
        ).get()  # Wait for initial DB setup (fill_run record created)

        reserve_shadow_credits(
            user=user,
            operation_type="template_fill_run",
            reference_id=fill_run_id,
            metadata={"template_id": template_id, "document_id": request.document_id},
        )

        logger.info(f"Fill run started: {fill_run_id}")

        return StartFillResponse(
            fill_run_id=fill_run_id,
            job_id=fill_run_id,  # Use fill_run_id as job tracking ID
            status="processing"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start fill run: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start fill run: {str(e)}")


@router.get("/fills/{fill_run_id}", response_model=FillRunStatus)
async def get_fill_status(
    fill_run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the status of a fill run."""
    logger.info(f"Getting fill run status: {fill_run_id}", extra={"user_id": user.id})

    try:
        repo = TemplateRepository(db)
        fill_run = repo.get_fill_run_with_data(fill_run_id, user.org_id)

        if not fill_run or fill_run.user_id != user.id:
            raise HTTPException(status_code=404, detail="Fill run not found")

        blob = fill_run.fill_run_data
        field_mapping = blob.field_mapping if blob else {}
        extracted_data = blob.extracted_data if blob else {}
        citation_context = blob.citation_context if blob else None

        # Debug: Log what we're returning
        mappings_count = len((field_mapping or {}).get("mappings", []))
        logger.info(f"Returning fill run {fill_run_id}: status={fill_run.status}, mappings={mappings_count}")

        # Fetch document metadata for PDF viewer
        document_metadata = None
        if fill_run.document_id:
            document_repo = DocumentRepository()
            document = document_repo.get_by_id(fill_run.document_id, user.org_id)

            if document:
                document_metadata = {
                    "id": document.id,
                    "filename": document.filename,
                    "page_count": document.page_count,
                    "file_size_bytes": document.file_size_bytes,
                }

        schema_summary = None
        if isinstance(field_mapping, dict):
            schema_summary = field_mapping.get("schema_summary")

        total_template_fields = None
        if isinstance(schema_summary, dict) and schema_summary.get("total_yaml_fields") is not None:
            total_template_fields = schema_summary.get("total_yaml_fields")
        else:
            schema_metadata = None
            if fill_run.template_snapshot and isinstance(fill_run.template_snapshot, dict):
                schema_metadata = fill_run.template_snapshot.get("schema_metadata")
            if not schema_metadata and fill_run.template_id:
                try:
                    template = repo.get_template(fill_run.template_id)
                    if template:
                        schema_metadata = template.schema_metadata
                except Exception:
                    schema_metadata = None

            if schema_metadata:
                total_template_fields = (
                    schema_metadata.get("total_key_value_fields", 0) +
                    sum(
                        table.get("total_fillable_cells", 0)
                        for sheet in schema_metadata.get("sheets", [])
                        for table in sheet.get("tables", [])
                    )
                )

        return FillRunStatus(
            id=fill_run.id,
            name=fill_run.name,
            template_id=fill_run.template_id,
            document_id=fill_run.document_id,
            status=fill_run.status,
            current_stage=fill_run.current_stage,
            field_mapping=field_mapping or {},
            extracted_data=extracted_data or {},
            artifact=fill_run.artifact,
            total_fields_detected=fill_run.total_fields_detected,
            total_fields_mapped=fill_run.total_fields_mapped,
            total_fields_filled=fill_run.total_fields_filled,
            total_template_fields=total_template_fields,
            auto_mapped_count=fill_run.auto_mapped_count,
            user_edited_count=fill_run.user_edited_count,
            created_at=fill_run.created_at,
            completed_at=fill_run.completed_at,
            document_metadata=document_metadata,
            citation_context=citation_context,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get fill status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get fill status")


@router.patch("/fills/{fill_run_id}")
async def rename_fill_run(
    fill_run_id: str,
    request: UpdateFillRunRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rename a fill run."""
    repo = TemplateRepository(db)
    fill_run = repo.get_fill_run(fill_run_id, user.org_id)
    if not fill_run or fill_run.user_id != user.id:
        raise HTTPException(status_code=404, detail="Fill run not found")
    updated = repo.update_fill_run(fill_run_id, name=request.name)
    return {"id": updated.id, "name": updated.name}


@router.put("/fills/{fill_run_id}/mappings")
async def update_mappings(
    fill_run_id: str,
    request: UpdateMappingRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update field mappings after reviewing auto-mapped fields.

    Users can:
    - Change which Excel cell a PDF field maps to
    - Add new mappings
    - Remove mappings
    """
    logger.info(f"Updating mappings for fill run: {fill_run_id}", extra={"user_id": user.id})

    try:
        repo = TemplateRepository(db)
        fill_run = repo.get_fill_run_with_data(fill_run_id, user.org_id)

        if not fill_run or fill_run.user_id != user.id:
            raise HTTPException(status_code=404, detail="Fill run not found")

        # Update mappings
        # Enforce 1 mapping per Excel cell (a PDF field can map to multiple cells).
        # Keep the last mapping provided for duplicate cell keys.
        deduped_by_cell = {}
        for m in request.mappings:
            excel_sheet = m.get("excel_sheet")
            excel_cell = m.get("excel_cell")
            if not excel_sheet or not excel_cell:
                continue
            cell_key = f"{excel_sheet}!{excel_cell}"
            deduped_by_cell[cell_key] = m

        deduped_mappings = list(deduped_by_cell.values())

        field_mapping = (fill_run.fill_run_data.field_mapping if fill_run.fill_run_data else {}) or {}
        field_mapping["mappings"] = deduped_mappings

        # Count user edits (compare to auto_mapped_count)
        user_edited_count = len([
            m for m in deduped_mappings
            if m.get("status") in ["user_edited", "manual"]
        ])

        # Write blob update separately from lean metadata
        repo.update_fill_run_data(fill_run_id, field_mapping=field_mapping)

        lean_updates = {
            "total_fields_mapped": len(deduped_mappings),
            "user_edited_count": user_edited_count,
        }

        if fill_run.status == "completed":
            logger.info("Fill run is completed. Resetting to awaiting_review for regeneration.")

            # Delete old filled Excel from storage
            if fill_run.artifact and fill_run.artifact.get("key"):
                try:
                    from app.core.storage.storage_factory import get_storage_backend
                    storage = get_storage_backend()
                    storage_key = fill_run.artifact["key"]
                    storage.delete(storage_key)
                    logger.info(f"Deleted old filled Excel from storage: {storage_key}")
                except Exception as e:
                    logger.warning(f"Failed to delete old filled Excel: {e}")

            lean_updates.update({
                "status": "awaiting_review",
                "artifact": None,
                "filling_completed": False,
                "completed_at": None,
            })

        repo.update_fill_run(fill_run_id, **lean_updates)

        # Debug: Verify what was actually saved
        saved_fill_run = repo.get_fill_run_with_data(fill_run_id, user.org_id)
        saved_field_mapping = (saved_fill_run.fill_run_data.field_mapping if saved_fill_run and saved_fill_run.fill_run_data else {}) or {}
        saved_mappings_count = len(saved_field_mapping.get("mappings", []))
        logger.info(
            f"Mappings updated: {len(deduped_mappings)} total, {user_edited_count} user-edited. "
            f"Verified in DB: {saved_mappings_count} mappings"
        )

        return {"message": "Mappings updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update mappings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update mappings")


@router.put("/fills/{fill_run_id}/extracted-data")
async def update_extracted_data(
    fill_run_id: str,
    extracted_data: Dict[str, Any],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update extracted data for a fill run.

    This endpoint allows users to manually edit extracted field values and unmapped cells.

    Args:
        fill_run_id: Fill run ID
        extracted_data: Updated extracted data dictionary (clean nested schema)
        user: Authenticated user
        db: Database session

    Request Body (Clean Nested Schema):
        {
            "llm_extracted": {
                "f1": {
                    "value": "Manually edited value",
                    "confidence": 1.0,
                    "user_edited": true,
                    "citations": ["[S1:p2]"]
                },
                ...
            },
            "manual_edits": {
                "Sheet1": {
                    "A1": {
                        "value": "Custom value",
                        "confidence": 1.0,
                        "user_edited": true,
                        "citations": []
                    },
                    ...
                },
                ...
            }
        }

    Returns:
        Success message

    Raises:
        HTTPException 403: User doesn't own the fill run
        HTTPException 404: Fill run not found
    """
    logger.info(f"Updating extracted data for fill run: {fill_run_id}", extra={"user_id": user.id})

    try:
        repo = TemplateRepository(db)
        fill_run = repo.get_fill_run(fill_run_id, user.org_id)

        if not fill_run or fill_run.user_id != user.id:
            raise HTTPException(status_code=404, detail="Fill run not found")

        # Handle clean nested schema format
        # Expected format: {"llm_extracted": {...}, "manual_edits": {...}}
        if "llm_extracted" in extracted_data or "manual_edits" in extracted_data:
            # New clean nested schema
            llm_extracted = extracted_data.get("llm_extracted", {})
            manual_edits = extracted_data.get("manual_edits", {})

            # Mark all LLM extracted fields as user_edited if modified
            for field_id, field_data in llm_extracted.items():
                if isinstance(field_data, dict) and "user_edited" not in field_data:
                    field_data["user_edited"] = True

            # Mark all manual edit cells as user_edited
            for sheet_name, cells in manual_edits.items():
                if isinstance(cells, dict):
                    for cell_address, cell_data in cells.items():
                        if isinstance(cell_data, dict) and "user_edited" not in cell_data:
                            cell_data["user_edited"] = True

            # Count total fields
            total_fields = len(llm_extracted)
            for cells in manual_edits.values():
                if isinstance(cells, dict):
                    total_fields += len(cells)

        else:
            # Legacy flat schema: {field_id: {value, confidence, ...}, ...}
            for field_id, field_data in extracted_data.items():
                if isinstance(field_data, dict) and "user_edited" not in field_data:
                    field_data["user_edited"] = True
            total_fields = len(extracted_data)

        # Write blob separately from lean metadata
        repo.update_fill_run_data(fill_run_id, extracted_data=extracted_data)

        # Compute correction counts for analytics
        flat_fields = extracted_data.get("llm_extracted", extracted_data)
        # manual_edits (raw cell overrides by sheet+cell address) are excluded intentionally —
        # correction counts track LLM field-level extraction quality, not direct cell edits.
        counts = _compute_correction_counts(flat_fields)

        lean_updates = {
            "total_fields_filled": total_fields,
            "user_edited_count": counts["user_edited_count"],
            # user_corrected_count and user_filled_blank_count columns added in migration
            # r5s6t7u8v9w0 — wired here after Task 3
            "user_corrected_count": counts["user_corrected_count"],
            "user_filled_blank_count": counts["user_filled_blank_count"],
        }

        # If fill run is already completed, reset to awaiting_review
        # This allows user to regenerate Excel with updated field values
        if fill_run.status == "completed":
            logger.info("Fill run is completed. Resetting to awaiting_review for regeneration.")

            # Delete old filled Excel from storage
            if fill_run.artifact and fill_run.artifact.get("key"):
                try:
                    from app.core.storage.storage_factory import get_storage_backend
                    storage = get_storage_backend()
                    storage_key = fill_run.artifact["key"]
                    storage.delete(storage_key)
                    logger.info(f"Deleted old filled Excel from storage: {storage_key}")
                except Exception as e:
                    logger.warning(f"Failed to delete old filled Excel: {e}")

            lean_updates.update({
                "status": "awaiting_review",
                "artifact": None,
                "filling_completed": False,
                "completed_at": None,
            })

        repo.update_fill_run(fill_run_id, **lean_updates)

        logger.info(f"Extracted data updated: {len(extracted_data)} fields")

        return {"message": "Extracted data updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update extracted data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update extracted data")


@router.post("/fills/{fill_run_id}/continue")
async def continue_fill(
    fill_run_id: str,
    request: ContinueFillRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Continue fill run after user has reviewed mappings.

    This will:
    1. Extract data from PDF using the approved mappings
    2. Fill the Excel template
    3. Generate the downloadable artifact
    """
    logger.info(f"Continuing fill run: {fill_run_id}", extra={"user_id": user.id})

    try:
        repo = TemplateRepository(db)
        fill_run = repo.get_fill_run(fill_run_id, user.org_id)

        if not fill_run or fill_run.user_id != user.id:
            raise HTTPException(status_code=404, detail="Fill run not found")

        # Create new job for continuation tracking
        job_id = generate_id()
        job_repo = JobRepository()
        job = job_repo.create_job(
            entity_type="template_fill_run",
            entity_id=fill_run_id,
            status="extracting",
            current_stage="data_extraction",
            progress_percent=70,
            job_id=job_id
        )
        if not job:
            raise HTTPException(status_code=500, detail="Failed to create job for fill run")

        # Continue async pipeline
        continue_fill_run_chain.delay(
            fill_run_id=fill_run_id,
            job_id=job_id,
        )

        logger.info(f"Fill run continuation started: {fill_run_id}")

        return {"message": "Fill run continued", "job_id": job_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to continue fill run: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to continue fill run: {str(e)}")


@router.delete("/fills/{fill_run_id}")
async def delete_fill_run(
    fill_run_id: str,
    user: User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Delete a fill run and its associated files."""
    logger.info(f"Deleting fill run: {fill_run_id}", extra={"user_id": user.id})

    try:
        repo = TemplateRepository(db)
        fill_run = repo.get_fill_run(fill_run_id, user.org_id)

        if not fill_run:
            raise HTTPException(status_code=404, detail="Fill run not found")

        if fill_run.user_id != user.id:
            role = get_current_org_role(request)
            if not is_admin_role(role):
                raise HTTPException(status_code=403, detail="Not authorized to delete this fill run")

        # Delete the fill run (includes R2 cleanup via repository)
        success = repo.delete_fill_run(fill_run_id)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete fill run")

        logger.info(f"Fill run deleted: {fill_run_id}")
        return {"message": "Fill run deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete fill run: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete fill run: {str(e)}")


@router.get("/fills/{fill_run_id}/download")
async def download_filled_excel(
    fill_run_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download the filled Excel file."""
    logger.info(f"Downloading filled Excel: {fill_run_id}", extra={"user_id": user.id})

    try:
        repo = TemplateRepository(db)
        fill_run = repo.get_fill_run(fill_run_id, user.org_id)

        if not fill_run or fill_run.user_id != user.id:
            raise HTTPException(status_code=404, detail="Fill run not found")

        if not fill_run.artifact:
            raise HTTPException(status_code=400, detail="Fill run not completed yet")

        # Download from storage
        storage = get_storage_backend()
        storage_key = fill_run.artifact["key"]
        local_path = f"/tmp/download_{fill_run_id}.xlsx"

        storage.download(storage_key, local_path)

        # Stream file to user
        def iterfile():
            with open(local_path, "rb") as f:
                yield from f

        filename = fill_run.artifact.get("filename", f"filled_{fill_run_id}.xlsx")

        return StreamingResponse(
            iterfile(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download filled Excel: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to download filled Excel")
