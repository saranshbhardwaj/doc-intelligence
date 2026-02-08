-- Fix ALL missing columns in database tables to match ORM models
-- Run this with: docker exec docint-postgres psql -U docint -d docint -f /path/to/fix_missing_columns.sql

-- ========== CHAT_SESSIONS ==========
ALTER TABLE chat_sessions
ADD COLUMN IF NOT EXISTS org_id VARCHAR(64),
ADD COLUMN IF NOT EXISTS last_summary_text TEXT,
ADD COLUMN IF NOT EXISTS last_summary_key_facts JSONB,
ADD COLUMN IF NOT EXISTS last_summarized_index INTEGER,
ADD COLUMN IF NOT EXISTS last_summary_updated_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX IF NOT EXISTS ix_chat_sessions_org_id ON chat_sessions(org_id);

-- ========== CHAT_MESSAGES ==========
ALTER TABLE chat_messages
ADD COLUMN IF NOT EXISTS input_tokens INTEGER,
ADD COLUMN IF NOT EXISTS output_tokens INTEGER,
ADD COLUMN IF NOT EXISTS cache_read_tokens INTEGER,
ADD COLUMN IF NOT EXISTS cache_write_tokens INTEGER,
ADD COLUMN IF NOT EXISTS comparison_metadata TEXT,
ADD COLUMN IF NOT EXISTS citation_metadata TEXT;

-- ========== DOCUMENT_CHUNKS ==========
ALTER TABLE document_chunks
ADD COLUMN IF NOT EXISTS narrative_text TEXT,
ADD COLUMN IF NOT EXISTS tables JSONB,
ADD COLUMN IF NOT EXISTS text_search_vector TSVECTOR,
ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(100),
ADD COLUMN IF NOT EXISTS embedding_version VARCHAR(20),
ADD COLUMN IF NOT EXISTS chunk_metadata JSONB;

CREATE INDEX IF NOT EXISTS idx_document_chunks_text_search ON document_chunks USING gin(text_search_vector);

-- ========== WORKFLOWS ==========
ALTER TABLE workflows
ADD COLUMN IF NOT EXISTS domain VARCHAR(50),
ADD COLUMN IF NOT EXISTS user_prompt_template TEXT,
ADD COLUMN IF NOT EXISTS user_prompt_max_length INTEGER,
ADD COLUMN IF NOT EXISTS output_schema JSONB,
ADD COLUMN IF NOT EXISTS retrieval_spec_json JSONB,
ADD COLUMN IF NOT EXISTS deprecated_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS replacement_workflow_id VARCHAR(36);

-- ========== WORKFLOW_RUNS ==========
ALTER TABLE workflow_runs
ADD COLUMN IF NOT EXISTS org_id VARCHAR(64),
ADD COLUMN IF NOT EXISTS user_id VARCHAR(100),
ADD COLUMN IF NOT EXISTS collection_id VARCHAR(36),
ADD COLUMN IF NOT EXISTS workflow_snapshot JSONB,
ADD COLUMN IF NOT EXISTS document_ids JSONB,
ADD COLUMN IF NOT EXISTS variables JSONB,
ADD COLUMN IF NOT EXISTS mode VARCHAR(30),
ADD COLUMN IF NOT EXISTS strategy VARCHAR(30),
ADD COLUMN IF NOT EXISTS artifact JSONB,
ADD COLUMN IF NOT EXISTS output_format VARCHAR(50),
ADD COLUMN IF NOT EXISTS token_usage INTEGER,
ADD COLUMN IF NOT EXISTS cost_usd FLOAT,
ADD COLUMN IF NOT EXISTS latency_ms INTEGER,
ADD COLUMN IF NOT EXISTS currency VARCHAR(10),
ADD COLUMN IF NOT EXISTS citations_count INTEGER,
ADD COLUMN IF NOT EXISTS attempts INTEGER,
ADD COLUMN IF NOT EXISTS citation_invalid_count INTEGER,
ADD COLUMN IF NOT EXISTS validation_errors JSONB,
ADD COLUMN IF NOT EXISTS context_stats JSONB,
ADD COLUMN IF NOT EXISTS section_summaries JSONB,
ADD COLUMN IF NOT EXISTS input_tokens INTEGER,
ADD COLUMN IF NOT EXISTS output_tokens INTEGER,
ADD COLUMN IF NOT EXISTS cache_read_tokens INTEGER,
ADD COLUMN IF NOT EXISTS cache_write_tokens INTEGER,
ADD COLUMN IF NOT EXISTS model_name VARCHAR(100),
ADD COLUMN IF NOT EXISTS version INTEGER,
ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX IF NOT EXISTS ix_workflow_runs_org_id ON workflow_runs(org_id);
CREATE INDEX IF NOT EXISTS ix_workflow_runs_user_id ON workflow_runs(user_id);
CREATE INDEX IF NOT EXISTS ix_workflow_runs_collection_id ON workflow_runs(collection_id);

ALTER TABLE workflow_runs
ADD CONSTRAINT IF NOT EXISTS fk_workflow_runs_collection_id
FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE SET NULL;

