# backend/app/services/tasks/document_processor.py
"""Celery tasks for Document indexing pipeline (Library uploads).

Pipeline: Parse → Chunk → Embed → Store

This pipeline is ONLY for document uploads to the Library.
It does NOT handle extraction logic (that's in tasks/extractions/).
"""
from __future__ import annotations
from typing import Dict, Any
import json
import asyncio
import os
from pathlib import Path

from celery import shared_task, chain
from sqlalchemy.sql import func

from app.database import get_db
from app.services.job_tracker import JobProgressTracker
from app.core.embeddings import get_embedding_provider
from app.core.parsers import ParserFactory
from app.core.chunkers import ChunkerFactory
from app.repositories.collection_repository import CollectionRepository
from app.repositories.document_repository import DocumentRepository
from app.db_models_chat import DocumentChunk
from app.utils.logging import logger
from app.utils.pdf_utils import detect_pdf_type
from app.utils.file_utils import save_raw_text, save_chunks
from app.config import settings
from app.core.storage.storage_factory import get_storage_backend


def _get_db_session():
    return next(get_db())


# ============================================================================
# DOCUMENT INDEXING TASKS (Library Upload Pipeline)
# ============================================================================


@shared_task(bind=True)
def parse_document_for_indexing_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse PDF document for library indexing.

    Input payload:
        - file_path: Path to uploaded PDF
        - filename: Original filename
        - job_id: JobState ID for progress tracking
        - document_id: Canonical Document ID (from documents table)
        - user_id: User ID

    Output payload:
        - All input fields
        - pdf_type: "digital" or "scanned"
        - parser_output: Parser output with text and metadata
    """
    job_id = payload["job_id"]
    document_id = payload["document_id"]
    file_path = payload["file_path"]
    filename = payload["filename"]

    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id)
    doc_repo = DocumentRepository()

    local_file_path = None  # Track if we downloaded from storage

    try:
        tracker.update_progress(
            status="parsing",
            current_stage="parsing",
            progress_percent=5,
            message="Parsing document..."
        )

        # Download from storage if needed (file_path is storage key, not local path)
        if not Path(file_path).exists():
            storage = get_storage_backend()
            local_file_path = f"/tmp/doc_{document_id}_{filename}"

            logger.info(
                f"Downloading document from storage",
                extra={"storage_key": file_path, "local_path": local_file_path}
            )

            storage.download(file_path, local_file_path)
            file_path = local_file_path  # Use local path for processing

        # Detect PDF type
        pdf_type = detect_pdf_type(file_path)
        tracker.update_progress(
            progress_percent=8,
            message=f"Detected {pdf_type} PDF"
        )

        # Get parser
        parser = ParserFactory.get_parser(settings.force_user_tier or "free", pdf_type)
        if not parser:
            raise ValueError("No parser available for detected PDF type")

        logger.info(
            f"Parsing document for indexing: {filename}",
            extra={"document_id": document_id, "job_id": job_id, "pdf_type": pdf_type}
        )

        # Run async parser
        parser_output = asyncio.run(parser.parse(file_path, pdf_type))

        # Save raw text for debugging
        save_raw_text(document_id, parser_output.text, filename)

        tracker.update_progress(
            progress_percent=15,
            message="Parsing complete",
            parsing_completed=True
        )

        logger.info(
            f"Parsed document: {parser_output.page_count} pages, {len(parser_output.text)} chars",
            extra={"document_id": document_id, "parser": parser_output.parser_name}
        )

        return {
            **payload,
            "pdf_type": pdf_type,
            "parser_output": {
                "text": parser_output.text,
                "page_count": parser_output.page_count,
                "parser_name": parser_output.parser_name,
                "parser_version": parser_output.parser_version,
                "processing_time_ms": parser_output.processing_time_ms,
                "cost_usd": parser_output.cost_usd,
                "metadata": parser_output.metadata,
            },
        }

    except Exception as e:
        tracker.mark_error(
            error_stage="parsing",
            error_message=str(e),
            error_type="parsing_error",
            is_retryable=True
        )
        # Mark document as failed
        doc_repo.mark_failed(
            document_id=document_id,
            error_message=str(e)[:500]
        )
        raise
    finally:
        # Cleanup: Delete temporary local file if we downloaded from storage
        if local_file_path and os.path.exists(local_file_path):
            try:
                os.remove(local_file_path)
                logger.info(
                    f"Cleaned up temporary file",
                    extra={"local_path": local_file_path}
                )
            except Exception as cleanup_error:
                logger.warning(
                    f"Failed to cleanup temporary file: {cleanup_error}",
                    extra={"local_path": local_file_path}
                )

        db.close()


@shared_task(bind=True)
def chunk_document_for_indexing_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chunk document for library indexing.

    Input payload:
        - parser_output: Parser output from previous task
        - job_id: JobState ID
        - document_id: Document ID

    Output payload:
        - All input fields
        - chunks: List of chunks with metadata
    """
    job_id = payload["job_id"]
    document_id = payload["document_id"]
    parser_output = payload.get("parser_output", {})

    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id)
    doc_repo = DocumentRepository()

    try:
        tracker.update_progress(
            status="chunking",
            current_stage="chunking",
            progress_percent=20,
            message="Chunking document..."
        )

        # Get chunker based on parser type
        parser_name = parser_output.get("parser_name", "unknown")
        chunker = ChunkerFactory.get_chunker(parser_name)

        logger.info(
            f"Chunking document with {chunker.__class__.__name__}",
            extra={"document_id": document_id, "job_id": job_id}
        )

        # Convert parser_output dict back to ParserOutput object for chunker compatibility
        # The chunker expects an object with attributes, not a dict
        from app.core.parsers.base import ParserOutput
        parser_output_obj = ParserOutput(
            text=parser_output["text"],
            page_count=parser_output["page_count"],
            parser_name=parser_output["parser_name"],
            parser_version=parser_output.get("parser_version", "1.0.0"),
            processing_time_ms=parser_output.get("processing_time_ms", 0),
            cost_usd=parser_output.get("cost_usd", 0.0),
            metadata=parser_output.get("metadata", {})
        )

        # Chunk the document
        chunking_output = chunker.chunk(parser_output_obj)

        # Convert ChunkingOutput object to list of chunk dicts for JSON serialization
        chunks_raw = chunking_output.chunks if hasattr(chunking_output, 'chunks') else chunking_output

        # Convert Chunk dataclass objects to plain dicts for Celery serialization
        from dataclasses import asdict, is_dataclass
        chunks_list = []
        for chunk in chunks_raw:
            if is_dataclass(chunk):
                chunks_list.append(asdict(chunk))
            elif isinstance(chunk, dict):
                chunks_list.append(chunk)
            else:
                # Fallback: try to convert to dict manually
                chunks_list.append({
                    'chunk_id': getattr(chunk, 'chunk_id', ''),
                    'text': getattr(chunk, 'text', ''),
                    'metadata': getattr(chunk, 'metadata', {}),
                    'narrative_text': getattr(chunk, 'narrative_text', None),
                    'tables': getattr(chunk, 'tables', None),
                })

        # Save chunks for debugging
        try:
            save_chunks(document_id, chunks_list, payload.get("filename", "unknown"))
        except Exception as save_err:
            logger.warning(f"Failed to save chunks: {save_err}")

        tracker.update_progress(
            progress_percent=30,
            message="Chunking complete",
            chunking_completed=True,
            details={"chunks_count": len(chunks_list)}
        )

        logger.info(
            f"Chunked document: {len(chunks_list)} chunks",
            extra={"document_id": document_id, "chunker": chunker.__class__.__name__}
        )

        return {
            **payload,
            "chunks": chunks_list,
        }

    except Exception as e:
        tracker.mark_error(
            error_stage="chunking",
            error_message=str(e),
            error_type="chunking_error",
            is_retryable=True
        )
        doc_repo.mark_failed(
            document_id=document_id,
            error_message=str(e)[:500]
        )
        raise
    finally:
        db.close()


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

        # Fetch document to get filename for citations
        from app.db_models_documents import Document
        document = db.query(Document).filter(Document.id == document_id).first()
        document_filename = document.filename if document else "Unknown"

        # Create DocumentChunk records with embeddings
        embedding_model = payload.get("embedding_model")
        db_chunks = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            metadata = chunk.get("metadata", {})

            # Inject citation metadata if not already present
            if "document_filename" not in metadata:
                metadata["document_filename"] = document_filename

            # Extract first sentence for citation snippet (if not already set)
            if "first_sentence" not in metadata and chunk.get("text"):
                text = chunk["text"]
                # Simple sentence extraction (split on period, take first)
                sentences = text.split('.')
                if sentences:
                    first_sentence = sentences[0].strip() + '.' if len(sentences) > 1 else sentences[0].strip()
                    # Limit to 200 chars
                    metadata["first_sentence"] = first_sentence[:200]

            # Extract smart chunking metadata fields
            # These fields go into the chunk_metadata JSONB column
            smart_metadata_fields = [
                "section_id", "parent_chunk_id", "sibling_chunk_ids",
                "linked_narrative_id", "linked_table_ids",
                "is_continuation", "chunk_sequence", "total_chunks_in_section",
                "heading_hierarchy", "paragraph_roles", "page_range",
                "table_caption", "table_context", "table_row_count", "table_column_count",
                "figure_id", "figure_caption", "has_figures", "content_type",
                # Citation metadata fields
                "document_filename", "document_title", "page_label",
                "first_sentence", "content_summary", "bbox", "source_url",
                # Key-value pairs and table data for template filling
                "key_value_pairs", "total_kv_pairs",  # Azure DI KV pairs
                "column_headers", "table_data", "table_name",  # Table metadata
                "chunk_type", "source_parser"  # Additional metadata
            ]

            # Build chunk_metadata dict (only include fields that exist)
            chunk_metadata = {
                key: metadata[key]
                for key in smart_metadata_fields
                if key in metadata
            }

            # Serialize JSONB fields for bulk_save_objects compatibility
            # bulk_save_objects() bypasses ORM type conversion, so we must manually serialize dicts/lists to JSON
            tables_data = chunk.get("tables", [])
            tables_json = json.dumps(tables_data) if tables_data else None

            chunk_metadata_json = json.dumps(chunk_metadata) if chunk_metadata else None

            db_chunk = DocumentChunk(
                document_id=document_id,
                text=chunk["text"],
                narrative_text=chunk.get("narrative_text", ""),
                tables=tables_json,  # JSON string for JSONB column
                chunk_index=i,
                embedding=embedding,
                embedding_model=embedding_model,
                embedding_version="1.0",  # Version for future migration tracking
                page_number=metadata.get("page_number"),
                section_type=metadata.get("section_type"),
                section_heading=metadata.get("section_heading"),
                is_tabular=metadata.get("has_tables", False),
                token_count=metadata.get("token_count") or len(chunk["text"].split()),  # Use actual token count if available
                chunk_metadata=chunk_metadata_json  # JSON string for JSONB column
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
    payload = {
        "file_path": file_path,
        "filename": filename,
        "job_id": job_id,
        "document_id": document_id,
        "collection_id": collection_id,
        "user_id": user_id,
        "canonical_document_id": canonical_document_id,
        "content_hash": content_hash,
    }

    # Chain: Parse → Chunk → Embed → Store
    # Uses dedicated document indexing tasks (NOT shared with extraction pipeline)
    task_chain = chain(
        parse_document_for_indexing_task.s(payload),
        chunk_document_for_indexing_task.s(),
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
