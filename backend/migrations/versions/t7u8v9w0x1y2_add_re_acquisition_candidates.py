"""add_re_acquisition_candidates

Revision ID: t7u8v9w0x1y2
Revises: 2d182a6f2a32
Create Date: 2026-06-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "t7u8v9w0x1y2"
down_revision = "2d182a6f2a32"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "re_underwriting_runs",
        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("re_underwriting_runs", "source_metadata", server_default=None)

    op.create_table(
        "re_acquisition_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("market", sa.String(length=255), nullable=True),
        sa.Column("asset_class", sa.String(length=50), nullable=False),
        sa.Column("asset_class_confidence", sa.Float(), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("source_status", sa.String(length=50), nullable=True),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("readiness_score", sa.Integer(), nullable=True),
        sa.Column("facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("missing_items", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("underwriting_run_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["underwriting_run_id"], ["re_underwriting_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_re_acquisition_candidates_org_id", "re_acquisition_candidates", ["org_id"])
    op.create_index("ix_re_acquisition_candidates_user_id", "re_acquisition_candidates", ["user_id"])
    op.create_index("idx_re_acq_candidates_user_status", "re_acquisition_candidates", ["user_id", "status"])
    op.create_index("idx_re_acq_candidates_org_created", "re_acquisition_candidates", ["org_id", "created_at"])
    op.create_index("idx_re_acq_candidates_run", "re_acquisition_candidates", ["underwriting_run_id"])

    op.create_table(
        "re_acquisition_candidate_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("doc_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["re_acquisition_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_re_acq_candidate_docs_candidate", "re_acquisition_candidate_documents", ["candidate_id"])
    op.create_index("idx_re_acq_candidate_docs_document", "re_acquisition_candidate_documents", ["document_id"])
    op.create_index(
        "uq_re_acq_candidate_docs_attached_type",
        "re_acquisition_candidate_documents",
        ["candidate_id", "doc_type"],
        unique=True,
        postgresql_where=sa.text("status = 'attached'"),
    )


def downgrade() -> None:
    op.drop_index("uq_re_acq_candidate_docs_attached_type", table_name="re_acquisition_candidate_documents", postgresql_where=sa.text("status = 'attached'"))
    op.drop_index("idx_re_acq_candidate_docs_document", table_name="re_acquisition_candidate_documents")
    op.drop_index("idx_re_acq_candidate_docs_candidate", table_name="re_acquisition_candidate_documents")
    op.drop_table("re_acquisition_candidate_documents")

    op.drop_index("idx_re_acq_candidates_run", table_name="re_acquisition_candidates")
    op.drop_index("idx_re_acq_candidates_org_created", table_name="re_acquisition_candidates")
    op.drop_index("idx_re_acq_candidates_user_status", table_name="re_acquisition_candidates")
    op.drop_index("ix_re_acquisition_candidates_user_id", table_name="re_acquisition_candidates")
    op.drop_index("ix_re_acquisition_candidates_org_id", table_name="re_acquisition_candidates")
    op.drop_table("re_acquisition_candidates")

    op.drop_column("re_underwriting_runs", "source_metadata")