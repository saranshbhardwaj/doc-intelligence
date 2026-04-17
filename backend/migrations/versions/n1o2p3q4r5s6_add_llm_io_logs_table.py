"""add llm_io_logs table and drop llm_io_log/prompt_version from template_fill_runs

Revision ID: n1o2p3q4r5s6
Revises: m0n1o2p3q4r5
Create Date: 2026-03-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'n1o2p3q4r5s6'
down_revision = 'm0n1o2p3q4r5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create unified LLM I/O log table
    op.create_table(
        "llm_io_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("stage", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(20), nullable=True),
        sa.Column("system_prompt", sa.Text, nullable=True),
        sa.Column("user_message", sa.Text, nullable=True),
        sa.Column("output", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("input_tokens", sa.Integer, server_default="0"),
        sa.Column("output_tokens", sa.Integer, server_default="0"),
        sa.Column("cache_creation_tokens", sa.Integer, server_default="0"),
        sa.Column("cache_read_tokens", sa.Integer, server_default="0"),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_llm_io_logs_source", "llm_io_logs", ["source_type", "source_id"])
    op.create_index("idx_llm_io_logs_stage", "llm_io_logs", ["stage"])
    op.create_index("idx_llm_io_logs_created", "llm_io_logs", ["created_at"])

    # Drop old per-table columns (moved to llm_io_logs)
    op.drop_column("template_fill_runs", "llm_io_log")
    op.drop_column("template_fill_runs", "prompt_version")


def downgrade() -> None:
    op.add_column("template_fill_runs", sa.Column("prompt_version", sa.String(20), nullable=True))
    op.add_column("template_fill_runs", sa.Column("llm_io_log", JSONB, nullable=True))

    op.drop_index("idx_llm_io_logs_created", table_name="llm_io_logs")
    op.drop_index("idx_llm_io_logs_stage", table_name="llm_io_logs")
    op.drop_index("idx_llm_io_logs_source", table_name="llm_io_logs")
    op.drop_table("llm_io_logs")
