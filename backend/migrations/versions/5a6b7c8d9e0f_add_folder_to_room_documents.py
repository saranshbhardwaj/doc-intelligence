"""add folder column to pe_diligence_room_documents

Revision ID: 5a6b7c8d9e0f
Revises: 4f5a6b7c8d9e
Create Date: 2026-03-09 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5a6b7c8d9e0f"
down_revision = "4f5a6b7c8d9e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pe_diligence_room_documents",
        sa.Column("folder", sa.String(120), nullable=True),
    )
    op.create_index(
        "idx_pe_diligence_room_documents_folder",
        "pe_diligence_room_documents",
        ["room_id", "folder"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_pe_diligence_room_documents_folder",
        table_name="pe_diligence_room_documents",
    )
    op.drop_column("pe_diligence_room_documents", "folder")
