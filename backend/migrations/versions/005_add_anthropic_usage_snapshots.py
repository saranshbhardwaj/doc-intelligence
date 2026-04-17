"""Add anthropic_usage_snapshots table for Admin API data.

Revision ID: 005
Revises: 004
Create Date: 2026-02-12 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    """Create anthropic_usage_snapshots table for storing Admin API data."""
    op.create_table(
        'anthropic_usage_snapshots',
        sa.Column('id', sa.String(36), primary_key=True),

        # Time dimensions
        sa.Column('snapshot_date', sa.Date, nullable=False, index=True,
                  comment='The date this snapshot covers (UTC)'),
        sa.Column('fetched_at', sa.DateTime, nullable=False,
                  comment='When we fetched this data from Anthropic API'),

        # Model dimension
        sa.Column('model', sa.String(100), nullable=False,
                  comment='Model name (e.g., claude-sonnet-4-5-20250929)'),

        # Usage data (from /usage_report/messages)
        sa.Column('input_tokens', sa.BigInteger, nullable=False, server_default='0',
                  comment='Input tokens (user messages + context)'),
        sa.Column('output_tokens', sa.BigInteger, nullable=False, server_default='0',
                  comment='Output tokens (assistant responses)'),
        sa.Column('cache_read_input_tokens', sa.BigInteger, nullable=False, server_default='0',
                  comment='Tokens read from prompt cache'),
        sa.Column('cache_creation_input_tokens', sa.BigInteger, nullable=False, server_default='0',
                  comment='Tokens written to prompt cache'),

        # Cost data (from /cost_report)
        sa.Column('cost_usd', sa.Numeric(12, 6), nullable=False, server_default='0',
                  comment='Cost in USD as reported by Anthropic'),

        # Raw API responses (for debugging/audit)
        sa.Column('raw_usage_response', postgresql.JSONB, nullable=True,
                  comment='Raw usage API response for this snapshot'),
        sa.Column('raw_cost_response', postgresql.JSONB, nullable=True,
                  comment='Raw cost API response for this snapshot'),

        # Unique constraint: one row per day per model
        sa.UniqueConstraint('snapshot_date', 'model', name='uq_snapshot_date_model'),
    )

    # Additional index for date range queries
    op.create_index(
        'idx_anthropic_snapshots_date_model',
        'anthropic_usage_snapshots',
        ['snapshot_date', 'model']
    )


def downgrade():
    """Drop anthropic_usage_snapshots table."""
    op.drop_index('idx_anthropic_snapshots_date_model', table_name='anthropic_usage_snapshots')
    op.drop_table('anthropic_usage_snapshots')
