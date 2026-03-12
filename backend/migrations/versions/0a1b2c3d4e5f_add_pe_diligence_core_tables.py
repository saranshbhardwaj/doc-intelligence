"""add pe diligence core tables

Revision ID: 0a1b2c3d4e5f
Revises: f3a4b5c6d7e8
Create Date: 2026-03-04 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0a1b2c3d4e5f"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pe_diligence_rooms",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("target_company", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("last_analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_pe_diligence_rooms_org_id", "pe_diligence_rooms", ["org_id"], unique=False)
    op.create_index("idx_pe_diligence_rooms_status", "pe_diligence_rooms", ["status"], unique=False)
    op.create_index("idx_pe_diligence_rooms_user_id", "pe_diligence_rooms", ["user_id"], unique=False)

    op.create_table(
        "pe_diligence_analysis_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
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
        sa.ForeignKeyConstraint(["room_id"], ["pe_diligence_rooms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_pe_diligence_analysis_runs_room_id", "pe_diligence_analysis_runs", ["room_id"], unique=False)
    op.create_index("idx_pe_diligence_analysis_runs_status", "pe_diligence_analysis_runs", ["status"], unique=False)
    op.create_index(op.f("ix_pe_diligence_analysis_runs_org_id"), "pe_diligence_analysis_runs", ["org_id"], unique=False)
    op.create_index(op.f("ix_pe_diligence_analysis_runs_user_id"), "pe_diligence_analysis_runs", ["user_id"], unique=False)

    op.create_table(
        "pe_diligence_room_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("room_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("ingest_status", sa.String(length=30), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["room_id"], ["pe_diligence_rooms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "document_id", name="uq_pe_diligence_room_documents_room_document"),
    )
    op.create_index("idx_pe_diligence_room_documents_document_id", "pe_diligence_room_documents", ["document_id"], unique=False)
    op.create_index("idx_pe_diligence_room_documents_room_id", "pe_diligence_room_documents", ["room_id"], unique=False)

    op.create_table(
        "pe_diligence_checklist_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("room_id", sa.String(length=36), nullable=False),
        sa.Column("item_key", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("matched_document_id", sa.String(length=36), nullable=True),
        sa.Column("matched_chunk_id", sa.String(length=120), nullable=True),
        sa.Column("matched_page_number", sa.Integer(), nullable=True),
        sa.Column("evidence_quote", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["matched_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["room_id"], ["pe_diligence_rooms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "item_key", name="uq_pe_diligence_checklist_items_room_item_key"),
    )
    op.create_index("idx_pe_diligence_checklist_items_room_id", "pe_diligence_checklist_items", ["room_id"], unique=False)
    op.create_index("idx_pe_diligence_checklist_items_status", "pe_diligence_checklist_items", ["status"], unique=False)

    op.create_table(
        "pe_diligence_findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("room_id", sa.String(length=36), nullable=False),
        sa.Column("analysis_run_id", sa.String(length=36), nullable=True),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("source_document_id", sa.String(length=36), nullable=True),
        sa.Column("source_chunk_id", sa.String(length=120), nullable=True),
        sa.Column("source_page_number", sa.Integer(), nullable=True),
        sa.Column("evidence_quote", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_by_user_id", sa.String(length=100), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["pe_diligence_analysis_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["room_id"], ["pe_diligence_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_pe_diligence_findings_room_id", "pe_diligence_findings", ["room_id"], unique=False)
    op.create_index("idx_pe_diligence_findings_severity", "pe_diligence_findings", ["severity"], unique=False)
    op.create_index("idx_pe_diligence_findings_status", "pe_diligence_findings", ["status"], unique=False)

    op.create_table(
        "pe_diligence_summaries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("room_id", sa.String(length=36), nullable=False),
        sa.Column("analysis_run_id", sa.String(length=36), nullable=True),
        sa.Column("summary_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=True),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["pe_diligence_analysis_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["room_id"], ["pe_diligence_rooms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "summary_type", name="uq_pe_diligence_summaries_room_summary_type"),
    )
    op.create_index("idx_pe_diligence_summaries_room_id", "pe_diligence_summaries", ["room_id"], unique=False)

    op.create_table(
        "pe_diligence_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("room_id", sa.String(length=36), nullable=False),
        sa.Column("analysis_run_id", sa.String(length=36), nullable=True),
        sa.Column("actor_user_id", sa.String(length=100), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.String(length=80), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["pe_diligence_analysis_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["room_id"], ["pe_diligence_rooms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_pe_diligence_audit_events_event_type", "pe_diligence_audit_events", ["event_type"], unique=False)
    op.create_index("idx_pe_diligence_audit_events_room_id", "pe_diligence_audit_events", ["room_id"], unique=False)
    op.create_index("idx_pe_diligence_audit_events_run_id", "pe_diligence_audit_events", ["analysis_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_pe_diligence_audit_events_run_id", table_name="pe_diligence_audit_events")
    op.drop_index("idx_pe_diligence_audit_events_room_id", table_name="pe_diligence_audit_events")
    op.drop_index("idx_pe_diligence_audit_events_event_type", table_name="pe_diligence_audit_events")
    op.drop_table("pe_diligence_audit_events")

    op.drop_index("idx_pe_diligence_summaries_room_id", table_name="pe_diligence_summaries")
    op.drop_table("pe_diligence_summaries")

    op.drop_index("idx_pe_diligence_findings_status", table_name="pe_diligence_findings")
    op.drop_index("idx_pe_diligence_findings_severity", table_name="pe_diligence_findings")
    op.drop_index("idx_pe_diligence_findings_room_id", table_name="pe_diligence_findings")
    op.drop_table("pe_diligence_findings")

    op.drop_index("idx_pe_diligence_checklist_items_status", table_name="pe_diligence_checklist_items")
    op.drop_index("idx_pe_diligence_checklist_items_room_id", table_name="pe_diligence_checklist_items")
    op.drop_table("pe_diligence_checklist_items")

    op.drop_index("idx_pe_diligence_room_documents_room_id", table_name="pe_diligence_room_documents")
    op.drop_index("idx_pe_diligence_room_documents_document_id", table_name="pe_diligence_room_documents")
    op.drop_table("pe_diligence_room_documents")

    op.drop_index(op.f("ix_pe_diligence_analysis_runs_user_id"), table_name="pe_diligence_analysis_runs")
    op.drop_index(op.f("ix_pe_diligence_analysis_runs_org_id"), table_name="pe_diligence_analysis_runs")
    op.drop_index("idx_pe_diligence_analysis_runs_status", table_name="pe_diligence_analysis_runs")
    op.drop_index("idx_pe_diligence_analysis_runs_room_id", table_name="pe_diligence_analysis_runs")
    op.drop_table("pe_diligence_analysis_runs")

    op.drop_index("idx_pe_diligence_rooms_user_id", table_name="pe_diligence_rooms")
    op.drop_index("idx_pe_diligence_rooms_status", table_name="pe_diligence_rooms")
    op.drop_index("idx_pe_diligence_rooms_org_id", table_name="pe_diligence_rooms")
    op.drop_table("pe_diligence_rooms")

