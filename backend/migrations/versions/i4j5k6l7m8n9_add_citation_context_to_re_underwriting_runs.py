"""add citation_context to re_underwriting_runs

Revision ID: i4j5k6l7m8n9
Revises: h3i4j5k6l7m8
Create Date: 2026-04-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'i4j5k6l7m8n9'
down_revision = 'h3i4j5k6l7m8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        're_underwriting_runs',
        sa.Column('citation_context', postgresql.JSONB(), nullable=True, server_default='{}'),
    )


def downgrade() -> None:
    op.drop_column('re_underwriting_runs', 'citation_context')
