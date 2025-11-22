# backend/app/services/tasks/document_processor.py
"""Celery tasks for Document indexing pipeline.

Pipeline: Parse → Chunk → Embed → Store

Reuses shared tasks from extraction.py:
- parse_document_task: Parse PDF to text
- chunk_document_task: Chunk text into sections
"""
from __future__ import annotations
from typing import Dict, Any

from celery import shared_task, chain
from sqlalchemy.sql import func

from app.database import get_db
from app.services.job_tracker import JobProgressTracker
from app.services.embeddings import get_embedding_provider
from app.repositories.collection_repository import CollectionRepository
from app.db_models_chat import DocumentChunk
from app.utils.logging import logger
from app.repositories.document_repository import DocumentRepository


def _get_db_session():
    return next(get_db())


@shared_task(bind=True)
def embed_chunks_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate embeddings for document chunks (Document indexing pipeline).

    Input payload:
        - chunks: List of chunks from chunk_document_task
        - job_id: JobState ID for progress tracking
        - document_id: Canonical Document ID (from documents table)

    Output payload:
        - All input fields
        - embeddings: List of embedding vectors
        - embedding_model: Model name used
        - embedding_dimension: Vector dimension
    """
    job_id = payload["job_id"]
    document_id = payload["document_id"]

    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id)

    try:
        tracker.update_progress(
            status="embedding",
            current_stage="embedding",
            progress_percent=40,
            message="Generating embeddings..."
        )

        chunks = payload.get("chunks", [])
        if not chunks:
            tracker.update_progress(
                progress_percent=50,
                message="No chunks to embed",
                details={"chunks_count": 0}
            )
            return {**payload, "embeddings": []}

        # Initialize embedding provider
        embedder = get_embedding_provider()
        logger.info(
            f"Embedding {len(chunks)} chunks using {embedder.provider_name} ({embedder.model_name})",
            extra={"job_id": job_id, "document_id": document_id}
        )

        # Extract texts for batch embedding
        texts = [chunk["text"] for chunk in chunks]

        # Generate embeddings in batches (efficient)
        batch_size = 50
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_embeddings = embedder.embed_batch(batch_texts)
            all_embeddings.extend(batch_embeddings)

            # Update progress
            progress = 40 + int((i / len(texts)) * 30)  # 40% to 70%
            tracker.update_progress(
                progress_percent=progress,
                message=f"Embedded {min(i + batch_size, len(texts))}/{len(texts)} chunks"
            )

        tracker.update_progress(
            progress_percent=70,
            message="Embeddings generated",
            details={
                "chunks_count": len(chunks),
                "embedding_model": embedder.model_name,
                "embedding_dimension": embedder.get_dimension()
            }
        )

        return {
            **payload,
            "embeddings": all_embeddings,
            "embedding_model": embedder.model_name,
            "embedding_dimension": embedder.get_dimension()
        }

    except Exception as e:
        tracker.mark_error(
            error_stage="embedding",
            error_message=str(e),
            error_type="embedding_error",
            is_retryable=True
        )
        # Mark canonical document as failed
        try:
            doc_repo = DocumentRepository()
            doc_repo.mark_failed(
                document_id=document_id,
                error_message=str(e)[:500]
            )
        except Exception:
            pass
        raise
    finally:
        db.close()


@shared_task(bind=True)
def store_vectors_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Store document chunks with embeddings in PostgreSQL vector store.

    Creates DocumentChunk records with pgvector embeddings for semantic search.

    Input payload:
        - chunks: List of chunks
        - embeddings: List of embedding vectors
        - job_id: JobState ID
        - document_id: Canonical Document ID (from documents table)
        - collection_id: Collection ID

    Output:
        - status: "completed"
        - document_id: Document ID
        - chunks_stored: Number of chunks stored
    """
    job_id = payload["job_id"]
    document_id = payload["document_id"]
    collection_id = payload["collection_id"]

    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id)

    try:
        tracker.update_progress(
            status="storing",
            current_stage="storing",
            progress_percent=75,
            message="Storing vectors in database..."
        )

        chunks = payload.get("chunks", [])
        embeddings = payload.get("embeddings", [])
        embedding_dimension = payload.get("embedding_dimension")

        # Validate inputs
        if len(chunks) != len(embeddings):
            raise ValueError(f"Chunk count ({len(chunks)}) does not match embedding count ({len(embeddings)})")

        if not chunks:
            raise ValueError("No chunks to store")

        # Validate embedding dimensions if provided
        if embeddings and embedding_dimension:
            actual_dim = len(embeddings[0]) if embeddings[0] else 0
            if actual_dim != embedding_dimension:
                logger.warning(
                    f"Embedding dimension mismatch: expected {embedding_dimension}, got {actual_dim}",
                    extra={"document_id": document_id, "collection_id": collection_id}
                )

        # Create DocumentChunk records with embeddings
        embedding_model = payload.get("embedding_model")
        db_chunks = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            db_chunk = DocumentChunk(
                document_id=document_id,
                text=chunk["text"],
                narrative_text =chunk.get("narrative_text", ""),
                tables=chunk.get("tables", []),
                chunk_index=i,
                embedding=embedding,
                embedding_model=embedding_model,
                embedding_version="1.0",  # Version for future migration tracking
                page_number=chunk.get("metadata", {}).get("page_number"),
                section_type=chunk.get("metadata", {}).get("section_type"),
                section_heading=chunk.get("metadata", {}).get("section_heading"),
                is_tabular=chunk.get("metadata", {}).get("has_tables", False),
                token_count=len(chunk["text"].split())  # Rough estimate
            )
            db_chunks.append(db_chunk)

        # Bulk insert chunks with error handling
        try:
            db.bulk_save_objects(db_chunks)
            db.commit()
            logger.info(
                f"Successfully bulk inserted {len(db_chunks)} chunks",
                extra={"document_id": document_id, "collection_id": collection_id}
            )
        except Exception as bulk_error:
            db.rollback()
            logger.error(
                f"Bulk insert failed: {bulk_error}",
                extra={"document_id": document_id, "chunks_count": len(db_chunks)}
            )
            raise ValueError(f"Failed to bulk insert chunks: {str(bulk_error)}")

        # Update canonical Document status and stats
        doc_repo = DocumentRepository()
        parser_info = payload.get("parser_output", {})
        page_count = parser_info.get("page_count", 0)
        processing_time_ms = parser_info.get("processing_time_ms", 0)
        parser_used = parser_info.get("parser_name", "unknown")

        doc_updated = doc_repo.mark_completed(
            document_id=document_id,
            chunk_count=len(db_chunks),
            page_count=page_count,
            processing_time_ms=processing_time_ms,
            parser_used=parser_used
        )

        if not doc_updated:
            logger.warning(
                f"Failed to update document status for {document_id}",
                extra={"document_id": document_id, "collection_id": collection_id}
            )

        # Update Collection stats using database aggregate functions
        # This recomputes document_count and total_chunks from the database,
        # ensuring accuracy and preventing race conditions from concurrent operations
        collection_repo = CollectionRepository()
        stats_updated = collection_repo.recompute_collection_stats(
            collection_id=collection_id,
            embedding_model=payload.get("embedding_model"),
            embedding_dimension=payload.get("embedding_dimension")
        )

        if not stats_updated:
            # Collection might have been deleted during indexing (edge case)
            logger.warning(
                f"Failed to recompute collection stats - collection may have been deleted",
                extra={"collection_id": collection_id, "document_id": document_id}
            )

        tracker.update_progress(
            progress_percent=95,
            message="Vectors stored successfully"
        )

        tracker.mark_completed()

        logger.info(
            f"Stored {len(db_chunks)} chunks with embeddings for document {document_id}",
            extra={"job_id": job_id, "collection_id": collection_id}
        )

        return {
            "status": "completed",
            "document_id": document_id,
            "collection_id": collection_id,
            "chunks_stored": len(db_chunks)
        }

    except Exception as e:
        tracker.mark_error(
            error_stage="storing",
            error_message=str(e),
            error_type="storage_error",
            is_retryable=True
        )
        # Mark canonical document as failed
        try:
            doc_repo = DocumentRepository()
            doc_repo.mark_failed(
                document_id=document_id,
                error_message=str(e)[:500]
            )
        except Exception:
            pass
        raise
    finally:
        db.close()


