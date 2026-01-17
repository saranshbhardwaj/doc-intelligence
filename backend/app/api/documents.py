# backend/app/api/chat/documents.py
"""Document upload and management endpoints."""

import os
import shutil
import uuid
import hashlib
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends

from app.auth import get_current_user
from app.db_models_users import User
from app.database import SessionLocal
from app.db_models_chat import CollectionDocument
from app.db_models_documents import Document
from app.services.tasks import start_document_indexing_chain
from app.repositories.collection_repository import CollectionRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.job_repository import JobRepository
from app.utils.logging import logger
from app.config import settings

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

    Supported formats: PDF (digital & scanned), DOCX

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
        file: Document file (PDF or DOCX)
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
    collection = collection_repo.get_collection(collection_id, user.id)
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

    # Validate file type - Azure Document Intelligence supported formats
    # https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/
    ALLOWED_EXTENSIONS = {
        # Documents
        '.pdf',   # PDF (digital and scanned/OCR)
        '.docx',  # Microsoft Word
        # Note: Excel, PowerPoint, and images not supported yet
        # - Excel loses table structure (returned as paragraphs)
        # - PowerPoint needs slide-based chunking strategy
        # - Images need OCR-specific handling
    }

    file_ext = os.path.splitext(file.filename.lower())[1]
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file_ext}' not supported. "
                   f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
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

    # Validate PDF magic number
    if not file_bytes.startswith(b'%PDF-'):
        raise HTTPException(
            status_code=400,
            detail="File does not appear to be a valid PDF"
        )

    # Calculate content hash for global deduplication
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    # Check if document already exists (global deduplication)
    doc_repo = DocumentRepository()
    existing_doc = doc_repo.get_by_hash(content_hash)
    reuse_mode = existing_doc is not None and existing_doc.is_ready()

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
                f"Reusing existing document",
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
                document_id=existing_doc.id,  # Reference canonical document
                status="completed",
                current_stage="reused",
                progress_percent=100,
                message="Reused existing document; indexing skipped."
            )

            return {
                "document_id": existing_doc.id,
                "job_id": job.job_id if job else None,
                "filename": safe_filename,
                "status": "completed",
                "reuse": True,
                "message": "Document already indexed. Added to collection instantly."
            }

        else:
            # NEW DOCUMENT MODE: Create and process
            # Create canonical document FIRST to get its ID
            document = doc_repo.create_document(
                user_id=user.id,
                filename=safe_filename,
                file_path="",  # Will be updated after upload
                file_size_bytes=len(file_bytes),
                content_hash=content_hash,
                page_count=0,  # Will be updated during parsing
                status="processing"
            )

            if not document:
                raise HTTPException(status_code=500, detail="Failed to create document record")

            # Upload to storage using document's ID (ensures ID match)
            file_path = None
            try:
                # Generate storage key: documents/{user_id}/{document.id}.pdf
                storage_key = f"documents/{user.id}/{document.id}.pdf"
                storage.upload(temp_path, storage_key)
                file_path = storage_key  # Store storage key (not local path)

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
                    fallback_path = os.path.join(upload_dir, f"{document.id}_{safe_filename}")

                    shutil.move(temp_path, fallback_path)
                    file_path = fallback_path

                    logger.warning(
                        f"Fell back to local storage: {fallback_path}",
                        extra={"original_error": str(e)}
                    )
                except Exception as fallback_error:
                    # Both R2 and local storage failed - rollback document creation
                    logger.error(f"Local storage fallback also failed: {fallback_error}", exc_info=True)
                    doc_repo.delete_document(document.id)
                    raise HTTPException(
                        status_code=500,
                        detail="Failed to store document file (both R2 and local storage failed)"
                    )

            # Update document with file_path
            doc_repo.update_file_path(document.id, file_path)

            # Create collection link
            collection_doc = collection_repo.link_document_to_collection(
                collection_id=collection_id,
                document_id=document.id
            )

            if not collection_doc:
                raise HTTPException(status_code=500, detail="Failed to link document to collection")

            # Create JobState (references canonical document, not collection_document)
            job = job_repo.create_job(
                document_id=document.id,  # NEW: References canonical documents table
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
                f"Started document indexing",
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Upload failed, cleaning up",
            extra={
                "collection_id": collection_id,
                "file_name": safe_filename,
                "error": str(e)
            },
            exc_info=True
        )

        # Cleanup on failure
        if collection_doc:
            try:
                collection_repo.unlink_document_from_collection(collection_doc.id)
            except Exception as del_err:
                logger.error(f"Failed to delete collection link during cleanup: {del_err}")

        if document and not reuse_mode:
            try:
                doc_repo.delete_document(document.id)
            except Exception as del_err:
                logger.error(f"Failed to delete document during cleanup: {del_err}")

        # Delete uploaded file
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as del_err:
                logger.error(f"Failed to delete file during cleanup: {del_err}")

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

    # Get document and verify ownership
    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()

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

    finally:
        db.close()

    try:
        storage = get_storage_backend()

        # Check if it's a legacy local path or new storage key
        if is_legacy_path(file_path):
            # Legacy local file - stream directly
            if not os.path.exists(file_path):
                raise HTTPException(status_code=404, detail="Document file not found on disk")

            return FileResponse(
                path=file_path,
                media_type="application/pdf",
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
    user: User = Depends(get_current_user)
):
    """
    Delete a document from ALL collections (canonical deletion).

    In the new schema, documents are canonical. Deleting a document
    removes it from all collections and deletes all chunks.

    Args:
        document_id: Canonical document ID to delete
        user: Authenticated user

    Returns:
        Success message

    Raises:
        HTTPException 403: User doesn't own the document
        HTTPException 404: Document not found
        HTTPException 500: Deletion failed
    """
    doc_repo = DocumentRepository()

    # Get document and verify ownership
    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        # Verify user owns this document
        if document.user_id != user.id:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to delete this document"
            )

        # Store info for response before deletion
        filename = document.filename
        file_path = document.file_path
        chunk_count = document.chunk_count or 0

    finally:
        db.close()

    # Delete document (cascades to chunks, collection_documents, job_states)
    success = doc_repo.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete document")

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
                    logger.info(f"Deleted legacy local file", extra={"document_id": document_id, "file_path": file_path})
            else:
                # New storage key (R2 or structured local) - use storage backend
                storage.delete(file_path)
                logger.info(f"Deleted file from {storage.get_storage_type()} storage", extra={"document_id": document_id, "storage_key": file_path})

        except Exception as e:
            logger.warning(f"Failed to delete physical file: {e}", extra={"file_path": file_path})

    logger.info(
        f"Document deleted",
        extra={
            "document_id": document_id,
            "file_name": filename,
            "chunks_removed": chunk_count
        }
    )

    return {
        "success": True,
        "document_id": document_id,
        "filename": filename,
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
    usage_data = document_repo.get_document_usage(document_id, user.id)

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
