"""add review fields to pe_diligence_clauses

Revision ID: j7k8l9m0n1o2
Revises: i6j7k8l9m0n1
Create Date: 2026-03-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'j7k8l9m0n1o2'
down_revision = 'i6j7k8l9m0n1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'pe_diligence_clauses',
        sa.Column('review_status', sa.String(20), nullable=True)
    )
    op.add_column(
        'pe_diligence_clauses',
        sa.Column('reviewed_by', sa.String(255), nullable=True)
    )
    op.add_column(
        'pe_diligence_clauses',
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        'pe_diligence_clauses',
        sa.Column('corrected_fields', JSONB, nullable=True)
    )


def downgrade():
    op.drop_column('pe_diligence_clauses', 'corrected_fields')
    op.drop_column('pe_diligence_clauses', 'reviewed_at')
    op.drop_column('pe_diligence_clauses', 'reviewed_by')
    op.drop_column('pe_diligence_clauses', 'review_status')
