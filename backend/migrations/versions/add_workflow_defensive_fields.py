"""add workflow_snapshot and defensive fields

Revision ID: 4d9e0f1g2h3i
Revises: add_retrieval_spec_to_workflows
Create Date: 2025-01-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '4d9e0f1g2h3i'
down_revision = '3c8d9e0f1g2h'  # Points to add_retrieval_spec_to_workflows
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add defensive fields to workflows table
    op.add_column(
        'workflows',
        sa.Column('deprecated_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'workflows',
        sa.Column('replacement_workflow_id', sa.String(36), nullable=True)
    )

    # Add workflow_snapshot to workflow_runs table for defensive preservation
    op.add_column(
        'workflow_runs',
        sa.Column('workflow_snapshot', postgresql.JSONB(), nullable=True)
    )

    # Optional: Add GIN index for query performance on workflow_snapshot JSONB column
    op.create_index(
        'idx_workflow_runs_snapshot',
        'workflow_runs',
        ['workflow_snapshot'],
        unique=False,
        postgresql_using='gin'
    )


def downgrade() -> None:
    # Drop index first
    op.drop_index('idx_workflow_runs_snapshot', table_name='workflow_runs')

    # Drop columns
    op.drop_column('workflow_runs', 'workflow_snapshot')
    op.drop_column('workflows', 'replacement_workflow_id')
    op.drop_column('workflows', 'deprecated_at')
