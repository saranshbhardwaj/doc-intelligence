"""make template_fill_runs.template_id nullable

Revision ID: o2p3q4r5s6t7
Revises: n1o2p3q4r5s6
Create Date: 2026-04-03

"""
from alembic import op
import sqlalchemy as sa


revision = "o2p3q4r5s6t7"
down_revision = "n1o2p3q4r5s6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "template_fill_runs",
        "template_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "template_fill_runs",
        "template_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
