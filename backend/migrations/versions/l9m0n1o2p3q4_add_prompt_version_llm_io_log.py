"""add prompt_version and llm_io_log to template_fill_runs

Revision ID: l9m0n1o2p3q4
Revises: k8l9m0n1o2p3
Create Date: 2026-03-24

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'l9m0n1o2p3q4'
down_revision = 'k8l9m0n1o2p3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("template_fill_runs", sa.Column("prompt_version", sa.String(20), nullable=True))
    op.add_column("template_fill_runs", sa.Column("llm_io_log", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("template_fill_runs", "llm_io_log")
    op.drop_column("template_fill_runs", "prompt_version")
