"""split_fill_run_data

Revision ID: 6fe0cd1339df
Revises: q4r5s6t7u8v9
Create Date: 2026-04-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "6fe0cd1339df"
down_revision = "q4r5s6t7u8v9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create fill_run_data table
    op.create_table(
        "fill_run_data",
        sa.Column("fill_run_id", sa.String(36), nullable=False),
        sa.Column("field_mapping", JSONB(), nullable=True),
        sa.Column("extracted_data", JSONB(), nullable=True),
        sa.Column("citation_context", JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ["fill_run_id"],
            ["template_fill_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("fill_run_id"),
    )

    # 2. Backfill existing data
    op.execute(
        """
        INSERT INTO fill_run_data (fill_run_id, field_mapping, extracted_data, citation_context)
        SELECT id, field_mapping, extracted_data, citation_context
        FROM template_fill_runs
        """
    )

    # 3. Drop columns from template_fill_runs
    op.drop_column("template_fill_runs", "field_mapping")
    op.drop_column("template_fill_runs", "extracted_data")
    op.drop_column("template_fill_runs", "citation_context")


def downgrade() -> None:
    # Re-add columns (data loss on downgrade is acceptable for dev rollback)
    op.add_column("template_fill_runs", sa.Column("field_mapping", JSONB(), nullable=True))
    op.add_column("template_fill_runs", sa.Column("extracted_data", JSONB(), nullable=True))
    op.add_column("template_fill_runs", sa.Column("citation_context", JSONB(), nullable=True))

    op.execute(
        """
        UPDATE template_fill_runs t
        SET
            field_mapping = d.field_mapping,
            extracted_data = d.extracted_data,
            citation_context = d.citation_context
        FROM fill_run_data d
        WHERE t.id = d.fill_run_id
        """
    )

    op.drop_table("fill_run_data")
