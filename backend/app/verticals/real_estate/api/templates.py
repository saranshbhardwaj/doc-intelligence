"""Real Estate Excel Templates API - Template management and filling endpoints.

Routes: /api/v1/re/templates/*

Provides Excel template upload, management, and filling functionality.
"""

import os
import shutil
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.db_models import JobState
from app.db_models_users import User
from app.repositories.template_repository import TemplateRepository
from app.core.storage.storage_factory import get_storage_backend
from app.utils.logging import logger
from app.utils.id_generator import generate_id
from app.verticals.real_estate.template_filling.excel_handler import ExcelHandler
from app.verticals.real_estate.template_filling.tasks import (
    analyze_template_task,
    continue_fill_run_chain,
    start_fill_run_chain,
)

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


class StartFillResponse(BaseModel):
    """Response for starting a fill run."""

    fill_run_id: str
    job_id: str
    status: str


class FillRunStatus(BaseModel):
    """Fill run status information."""

    id: str
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
    auto_mapped_count: Optional[int]
    user_edited_count: Optional[int]
    created_at: datetime
    completed_at: Optional[datetime]
    document_metadata: Optional[Dict[str, Any]]  # PDF metadata for viewer


class FillRunListItem(BaseModel):
    """Fill run list item (simplified)."""

    id: str
    template_id: Optional[str]  # Can be null if template deleted
    template_snapshot: Optional[Dict[str, Any]]  # Template metadata snapshot
    document_id: Optional[str]  # Can be null if document deleted
    document_metadata: Optional[Dict[str, Any]]  # Document metadata
    status: str
    current_stage: Optional[str]
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

        # Create template record FIRST to get the real ID
        template = repo.create_template(
            user_id=user.id,
            name=template_name,
            file_path="",  # Placeholder, will update after upload
            file_extension=file_ext,  # Store the extension!
            file_size_bytes=file_size,
            content_hash=content_hash,
            description=description,
            category=category,
        )

        # Now upload to storage using the real template ID WITH CORRECT EXTENSION
        storage_key = f"templates/{user.id}/{template.id}{file_ext}"
        storage.upload(temp_path, storage_key)

        # Update template with correct file path
        template = repo.update_template(template.id, file_path=storage_key)

        # Trigger async analysis (no JobState needed - template analysis is fast)
        analyze_template_task.delay({
            "template_id": template.id,
            "file_path": storage_key,
        })

        logger.info(f"Template uploaded successfully: {template.id}")

        return TemplateUploadResponse(
            id=template.id,
            name=template.name,
            description=template.description,
            file_path=template.file_path,
            file_size_bytes=template.file_size_bytes,
            schema_metadata=template.schema_metadata,
            created_at=template.created_at,
        )

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
                # Calculate total fillable fields: key-value fields + all table cells
                total_fields=(
                    t.schema_metadata.get("total_key_value_fields", 0) +
                    sum(
                        table.get("total_fillable_cells", 0)
                        for sheet in t.schema_metadata.get("sheets", [])
                        for table in sheet.get("tables", [])
                    )
                ) if t.schema_metadata else 0,
                total_sheets=len(t.schema_metadata.get("sheets", [])) if t.schema_metadata else 0,
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
        from app.db_models_documents import Document

        repo = TemplateRepository(db)
        fill_runs = repo.list_user_fill_runs(user_id=user.id, limit=limit, offset=offset)

        # Batch fetch documents to avoid N+1 queries
        document_ids = [fr.document_id for fr in fill_runs if fr.document_id]
        documents_map = {}
        if document_ids:
            documents = db.query(Document).filter(Document.id.in_(document_ids)).all()
            documents_map = {doc.id: doc for doc in documents}

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
                    "filename": doc.filename,
                    "page_count": doc.page_count,
                    "file_size_bytes": doc.file_size_bytes,
                }

            result.append(FillRunListItem(
                id=fill_run.id,
                template_id=fill_run.template_id,
                template_snapshot=template_snapshot,
                document_id=fill_run.document_id,
                document_metadata=document_metadata,
                status=fill_run.status,
                current_stage=fill_run.current_stage,
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
        template = repo.get_template(template_id)

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
        template = repo.get_template(template_id)

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
        template = repo.get_template(template_id)

        if not template or template.user_id != user.id:
            raise HTTPException(status_code=404, detail="Template not found")

        result = repo.delete_template(template_id)

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])

        return {
            "message": result["message"],
            "affected_fill_runs": result["affected_fill_runs"],
        }

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
    """Stream Excel template file through backend to avoid CORS issues."""
    logger.info(f"Downloading template: {template_id}", extra={"user_id": user.id})

    try:
        repo = TemplateRepository(db)
        template = repo.get_template(template_id)

        if not template or template.user_id != user.id:
            raise HTTPException(status_code=404, detail="Template not found")

        storage = get_storage_backend()

        # Download to temp file
        temp_path = f"/tmp/{template_id}.xlsx"
        try:
            storage.download(template.file_path, temp_path)

            # Read into memory
            with open(temp_path, "rb") as f:
                file_bytes = f.read()
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)

        # Stream to frontend
        return StreamingResponse(
            BytesIO(file_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'inline; filename="{template.name}.xlsx"',
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

        # Verify template exists and belongs to user
        template = repo.get_template(template_id)
        if not template or template.user_id != user.id:
            raise HTTPException(status_code=404, detail="Template not found")

        # Start async pipeline (worker will create JobState and TemplateFillRun)
        fill_run_id = start_fill_run_chain.delay(
            template_id=template_id,
            document_id=request.document_id,
            user_id=user.id,
        ).get()  # Wait for initial setup to complete

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
        from app.db_models_documents import Document
        from app.repositories.document_repository import DocumentRepository

        repo = TemplateRepository(db)
        fill_run = repo.get_fill_run(fill_run_id)

        if not fill_run or fill_run.user_id != user.id:
            raise HTTPException(status_code=404, detail="Fill run not found")

        # Debug: Log what we're returning
        mappings_count = len(fill_run.field_mapping.get("mappings", [])) if fill_run.field_mapping else 0
        logger.info(f"Returning fill run {fill_run_id}: status={fill_run.status}, mappings={mappings_count}")

        # Fetch document metadata for PDF viewer
        document_metadata = None
        if fill_run.document_id:
            document = db.query(Document).filter(Document.id == fill_run.document_id).first()

            if document:
                document_metadata = {
                    "id": document.id,
                    "filename": document.filename,
                    "page_count": document.page_count,
                    "file_size_bytes": document.file_size_bytes,
                }

        return FillRunStatus(
            id=fill_run.id,
            template_id=fill_run.template_id,
            document_id=fill_run.document_id,
            status=fill_run.status,
            current_stage=fill_run.current_stage,
            field_mapping=fill_run.field_mapping or {},
            extracted_data=fill_run.extracted_data or {},
            artifact=fill_run.artifact,
            total_fields_detected=fill_run.total_fields_detected,
            total_fields_mapped=fill_run.total_fields_mapped,
            total_fields_filled=fill_run.total_fields_filled,
            auto_mapped_count=fill_run.auto_mapped_count,
            user_edited_count=fill_run.user_edited_count,
            created_at=fill_run.created_at,
            completed_at=fill_run.completed_at,
            document_metadata=document_metadata,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get fill status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get fill status")


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
        fill_run = repo.get_fill_run(fill_run_id)

        if not fill_run or fill_run.user_id != user.id:
            raise HTTPException(status_code=404, detail="Fill run not found")

        # Update mappings
        # Enforce 1 mapping per pdf_field_id (keep the last one provided, since this is user-edited input)
        deduped_by_field_id = {}
        for m in request.mappings:
            field_id = m.get("pdf_field_id")
            if not field_id:
                continue
            deduped_by_field_id[field_id] = m

        deduped_mappings = list(deduped_by_field_id.values())

        field_mapping = fill_run.field_mapping or {}
        field_mapping["mappings"] = deduped_mappings

        # Count user edits (compare to auto_mapped_count)
        user_edited_count = len([
            m for m in request.mappings
            if m.get("status") in ["user_edited", "manual"]
        ])

        # If fill run is already completed, reset to awaiting_review
        # This allows user to regenerate Excel with updated mappings
        updates = {
            "field_mapping": field_mapping,
            "total_fields_mapped": len(deduped_mappings),
            "user_edited_count": user_edited_count,
        }

        if fill_run.status == "completed":
            logger.info(f"Fill run is completed. Resetting to awaiting_review for regeneration.")

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

            # Reset to awaiting_review
            updates.update({
                "status": "awaiting_review",
                "artifact": None,
                "filling_completed": False,
                "completed_at": None,
            })

        repo.update_fill_run(fill_run_id, **updates)

        # Debug: Verify what was actually saved
        saved_fill_run = repo.get_fill_run(fill_run_id)
        saved_mappings_count = len(saved_fill_run.field_mapping.get("mappings", [])) if saved_fill_run else 0
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

    This endpoint allows users to manually edit extracted field values,
    for example after copying text from the PDF viewer.

    Args:
        fill_run_id: Fill run ID
        extracted_data: Updated extracted data dictionary
        user: Authenticated user
        db: Database session

    Request Body:
        {
            "f1": {
                "value": "Manually edited value",
                "confidence": 1.0,
                "user_edited": true,
                "source_page": 3
            },
            ...
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
        fill_run = repo.get_fill_run(fill_run_id)

        if not fill_run or fill_run.user_id != user.id:
            raise HTTPException(status_code=404, detail="Fill run not found")

        # Mark all updated fields as user_edited
        for field_id, field_data in extracted_data.items():
            if "user_edited" not in field_data:
                field_data["user_edited"] = True

        # Prepare updates
        updates = {
            "extracted_data": extracted_data,
            "total_fields_filled": len(extracted_data),
        }

        # If fill run is already completed, reset to awaiting_review
        # This allows user to regenerate Excel with updated field values
        if fill_run.status == "completed":
            logger.info(f"Fill run is completed. Resetting to awaiting_review for regeneration.")

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

            # Reset to awaiting_review
            updates.update({
                "status": "awaiting_review",
                "artifact": None,
                "filling_completed": False,
                "completed_at": None,
            })

        # Update extracted data
        repo.update_fill_run(fill_run_id, **updates)

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
        fill_run = repo.get_fill_run(fill_run_id)

        if not fill_run or fill_run.user_id != user.id:
            raise HTTPException(status_code=404, detail="Fill run not found")

        # Create new job for continuation tracking
        job_id = generate_id()
        job = JobState(
            job_id=job_id,
            status="extracting",
            current_stage="data_extraction",
            progress_percent=70,
            template_fill_run_id=fill_run_id,
        )
        db.add(job)
        db.commit()

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
    db: Session = Depends(get_db),
):
    """Delete a fill run and its associated files."""
    logger.info(f"Deleting fill run: {fill_run_id}", extra={"user_id": user.id})

    try:
        repo = TemplateRepository(db)
        fill_run = repo.get_fill_run(fill_run_id)

        if not fill_run or fill_run.user_id != user.id:
            raise HTTPException(status_code=404, detail="Fill run not found")

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
        fill_run = repo.get_fill_run(fill_run_id)

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
