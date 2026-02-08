"""Initial schema - creates all tables for Doc Intelligence platform.

Revision ID: 001_initial_schema
Revises: None
Create Date: 2025-02-05

This single migration creates the complete database schema including:
- Users and usage tracking
- Documents and collections
- Chat sessions and messages
- Workflows and workflow runs
- Extractions and parser outputs
- Excel templates and template fill runs
- Job state tracking
- Cache entries
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # ========== USERS ==========
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(64), nullable=False, index=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('tier', sa.String(20), server_default='free'),
        sa.Column('vertical', sa.String(50), nullable=False, server_default='private_equity', index=True),
        sa.Column('total_pages_processed', sa.Integer, server_default='0'),
        sa.Column('pages_this_month', sa.Integer, server_default='0'),
        sa.Column('pages_limit', sa.Integer, server_default='100'),
        sa.Column('subscription_id', sa.String(255), nullable=True),
        sa.Column('subscription_status', sa.String(20), server_default='inactive'),
        sa.Column('billing_period_start', sa.DateTime, nullable=True),
        sa.Column('billing_period_end', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('last_login', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
    )

    # ========== DOCUMENTS ==========
    op.create_table(
        'documents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(64), nullable=False, index=True),
        sa.Column('user_id', sa.String(100), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(512), nullable=False),
        sa.Column('file_size_bytes', sa.Integer, nullable=False),
        sa.Column('mime_type', sa.String(100)),
        sa.Column('content_hash', sa.String(64), nullable=False, index=True),
        sa.Column('page_count', sa.Integer),
        sa.Column('status', sa.String(20), nullable=False, server_default='uploaded'),
        sa.Column('parsing_status', sa.String(20)),
        sa.Column('embedding_status', sa.String(20)),
        sa.Column('error_message', sa.Text),
        sa.Column('parsed_content_path', sa.String(512)),
        sa.Column('metadata', JSONB),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('org_id', 'content_hash', name='uq_documents_org_id_content_hash'),
    )
    op.create_index('idx_documents_org_id', 'documents', ['org_id'])
    op.create_index('idx_documents_user_id', 'documents', ['user_id'])
    op.create_index('idx_documents_content_hash', 'documents', ['content_hash'])
    op.create_index('idx_documents_status', 'documents', ['status'])

    # ========== COLLECTIONS ==========
    op.create_table(
        'collections',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(64), index=True),
        sa.Column('user_id', sa.String(100), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('document_count', sa.Integer, server_default='0'),
        sa.Column('total_chunks', sa.Integer, server_default='0'),
        sa.Column('embedding_model', sa.String(100)),
        sa.Column('embedding_dimension', sa.Integer),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ========== COLLECTION_DOCUMENTS ==========
    op.create_table(
        'collection_documents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('collection_id', sa.String(36), sa.ForeignKey('collections.id', ondelete='CASCADE'), nullable=False),
        sa.Column('document_id', sa.String(36), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_path', sa.String(512)),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('collection_id', 'document_id', name='uq_collection_documents'),
    )
    op.create_index('idx_collection_documents_collection_id', 'collection_documents', ['collection_id'])
    op.create_index('idx_collection_documents_document_id', 'collection_documents', ['document_id'])

    # ========== DOCUMENT_CHUNKS ==========
    op.create_table(
        'document_chunks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('document_id', sa.String(36), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chunk_index', sa.Integer, nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('narrative_text', sa.Text),
        sa.Column('tables', JSONB),
        sa.Column('start_page', sa.Integer),
        sa.Column('end_page', sa.Integer),
        sa.Column('token_count', sa.Integer),
        sa.Column('embedding', sa.LargeBinary),  # pgvector stored as binary
        sa.Column('text_search_vector', sa.Text),  # TSVECTOR
        sa.Column('embedding_model', sa.String(100)),
        sa.Column('embedding_version', sa.String(20)),
        sa.Column('chunk_metadata', JSONB),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_document_chunks_document_id', 'document_chunks', ['document_id'])

    # ========== CHAT_SESSIONS ==========
    op.create_table(
        'chat_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(64), index=True),
        sa.Column('user_id', sa.String(100), nullable=False, index=True),
        sa.Column('collection_id', sa.String(36), sa.ForeignKey('collections.id', ondelete='CASCADE')),
        sa.Column('title', sa.String(255)),
        sa.Column('description', sa.Text),
        sa.Column('message_count', sa.Integer, server_default='0'),
        sa.Column('last_summary_text', sa.Text),
        sa.Column('last_summary_key_facts', JSONB),
        sa.Column('last_summarized_index', sa.Integer),
        sa.Column('last_summary_updated_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ========== SESSION_DOCUMENTS ==========
    op.create_table(
        'session_documents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('document_id', sa.String(36), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_session_documents_session_id', 'session_documents', ['session_id'])
    op.create_index('ix_session_documents_document_id', 'session_documents', ['document_id'])

    # ========== CHAT_MESSAGES ==========
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('citations', JSONB),
        sa.Column('input_tokens', sa.Integer),
        sa.Column('output_tokens', sa.Integer),
        sa.Column('cache_read_tokens', sa.Integer),
        sa.Column('cache_write_tokens', sa.Integer),
        sa.Column('comparison_metadata', sa.Text),
        sa.Column('citation_metadata', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_chat_messages_session_id', 'chat_messages', ['session_id'])

    # ========== WORKFLOWS ==========
    op.create_table(
        'workflows',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('domain', sa.String(50), nullable=False, server_default='private_equity'),
        sa.Column('category', sa.String(100)),
        sa.Column('description', sa.Text),
        sa.Column('prompt_template', sa.Text, nullable=False),
        sa.Column('user_prompt_template', sa.Text),
        sa.Column('user_prompt_max_length', sa.Integer),
        sa.Column('variables_schema', JSONB),
        sa.Column('output_schema', JSONB),
        sa.Column('retrieval_spec_json', JSONB),
        sa.Column('output_format', sa.String(50), nullable=False, server_default='markdown'),
        sa.Column('min_documents', sa.Integer, nullable=False, server_default='1'),
        sa.Column('max_documents', sa.Integer),
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
        sa.Column('active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('deprecated_at', sa.DateTime(timezone=True)),
        sa.Column('replacement_workflow_id', sa.String(36)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_workflows_name', 'workflows', ['name'])
    op.create_index('idx_workflows_domain', 'workflows', ['domain'])

    # ========== WORKFLOW_RUNS ==========
    op.create_table(
        'workflow_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('workflow_id', sa.String(36), sa.ForeignKey('workflows.id', ondelete='SET NULL')),
        sa.Column('org_id', sa.String(64), nullable=False, index=True),
        sa.Column('user_id', sa.String(100), nullable=False),
        sa.Column('collection_id', sa.String(36), sa.ForeignKey('collections.id', ondelete='SET NULL')),
        sa.Column('workflow_snapshot', JSONB),
        sa.Column('document_ids', JSONB),
        sa.Column('variables', JSONB),
        sa.Column('mode', sa.String(30), nullable=False, server_default='single_doc'),
        sa.Column('strategy', sa.String(30)),
        sa.Column('status', sa.String(20), nullable=False, server_default='queued'),
        sa.Column('error_message', sa.Text),
        sa.Column('artifact', JSONB),
        sa.Column('output_format', sa.String(50)),
        sa.Column('token_usage', sa.Integer),
        sa.Column('cost_usd', sa.Float),
        sa.Column('latency_ms', sa.Integer),
        sa.Column('currency', sa.String(10)),
        sa.Column('citations_count', sa.Integer),
        sa.Column('attempts', sa.Integer),
        sa.Column('citation_invalid_count', sa.Integer),
        sa.Column('validation_errors', JSONB),
        sa.Column('context_stats', JSONB),
        sa.Column('section_summaries', JSONB),
        sa.Column('input_tokens', sa.Integer),
        sa.Column('output_tokens', sa.Integer),
        sa.Column('cache_read_tokens', sa.Integer),
        sa.Column('cache_write_tokens', sa.Integer),
        sa.Column('model_name', sa.String(100)),
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
    )
    op.create_index('idx_workflow_runs_workflow_id', 'workflow_runs', ['workflow_id'])
    op.create_index('idx_workflow_runs_user_id', 'workflow_runs', ['user_id'])
    op.create_index('idx_workflow_runs_org_id', 'workflow_runs', ['org_id'])
    op.create_index('idx_workflow_runs_collection_id', 'workflow_runs', ['collection_id'])

    # ========== EXTRACTIONS ==========
    op.create_table(
        'extractions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('document_id', sa.String(36), sa.ForeignKey('documents.id', ondelete='SET NULL')),
        sa.Column('org_id', sa.String(64), nullable=False, index=True),
        sa.Column('user_id', sa.String(100), nullable=False, index=True),
        sa.Column('filename', sa.String(255)),
        sa.Column('file_size_bytes', sa.Integer),
        sa.Column('page_count', sa.Integer),
        sa.Column('pdf_type', sa.String(20)),
        sa.Column('parser_used', sa.String(50)),
        sa.Column('processing_time_ms', sa.Integer),
        sa.Column('cost_usd', sa.Float),
        sa.Column('content_hash', sa.String(64), index=True),
        sa.Column('context', sa.Text),
        sa.Column('result', JSONB),
        sa.Column('artifact', JSONB),
        sa.Column('status', sa.String(20), nullable=False, server_default='processing'),
        sa.Column('error_message', sa.Text),
        sa.Column('from_cache', sa.Boolean, server_default='false'),
        sa.Column('from_history', sa.Boolean, server_default='false'),
        sa.Column('total_cost_usd', sa.Float, server_default='0.0'),
        sa.Column('llm_input_tokens', sa.Integer),
        sa.Column('llm_output_tokens', sa.Integer),
        sa.Column('llm_model_name', sa.String(100)),
        sa.Column('llm_cost_usd', sa.Float),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
    )
    op.create_index('idx_extractions_user_id', 'extractions', ['user_id'])
    op.create_index('idx_extractions_org_id', 'extractions', ['org_id'])
    op.create_index('idx_extractions_document_id', 'extractions', ['document_id'])

    # ========== PARSER_OUTPUTS ==========
    op.create_table(
        'parser_outputs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('extraction_id', sa.String(36), sa.ForeignKey('extractions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('parser_name', sa.String(50), nullable=False),
        sa.Column('parser_version', sa.String(20)),
        sa.Column('pdf_type', sa.String(20)),
        sa.Column('raw_output', JSONB),
        sa.Column('raw_output_length', sa.Integer),
        sa.Column('processing_time_ms', sa.Integer),
        sa.Column('cost_usd', sa.Float, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ========== CACHE_ENTRIES ==========
    op.create_table(
        'cache_entries',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('content_hash', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=False),
        sa.Column('page_count', sa.Integer, nullable=False),
        sa.Column('company_name', sa.String(255)),
        sa.Column('industry', sa.String(255)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('last_accessed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('access_count', sa.Integer, server_default='0'),
    )

    # ========== USAGE_LOGS ==========
    op.create_table(
        'usage_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('org_id', sa.String(64), nullable=False, index=True),
        sa.Column('extraction_id', sa.String(36), sa.ForeignKey('extractions.id', ondelete='SET NULL')),
        sa.Column('filename', sa.String(255)),
        sa.Column('is_deleted', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.Column('pages_processed', sa.Integer, nullable=False),
        sa.Column('operation_type', sa.String(50), server_default='extraction'),
        sa.Column('cost_usd', sa.Float, server_default='0.0'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ========== EXCEL_TEMPLATES ==========
    op.create_table(
        'excel_templates',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(64), nullable=False, index=True),
        sa.Column('user_id', sa.String(100), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('category', sa.String(100), index=True),
        sa.Column('file_path', sa.String(512), nullable=False),
        sa.Column('file_extension', sa.String(10), nullable=False, server_default='.xlsx'),
        sa.Column('file_size_bytes', sa.Integer, nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('schema_metadata', JSONB),
        sa.Column('usage_count', sa.Integer, server_default='0'),
        sa.Column('last_used_at', sa.DateTime(timezone=True)),
        sa.Column('active', sa.Boolean, server_default='true', index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
    )

    # ========== TEMPLATE_FILL_RUNS ==========
    op.create_table(
        'template_fill_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('template_id', sa.String(36), sa.ForeignKey('excel_templates.id', ondelete='SET NULL')),
        sa.Column('document_id', sa.String(36), sa.ForeignKey('documents.id', ondelete='SET NULL')),
        sa.Column('org_id', sa.String(64), nullable=False, index=True),
        sa.Column('user_id', sa.String(100), nullable=False, index=True),
        sa.Column('template_snapshot', JSONB),
        sa.Column('field_mapping', JSONB, nullable=False, server_default='{}'),
        sa.Column('extracted_data', JSONB, server_default='{}'),
        sa.Column('artifact', JSONB),
        sa.Column('status', sa.String(20), nullable=False, server_default='queued', index=True),
        sa.Column('current_stage', sa.String(50)),
        sa.Column('field_detection_completed', sa.Boolean, server_default='false'),
        sa.Column('auto_mapping_completed', sa.Boolean, server_default='false'),
        sa.Column('user_review_completed', sa.Boolean, server_default='false'),
        sa.Column('extraction_completed', sa.Boolean, server_default='false'),
        sa.Column('filling_completed', sa.Boolean, server_default='false'),
        sa.Column('total_fields_detected', sa.Integer),
        sa.Column('total_fields_mapped', sa.Integer),
        sa.Column('total_fields_filled', sa.Integer),
        sa.Column('auto_mapped_count', sa.Integer),
        sa.Column('user_edited_count', sa.Integer),
        sa.Column('cost_usd', sa.Float, server_default='0.0'),
        sa.Column('processing_time_ms', sa.Integer),
        sa.Column('input_tokens', sa.Integer),
        sa.Column('output_tokens', sa.Integer),
        sa.Column('cache_read_tokens', sa.Integer),
        sa.Column('cache_write_tokens', sa.Integer),
        sa.Column('model_name', sa.String(100)),
        sa.Column('llm_batches_count', sa.Integer),
        sa.Column('cache_hit_rate', sa.Float),
        sa.Column('error_stage', sa.String(50)),
        sa.Column('error_message', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
    )
    op.create_index('ix_template_fill_runs_template_id', 'template_fill_runs', ['template_id'])

    # ========== JOB_STATES ==========
    op.create_table(
        'job_states',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('job_id', sa.String(36), unique=True, nullable=False),
        sa.Column('extraction_id', sa.String(36), sa.ForeignKey('extractions.id', ondelete='CASCADE')),
        sa.Column('document_id', sa.String(36), sa.ForeignKey('documents.id', ondelete='CASCADE')),
        sa.Column('workflow_run_id', sa.String(36), sa.ForeignKey('workflow_runs.id', ondelete='CASCADE')),
        sa.Column('template_fill_run_id', sa.String(36), sa.ForeignKey('template_fill_runs.id', ondelete='CASCADE')),
        sa.Column('status', sa.String(20), server_default='queued'),
        sa.Column('current_stage', sa.String(50)),
        sa.Column('progress_percent', sa.Integer, server_default='0'),
        sa.Column('parsing_completed', sa.Boolean, server_default='false'),
        sa.Column('chunking_completed', sa.Boolean, server_default='false'),
        sa.Column('summarizing_completed', sa.Boolean, server_default='false'),
        sa.Column('extracting_completed', sa.Boolean, server_default='false'),
        sa.Column('embedding_completed', sa.Boolean, server_default='false'),
        sa.Column('storing_completed', sa.Boolean, server_default='false'),
        sa.Column('context_completed', sa.Boolean, server_default='false'),
        sa.Column('artifact_completed', sa.Boolean, server_default='false'),
        sa.Column('validation_completed', sa.Boolean, server_default='false'),
        sa.Column('field_detection_completed', sa.Boolean, server_default='false'),
        sa.Column('auto_mapping_completed', sa.Boolean, server_default='false'),
        sa.Column('data_extraction_completed', sa.Boolean, server_default='false'),
        sa.Column('excel_filling_completed', sa.Boolean, server_default='false'),
        sa.Column('parsed_output_path', sa.String(500)),
        sa.Column('chunks_path', sa.String(500)),
        sa.Column('summaries_path', sa.String(500)),
        sa.Column('combined_context_path', sa.String(500)),
        sa.Column('error_stage', sa.String(50)),
        sa.Column('error_message', sa.Text),
        sa.Column('error_type', sa.String(50)),
        sa.Column('is_retryable', sa.Boolean, server_default='true'),
        sa.Column('message', sa.Text),
        sa.Column('details', JSONB),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
    )
    op.create_check_constraint(
        'job_states_entity_exactly_one_fk_check',
        'job_states',
        '((extraction_id IS NOT NULL AND document_id IS NULL AND workflow_run_id IS NULL AND template_fill_run_id IS NULL) OR '
        '(extraction_id IS NULL AND document_id IS NOT NULL AND workflow_run_id IS NULL AND template_fill_run_id IS NULL) OR '
        '(extraction_id IS NULL AND document_id IS NULL AND workflow_run_id IS NOT NULL AND template_fill_run_id IS NULL) OR '
        '(extraction_id IS NULL AND document_id IS NULL AND workflow_run_id IS NULL AND template_fill_run_id IS NOT NULL))'
    )
    op.create_index('idx_job_states_job_id', 'job_states', ['job_id'])
    op.create_index('idx_job_states_status', 'job_states', ['status'])
    op.create_index('idx_job_states_extraction_id', 'job_states', ['extraction_id'])
    op.create_index('idx_job_states_document_id', 'job_states', ['document_id'])
    op.create_index('idx_job_states_workflow_run_id', 'job_states', ['workflow_run_id'])
    op.create_index('idx_job_states_template_fill_run_id', 'job_states', ['template_fill_run_id'])

    # ========== FEEDBACK ==========
    op.create_table(
        'feedback',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('extraction_id', sa.String(36), sa.ForeignKey('extractions.id', ondelete='SET NULL')),
        sa.Column('rating', sa.Integer),
        sa.Column('comment', sa.Text),
        sa.Column('email', sa.String(255)),
        sa.Column('accuracy_rating', sa.Integer),
        sa.Column('would_pay', sa.Boolean),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    # Drop all tables in reverse order of creation
    op.drop_table('feedback')
    op.drop_check_constraint('job_states_entity_exactly_one_fk_check', 'job_states')
    op.drop_table('job_states')
    op.drop_table('template_fill_runs')
    op.drop_table('excel_templates')
    op.drop_table('usage_logs')
    op.drop_table('cache_entries')
    op.drop_table('parser_outputs')
    op.drop_table('extractions')
    op.drop_table('workflow_runs')
    op.drop_table('workflows')
    op.drop_table('chat_messages')
    op.drop_table('session_documents')
    op.drop_table('chat_sessions')
    op.drop_table('document_chunks')
    op.drop_table('collection_documents')
    op.drop_table('collections')
    op.drop_table('documents')
    op.drop_table('users')
