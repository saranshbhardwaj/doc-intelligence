"""add org_id tenant scoping

Revision ID: f1a2b3c4d5e6
Revises: d6e7f8a9b0c1
Create Date: 2026-02-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'd6e7f8a9b0c1'
branch_labels = None
depends_on = None


def upgrade():
    # users + usage_logs
    op.add_column('users', sa.Column('org_id', sa.String(64), nullable=False, server_default='dev-org'))
    op.create_index('idx_users_org_id', 'users', ['org_id'])

    op.add_column('usage_logs', sa.Column('org_id', sa.String(64), nullable=False, server_default='dev-org'))
    op.create_index('idx_usage_logs_org_id', 'usage_logs', ['org_id'])

    # documents
    op.add_column('documents', sa.Column('org_id', sa.String(64), nullable=False, server_default='dev-org'))
    op.create_index('idx_documents_org_id', 'documents', ['org_id'])
    op.drop_constraint('uq_documents_content_hash', 'documents', type_='unique')
    op.create_unique_constraint('uq_documents_org_id_content_hash', 'documents', ['org_id', 'content_hash'])

    # collections + chat sessions
    op.add_column('collections', sa.Column('org_id', sa.String(64), nullable=False, server_default='dev-org'))
    op.create_index('idx_collections_org_id', 'collections', ['org_id'])

    op.add_column('chat_sessions', sa.Column('org_id', sa.String(64), nullable=False, server_default='dev-org'))
    op.create_index('idx_chat_sessions_org_id', 'chat_sessions', ['org_id'])

    # workflow runs
    op.add_column('workflow_runs', sa.Column('org_id', sa.String(64), nullable=False, server_default='dev-org'))
    op.create_index('idx_workflow_runs_org_id', 'workflow_runs', ['org_id'])

    # extractions
    op.add_column('extractions', sa.Column('org_id', sa.String(64), nullable=False, server_default='dev-org'))
    op.create_index('idx_extractions_org_id', 'extractions', ['org_id'])

    # templates
    op.add_column('excel_templates', sa.Column('org_id', sa.String(64), nullable=False, server_default='dev-org'))
    op.create_index('idx_excel_templates_org_id', 'excel_templates', ['org_id'])

    op.add_column('template_fill_runs', sa.Column('org_id', sa.String(64), nullable=False, server_default='dev-org'))
    op.create_index('idx_template_fill_runs_org_id', 'template_fill_runs', ['org_id'])

    # Remove server defaults (keep not-null constraint)
    op.alter_column('users', 'org_id', server_default=None)
    op.alter_column('usage_logs', 'org_id', server_default=None)
    op.alter_column('documents', 'org_id', server_default=None)
    op.alter_column('collections', 'org_id', server_default=None)
    op.alter_column('chat_sessions', 'org_id', server_default=None)
    op.alter_column('workflow_runs', 'org_id', server_default=None)
    op.alter_column('extractions', 'org_id', server_default=None)
    op.alter_column('excel_templates', 'org_id', server_default=None)
    op.alter_column('template_fill_runs', 'org_id', server_default=None)


def downgrade():
    # templates
    op.drop_index('idx_template_fill_runs_org_id', table_name='template_fill_runs')
    op.drop_column('template_fill_runs', 'org_id')
    op.drop_index('idx_excel_templates_org_id', table_name='excel_templates')
    op.drop_column('excel_templates', 'org_id')

    # extractions
    op.drop_index('idx_extractions_org_id', table_name='extractions')
    op.drop_column('extractions', 'org_id')

    # workflow runs
    op.drop_index('idx_workflow_runs_org_id', table_name='workflow_runs')
    op.drop_column('workflow_runs', 'org_id')

    # chat sessions + collections
    op.drop_index('idx_chat_sessions_org_id', table_name='chat_sessions')
    op.drop_column('chat_sessions', 'org_id')
    op.drop_index('idx_collections_org_id', table_name='collections')
    op.drop_column('collections', 'org_id')

    # documents
    op.drop_constraint('uq_documents_org_id_content_hash', 'documents', type_='unique')
    op.create_unique_constraint('uq_documents_content_hash', 'documents', ['content_hash'])
    op.drop_index('idx_documents_org_id', table_name='documents')
    op.drop_column('documents', 'org_id')

    # usage_logs + users
    op.drop_index('idx_usage_logs_org_id', table_name='usage_logs')
    op.drop_column('usage_logs', 'org_id')

    op.drop_index('idx_users_org_id', table_name='users')
    op.drop_column('users', 'org_id')