# ============================================================================
# PIPELINE ENTRY POINT
# ============================================================================


def start_document_indexing_chain(
    file_path: str,
    filename: str,
    job_id: str,
    document_id: str,  # Canonical Document ID (from documents table)
    collection_id: str,
    user_id: str,
    canonical_document_id: str | None = None,  # DEPRECATED: document_id is already canonical
    content_hash: str | None = None
):
    """
    Start the document indexing pipeline chain.

    Pipeline: Parse → Chunk → Embed → Store

    Args:
        file_path: Path to uploaded PDF file
        filename: Original filename
        job_id: JobState ID for progress tracking
        document_id: Canonical Document ID (from documents table)
        collection_id: Collection ID
        user_id: User ID
        canonical_document_id: DEPRECATED - document_id is already the canonical ID
        content_hash: SHA256 hash of file content (for deduplication tracking)

    Returns:
        Task ID of the chain
    """
    # Import shared tasks from extraction module
    from app.services.tasks.extraction import parse_document_task, chunk_document_task

    payload = {
        "file_path": file_path,
        "filename": filename,
        "job_id": job_id,
        "document_id": document_id,
        "collection_id": collection_id,
        "user_id": user_id,
        "extraction_id": document_id,  # For compatibility with shared parse/chunk tasks
        "mode": "document",  # Mark as document mode
        "canonical_document_id": canonical_document_id,
        "content_hash": content_hash,
    }

    # Chain: Parse → Chunk → Embed → Store
    # parse_document_task and chunk_document_task are SHARED from extraction.py
    task_chain = chain(
        parse_document_task.s(payload),
        chunk_document_task.s(),
        embed_chunks_task.s(),
        store_vectors_task.s(),
    )

    result = task_chain.apply_async()
    logger.info(
        "Document indexing pipeline started",
        extra={
            "user_id": user_id,
            "job_id": job_id,
            "task_id": result.id,
            "collection_id": collection_id,
            "document_id": document_id
        }
    )
    return result.id