-- ========== EXTRACTIONS ==========
ALTER TABLE extractions
ADD COLUMN IF NOT EXISTS document_id VARCHAR(36),
ADD COLUMN IF NOT EXISTS org_id VARCHAR(64),
ADD COLUMN IF NOT EXISTS result JSONB,
ADD COLUMN IF NOT EXISTS artifact JSONB,
ADD COLUMN IF NOT EXISTS from_history BOOLEAN,
ADD COLUMN IF NOT EXISTS total_cost_usd FLOAT,
ADD COLUMN IF NOT EXISTS llm_input_tokens INTEGER,
ADD COLUMN IF NOT EXISTS llm_output_tokens INTEGER,
ADD COLUMN IF NOT EXISTS llm_model_name VARCHAR(100),
ADD COLUMN IF NOT EXISTS llm_cost_usd FLOAT;

CREATE INDEX IF NOT EXISTS ix_extractions_org_id ON extractions(org_id);
CREATE INDEX IF NOT EXISTS ix_extractions_document_id ON extractions(document_id);

ALTER TABLE extractions
ADD CONSTRAINT IF NOT EXISTS fk_extractions_document_id
FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE;

-- ========== JOB_STATES ==========
ALTER TABLE job_states
ADD COLUMN IF NOT EXISTS job_id VARCHAR(36),
ADD COLUMN IF NOT EXISTS document_id VARCHAR(36),
ADD COLUMN IF NOT EXISTS workflow_run_id VARCHAR(36),
ADD COLUMN IF NOT EXISTS template_fill_run_id VARCHAR(36),
ADD COLUMN IF NOT EXISTS embedding_completed BOOLEAN,
ADD COLUMN IF NOT EXISTS storing_completed BOOLEAN,
ADD COLUMN IF NOT EXISTS context_completed BOOLEAN,
ADD COLUMN IF NOT EXISTS artifact_completed BOOLEAN,
ADD COLUMN IF NOT EXISTS validation_completed BOOLEAN,
ADD COLUMN IF NOT EXISTS field_detection_completed BOOLEAN,
ADD COLUMN IF NOT EXISTS auto_mapping_completed BOOLEAN,
ADD COLUMN IF NOT EXISTS data_extraction_completed BOOLEAN,
ADD COLUMN IF NOT EXISTS excel_filling_completed BOOLEAN;

CREATE INDEX IF NOT EXISTS ix_job_states_document_id ON job_states(document_id);
CREATE INDEX IF NOT EXISTS ix_job_states_workflow_run_id ON job_states(workflow_run_id);

ALTER TABLE job_states
ADD CONSTRAINT IF NOT EXISTS fk_job_states_document_id
FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
ADD CONSTRAINT IF NOT EXISTS fk_job_states_workflow_run_id
FOREIGN KEY (workflow_run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE;

-- ========== DOCUMENTS (check if needed columns exist) ==========
ALTER TABLE documents
ADD COLUMN IF NOT EXISTS org_id VARCHAR(64),
ADD COLUMN IF NOT EXISTS user_id VARCHAR(100);

CREATE INDEX IF NOT EXISTS ix_documents_org_id ON documents(org_id);
CREATE INDEX IF NOT EXISTS ix_documents_user_id ON documents(user_id);

-- ========== SESSION_DOCUMENTS (create if doesn't exist) ==========
CREATE TABLE IF NOT EXISTS session_documents (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL,
    document_id VARCHAR(36) NOT NULL,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_session_documents_session_id ON session_documents(session_id);
CREATE INDEX IF NOT EXISTS ix_session_documents_document_id ON session_documents(document_id);

-- ========== COLLECTION_DOCUMENTS (check columns) ==========
ALTER TABLE collection_documents
ADD COLUMN IF NOT EXISTS added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- ========== EXCEL_TEMPLATES (create if doesn't exist) ==========
CREATE TABLE IF NOT EXISTS excel_templates (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    org_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    file_path VARCHAR(512) NOT NULL,
    file_extension VARCHAR(10),
    file_size_bytes INTEGER NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    schema_metadata JSONB,
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP WITH TIME ZONE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_excel_templates_org_id ON excel_templates(org_id);
CREATE INDEX IF NOT EXISTS ix_excel_templates_user_id ON excel_templates(user_id);

-- ========== TEMPLATE_FILL_RUNS (create if doesn't exist) ==========
CREATE TABLE IF NOT EXISTS template_fill_runs (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    template_id VARCHAR(36) NOT NULL,
    document_id VARCHAR(36),
    org_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(100) NOT NULL,
    template_snapshot JSONB,
    field_mapping JSONB,
    extracted_data JSONB,
    artifact JSONB,
    status VARCHAR(20),
    current_stage VARCHAR(50),
    field_detection_completed BOOLEAN,
    auto_mapping_completed BOOLEAN,
    user_review_completed BOOLEAN,
    extraction_completed BOOLEAN,
    filling_completed BOOLEAN,
    total_fields_detected INTEGER,
    total_fields_mapped INTEGER,
    total_fields_filled INTEGER,
    auto_mapped_count INTEGER,
    user_edited_count INTEGER,
    cost_usd FLOAT,
    processing_time_ms INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_write_tokens INTEGER,
    model_name VARCHAR(100),
    llm_batches_count INTEGER,
    cache_hit_rate FLOAT,
    error_stage VARCHAR(50),
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    FOREIGN KEY (template_id) REFERENCES excel_templates(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_template_fill_runs_template_id ON template_fill_runs(template_id);
CREATE INDEX IF NOT EXISTS ix_template_fill_runs_org_id ON template_fill_runs(org_id);
CREATE INDEX IF NOT EXISTS ix_template_fill_runs_user_id ON template_fill_runs(user_id);

SELECT 'All missing columns and tables have been added!' AS result;
