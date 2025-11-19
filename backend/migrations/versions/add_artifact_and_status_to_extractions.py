"""add artifact, status, error_message, completed_at to extractions

Revision ID: add_artifact_status_extractions
Revises: 10fc91b027e5
Create Date: 2025-11-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_artifact_status_extractions'
down_revision = '10fc91b027e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add artifact column (JSON pointer to R2 or inline data)
    op.add_column('extractions', sa.Column('artifact', sa.JSON(), nullable=True))

    # Add status lifecycle columns
    op.add_column('extractions', sa.Column('status', sa.String(20), nullable=False, server_default='processing'))
    op.add_column('extractions', sa.Column('error_message', sa.Text(), nullable=True))
    op.add_column('extractions', sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))

    # Update existing records to 'completed' status (they're old completed extractions)
    op.execute("UPDATE extractions SET status = 'completed' WHERE status = 'processing'")


def downgrade() -> None:
    op.drop_column('extractions', 'completed_at')
    op.drop_column('extractions', 'error_message')
    op.drop_column('extractions', 'status')
    op.drop_column('extractions', 'artifact')
