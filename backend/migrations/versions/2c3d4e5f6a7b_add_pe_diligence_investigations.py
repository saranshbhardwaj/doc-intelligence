"""add pe diligence investigations

Revision ID: 2c3d4e5f6a7b
Revises: 1b2c3d4e5f6a
Create Date: 2026-03-04 12:15:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "2c3d4e5f6a7b"
down_revision = "1b2c3d4e5f6a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pe_diligence_investigations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("room_id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("investigation_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("conclusion_markdown", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("coverage_score", sa.Float(), nullable=True),
        sa.Column("coverage_status", sa.String(length=30), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["room_id"], ["pe_diligence_rooms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_pe_diligence_investigations_room_id", "pe_diligence_investigations", ["room_id"], unique=False)
    op.create_index("idx_pe_diligence_investigations_status", "pe_diligence_investigations", ["status"], unique=False)
    op.create_index("idx_pe_diligence_investigations_type", "pe_diligence_investigations", ["investigation_type"], unique=False)
    op.create_index(op.f("ix_pe_diligence_investigations_org_id"), "pe_diligence_investigations", ["org_id"], unique=False)
    op.create_index(op.f("ix_pe_diligence_investigations_user_id"), "pe_diligence_investigations", ["user_id"], unique=False)

    op.create_table(
        "pe_diligence_investigation_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("room_id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("current_stage", sa.String(length=50), nullable=True),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["investigation_id"], ["pe_diligence_investigations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_id"], ["pe_diligence_rooms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_pe_diligence_investigation_runs_investigation_id", "pe_diligence_investigation_runs", ["investigation_id"], unique=False)
    op.create_index("idx_pe_diligence_investigation_runs_room_id", "pe_diligence_investigation_runs", ["room_id"], unique=False)
    op.create_index("idx_pe_diligence_investigation_runs_status", "pe_diligence_investigation_runs", ["status"], unique=False)
    op.create_index(op.f("ix_pe_diligence_investigation_runs_org_id"), "pe_diligence_investigation_runs", ["org_id"], unique=False)
    op.create_index(op.f("ix_pe_diligence_investigation_runs_user_id"), "pe_diligence_investigation_runs", ["user_id"], unique=False)

    op.create_table(
        "pe_diligence_investigation_claims",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("room_id", sa.String(length=36), nullable=False),
        sa.Column("claim_key", sa.String(length=120), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("stance", sa.String(length=30), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("verification_status", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["investigation_id"], ["pe_diligence_investigations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_id"], ["pe_diligence_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["pe_diligence_investigation_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_pe_diligence_investigation_claims_investigation_id", "pe_diligence_investigation_claims", ["investigation_id"], unique=False)
    op.create_index("idx_pe_diligence_investigation_claims_room_id", "pe_diligence_investigation_claims", ["room_id"], unique=False)
    op.create_index("idx_pe_diligence_investigation_claims_run_id", "pe_diligence_investigation_claims", ["run_id"], unique=False)
    op.create_index(
        "idx_pe_diligence_investigation_claims_verification_status",
        "pe_diligence_investigation_claims",
        ["verification_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_pe_diligence_investigation_claims_verification_status", table_name="pe_diligence_investigation_claims")
    op.drop_index("idx_pe_diligence_investigation_claims_run_id", table_name="pe_diligence_investigation_claims")
    op.drop_index("idx_pe_diligence_investigation_claims_room_id", table_name="pe_diligence_investigation_claims")
    op.drop_index("idx_pe_diligence_investigation_claims_investigation_id", table_name="pe_diligence_investigation_claims")
    op.drop_table("pe_diligence_investigation_claims")

    op.drop_index(op.f("ix_pe_diligence_investigation_runs_user_id"), table_name="pe_diligence_investigation_runs")
    op.drop_index(op.f("ix_pe_diligence_investigation_runs_org_id"), table_name="pe_diligence_investigation_runs")
    op.drop_index("idx_pe_diligence_investigation_runs_status", table_name="pe_diligence_investigation_runs")
    op.drop_index("idx_pe_diligence_investigation_runs_room_id", table_name="pe_diligence_investigation_runs")
    op.drop_index("idx_pe_diligence_investigation_runs_investigation_id", table_name="pe_diligence_investigation_runs")
    op.drop_table("pe_diligence_investigation_runs")

    op.drop_index(op.f("ix_pe_diligence_investigations_user_id"), table_name="pe_diligence_investigations")
    op.drop_index(op.f("ix_pe_diligence_investigations_org_id"), table_name="pe_diligence_investigations")
    op.drop_index("idx_pe_diligence_investigations_type", table_name="pe_diligence_investigations")
    op.drop_index("idx_pe_diligence_investigations_status", table_name="pe_diligence_investigations")
    op.drop_index("idx_pe_diligence_investigations_room_id", table_name="pe_diligence_investigations")
    op.drop_table("pe_diligence_investigations")

