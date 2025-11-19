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
from app.db_models_documents import Document
from app.services.tasks import start_chat_indexing_chain
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
    Upload a PDF to a collection and start async indexing.

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
        file: PDF file to upload
        user: Current user

    Returns:
        job_id and document_id for tracking indexing progress

    Raises:
        HTTPException 400: Invalid file
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

    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

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

    # Save file to disk
    upload_dir = os.path.join("uploads", "chat", collection_id)
    os.makedirs(upload_dir, exist_ok=True)

    safe_filename = os.path.basename(file.filename)
    file_path = os.path.join(upload_dir, f"{uuid.uuid4()}_{safe_filename}")

    document = None
    collection_doc = None
    job_repo = JobRepository()

    try:
        # Save file
        try:
            with open(file_path, "wb") as f:
                f.write(file_bytes)
        except IOError as e:
            logger.error(f"Failed to write file to disk: {e}")
            raise HTTPException(status_code=500, detail="Failed to save file to disk")

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
            # Create canonical document first
            document = doc_repo.create_document(
                user_id=user.id,
                filename=safe_filename,
                file_path=file_path,
                file_size_bytes=len(file_bytes),
                content_hash=content_hash,
                page_count=0,  # Will be updated during parsing
                status="processing"
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
            task_id = start_chat_indexing_chain(
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

    # Delete physical file if it exists
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.info(f"Deleted physical file", extra={"document_id": document_id, "file_path": file_path})
        except Exception as e:
            logger.warning(f"Failed to delete physical file: {e}")

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
