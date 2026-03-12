"""add pe diligence evidence spans

Revision ID: 1b2c3d4e5f6a
Revises: 0a1b2c3d4e5f
Create Date: 2026-03-04 00:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "1b2c3d4e5f6a"
down_revision = "0a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pe_diligence_evidence_spans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("room_id", sa.String(length=36), nullable=False),
        sa.Column("analysis_run_id", sa.String(length=36), nullable=True),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=False),
        sa.Column("source_document_id", sa.String(length=36), nullable=True),
        sa.Column("source_chunk_id", sa.String(length=120), nullable=True),
        sa.Column("source_page_number", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["pe_diligence_analysis_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["room_id"], ["pe_diligence_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_pe_diligence_evidence_spans_room_id", "pe_diligence_evidence_spans", ["room_id"], unique=False)
    op.create_index("idx_pe_diligence_evidence_spans_run_id", "pe_diligence_evidence_spans", ["analysis_run_id"], unique=False)
    op.create_index("idx_pe_diligence_evidence_spans_entity", "pe_diligence_evidence_spans", ["entity_type", "entity_id"], unique=False)
    op.create_index("idx_pe_diligence_evidence_spans_document", "pe_diligence_evidence_spans", ["source_document_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_pe_diligence_evidence_spans_document", table_name="pe_diligence_evidence_spans")
    op.drop_index("idx_pe_diligence_evidence_spans_entity", table_name="pe_diligence_evidence_spans")
    op.drop_index("idx_pe_diligence_evidence_spans_run_id", table_name="pe_diligence_evidence_spans")
    op.drop_index("idx_pe_diligence_evidence_spans_room_id", table_name="pe_diligence_evidence_spans")
    op.drop_table("pe_diligence_evidence_spans")

