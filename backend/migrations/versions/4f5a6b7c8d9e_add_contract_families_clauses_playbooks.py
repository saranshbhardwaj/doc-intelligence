"""add contract families, clauses, and playbooks tables

Revision ID: 4f5a6b7c8d9e
Revises: 3e4f5a6b7c8d
Create Date: 2026-03-08 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "4f5a6b7c8d9e"
down_revision = "3e4f5a6b7c8d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Contract Families ---
    op.create_table(
        "pe_diligence_contract_families",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "room_id",
            sa.String(36),
            sa.ForeignKey("pe_diligence_rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column(
            "base_document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("family_type", sa.String(80), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_pe_diligence_contract_families_room_id",
        "pe_diligence_contract_families",
        ["room_id"],
    )
    op.create_index(
        "idx_pe_diligence_contract_families_base_doc",
        "pe_diligence_contract_families",
        ["base_document_id"],
    )

    # --- Clauses ---
    op.create_table(
        "pe_diligence_clauses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "room_id",
            sa.String(36),
            sa.ForeignKey("pe_diligence_rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "analysis_run_id",
            sa.String(36),
            sa.ForeignKey("pe_diligence_analysis_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "contract_family_id",
            sa.String(36),
            sa.ForeignKey("pe_diligence_contract_families.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_chunk_id", sa.String(120), nullable=True),
        sa.Column("source_page_number", sa.Integer, nullable=True),
        sa.Column("clause_type", sa.String(80), nullable=False),
        sa.Column("playbook_id", sa.String(80), nullable=True),
        sa.Column("extracted_fields", postgresql.JSONB, nullable=True),
        sa.Column("raw_quote", sa.Text, nullable=True),
        sa.Column("interpretation", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("engine", sa.String(50), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_pe_diligence_clauses_room_id",
        "pe_diligence_clauses",
        ["room_id"],
    )
    op.create_index(
        "idx_pe_diligence_clauses_run_id",
        "pe_diligence_clauses",
        ["analysis_run_id"],
    )
    op.create_index(
        "idx_pe_diligence_clauses_type",
        "pe_diligence_clauses",
        ["clause_type"],
    )
    op.create_index(
        "idx_pe_diligence_clauses_document",
        "pe_diligence_clauses",
        ["source_document_id"],
    )
    op.create_index(
        "idx_pe_diligence_clauses_family",
        "pe_diligence_clauses",
        ["contract_family_id"],
    )

    # --- Playbooks ---
    op.create_table(
        "pe_diligence_playbooks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("clause_types", postgresql.JSONB, nullable=True),
        sa.Column("prompt_template", sa.Text, nullable=True),
        sa.Column("output_schema", postgresql.JSONB, nullable=True),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_unique_constraint(
        "uq_pe_diligence_playbooks_slug",
        "pe_diligence_playbooks",
        ["slug"],
    )


def downgrade() -> None:
    op.drop_table("pe_diligence_clauses")
    op.drop_table("pe_diligence_contract_families")
    op.drop_table("pe_diligence_playbooks")
