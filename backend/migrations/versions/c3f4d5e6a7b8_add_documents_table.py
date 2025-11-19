"""add_documents_table

Revision ID: c3f4d5e6a7b8
Revises: 2b7e4c9d8f10
Create Date: 2025-11-14 00:00:00.000000

Add a canonical `documents` table for deduplication and link existing
`collection_documents` rows to the canonical table via `document_id`.

This migration:
 - creates `documents` table (unique content_hash)
 - adds nullable `document_id` column to `collection_documents`
 - backfills a canonical document per distinct content_hash (if present)
 - updates `collection_documents.document_id` to map to canonical rows
 - marks canonical documents with chunk_count > 0 as completed

Note: This migration uses the pgcrypto `gen_random_uuid()` function to
generate UUIDs for backfilled rows. Ensure pgcrypto is available in your DB.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'c3f4d5e6a7b8'
down_revision = '2b7e4c9d8f10'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgcrypto (gen_random_uuid) exists
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    except Exception:
        # If extension creation fails, the INSERT using gen_random_uuid() may also fail.
        pass

    # Create canonical documents table
    op.create_table(
        'documents',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=512), nullable=True),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False),
        sa.Column('page_count', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True, server_default='processing'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('parser_used', sa.String(length=50), nullable=True),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('chunk_count', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('source_collection_document_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('content_hash', name='uq_documents_content_hash')
    )
    op.create_index('idx_documents_content_hash', 'documents', ['content_hash'])

    # Add document_id column to collection_documents
    op.add_column('collection_documents', sa.Column('document_id', sa.String(length=36), nullable=True))
    op.create_index(op.f('ix_collection_documents_document_id'), 'collection_documents', ['document_id'], unique=False)

    # Create FK constraint (nullable during backfill)
    op.create_foreign_key('fk_collection_documents_document_id', 'collection_documents', 'documents', ['document_id'], ['id'], ondelete='CASCADE')

    # Backfill canonical documents from existing collection_documents grouped by content_hash
    conn = op.get_bind()

    # Insert one canonical document per distinct content_hash (skip NULLs)
    conn.execute(text("""
        INSERT INTO documents (
            id, content_hash, filename, file_path, file_size_bytes, page_count, status, chunk_count, source_collection_document_id, created_at
        )
        SELECT
            gen_random_uuid(),
            content_hash,
            MIN(filename) AS filename,
            MIN(file_path) AS file_path,
            MAX(file_size_bytes) AS file_size_bytes,
            MAX(page_count) AS page_count,
            MAX(status) AS status,
            MAX(chunk_count) AS chunk_count,
            MIN(id) AS source_collection_document_id,
            NOW()::timestamp
        FROM collection_documents
        WHERE content_hash IS NOT NULL
        GROUP BY content_hash
    """))

    # Map collection_documents to canonical documents via content_hash
    conn.execute(text("""
        UPDATE collection_documents cd
        SET document_id = d.id
        FROM documents d
        WHERE cd.content_hash = d.content_hash
    """))

    # Mark canonical documents as completed if they have chunks copied/backfilled
    conn.execute(text("UPDATE documents SET status = 'completed' WHERE chunk_count IS NOT NULL AND chunk_count > 0"))


def downgrade() -> None:
    # Drop FK/column and table
    op.drop_constraint('fk_collection_documents_document_id', 'collection_documents', type_='foreignkey')
    op.drop_index(op.f('ix_collection_documents_document_id'), table_name='collection_documents')
    op.drop_column('collection_documents', 'document_id')
    op.drop_index('idx_documents_content_hash', table_name='documents')
    op.drop_table('documents')
