"""remove stray content column from document_chunks

Revision ID: 05b5a3174545
Revises: d0f0d19b3702
Create Date: 2026-02-23 02:03:41.087030

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '05b5a3174545'
down_revision = 'd0f0d19b3702'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = [c["name"] for c in inspector.get_columns("document_chunks")]

    if "content" in cols:
        op.drop_column("document_chunks", "content")


def downgrade() -> None:
    # Only recreate if really needed
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = [c["name"] for c in inspector.get_columns("document_chunks")]

    if "content" not in cols:
        op.add_column(
            "document_chunks",
            sa.Column("content", sa.Text(), nullable=False)
        )