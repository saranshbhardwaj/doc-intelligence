"""Drop collection_id from chat_sessions - sessions are independent of collections.

Revision ID: 002
Revises: 001_initial_schema
Create Date: 2026-02-06 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade():
    """Drop the collection_id column from chat_sessions table."""
    # Drop the foreign key constraint first
    op.drop_constraint('chat_sessions_collection_id_fkey', 'chat_sessions', type_='foreignkey')

    # Drop the column
    op.drop_column('chat_sessions', 'collection_id')


def downgrade():
    """Add back the collection_id column to chat_sessions table."""
    op.add_column(
        'chat_sessions',
        sa.Column('collection_id', sa.String(36), sa.ForeignKey('collections.id', ondelete='CASCADE'), nullable=True)
    )
