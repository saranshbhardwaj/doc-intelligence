"""add re_underwriting_runs table

Revision ID: h3i4j5k6l7m8
Revises: g2h3i4j5k6l7
Create Date: 2026-04-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'h3i4j5k6l7m8'
down_revision = 'r5s6t7u8v9w0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        're_underwriting_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(100), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('asset_type', sa.String(50), nullable=False, server_default='self_storage'),
        sa.Column('address', sa.String(500), nullable=True),

        # JSONB columns
        sa.Column('document_ids', postgresql.JSONB(), nullable=True),
        sa.Column('inputs', postgresql.JSONB(), nullable=True),
        sa.Column('field_citations', postgresql.JSONB(), nullable=True),
        sa.Column('discrepancies', postgresql.JSONB(), nullable=True),
        sa.Column('result_artifact', postgresql.JSONB(), nullable=True),
        sa.Column('verdict_failures', postgresql.JSONB(), nullable=True),
        sa.Column('loi_inputs', postgresql.JSONB(), nullable=True),

        # Typed metric columns
        sa.Column('irr', sa.Float(), nullable=True),
        sa.Column('cash_on_cash', sa.Float(), nullable=True),
        sa.Column('equity_multiple', sa.Float(), nullable=True),
        sa.Column('dscr_year_one', sa.Float(), nullable=True),
        sa.Column('ltv', sa.Float(), nullable=True),
        sa.Column('cap_rate_year_one', sa.Float(), nullable=True),
        sa.Column('cap_rate_pro_forma', sa.Float(), nullable=True),
        sa.Column('noi_year_one', sa.Float(), nullable=True),
        sa.Column('total_profit', sa.Float(), nullable=True),
        sa.Column('monthly_cashflow', sa.Float(), nullable=True),

        # Verdict
        sa.Column('verdict_status', sa.String(20), nullable=True),

        # Status lifecycle
        sa.Column('status', sa.String(30), nullable=False, server_default='extracting'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('extraction_job_id', sa.String(100), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        'idx_re_uw_runs_user_id_created',
        're_underwriting_runs',
        ['user_id', 'created_at'],
    )
    op.create_index(
        'idx_re_uw_runs_verdict_status',
        're_underwriting_runs',
        ['user_id', 'verdict_status'],
    )
    op.create_index(
        'idx_re_uw_runs_extraction_job_id',
        're_underwriting_runs',
        ['extraction_job_id'],
    )



def downgrade() -> None:
    op.drop_index('idx_re_uw_runs_extraction_job_id', table_name='re_underwriting_runs')
    op.drop_index('idx_re_uw_runs_verdict_status', table_name='re_underwriting_runs')
    op.drop_index('idx_re_uw_runs_user_id_created', table_name='re_underwriting_runs')
    op.drop_table('re_underwriting_runs')
