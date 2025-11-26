"""add full-text search to document_chunks

Revision ID: add_fts_to_document_chunks
Revises:
Create Date: 2025-11-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_fts_to_document_chunks'
down_revision = 'bd82ec3bf551'  # Previous migration in main chain
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add full-text search support to document_chunks table

    Adds:
    1. text_search_vector column (TSVECTOR type)
    2. Trigger to auto-update tsvector when text changes
    3. GIN index for fast full-text search
    """

    # 1. Add text_search_vector column
    op.add_column(
        'document_chunks',
        sa.Column(
            'text_search_vector',
            postgresql.TSVECTOR,
            nullable=True
        )
    )

    # 2. Populate existing rows with tsvector values
    op.execute("""
        UPDATE document_chunks
        SET text_search_vector = to_tsvector('english', text)
        WHERE text IS NOT NULL
    """)

    # 3. Create trigger function to auto-update tsvector on text changes
    op.execute("""
        CREATE OR REPLACE FUNCTION document_chunks_text_search_trigger()
        RETURNS trigger AS $$
        BEGIN
            NEW.text_search_vector := to_tsvector('english', COALESCE(NEW.text, ''));
            RETURN NEW;
        END
        $$ LANGUAGE plpgsql;
    """)

    # 4. Create trigger to call the function on INSERT or UPDATE
    op.execute("""
        CREATE TRIGGER document_chunks_text_search_update
        BEFORE INSERT OR UPDATE OF text
        ON document_chunks
        FOR EACH ROW
        EXECUTE FUNCTION document_chunks_text_search_trigger();
    """)

    # 5. Create GIN index for fast full-text search
    op.create_index(
        'idx_document_chunks_fts',
        'document_chunks',
        ['text_search_vector'],
        postgresql_using='gin'
    )


def downgrade() -> None:
    """Remove full-text search support"""

    # Drop index
    op.drop_index('idx_document_chunks_fts', table_name='document_chunks')

    # Drop trigger
    op.execute('DROP TRIGGER IF EXISTS document_chunks_text_search_update ON document_chunks')

    # Drop trigger function
    op.execute('DROP FUNCTION IF EXISTS document_chunks_text_search_trigger()')

    # Drop column
    op.drop_column('document_chunks', 'text_search_vector')
