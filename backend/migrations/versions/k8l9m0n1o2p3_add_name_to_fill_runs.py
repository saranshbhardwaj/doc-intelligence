"""add name to template_fill_runs

Revision ID: k8l9m0n1o2p3
Revises: j7k8l9m0n1o2
Create Date: 2026-03-21

"""
from alembic import op
import sqlalchemy as sa

revision = 'k8l9m0n1o2p3'
down_revision = 'j7k8l9m0n1o2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'template_fill_runs',
        sa.Column('name', sa.String(255), nullable=True)
    )


def downgrade():
    op.drop_column('template_fill_runs', 'name')
