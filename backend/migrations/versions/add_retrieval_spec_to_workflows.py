"""add retrieval_spec_json to workflows

Revision ID: 3c8d9e0f1g2h
Revises: 2b7e4c9d8f10
Create Date: 2025-01-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '3c8d9e0f1g2h'
down_revision = 'add_fts_to_document_chunks'  # Run after FTS migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add retrieval_spec_json column to workflows table
    op.add_column(
        'workflows',
        sa.Column('retrieval_spec_json', postgresql.JSONB(), nullable=True)
    )

    # Optional: Add GIN index for query performance on JSONB column
    op.create_index(
        'idx_workflows_retrieval_spec',
        'workflows',
        ['retrieval_spec_json'],
        unique=False,
        postgresql_using='gin'
    )


def downgrade() -> None:
    # Drop index first
    op.drop_index('idx_workflows_retrieval_spec', table_name='workflows')

    # Drop column
    op.drop_column('workflows', 'retrieval_spec_json')
