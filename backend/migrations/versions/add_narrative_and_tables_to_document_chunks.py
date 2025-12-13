"""add narrative_text and tables to document_chunks

Revision ID: add_narrative_and_tables_to_document_chunks
Revises: add_fts_to_document_chunks
Create Date: 2025-12-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f1g2h3i4j5k6'
down_revision = '10fc91b027e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add missing columns used by worker for chunk storage.

    Columns:
    - narrative_text (TEXT, nullable)
    - tables (JSONB, nullable)
    - chunk_metadata (JSONB, nullable) — added defensively if missing
    """
    # Add narrative_text
    op.add_column('document_chunks', sa.Column('narrative_text', sa.Text(), nullable=True))

    # Add tables as JSONB for structured table payload
    op.add_column('document_chunks', sa.Column('tables', postgresql.JSONB, nullable=True))

    # Add chunk_metadata if not present (defensive)
    # Alembic does not support IF NOT EXISTS for add_column; we attempt add and
    # rely on migration ordering where it doesn't exist yet in this environment.
    try:
        op.add_column('document_chunks', sa.Column('chunk_metadata', postgresql.JSONB, nullable=True))
    except Exception:
        # Column likely already exists from previous migration; ignore
        pass


def downgrade() -> None:
    """Remove added columns."""
    op.drop_column('document_chunks', 'chunk_metadata')
    op.drop_column('document_chunks', 'tables')
    op.drop_column('document_chunks', 'narrative_text')
