"""add applicable_doc_types to pe_diligence_playbooks

Revision ID: i6j7k8l9m0n1
Revises: h5i6j7k8l9m0
Create Date: 2026-03-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'i6j7k8l9m0n1'
down_revision = 'h5i6j7k8l9m0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'pe_diligence_playbooks',
        sa.Column('applicable_doc_types', JSONB, nullable=True)
    )


def downgrade():
    op.drop_column('pe_diligence_playbooks', 'applicable_doc_types')
