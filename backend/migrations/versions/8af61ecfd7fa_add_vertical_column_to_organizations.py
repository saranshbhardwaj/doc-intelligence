"""add_vertical_column_to_users

Revision ID: 8af61ecfd7fa
Revises: g2h3i4j5k6l7
Create Date: 2025-12-14 22:20:38.289418

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8af61ecfd7fa'
down_revision = 'g2h3i4j5k6l7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add vertical column to users table.

    This column identifies which vertical/domain a user belongs to.
    Default is 'private_equity' for backward compatibility with existing users.
    Future: evolve to organization-based multi-tenancy.
    """
    op.add_column(
        'users',
        sa.Column('vertical', sa.String(50), nullable=False, server_default='private_equity')
    )

    # Create index for faster vertical lookups
    op.create_index('idx_users_vertical', 'users', ['vertical'])


def downgrade() -> None:
    """Remove vertical column from users table."""
    op.drop_index('idx_users_vertical', table_name='users')
    op.drop_column('users', 'vertical')