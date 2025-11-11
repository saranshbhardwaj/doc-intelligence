# backend/app/api/chat/documents.py
"""Document upload and management endpoints for Chat Mode."""

import os
import uuid
import hashlib
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends

from app.auth import get_current_user
from app.db_models_users import User
from app.database import SessionLocal
from app.db_models_chat import CollectionDocument
from app.services.tasks import start_chat_indexing_chain
from app.repositories.collection_repository import CollectionRepository
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
    Upload a PDF to a collection and start async indexing.

    Flow:
    1. Validate file (type, size, name)
    2. Save file to disk
    3. Create CollectionDocument record
    4. Create JobState for progress tracking
    5. Start Celery indexing chain (parse → chunk → embed → store)
    6. Return job_id for SSE progress tracking

    Args:
        collection_id: Collection ID (UUID format)
        file: PDF file to upload
        user: Current user

    Returns:
        job_id and document_id for tracking indexing progress

    Raises:
        HTTPException 400: Invalid file (wrong type, too large, empty, bad name)
        HTTPException 404: Collection not found
        HTTPException 409: Duplicate document (same content hash)
        HTTPException 413: File too large
        HTTPException 500: Server error during upload/processing
    """
    # Verify collection exists and belongs to user
    collection_repo = CollectionRepository()
    collection = collection_repo.get_collection(collection_id, user.id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Edge case: Validate filename exists
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Edge case: Validate filename length
    if len(file.filename) > MAX_FILENAME_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Filename too long (max {MAX_FILENAME_LENGTH} characters)"
        )

    # Edge case: Validate file type by extension
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Edge case: Validate content type header if provided
    if file.content_type and not file.content_type.lower().startswith('application/pdf'):
        logger.warning(
            f"Suspicious content type for PDF upload",
            extra={
                "filename": file.filename,
                "content_type": file.content_type,
                "user_id": user.id
            }
        )
        # Allow but log - some clients send wrong content types

    # Read file and validate size
    try:
        file_bytes = await file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(status_code=400, detail="Failed to read uploaded file")

    # Edge case: Validate file is not empty
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Edge case: Validate file size
    file_size_mb = len(file_bytes) / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({file_size_mb:.1f}MB). Maximum size is {MAX_FILE_SIZE_MB}MB"
        )

    # Edge case: Validate PDF magic number (basic PDF validation)
    if not file_bytes.startswith(b'%PDF-'):
        raise HTTPException(
            status_code=400,
            detail="File does not appear to be a valid PDF (missing PDF header)"
        )

    # Calculate content hash for duplicate detection
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    # Check for duplicate in this collection
    existing_doc = collection_repo.check_duplicate_document(collection_id, content_hash)
    if existing_doc:
        raise HTTPException(
            status_code=409,
            detail=f"This document already exists in the collection: {existing_doc.filename}"
        )

    # Save file to disk
    upload_dir = os.path.join("uploads", "chat", collection_id)
    os.makedirs(upload_dir, exist_ok=True)

    # Edge case: Sanitize filename to prevent path traversal
    safe_filename = os.path.basename(file.filename)  # Remove any path components
    file_path = os.path.join(upload_dir, f"{uuid.uuid4()}_{safe_filename}")

    document = None
    job_repo = JobRepository()

    try:
        # Save file with proper error handling
        try:
            with open(file_path, "wb") as f:
                f.write(file_bytes)
        except IOError as e:
            logger.error(f"Failed to write file to disk: {e}")
            raise HTTPException(status_code=500, detail="Failed to save file to disk")

        # Create CollectionDocument record
        document = collection_repo.create_document(
            collection_id=collection_id,
            filename=safe_filename,
            file_path=file_path,
            file_size_bytes=len(file_bytes),
            page_count=0,  # Will be updated during parsing
            content_hash=content_hash
        )

        if not document:
            raise HTTPException(status_code=500, detail="Failed to create document record")

        # Create JobState for progress tracking (Chat Mode)
        job = job_repo.create_job(
            collection_document_id=document.id,  # Chat Mode uses collection_document_id
            status="queued",
            current_stage="queued",
            progress_percent=0,
            message="Queued for processing..."
        )

        if not job:
            raise HTTPException(status_code=500, detail="Failed to create job tracking record")

        # Update collection document count
        documents = collection_repo.list_documents(collection_id)
        collection_repo.update_collection_stats(
            collection_id=collection_id,
            document_count=len(documents)
        )

        # Start Celery indexing chain
        task_id = start_chat_indexing_chain(
            file_path=file_path,
            filename=safe_filename,
            job_id=job.id,
            document_id=document.id,
            collection_id=collection_id,
            user_id=user.id
        )

        logger.info(
            f"Started document indexing",
            extra={
                "document_id": document.id,
                "collection_id": collection_id,
                "job_id": job.id,
                "task_id": task_id,
                "file_name": safe_filename,
                "file_size_mb": round(file_size_mb, 2)
            }
        )

        return {
            "document_id": document.id,
            "job_id": job.id,
            "task_id": task_id,
            "filename": safe_filename,
            "status": "processing",
            "message": "Document indexing started. Use job_id to track progress via SSE."
        }

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Cleanup on failure: delete document (cascades to job_state), delete file
        logger.error(
            f"Upload failed, cleaning up",
            extra={
                "collection_id": collection_id,
                "file_name": safe_filename,
                "error": str(e)
            },
            exc_info=True
        )

        # Delete document record (cascades to job_state due to ON DELETE CASCADE)
        if document:
            try:
                collection_repo.delete_document(document.id)
            except Exception as del_err:
                logger.error(f"Failed to delete document record during cleanup: {del_err}")

        # Delete uploaded file
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as del_err:
                logger.error(f"Failed to delete file during cleanup: {del_err}")

        # Re-raise as 500 error
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    user: User = Depends(get_current_user)
):
    """
    Delete a document from a collection.

    Removes document record, associated chunks, job states, and physical file.
    Requires user to own the collection.

    Args:
        document_id: Document ID to delete (UUID format)
        user: Authenticated user

    Returns:
        Success message with deleted document details

    Raises:
        HTTPException 403: User doesn't own the collection
        HTTPException 404: Document not found
        HTTPException 500: Deletion failed
    """
    collection_repo = CollectionRepository()

    # Get document (with collection ownership check)
    db = SessionLocal()
    try:
        document = db.query(CollectionDocument).filter(
            CollectionDocument.id == document_id
        ).first()

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        # Verify user owns the collection
        collection = collection_repo.get_collection(document.collection_id, user.id)
        if not collection:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to delete this document"
            )

        # Store info for response and cleanup before deletion
        filename = document.filename
        collection_id = document.collection_id
        file_path = document.file_path
        chunk_count = document.chunk_count or 0

    finally:
        db.close()

    # Delete document from database (cascades to chunks and job_states)
    success = collection_repo.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete document from database")

    # Delete physical file if it exists
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.info(
                f"Deleted physical file",
                extra={"document_id": document_id, "file_path": file_path}
            )
        except Exception as e:
            # Log warning but don't fail the request - DB cleanup succeeded
            logger.warning(
                f"Failed to delete physical file (DB record deleted successfully): {e}",
                extra={"document_id": document_id, "file_path": file_path, "error": str(e)}
            )

    # Update collection stats
    try:
        collection_repo.update_collection_stats(
            collection_id=collection_id,
            total_chunks=max(0, (collection.total_chunks or 0) - chunk_count)
        )
    except Exception as e:
        # Log but don't fail - document is already deleted
        logger.warning(f"Failed to update collection stats after document deletion: {e}")

    logger.info(
        f"Document deleted",
        extra={
            "document_id": document_id,
            "collection_id": collection_id,
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
