"""convert embedding to vector and text_search_vector to tsvector

Revision ID: ed9083b88fa4
Revises: 05b5a3174545
Create Date: 2026-02-23 02:16:28.843269

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ed9083b88fa4'
down_revision = '05b5a3174545'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = {c["name"]: c for c in inspector.get_columns("document_chunks")}

    # Convert embedding bytea -> vector(384)
    if "embedding" in cols and cols["embedding"]["type"].__class__.__name__ != "VECTOR":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

        # ⚠️ If embedding currently contains data, this cast may fail.
        # If you don't need old embeddings, drop and recreate instead.
        op.execute("""
            ALTER TABLE document_chunks
            ALTER COLUMN embedding TYPE vector(384)
            USING NULL
        """)

    # Convert text_search_vector text -> tsvector
    if "text_search_vector" in cols:
        op.execute("""
            ALTER TABLE document_chunks
            ALTER COLUMN text_search_vector TYPE tsvector
            USING text_search_vector::tsvector
        """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE document_chunks
        ALTER COLUMN embedding TYPE bytea
    """)

    op.execute("""
        ALTER TABLE document_chunks
        ALTER COLUMN text_search_vector TYPE text
    """)