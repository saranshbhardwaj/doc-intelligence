"""
One-time script to re-embed all document chunks with the new embedding model.

Run after migrating the embedding column dimension (e.g., 384 → 768).
This script re-generates embeddings for all chunks using the currently
configured embedding provider (set in config.py / .env).

Usage:
    cd backend
    python -m scripts.reembed_all_chunks

    # Dry run (count chunks, don't embed):
    python -m scripts.reembed_all_chunks --dry-run
"""
import argparse
import sys
import time

# Add backend to path if running as script
sys.path.insert(0, ".")

from app.database import get_db
from app.core.embeddings.factory import get_embedding_provider
from app.utils.logging import logger

# Import all models to register them with SQLAlchemy Base (required for relationship resolution)
# These imports have side effects: they register model classes with Base's metadata registry
import app.db_models  # noqa: F401 - Extraction, ParserOutput, CacheEntry, JobState
import app.db_models_users  # noqa: F401 - User
import app.db_models_chat  # noqa: F401 - Collection, CollectionDocument, DocumentChunk, ChatSession, ChatMessage
import app.db_models_workflows  # noqa: F401 - Workflow, WorkflowRun
import app.db_models_documents  # noqa: F401 - Document (canonical)
import app.db_models_templates  # noqa: F401 - ExcelTemplate, TemplateFillRun

from app.db_models_chat import DocumentChunk


BATCH_SIZE = 50  # Match existing embed_chunks_task batch size


def reembed_all_chunks(dry_run: bool = False):
    """Re-embed all document chunks with the currently configured embedding model."""
    db = next(get_db())

    try:
        # Count total chunks
        total = db.query(DocumentChunk).count()
        null_embeddings = db.query(DocumentChunk).filter(DocumentChunk.embedding.is_(None)).count()

        logger.info(
            f"Re-embed: {total} total chunks, {null_embeddings} with NULL embeddings"
        )

        if total == 0:
            logger.info("No chunks to re-embed")
            return

        if dry_run:
            logger.info(f"DRY RUN: Would re-embed {total} chunks in {(total + BATCH_SIZE - 1) // BATCH_SIZE} batches")
            return

        # Initialize embedding provider
        embedder = get_embedding_provider()
        logger.info(
            f"Using {embedder.provider_name} ({embedder.model_name}, {embedder.get_dimension()}d)"
        )

        # Process in batches using offset/limit
        processed = 0
        failed = 0
        start_time = time.time()

        while processed < total:
            # Fetch batch of chunks
            chunks = (
                db.query(DocumentChunk)
                .order_by(DocumentChunk.id)
                .offset(processed)
                .limit(BATCH_SIZE)
                .all()
            )

            if not chunks:
                break

            # Extract texts
            texts = [chunk.text or "" for chunk in chunks]

            try:
                embeddings = embedder.embed_batch(texts)

                # Update each chunk
                for chunk, embedding in zip(chunks, embeddings):
                    chunk.embedding = embedding
                    chunk.embedding_model = embedder.model_name
                    chunk.embedding_version = f"{embedder.get_dimension()}d"

                db.commit()
                processed += len(chunks)

                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                logger.info(
                    f"Re-embedded {processed}/{total} chunks "
                    f"({processed * 100 // total}%, {rate:.1f} chunks/sec)"
                )

            except Exception as e:
                db.rollback()
                failed += len(chunks)
                processed += len(chunks)
                logger.error(f"Failed to embed batch at offset {processed}: {e}")

        elapsed = time.time() - start_time
        logger.info(
            f"Re-embedding complete: {processed - failed}/{total} succeeded, "
            f"{failed} failed, {elapsed:.1f}s total"
        )

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-embed all document chunks")
    parser.add_argument("--dry-run", action="store_true", help="Count chunks without embedding")
    args = parser.parse_args()

    reembed_all_chunks(dry_run=args.dry_run)
