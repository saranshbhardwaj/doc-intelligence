"""add output_schema to workflows and metrics columns to workflow_runs

Revision ID: 2b7e4c9d8f10
Revises: 5a1b2c3d4e5f
Create Date: 2025-11-12 23:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2b7e4c9d8f10'
down_revision = '5a1b2c3d4e5f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add output_schema to workflows
    op.add_column('workflows', sa.Column('output_schema', sa.Text(), nullable=True))

    # Add metrics / validation columns to workflow_runs
    op.add_column('workflow_runs', sa.Column('attempts', sa.Integer(), nullable=True))
    op.add_column('workflow_runs', sa.Column('validation_errors_json', sa.Text(), nullable=True))
    op.add_column('workflow_runs', sa.Column('citation_invalid_count', sa.Integer(), nullable=True))
    op.add_column('workflow_runs', sa.Column('context_stats_json', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('workflow_runs', 'context_stats_json')
    op.drop_column('workflow_runs', 'citation_invalid_count')
    op.drop_column('workflow_runs', 'validation_errors_json')
    op.drop_column('workflow_runs', 'attempts')
    op.drop_column('workflows', 'output_schema')
