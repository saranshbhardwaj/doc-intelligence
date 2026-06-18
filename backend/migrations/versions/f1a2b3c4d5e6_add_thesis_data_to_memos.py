"""add thesis_data column to underwriting_memos

Revision ID: f1a2b3c4d5e6
Revises: eeadaf9bfc10
Create Date: 2026-05-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f1a2b3c4d5e6"
down_revision = "eeadaf9bfc10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "underwriting_memos",
        sa.Column(
            "thesis_data",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("underwriting_memos", "thesis_data")
