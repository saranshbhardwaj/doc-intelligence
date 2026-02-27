"""Add tsvector trigger for hybrid search (fixes text_search_vector never being populated)

text_search_vector was declared as a TSVECTOR column and queried in hybrid retrieval,
but was never set during chunk inserts — so keyword search always returned 0 results.

This migration:
1. Creates a PL/pgSQL trigger function that sets text_search_vector on every
   INSERT or UPDATE of the text column (BEFORE trigger so it fires automatically)
2. Attaches the trigger to document_chunks
3. Backfills existing rows where text_search_vector IS NULL

Revision ID: c4d5e6f7a8b9
Revises: b1c2d3e4f5a6
Create Date: 2026-02-24 00:00:00.000000
"""
from alembic import op


revision = "c4d5e6f7a8b9"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION document_chunks_tsvector_update()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.text_search_vector := to_tsvector('english', COALESCE(NEW.text, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # 2. Attach trigger — fires BEFORE INSERT OR UPDATE of text column
    op.execute("""
        DROP TRIGGER IF EXISTS tsvector_update ON document_chunks;
        CREATE TRIGGER tsvector_update
            BEFORE INSERT OR UPDATE OF text
            ON document_chunks
            FOR EACH ROW
            EXECUTE FUNCTION document_chunks_tsvector_update();
    """)

    # 3. Backfill existing rows (trigger only fires on future writes)
    op.execute("""
        UPDATE document_chunks
        SET text_search_vector = to_tsvector('english', COALESCE(text, ''))
        WHERE text_search_vector IS NULL;
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tsvector_update ON document_chunks")
    op.execute("DROP FUNCTION IF EXISTS document_chunks_tsvector_update()")
    op.execute("UPDATE document_chunks SET text_search_vector = NULL")
