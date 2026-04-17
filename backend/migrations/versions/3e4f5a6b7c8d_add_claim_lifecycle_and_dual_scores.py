"""add claim lifecycle and dual scores

Revision ID: 3e4f5a6b7c8d
Revises: 2c3d4e5f6a7b
Create Date: 2026-03-05 09:10:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "3e4f5a6b7c8d"
down_revision = "2c3d4e5f6a7b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pe_diligence_investigation_claims",
        sa.Column("status", sa.String(length=30), nullable=False, server_default="proposed"),
    )
    op.add_column(
        "pe_diligence_investigation_claims",
        sa.Column("supersedes_claim_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "pe_diligence_investigation_claims",
        sa.Column("interpretation_confidence", sa.Float(), nullable=True),
    )
    op.add_column(
        "pe_diligence_investigation_claims",
        sa.Column("coverage_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "pe_diligence_investigation_claims",
        sa.Column("source_workers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "pe_diligence_investigation_claims",
        sa.Column("confidence_history", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.execute(
        """
        UPDATE pe_diligence_investigation_claims
        SET source_workers = '[\"rule\"]'::jsonb
        WHERE source_workers IS NULL
        """
    )
    op.execute(
        """
        UPDATE pe_diligence_investigation_claims
        SET confidence_history =
            CASE
                WHEN confidence IS NOT NULL THEN jsonb_build_array(confidence)
                ELSE '[]'::jsonb
            END
        WHERE confidence_history IS NULL
        """
    )

    op.create_index(
        "idx_pe_diligence_investigation_claims_status",
        "pe_diligence_investigation_claims",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_pe_diligence_investigation_claims_status", table_name="pe_diligence_investigation_claims")

    op.drop_column("pe_diligence_investigation_claims", "confidence_history")
    op.drop_column("pe_diligence_investigation_claims", "source_workers")
    op.drop_column("pe_diligence_investigation_claims", "coverage_score")
    op.drop_column("pe_diligence_investigation_claims", "interpretation_confidence")
    op.drop_column("pe_diligence_investigation_claims", "supersedes_claim_id")
    op.drop_column("pe_diligence_investigation_claims", "status")
