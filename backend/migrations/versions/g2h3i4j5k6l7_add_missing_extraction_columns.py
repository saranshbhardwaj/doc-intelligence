"""add missing extraction metadata columns

Revision ID: g2h3i4j5k6l7
Revises: 0e0fe1243464, f1g2h3i4j5k6
Create Date: 2025-12-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'g2h3i4j5k6l7'
down_revision = ('0e0fe1243464', 'f1g2h3i4j5k6')
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add missing metadata columns to extractions table"""
    # Add document/file metadata columns (snapshot for historical audit)
    try:
        op.add_column('extractions', sa.Column('filename', sa.String(255), nullable=True))
    except:
        pass

    try:
        op.add_column('extractions', sa.Column('file_size_bytes', sa.Integer(), nullable=True))
    except:
        pass

    try:
        op.add_column('extractions', sa.Column('page_count', sa.Integer(), nullable=True))
    except:
        pass

    try:
        op.add_column('extractions', sa.Column('pdf_type', sa.String(20), nullable=True))
    except:
        pass

    try:
        op.add_column('extractions', sa.Column('parser_used', sa.String(50), nullable=True))
    except:
        pass

    try:
        op.add_column('extractions', sa.Column('processing_time_ms', sa.Integer(), nullable=True))
    except:
        pass

    try:
        op.add_column('extractions', sa.Column('cost_usd', sa.Float(), nullable=True))
    except:
        pass

    try:
        op.add_column('extractions', sa.Column('content_hash', sa.String(64), nullable=True))
    except:
        pass

    # Create index on content_hash for fast duplicate detection
    try:
        op.create_index('idx_extractions_content_hash', 'extractions', ['content_hash'])
    except:
        pass


def downgrade() -> None:
    """Remove added columns"""
    try:
        op.drop_index('idx_extractions_content_hash', 'extractions')
    except:
        pass

    try:
        op.drop_column('extractions', 'content_hash')
    except:
        pass

    try:
        op.drop_column('extractions', 'cost_usd')
    except:
        pass

    try:
        op.drop_column('extractions', 'processing_time_ms')
    except:
        pass

    try:
        op.drop_column('extractions', 'parser_used')
    except:
        pass

    try:
        op.drop_column('extractions', 'pdf_type')
    except:
        pass

    try:
        op.drop_column('extractions', 'page_count')
    except:
        pass

    try:
        op.drop_column('extractions', 'file_size_bytes')
    except:
        pass

    try:
        op.drop_column('extractions', 'filename')
    except:
        pass
