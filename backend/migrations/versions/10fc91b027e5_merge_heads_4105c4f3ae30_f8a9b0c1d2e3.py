"""merge heads 4105c4f3ae30 + f8a9b0c1d2e3

Revision ID: 10fc91b027e5
Revises: ('4105c4f3ae30', 'f8a9b0c1d2e3')
Create Date: 2025-11-17 20:51:31.798904

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '10fc91b027e5'
down_revision = ('4105c4f3ae30', 'f8a9b0c1d2e3')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass