"""add chunk_count to documents

Revision ID: 2a9c2b132df2
Revises: 90eb9e953431
Create Date: 2026-02-22 17:09:14.088034

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2a9c2b132df2'
down_revision = '90eb9e953431'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'documents',
        sa.Column('chunk_count', sa.Integer(), nullable=True)
    )



def downgrade() -> None:
    op.drop_column('documents', 'chunk_count')