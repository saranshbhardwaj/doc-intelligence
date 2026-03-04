"""Fix document_chunks_tsvector_update function search_path (Supabase security lint)

Recreates the trigger function with SET search_path = public to prevent
mutable search_path vulnerability flagged by Supabase's security linter.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-03-01 00:00:00.000000
"""
from alembic import op


revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Recreate with an explicit, immutable search_path.
    # All behavior is identical — only the search_path is now pinned to 'public'.
    op.execute("""
        CREATE OR REPLACE FUNCTION public.document_chunks_tsvector_update()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.text_search_vector := to_tsvector('english', COALESCE(NEW.text, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        SET search_path = public;
    """)


def downgrade() -> None:
    # Revert to function without search_path (re-introduces the warning)
    op.execute("""
        CREATE OR REPLACE FUNCTION public.document_chunks_tsvector_update()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.text_search_vector := to_tsvector('english', COALESCE(NEW.text, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
