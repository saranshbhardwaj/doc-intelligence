"""Clean schema - drop all and recreate with proper architecture

Revision ID: clean_schema_2025_11_16
Revises:
Create Date: 2025-11-16

This migration drops ALL existing tables and recreates them with clean architecture:
- documents: Single source of truth for all documents
- document_chunks: Chunks belong to documents (not collection_documents)
- collection_documents: Pure link table (no duplicate metadata)
- extractions: References documents table
- job_states: References documents (not collection_documents)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = 'clean_schema_2025_11_16'
down_revision = None  # This is a clean slate migration
branch_labels = None
depends_on = None


def upgrade():
    """Drop all tables and recreate with clean schema"""

    # Drop all existing tables (order matters due to foreign keys)
    op.execute("DROP TABLE IF EXISTS chat_messages CASCADE")
    op.execute("DROP TABLE IF EXISTS chat_sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS document_chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS collection_documents CASCADE")
    op.execute("DROP TABLE IF EXISTS collections CASCADE")
    op.execute("DROP TABLE IF EXISTS job_states CASCADE")
    op.execute("DROP TABLE IF EXISTS parser_outputs CASCADE")
    op.execute("DROP TABLE IF EXISTS extractions CASCADE")
    op.execute("DROP TABLE IF EXISTS cache_entries CASCADE")
    op.execute("DROP TABLE IF EXISTS workflow_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS workflows CASCADE")
    op.execute("DROP TABLE IF EXISTS documents CASCADE")

    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ==================== DOCUMENTS (Canonical) ====================
    op.create_table(
        'documents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(100), nullable=False, index=True),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(512), nullable=True),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('page_count', sa.Integer(), nullable=False),
        sa.Column('chunk_count', sa.Integer(), default=0),
        sa.Column('status', sa.String(20), default='processing'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('parser_used', sa.String(50), nullable=True),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('content_hash', name='uq_documents_content_hash'),
    )
    op.create_index('idx_documents_user_id', 'documents', ['user_id'])
    op.create_index('idx_documents_content_hash', 'documents', ['content_hash'])
    op.create_index('idx_documents_status', 'documents', ['status'])

    # ==================== COLLECTIONS ====================
    op.create_table(
        'collections',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(100), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('document_count', sa.Integer(), default=0),
        sa.Column('total_chunks', sa.Integer(), default=0),
        sa.Column('embedding_model', sa.String(100), nullable=True),
        sa.Column('embedding_dimension', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_collections_user_id', 'collections', ['user_id'])

    # ==================== COLLECTION_DOCUMENTS (Link Table) ====================
    op.create_table(
        'collection_documents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('collection_id', sa.String(36), sa.ForeignKey('collections.id', ondelete='CASCADE'), nullable=False),
        sa.Column('document_id', sa.String(36), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_collection_documents_collection_id', 'collection_documents', ['collection_id'])
    op.create_index('idx_collection_documents_document_id', 'collection_documents', ['document_id'])

    # ==================== DOCUMENT_CHUNKS ====================
    op.create_table(
        'document_chunks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('document_id', sa.String(36), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('embedding', Vector(384), nullable=True),  # 384 dimensions for all-MiniLM-L6-v2
        sa.Column('embedding_model', sa.String(100), nullable=True),  # Track which model was used
        sa.Column('embedding_version', sa.String(20), nullable=True),  # Model version for migration
        sa.Column('page_number', sa.Integer(), nullable=True),
        sa.Column('section_type', sa.String(50), nullable=True),
        sa.Column('section_heading', sa.Text(), nullable=True),
        sa.Column('is_tabular', sa.Boolean(), default=False),
        sa.Column('token_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_document_chunks_document_id', 'document_chunks', ['document_id'])
    # Create HNSW index for vector similarity search with cosine distance
    op.execute("CREATE INDEX idx_document_chunks_embedding ON document_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)")

    # ==================== EXTRACTIONS ====================
    op.create_table(
        'extractions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('document_id', sa.String(36), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(100), nullable=False, index=True),
        sa.Column('context', sa.Text(), nullable=True),
        sa.Column('result', postgresql.JSONB(), nullable=True),
        sa.Column('from_cache', sa.Boolean(), default=False),
        sa.Column('from_history', sa.Boolean(), default=False),
        sa.Column('total_cost_usd', sa.Float(), default=0.0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_extractions_user_id', 'extractions', ['user_id'])
    op.create_index('idx_extractions_document_id', 'extractions', ['document_id'])

    # ==================== PARSER_OUTPUTS ====================
    op.create_table(
        'parser_outputs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('extraction_id', sa.String(36), sa.ForeignKey('extractions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('parser_name', sa.String(50), nullable=False),
        sa.Column('parser_version', sa.String(20), nullable=True),
        sa.Column('pdf_type', sa.String(20), nullable=True),
        sa.Column('raw_output', postgresql.JSONB(), nullable=True),
        sa.Column('raw_output_length', sa.Integer(), nullable=True),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), default=0.0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ==================== CACHE_ENTRIES ====================
    op.create_table(
        'cache_entries',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('content_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=False),
        sa.Column('page_count', sa.Integer(), nullable=False),
        sa.Column('company_name', sa.String(255), nullable=True),
        sa.Column('industry', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('last_accessed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('access_count', sa.Integer(), default=0),
    )
    op.create_index('idx_cache_entries_content_hash', 'cache_entries', ['content_hash'])

    # ==================== WORKFLOWS ====================
    op.create_table(
        'workflows',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('prompt_template', sa.Text(), nullable=False),
        sa.Column('variables_schema', postgresql.JSONB(), nullable=True),
        sa.Column('output_schema', postgresql.JSONB(), nullable=True),
        sa.Column('output_format', sa.String(50), nullable=False, server_default='markdown'),
        sa.Column('min_documents', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('max_documents', sa.Integer(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_workflows_name', 'workflows', ['name'])

    # ==================== WORKFLOW_RUNS ====================
    op.create_table(
        'workflow_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('workflow_id', sa.String(36), sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(100), nullable=False),
        sa.Column('collection_id', sa.String(36), sa.ForeignKey('collections.id', ondelete='SET NULL'), nullable=True),
        sa.Column('document_ids', postgresql.JSONB(), nullable=True),
        sa.Column('variables', postgresql.JSONB(), nullable=True),
        sa.Column('mode', sa.String(30), nullable=False, server_default='single_doc'),
        sa.Column('strategy', sa.String(30), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='queued'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('artifact', postgresql.JSONB(), nullable=True),
        sa.Column('output_format', sa.String(50), nullable=True),
        sa.Column('token_usage', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('citations_count', sa.Integer(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=True),
        sa.Column('citation_invalid_count', sa.Integer(), nullable=True),
        sa.Column('validation_errors', postgresql.JSONB(), nullable=True),
        sa.Column('context_stats', postgresql.JSONB(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('idx_workflow_runs_workflow_id', 'workflow_runs', ['workflow_id'])
    op.create_index('idx_workflow_runs_user_id', 'workflow_runs', ['user_id'])
    op.create_index('idx_workflow_runs_collection_id', 'workflow_runs', ['collection_id'])

    # ==================== JOB_STATES ====================
    op.create_table(
        'job_states',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('job_id', sa.String(36), nullable=False, unique=True),
        sa.Column('extraction_id', sa.String(36), sa.ForeignKey('extractions.id', ondelete='CASCADE'), nullable=True),
        sa.Column('document_id', sa.String(36), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=True),
        sa.Column('workflow_run_id', sa.String(36), sa.ForeignKey('workflow_runs.id', ondelete='CASCADE'), nullable=True),
        sa.Column('status', sa.String(20), default='queued'),
        sa.Column('current_stage', sa.String(50), nullable=True),
        sa.Column('progress_percent', sa.Integer(), default=0),
        sa.Column('parsing_completed', sa.Boolean(), default=False),
        sa.Column('chunking_completed', sa.Boolean(), default=False),
        sa.Column('summarizing_completed', sa.Boolean(), default=False),
        sa.Column('extracting_completed', sa.Boolean(), default=False),
        sa.Column('embedding_completed', sa.Boolean(), default=False),
        sa.Column('storing_completed', sa.Boolean(), default=False),
        sa.Column('context_completed', sa.Boolean(), default=False),
        sa.Column('artifact_completed', sa.Boolean(), default=False),
        sa.Column('validation_completed', sa.Boolean(), default=False),
        sa.Column('parsed_output_path', sa.String(500), nullable=True),
        sa.Column('chunks_path', sa.String(500), nullable=True),
        sa.Column('summaries_path', sa.String(500), nullable=True),
        sa.Column('combined_context_path', sa.String(500), nullable=True),
        sa.Column('error_stage', sa.String(50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_type', sa.String(50), nullable=True),
        sa.Column('is_retryable', sa.Boolean(), default=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            '((extraction_id IS NOT NULL AND document_id IS NULL AND workflow_run_id IS NULL) OR '
            '(extraction_id IS NULL AND document_id IS NOT NULL AND workflow_run_id IS NULL) OR '
            '(extraction_id IS NULL AND document_id IS NULL AND workflow_run_id IS NOT NULL))',
            name='job_states_entity_exactly_one_fk_check'
        ),
    )
    op.create_index('idx_job_states_job_id', 'job_states', ['job_id'])
    op.create_index('idx_job_states_status', 'job_states', ['status'])
    op.create_index('idx_job_states_extraction_id', 'job_states', ['extraction_id'])
    op.create_index('idx_job_states_document_id', 'job_states', ['document_id'])
    op.create_index('idx_job_states_workflow_run_id', 'job_states', ['workflow_run_id'])

    # ==================== CHAT_SESSIONS ====================
    op.create_table(
        'chat_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('collection_id', sa.String(36), sa.ForeignKey('collections.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(100), nullable=False, index=True),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('message_count', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_chat_sessions_collection_id', 'chat_sessions', ['collection_id'])
    op.create_index('idx_chat_sessions_user_id', 'chat_sessions', ['user_id'])

    # ==================== CHAT_MESSAGES ====================
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('message_index', sa.Integer(), nullable=False),
        sa.Column('source_chunks', sa.Text(), nullable=True),
        sa.Column('retrieval_query', sa.Text(), nullable=True),
        sa.Column('num_chunks_retrieved', sa.Integer(), nullable=True),
        sa.Column('model_used', sa.String(100), nullable=True),
        sa.Column('tokens_used', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_chat_messages_session_id_index', 'chat_messages', ['session_id', 'message_index'])


def downgrade():
    """Drop all tables"""
    op.execute("DROP TABLE IF EXISTS chat_messages CASCADE")
    op.execute("DROP TABLE IF EXISTS chat_sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS document_chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS collection_documents CASCADE")
    op.execute("DROP TABLE IF EXISTS collections CASCADE")
    op.execute("DROP TABLE IF EXISTS job_states CASCADE")
    op.execute("DROP TABLE IF EXISTS parser_outputs CASCADE")
    op.execute("DROP TABLE IF EXISTS extractions CASCADE")
    op.execute("DROP TABLE IF EXISTS cache_entries CASCADE")
    op.execute("DROP TABLE IF EXISTS workflow_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS workflows CASCADE")
    op.execute("DROP TABLE IF EXISTS documents CASCADE")
