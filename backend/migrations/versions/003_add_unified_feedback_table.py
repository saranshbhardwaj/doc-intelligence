"""Add unified feedback table for all operation types.

Revision ID: 003
Revises: 002
Create Date: 2026-02-07 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    """Create unified feedback table supporting all operation types."""
    op.create_table(
        'feedback',
        sa.Column('id', sa.String(36), primary_key=True),

        # Multi-tenant fields
        sa.Column('org_id', sa.String(64), nullable=False, index=True),
        sa.Column('user_id', sa.String(100), nullable=False, index=True),

        # Polymorphic entity references (exactly one must be set)
        sa.Column('chat_message_id', sa.String(36), sa.ForeignKey('chat_messages.id', ondelete='SET NULL'), nullable=True),
        sa.Column('workflow_run_id', sa.String(36), sa.ForeignKey('workflow_runs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('template_fill_run_id', sa.String(36), sa.ForeignKey('template_fill_runs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('extraction_id', sa.String(36), sa.ForeignKey('extractions.id', ondelete='SET NULL'), nullable=True),

        # Operation type (denormalized for query efficiency)
        sa.Column('operation_type', sa.String(20), nullable=False),

        # Rating fields
        sa.Column('rating_type', sa.String(20), nullable=False, server_default='thumbs'),
        sa.Column('rating_value', sa.Integer, nullable=True),

        # Free text & categorization
        sa.Column('comment', sa.Text, nullable=True),
        sa.Column('feedback_category', sa.String(50), nullable=True),
        sa.Column('tags', postgresql.JSONB, server_default='[]'),

        # Response tracking (for admin follow-up)
        sa.Column('requires_response', sa.Boolean, server_default='false'),
        sa.Column('response_status', sa.String(20), server_default='none'),
        sa.Column('response_text', sa.Text, nullable=True),
        sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('responded_by', sa.String(100), nullable=True),

        # Context snapshot (preserve state at feedback time)
        sa.Column('context_snapshot', postgresql.JSONB, nullable=True),

        # Metadata
        sa.Column('client_ip', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text, nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create indexes for efficient queries
    op.create_index('idx_feedback_org_id', 'feedback', ['org_id'])
    op.create_index('idx_feedback_user_id', 'feedback', ['user_id'])
    op.create_index('idx_feedback_operation_type', 'feedback', ['operation_type'])
    op.create_index('idx_feedback_created_at', 'feedback', ['created_at'])
    op.create_index('idx_feedback_org_type_created', 'feedback', ['org_id', 'operation_type', 'created_at'])
    op.create_index('idx_feedback_requires_response', 'feedback', ['requires_response', 'response_status'],
                    postgresql_where=sa.text('requires_response = true'))


def downgrade():
    """Drop the feedback table and its indexes."""
    op.drop_index('idx_feedback_requires_response', 'feedback')
    op.drop_index('idx_feedback_org_type_created', 'feedback')
    op.drop_index('idx_feedback_created_at', 'feedback')
    op.drop_index('idx_feedback_operation_type', 'feedback')
    op.drop_index('idx_feedback_user_id', 'feedback')
    op.drop_index('idx_feedback_org_id', 'feedback')
    op.drop_table('feedback')
