"""Private Equity Extraction API - Vertical-specific extraction endpoints.

Routes: /api/v1/pe/extraction/*

Provides extraction functionality for PE vertical.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body, Request
from fastapi.responses import JSONResponse, Response
from typing import Optional
from pydantic import BaseModel

from app.auth import get_current_user
from app.db_models_users import User
from app.repositories.extraction_repository import ExtractionRepository
from app.utils.logging import logger
from app.models import ExtractionListItem, PaginatedExtractionResponse

# Reuse request models from main API
from app.api.extractions import LibraryExtractionRequest

router = APIRouter(prefix="/extraction", tags=["pe_extraction"])


@router.get("", response_model=PaginatedExtractionResponse)
async def list_pe_extractions(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    user: User = Depends(get_current_user)
):
    """List extractions for PE vertical (user's extractions)."""
    logger.info("Listing PE extractions", extra={"user_id": user.id, "limit": limit, "offset": offset})
    repo = ExtractionRepository()
    extractions, total = repo.list_user_extractions(user.id, limit=limit, offset=offset, status=status)
    result = []
    for e in extractions:
        result.append(ExtractionListItem(
            id=e.id,
            document_id=getattr(e, "document_id", None),
            filename=e.filename,
            page_count=e.page_count,
            status=e.status,
            created_at=e.created_at,
            completed_at=e.completed_at,
            cost_usd=e.cost_usd,
            parser_used=e.parser_used,
            from_cache=e.from_cache,
            error_message=e.error_message,
        ))
    return PaginatedExtractionResponse(
        items=result,
        total=total,
        limit=limit,
        offset=offset
    )


@router.post("")
async def extract_pe_document(
    file: UploadFile = File(...),
    context: str = Form(None),
    request: Request = None,
    user: User = Depends(get_current_user)
):
    """Extract CIM data from uploaded document (PE vertical).

    Delegates to main extraction endpoint.
    """
    from app.api.extractions import extract_document as main_extract
    return await main_extract(file, context, request, user)


@router.get("/{extraction_id}")
async def get_pe_extraction_result(extraction_id: str, user: User = Depends(get_current_user)):
    """Get extraction result by ID."""
    from app.api.extractions import get_extraction_result as main_get
    return await main_get(extraction_id)


@router.post("/temp")
async def extract_pe_temp_document(
    file: UploadFile = File(...),
    context: str = Form(None),
    user: User = Depends(get_current_user)
):
    """Upload temporary file for extraction (no library save)."""
    from app.api.extractions import extract_temp_document as main_temp
    return await main_temp(file, context, user)


@router.post("/documents/{document_id}")
async def extract_from_pe_library_document(
    document_id: str,
    request: LibraryExtractionRequest = Body(default=LibraryExtractionRequest()),
    user: User = Depends(get_current_user)
):
    """Run extraction on existing library document."""
    from app.api.extractions import extract_from_document as main_from_doc
    return await main_from_doc(document_id, request, user)


@router.delete("/{extraction_id}")
async def delete_pe_extraction(
    extraction_id: str,
    user: User = Depends(get_current_user)
):
    """Delete an extraction and its artifacts."""
    from app.api.extractions import delete_extraction as main_delete
    return await main_delete(extraction_id, user)


@router.post("/{extraction_id}/retry")
async def retry_pe_extraction(
    extraction_id: str,
    user: User = Depends(get_current_user)
):
    """Retry a failed extraction."""
    from app.api.extractions import retry_extraction as main_retry
    return await main_retry(extraction_id, user)


@router.get("/{extraction_id}/export")
async def export_pe_extraction(
    extraction_id: str,
    format: str = 'word',
    user: User = Depends(get_current_user)
):
    """Export extraction result to Word or Excel."""
    from app.api.extractions import export_extraction as main_export
    return await main_export(extraction_id, format, user)
