"""add underwriting memo gate override fields

Revision ID: 2d182a6f2a32
Revises: f2b3c4d5e6f7
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "2d182a6f2a32"
down_revision = "f2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "underwriting_memos",
        sa.Column(
            "generated_with_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "underwriting_memos",
        sa.Column("gate_override_rationale", sa.Text(), nullable=True),
    )
    op.add_column(
        "underwriting_memos",
        sa.Column(
            "workflow_snapshot",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("underwriting_memos", "workflow_snapshot")
    op.drop_column("underwriting_memos", "gate_override_rationale")
    op.drop_column("underwriting_memos", "generated_with_override")