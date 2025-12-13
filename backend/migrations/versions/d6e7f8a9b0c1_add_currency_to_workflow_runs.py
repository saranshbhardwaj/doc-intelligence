"""add currency to workflow runs

Revision ID: d6e7f8a9b0c1
Revises: c4d5e6f7a8b9
Create Date: 2025-12-05 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd6e7f8a9b0c1'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade():
    # Add currency column to workflow_runs table
    op.add_column('workflow_runs', sa.Column('currency', sa.String(10), nullable=True))


def downgrade():
    # Remove currency column from workflow_runs table
    op.drop_column('workflow_runs', 'currency')
