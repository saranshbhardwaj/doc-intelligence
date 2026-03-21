"""Add job_id column to analysis_runs for SSE progress tracking

The job_id links analysis runs to JobState records for real-time progress
streaming via the existing /api/jobs/{job_id}/stream SSE endpoint.

Revision ID: h5i6j7k8l9m0
Revises: g4h5i6j7k8l9
Create Date: 2026-03-14 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "h5i6j7k8l9m0"
down_revision = "g4h5i6j7k8l9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('pe_diligence_analysis_runs', sa.Column('job_id', sa.String(36), nullable=True))
    op.create_index('idx_pe_diligence_analysis_runs_job_id', 'pe_diligence_analysis_runs', ['job_id'])


def downgrade():
    op.drop_index('idx_pe_diligence_analysis_runs_job_id', table_name='pe_diligence_analysis_runs')
    op.drop_column('pe_diligence_analysis_runs', 'job_id')
