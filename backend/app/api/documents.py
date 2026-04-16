# backend/app/api/chat/documents.py
"""Document upload and management endpoints."""

import os
import shutil
import uuid
import hashlib
from io import BytesIO
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Request, Query

from app.auth import get_current_user, get_current_org_role, is_admin_role
from app.db_models_users import User
from app.services.tasks import start_document_indexing_chain
from app.repositories.collection_repository import CollectionRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.job_repository import JobRepository
from app.services.beta_limits import enforce_page_limit
from app.utils.document_uploads import (
    SUPPORTED_UPLOAD_EXTENSIONS,
    get_content_type_for_filename,
    validate_uploaded_file_signature,
)
from app.utils.logging import logger

router = APIRouter()

# Constants
MAX_FILE_SIZE_MB = 50  # Maximum PDF file size
MAX_FILENAME_LENGTH = 255  # Maximum filename length


@router.post("/collections/{collection_id}/documents")
async def upload_document(
    collection_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user)
):
    """
    Upload a document to a collection and start async indexing.

    Supported formats: PDF, DOCX, PPTX, and supported image files

    New Schema Flow:
    1. Validate file (type, size, name)
    2. Calculate content_hash for deduplication
    3. Check if Document with this hash already exists (global dedup)
    4. If exists and ready: Link to collection + copy chunks (instant)
    5. If not exists: Create Document + CollectionDocument link
    6. Create JobState for progress tracking (references document_id)
    7. Start Celery indexing chain
    8. Return job_id for SSE progress tracking

    Args:
        collection_id: Collection ID (UUID format)
        file: Document file (PDF, DOCX, PPTX, or supported image)
        user: Current user

    Returns:
        job_id and document_id for tracking indexing progress

    Raises:
        HTTPException 400: Invalid file or unsupported format
        HTTPException 404: Collection not found
        HTTPException 413: File too large
        HTTPException 500: Server error
    """
    # Verify collection exists and belongs to user
    collection_repo = CollectionRepository()
    collection = collection_repo.get_collection(collection_id, user.id, user.org_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Validate filename
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    if len(file.filename) > MAX_FILENAME_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Filename too long (max {MAX_FILENAME_LENGTH} characters)"
        )

    file_ext = os.path.splitext(file.filename.lower())[1]
    if file_ext not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file_ext}' not supported. "
                   f"Allowed: {', '.join(sorted(SUPPORTED_UPLOAD_EXTENSIONS))}"
        )

    # Read file and validate
    try:
        file_bytes = await file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(status_code=400, detail="Failed to read uploaded file")

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    file_size_mb = len(file_bytes) / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({file_size_mb:.1f}MB). Maximum size is {MAX_FILE_SIZE_MB}MB"
        )

    validation_error = validate_uploaded_file_signature(file_ext, file_bytes)
    if validation_error:
        raise HTTPException(status_code=400, detail=validation_error)

    # Calculate content hash for global deduplication
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    # Check if document already exists (global deduplication)
    doc_repo = DocumentRepository()
    existing_doc = doc_repo.get_by_hash(content_hash, user.org_id)
    reuse_mode = existing_doc is not None and existing_doc.is_ready()

    # Enforce page limits only for new indexing jobs.
    # Reused documents are already indexed and do not consume additional pages.
    if not reuse_mode and file_ext == ".pdf":
        estimated_pages = 0
        try:
            from PyPDF2 import PdfReader

            estimated_pages = len(PdfReader(BytesIO(file_bytes)).pages)
        except Exception as e:
            logger.warning(
                "Failed to estimate PDF page count before upload; deferring to pipeline check",
                extra={"filename": file.filename, "error": str(e)},
            )

        if estimated_pages > 0:
            enforce_page_limit(user, pages_to_add=estimated_pages)

    # Initialize storage backend
    from app.core.storage.storage_factory import get_storage_backend
    storage = get_storage_backend()

    safe_filename = os.path.basename(file.filename)

    # Generate unique temp ID for temp file
    temp_id = str(uuid.uuid4())

    # Save to temp file first (needed for storage upload)
    temp_path = os.path.join("/tmp", f"upload_{temp_id}_{safe_filename}")
    file_path = None  # Will be set after storage upload

    document = None
    collection_doc = None
    job_repo = JobRepository()

    try:
        # Save to temp file
        try:
            with open(temp_path, "wb") as f:
                f.write(file_bytes)
        except IOError as e:
            logger.error(f"Failed to write file to temp: {e}")
            raise HTTPException(status_code=500, detail="Failed to save file temporarily")

        if reuse_mode and existing_doc:
            # REUSE MODE: Document already processed
            logger.info(
                "Reusing existing document",
                extra={
                    "content_hash": content_hash,
                    "existing_document_id": existing_doc.id,
                    "collection_id": collection_id
                }
            )

            # Use existing canonical document
            document = existing_doc

            # Create collection link
            collection_doc = collection_repo.link_document_to_collection(
                collection_id=collection_id,
                document_id=existing_doc.id
            )

            # Copy chunks to maintain per-collection isolation (if needed)
            # For now, chunks are global - just update stats
            collection_repo.recompute_collection_stats(collection_id=collection_id)

            # Create completed job for UI consistency
            job = job_repo.create_job(
                entity_type="document",
                entity_id=existing_doc.id,  # Reference canonical document
                status="completed",
                current_stage="reused",
                progress_percent=100,
                message="Reused existing document; indexing skipped."
            )

            return {
                "document_id": existing_doc.id,
                "existing_filename": existing_doc.filename,
                "job_id": job.job_id if job else None,
                "filename": safe_filename,
                "status": "completed",
                "reuse": True,
                "message": "Document already indexed. Added to collection instantly."
            }

        else:
            # NEW DOCUMENT MODE: Create and process
            #
            # Operation order matters for atomicity:
            #   1. Upload file to storage FIRST — if this fails, no DB row is created.
            #   2. Create the document record with the real file_path already known — single commit.
            #   3. Link to collection, create job.
            #
            # This prevents orphaned 'processing' rows with an empty file_path from
            # appearing in the UI when a storage upload or subsequent DB write fails.

            # --- Step 1: Upload to storage (before any DB writes) ---
            # We need a stable document ID for the storage key, so generate one up front.
            pre_assigned_id = str(uuid.uuid4())

            file_path = None
            try:
                # Generate storage key: documents/{YYYY}/{MM}/{DD}/{document_id}_{filename}
                # Date-partitioned, consistent with workflow-artifacts. Readable in R2 browser.
                from datetime import datetime as _dt
                _now = _dt.utcnow()
                storage_key = (
                    f"documents/{_now.year}/{_now.month:02d}/{_now.day:02d}"
                    f"/{pre_assigned_id}_{safe_filename}"
                )
                storage.upload(temp_path, storage_key)
                file_path = storage_key

                logger.info(
                    f"Uploaded document to {storage.get_storage_type()} storage",
                    extra={"storage_key": storage_key}
                )

            except Exception as e:
                logger.error(f"Storage upload failed: {e}", exc_info=True)

                # Fallback to local filesystem if R2 fails
                try:
                    upload_dir = os.path.join("uploads", "chat", collection_id)
                    os.makedirs(upload_dir, exist_ok=True)
                    fallback_path = os.path.join(upload_dir, f"{pre_assigned_id}_{safe_filename}")

                    shutil.move(temp_path, fallback_path)
                    file_path = fallback_path

                    logger.warning(
                        f"Fell back to local storage: {fallback_path}",
                        extra={"original_error": str(e)}
                    )
                except Exception as fallback_error:
                    # Both R2 and local storage failed — no DB row has been created yet.
                    logger.error(f"Local storage fallback also failed: {fallback_error}", exc_info=True)
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to store document file (both R2 and local storage failed)"
                    )

            # --- Step 2: Create document record with real file_path (single commit) ---
            document = doc_repo.create_document(
                org_id=user.org_id,
                user_id=user.id,
                filename=safe_filename,
                file_path=file_path,
                file_size_bytes=len(file_bytes),
                content_hash=content_hash,
                page_count=0,  # Will be updated during parsing
                status="processing",
                document_id=pre_assigned_id,
            )

            if not document:
                raise HTTPException(status_code=500, detail="Failed to create document record")

            # Create collection link
            collection_doc = collection_repo.link_document_to_collection(
                collection_id=collection_id,
                document_id=document.id
            )

            if not collection_doc:
                raise HTTPException(status_code=500, detail="Failed to link document to collection")

            # Create JobState (references canonical document, not collection_document)
            job = job_repo.create_job(
                entity_type="document",
                entity_id=document.id,  # NEW: References canonical documents table
                status="queued",
                current_stage="queued",
                progress_percent=0,
                message="Queued for processing..."
            )

            if not job:
                raise HTTPException(status_code=500, detail="Failed to create job tracking record")

            # Update collection stats
            collection_repo.recompute_collection_stats(collection_id=collection_id)

            # Start Celery indexing chain
            task_id = start_document_indexing_chain(
                file_path=file_path,
                filename=safe_filename,
                job_id=job.job_id,
                document_id=document.id,  # Canonical document ID
                collection_id=collection_id,
                user_id=user.id
            )

            logger.info(
                "Started document indexing",
                extra={
                    "user_id": user.id,
                    "document_id": document.id,
                    "collection_id": collection_id,
                    "job_id": job.job_id,
                    "task_id": task_id,
                    "file_name": safe_filename,
                    "file_size_mb": round(file_size_mb, 2)
                }
            )

            return {
                "document_id": document.id,
                "job_id": job.job_id,
                "task_id": task_id,
                "filename": safe_filename,
                "status": "processing",
                "reuse": False,
                "message": "Document indexing started. Use job_id to track progress via SSE."
            }

    except Exception as e:
        # Cleanup on any failure (including HTTPException)
        logger.error(
            "Upload failed, cleaning up",
            extra={
                "collection_id": collection_id,
                "file_name": safe_filename,
                "error": str(e)
            },
            exc_info=True
        )

        # Cleanup collection link
        if collection_doc:
            try:
                collection_repo.unlink_document_from_collection(collection_doc.id)
            except Exception as del_err:
                logger.error(f"Failed to delete collection link during cleanup: {del_err}")

        # Cleanup document (only if new, not reused)
        if document and not reuse_mode:
            try:
                doc_repo.delete_document(document.id)
                logger.info("Cleaned up orphaned document during error handling", extra={"document_id": document.id})
            except Exception as del_err:
                logger.error(f"Failed to delete document during cleanup: {del_err}")

        # Cleanup local fallback file (R2 storage keys are not local paths)
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as del_err:
                logger.error(f"Failed to delete local fallback file during cleanup: {del_err}")

        # Re-raise original exception
        if isinstance(e, HTTPException):
            raise
        else:
            raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: str,
    user: User = Depends(get_current_user)
):
    """
    Get presigned URL for PDF download/viewing.

    For R2-stored PDFs: Returns presigned URL (valid 2 hours)
    For local files: Streams file directly (backward compatibility)

    Args:
        document_id: Document ID (UUID format)
        user: Authenticated user

    Returns:
        {
            "url": "https://...",  # Presigned URL for R2, or relative path for local
            "expires_in": 7200,  # Seconds until URL expires (R2 only)
            "storage_backend": "r2" | "local"
        }

    Raises:
        HTTPException 403: User doesn't own the document
        HTTPException 404: Document not found or file missing
    """
    from fastapi.responses import FileResponse
    from app.core.storage.storage_factory import get_storage_backend, is_legacy_path

    # Get document and verify ownership via repository
    doc_repo = DocumentRepository()
    document = doc_repo.get_by_id(document_id, user.org_id)

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Verify user owns this document
    if document.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to access this document"
        )

    file_path = document.file_path

    if not file_path:
        raise HTTPException(status_code=404, detail="Document file path not found")

    try:
        storage = get_storage_backend()

        # Check if it's a legacy local path or new storage key
        if is_legacy_path(file_path):
            # Legacy local file - stream directly
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="Document file not found on disk")

            media_type = get_content_type_for_filename(document.filename)

            return FileResponse(
                path=file_path,
                media_type=media_type,
                filename=document.filename
            )

        else:
            # Generate presigned URL from storage (R2)
            try:
                presigned_url = storage.generate_presigned_url(file_path, expiry_seconds=7200)
                storage_type = storage.get_storage_type()

                return {
                    "url": presigned_url,
                    "expires_in": 7200,
                    "storage_backend": storage_type
                }
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Document file not found in storage")
            except Exception as e:
                logger.error(f"Failed to generate presigned URL: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail="Failed to generate presigned URL")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate download URL: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate download URL")


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    collection_id: Optional[str] = Query(
        default=None,
        description="Collection context for safe delete. If document is linked to multiple collections, it will be unlinked from this collection only."
    ),
    user: User = Depends(get_current_user),
    request: Request = None
):
    """
    Delete or unlink a document depending on collection usage.

    Behavior:
    - If `collection_id` is provided and the document is linked to multiple
      collections, the document is unlinked from that collection only.
    - If the document is linked to only one collection (or no collection
      context is provided), perform canonical hard delete.

    Args:
        document_id: Canonical document ID to delete
        collection_id: Optional collection context for safe scoped deletion
        user: Authenticated user

    Returns:
        Success payload with action: "unlinked" or "deleted"

    Raises:
        HTTPException 403: User doesn't own the document
        HTTPException 404: Document not found
        HTTPException 500: Deletion failed
    """
    doc_repo = DocumentRepository()
    collection_repo = CollectionRepository()

    # Get document and verify ownership via repository
    document = doc_repo.get_by_id(document_id, user.org_id)

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Owner can delete; otherwise admin role required
    if document.user_id != user.id:
        role = get_current_org_role(request)
        if not is_admin_role(role):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to delete this document"
            )

    # If collection context is provided, validate access + link first.
    # When a document is shared across multiple collections, we unlink only.
    if collection_id:
        collection = collection_repo.get_collection(collection_id, user.id, user.org_id)
        if not collection:
            # Allow org admins to scope-delete from any collection in their org.
            collection = collection_repo.get_collection_by_id(collection_id, org_id=user.org_id)
            if not collection:
                raise HTTPException(status_code=404, detail="Collection not found")
            role = get_current_org_role(request)
            if not is_admin_role(role):
                raise HTTPException(
                    status_code=403,
                    detail="You don't have permission to modify this collection"
                )

        linked = doc_repo.is_linked_to_collection(document_id, collection_id, user.org_id)
        if not linked:
            raise HTTPException(
                status_code=404,
                detail="Document is not linked to this collection"
            )

        link_count = doc_repo.get_collection_link_count(document_id, user.org_id)
        vdr_ref_count = doc_repo.get_vdr_reference_count(document_id)
        if link_count > 1 or vdr_ref_count > 0:
            success = collection_repo.remove_document_from_collection(collection_id, document_id)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to unlink document from collection")

            logger.info(
                "Document unlinked from collection",
                extra={
                    "document_id": document_id,
                    "collection_id": collection_id,
                    "remaining_collections": link_count - 1,
                    "user_id": user.id,
                }
            )
            return {
                "success": True,
                "action": "unlinked",
                "document_id": document_id,
                "filename": document.filename,
                "collection_id": collection_id,
                "remaining_collections": max(link_count - 1, 0),
                "message": f"Document '{document.filename}' removed from this collection",
            }

    # Store info for response before hard deletion
    filename = document.filename
    file_path = document.file_path
    chunk_count = document.chunk_count or 0
    linked_collection_ids = doc_repo.get_linked_collection_ids(document_id, user.org_id)

    # Delete document (cascades to chunks, collection_documents, job_states)
    success = doc_repo.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete document")

    # Recompute cached collection stats for affected collections.
    for linked_collection_id in linked_collection_ids:
        collection_repo.recompute_collection_stats(linked_collection_id)

    # Delete physical file from storage (R2 or local)
    if file_path:
        try:
            from app.core.storage.storage_factory import get_storage_backend, is_legacy_path
            storage = get_storage_backend()

            # Check if it's a legacy local path or new storage key
            if is_legacy_path(file_path):
                # Legacy local file - delete directly
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info("Deleted legacy local file", extra={"document_id": document_id, "file_path": file_path})
            else:
                # New storage key (R2 or structured local) - use storage backend
                storage.delete(file_path)
                logger.info(f"Deleted file from {storage.get_storage_type()} storage", extra={"document_id": document_id, "storage_key": file_path})

        except Exception as e:
            logger.warning(f"Failed to delete physical file: {e}", extra={"file_path": file_path})

    logger.info(
        "Document deleted",
        extra={
            "document_id": document_id,
            "file_name": filename,
            "chunks_removed": chunk_count
        }
    )

    return {
        "success": True,
        "action": "deleted",
        "document_id": document_id,
        "filename": filename,
        "collections_removed": len(linked_collection_ids),
        "message": f"Document '{filename}' deleted successfully"
    }


