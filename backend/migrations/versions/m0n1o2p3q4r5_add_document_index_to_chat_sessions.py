"""add document_index to chat_sessions for stable D1/D2 citation mapping

Revision ID: m0n1o2p3q4r5
Revises: l9m0n1o2p3q4
Create Date: 2026-03-26

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'm0n1o2p3q4r5'
down_revision = 'l9m0n1o2p3q4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("document_index", JSONB, nullable=True, server_default='{}')
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "document_index")
