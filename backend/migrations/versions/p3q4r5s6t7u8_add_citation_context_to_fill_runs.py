"""Add citation_context to template_fill_runs

Revision ID: p3q4r5s6t7u8
Revises: o2p3q4r5s6t7
Create Date: 2026-04-04

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'p3q4r5s6t7u8'
down_revision = 'o2p3q4r5s6t7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'template_fill_runs',
        sa.Column('citation_context', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade():
    op.drop_column('template_fill_runs', 'citation_context')
