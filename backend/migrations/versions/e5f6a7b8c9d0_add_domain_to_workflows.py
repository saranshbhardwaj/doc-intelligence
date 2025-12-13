"""add domain to workflows

Revision ID: e5f6a7b8c9d0
Revises: d6e7f8a9b0c1
Create Date: 2025-12-08 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd6e7f8a9b0c1'
branch_labels = None
depends_on = None


def upgrade():
    # Add domain column to workflows table with default 'private_equity'
    # All existing workflows are PE workflows
    op.add_column('workflows', sa.Column('domain', sa.String(50), nullable=False, server_default='private_equity'))

    # Add index for efficient filtering by domain
    op.create_index('idx_workflows_domain', 'workflows', ['domain'])


def downgrade():
    # Remove index and column
    op.drop_index('idx_workflows_domain', table_name='workflows')
    op.drop_column('workflows', 'domain')
