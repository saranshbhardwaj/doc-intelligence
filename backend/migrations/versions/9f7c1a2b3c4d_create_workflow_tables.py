"""create workflows and workflow_runs tables

Revision ID: 9f7c1a2b3c4d
Revises: e26f80b0d932
Create Date: 2025-11-12 19:05:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9f7c1a2b3c4d'
down_revision = '7710583860d9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create workflows table
    op.create_table(
        'workflows',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('prompt_template', sa.Text(), nullable=False),
        sa.Column('variables_schema', sa.Text(), nullable=True),
        sa.Column('output_format', sa.String(length=50), nullable=False, server_default='markdown'),
        sa.Column('min_documents', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('max_documents', sa.Integer(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
    )
    op.create_index('ix_workflows_name', 'workflows', ['name'], unique=False)

    # Create workflow_runs table
    op.create_table(
        'workflow_runs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('workflow_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=100), nullable=False),
        sa.Column('collection_id', sa.String(length=36), nullable=True),
        sa.Column('document_ids_json', sa.Text(), nullable=True),
        sa.Column('variables_json', sa.Text(), nullable=True),
        sa.Column('mode', sa.String(length=30), nullable=False, server_default='single_doc'),
        sa.Column('strategy', sa.String(length=30), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='queued'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('artifact_json', sa.Text(), nullable=True),
        sa.Column('output_format', sa.String(length=50), nullable=True),
        sa.Column('token_usage', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('citations_count', sa.Integer(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['collection_id'], ['collections.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_workflow_runs_workflow_id', 'workflow_runs', ['workflow_id'], unique=False)
    op.create_index('ix_workflow_runs_user_id', 'workflow_runs', ['user_id'], unique=False)
    op.create_index('ix_workflow_runs_collection_id', 'workflow_runs', ['collection_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_workflow_runs_collection_id', table_name='workflow_runs')
    op.drop_index('ix_workflow_runs_user_id', table_name='workflow_runs')
    op.drop_index('ix_workflow_runs_workflow_id', table_name='workflow_runs')
    op.drop_table('workflow_runs')
    op.drop_index('ix_workflows_name', table_name='workflows')
    op.drop_table('workflows')
