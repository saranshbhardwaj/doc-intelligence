"""add chunk_metadata for smart chunking

Revision ID: a1b2c3d4e5f6
Revises: 391dff3481ad
Create Date: 2025-11-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '391dff3481ad'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add chunk_metadata JSONB column for smart chunking relationships and metadata.

    Adds:
    1. chunk_metadata JSONB column (nullable for backward compatibility)
    2. GIN index for efficient JSONB queries
    3. Specific indexes for commonly queried metadata fields

    Metadata schema:
    {
        # Relationships
        "section_id": "sec_2",
        "parent_chunk_id": "chunk_123",
        "sibling_chunk_ids": ["chunk_123", "chunk_124"],
        "linked_narrative_id": "chunk_120",
        "linked_table_ids": ["chunk_125"],

        # Sequence tracking
        "is_continuation": true,
        "chunk_sequence": 2,
        "total_chunks_in_section": 3,

        # Context
        "heading_hierarchy": ["Main Report", "Section 2"],
        "paragraph_roles": ["sectionHeading", "content"],
        "page_range": [2, 3],

        # Table-specific
        "table_caption": "Pro Forma Sources & Uses",
        "table_context": "The following table shows...",
        "table_row_count": 15,
        "table_column_count": 4,

        # Figure-specific
        "figure_id": "1.2",
        "figure_caption": "Corporate Structure Diagram",

        # Content characteristics
        "has_figures": false,
        "content_type": "financial_table"
    }
    """

    from sqlalchemy import inspect
    from alembic import context

    conn = context.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('document_chunks')]
    indexes = [idx['name'] for idx in inspector.get_indexes('document_chunks')]

    # 1. Add chunk_metadata JSONB column (if it doesn't exist)
    if 'chunk_metadata' not in columns:
        op.add_column(
            'document_chunks',
            sa.Column('chunk_metadata', postgresql.JSONB, nullable=True)
        )

    # 2. Create GIN index for general JSONB queries (if it doesn't exist)
    if 'idx_document_chunks_metadata_gin' not in indexes:
        op.create_index(
            'idx_document_chunks_metadata_gin',
            'document_chunks',
            ['chunk_metadata'],
            postgresql_using='gin'
        )

    # 3. Create expression indexes for commonly queried fields (if they don't exist)

    # Index for section_id lookups (to find all chunks in a section)
    if 'idx_document_chunks_metadata_section_id' not in indexes:
        op.execute("""
            CREATE INDEX idx_document_chunks_metadata_section_id
            ON document_chunks ((chunk_metadata->>'section_id'))
            WHERE chunk_metadata->>'section_id' IS NOT NULL
        """)

    # Index for is_continuation flag (to filter continuation chunks)
    if 'idx_document_chunks_metadata_is_continuation' not in indexes:
        op.execute("""
            CREATE INDEX idx_document_chunks_metadata_is_continuation
            ON document_chunks ((chunk_metadata->>'is_continuation'))
            WHERE chunk_metadata->>'is_continuation' IS NOT NULL
        """)

    # Index for chunk_sequence (to sort chunks within sections)
    if 'idx_document_chunks_metadata_chunk_sequence' not in indexes:
        op.execute("""
            CREATE INDEX idx_document_chunks_metadata_chunk_sequence
            ON document_chunks (((chunk_metadata->>'chunk_sequence')::INTEGER))
            WHERE chunk_metadata->>'chunk_sequence' IS NOT NULL
        """)

    # Index for parent_chunk_id (to find children of a chunk)
    if 'idx_document_chunks_metadata_parent_chunk_id' not in indexes:
        op.execute("""
            CREATE INDEX idx_document_chunks_metadata_parent_chunk_id
            ON document_chunks ((chunk_metadata->>'parent_chunk_id'))
            WHERE chunk_metadata->>'parent_chunk_id' IS NOT NULL
        """)


def downgrade() -> None:
    """Remove chunk_metadata and all related indexes"""

    # Drop expression indexes
    op.execute('DROP INDEX IF EXISTS idx_document_chunks_metadata_parent_chunk_id')
    op.execute('DROP INDEX IF EXISTS idx_document_chunks_metadata_chunk_sequence')
    op.execute('DROP INDEX IF EXISTS idx_document_chunks_metadata_is_continuation')
    op.execute('DROP INDEX IF EXISTS idx_document_chunks_metadata_section_id')

    # Drop GIN index
    op.drop_index('idx_document_chunks_metadata_gin', table_name='document_chunks')

    # Drop column
    op.drop_column('document_chunks', 'chunk_metadata')
