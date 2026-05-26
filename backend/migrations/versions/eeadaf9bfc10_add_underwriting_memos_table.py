"""add underwriting_memos table

Revision ID: eeadaf9bfc10
Revises: 80f689c17c60
Create Date: 2026-05-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'eeadaf9bfc10'
down_revision = '80f689c17c60'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "underwriting_memos",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("re_underwriting_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("r2_key", sa.String(length=500), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("cover_data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("sponsor_data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("market_notes", sa.Text(), nullable=True),
        sa.Column("section_warnings", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", "version", name="uq_underwriting_memos_run_version"),
    )
    op.create_index("idx_underwriting_memos_run_id", "underwriting_memos", ["run_id"])
    op.create_index("idx_underwriting_memos_user_id", "underwriting_memos", ["user_id"])
    op.create_index("idx_underwriting_memos_job_id", "underwriting_memos", ["job_id"])


def downgrade() -> None:
    op.drop_index("idx_underwriting_memos_job_id", table_name="underwriting_memos")
    op.drop_index("idx_underwriting_memos_user_id", table_name="underwriting_memos")
    op.drop_index("idx_underwriting_memos_run_id", table_name="underwriting_memos")
    op.drop_table("underwriting_memos")
