"""add_correction_counts_to_fill_runs

Revision ID: r5s6t7u8v9w0
Revises: 6fe0cd1339df
Create Date: 2026-04-13

"""
from alembic import op
import sqlalchemy as sa

revision = "r5s6t7u8v9w0"
down_revision = "6fe0cd1339df"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "template_fill_runs",
        sa.Column("user_corrected_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "template_fill_runs",
        sa.Column("user_filled_blank_count", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("template_fill_runs", "user_corrected_count")
    op.drop_column("template_fill_runs", "user_filled_blank_count")