@router.get("/documents/{document_id}/usage")
async def get_document_usage(
    document_id: str,
    user: User = Depends(get_current_user)
):
    """
    Get document usage across all modes (chat, extract, workflow).

    Args:
        document_id: Document ID (UUID format)
        user: Current user

    Returns:
        Document usage statistics

    Raises:
        HTTPException 404: Document not found or access denied

    Input:
        - document_id: str (from path)
        - user_id: str (from auth)

    Output:
        {
            "document_id": "uuid",
            "document_name": "Q4 Report.pdf",
            "usage": {
                "chat_sessions": [
                    {"session_id": "uuid", "title": "Q4 Analysis", "created_at": "2025-01-24T10:00:00Z"},
                    ...
                ],
                "extracts": [
                    {"request_id": "uuid", "created_at": "2025-01-24T10:00:00Z", "status": "completed"},
                    ...
                ],
                "workflows": [
                    {"run_id": "uuid", "workflow_name": "Investment Analysis", "created_at": "2025-01-24T10:00:00Z"},
                    ...
                ]
            },
            "total_usage_count": 4
        }
    """
    document_repo = DocumentRepository()

    # Get usage statistics
    usage_data = document_repo.get_document_usage(document_id, user.id, user.org_id)

    if not usage_data:
        raise HTTPException(
            status_code=404,
            detail="Document not found or access denied"
        )

    logger.debug(
        "Retrieved document usage via API",
        extra={
            "document_id": document_id,
            "user_id": user.id,
            "total_usage": usage_data["total_usage_count"]
        }
    )

    return usage_data
