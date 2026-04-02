# backend/app/config.py
from pydantic_settings import BaseSettings
from pathlib import Path
from pydantic import field_validator

class Settings(BaseSettings):
    """Application settings from environment variables"""

    # API Keys
    anthropic_api_key: str = ""  # Required at runtime; default allows container to boot for health checks
    anthropic_admin_api_key: str = ""  # sk-ant-admin-... from Anthropic Console (for Usage & Cost API)
    admin_api_key: str = "change-this-in-production"  # For analytics endpoint access

    # Authentication (WorkOS AuthKit)
    workos_client_id: str = ""  # Get from https://dashboard.workos.com
    workos_api_key: str = ""    # WorkOS API key (sk_...)

    # Database
    database_url: str = ""
    supabase_database_url: str = ""  # Use this name in Railway (DATABASE_URL is reserved)

    # Azure Document Intelligence (optional)
    azure_doc_intelligence_api_key: str = ""
    azure_doc_intelligence_endpoint: str = ""
    azure_doc_model: str = "prebuilt-layout"  # Azure Document Intelligence model to use
    azure_doc_timeout_seconds: int = 700  # Timeout for Azure parsing

    # Email notifications (simpler for MVP - using Gmail SMTP)
    notification_email: str = ""  # Your email to receive feedback notifications
    gmail_app_password: str = ""  # Gmail App Password (not your regular password!)


    # cache ttl
    cache_ttl: int = 48
    default_pages_limit: int = 100  # Default pages limit if user.pages_limit is None

    # Full extraction scalability limits
    max_pages_per_extraction: int = 150  # Max document size for full extraction (larger docs should use workflows)

    # ===== EXCEL TEMPLATE MAPPING CONFIGURATION =====
    # Schema-based mapping system for known Excel templates
    excel_schema_only: bool = True  # If True, only use schema (skip generic analyzer)
    excel_skip_schema: bool = False  # If True, skip schema (use generic analyzer only)
    # Default (both False) = Hybrid mode: schema first, generic fallback
    re_template_prompt_version: str = "v1"  # Active prompt version for template fill LLM calls
    rag_prompt_version: str = "v1"  # Active prompt version for RAG chat LLM calls

    # ===== LLM I/O CAPTURE (Eval / Debugging) =====
    # Off by default — never store full prompts in production unless explicitly enabled.
    # Set CAPTURE_LLM_IO_LOG=true to capture prompts/responses into llm_io_logs table
    # for eval dataset export. Applies to all verticals (template fill, RAG, PE).
    capture_llm_io_log: bool = True

    # ===== PARSER TIMEOUTS =====
    parser_timeout_seconds: int = 300  # Generic parser timeout

    # ===== TESTING OVERRIDES (Development Only - DO NOT USE IN PRODUCTION) =====
    # Force specific parser for all requests
    # Example: FORCE_PARSER=azure_document_intelligence to override default
    force_parser: str = ""

    # Force specific user tier for all requests (overrides database lookup)
    force_user_tier: str = ""

    # File Upload Limits
    max_file_size_mb: int = 5
    max_pages: int = 200 # Maximum number of pages per document
    
    # LLM Settings - Expensive Model (Structured Extraction)
    llm_model: str = "claude-sonnet-4-5-20250929"
    llm_max_tokens: int = 16000
    llm_max_input_chars: int = 130000
    llm_timeout_seconds: int = 300  # 5 minutes timeout for API calls (large documents can take 2-3 min)

    # LLM Settings - Cheap Model (Chunk Summarization & Workflows)
    cheap_llm_model: str = "claude-3-5-haiku-20241022"  # Much cheaper for summarization
    cheap_llm_max_tokens: int = 8000  # Increased for workflow outputs (Investment Memos need ~10-15K tokens)
    cheap_llm_timeout_seconds: int = 300  # Longer outputs need more time

    # LLM Settings - Synthesis Model (Final workflow synthesis in map-reduce)
    synthesis_llm_model: str = "claude-haiku-4-5-20251001"  # Haiku 4.5 for cost-effective synthesis (testing)
    synthesis_llm_max_tokens: int = 50000  # Haiku 4.5 max output: 64K tokens (leave room for overhead)
    synthesis_llm_timeout_seconds: int = 600  # 10 minutes for large workflow outputs

    # PE diligence classification fallback
    pe_diligence_classifier_llm_fallback_enabled: bool = True
    pe_diligence_classifier_llm_min_confidence: float = 0.60
    pe_diligence_classifier_llm_input_chars: int = 4000

    pe_diligence_llm_classification_enabled: bool = True  # opt-in until validated

    # PE diligence investigation LLM claim augmentation
    pe_diligence_investigation_llm_enabled: bool = True
    pe_diligence_investigation_llm_max_chunks: int = 30  # max unmatched chunks to send to LLM

    # PE diligence amendment linking (T11)
    pe_diligence_amendment_linking_enabled: bool = True  # opt-in until validated
    pe_diligence_amendment_linking_input_chars: int = 4000  # chars of amendment text sent to LLM
    pe_diligence_amendment_linking_max_room_docs: int = 100  # system prompt size guard
    pe_diligence_amendment_linking_concurrency: int = 10  # parallel LLM call cap

    # PE diligence LLM clause extraction (stage 4b)
    pe_diligence_llm_clause_extraction_enabled: bool = True  # opt-in until validated
    pe_diligence_llm_clause_max_chunks_per_type: int = 10    # max candidate chunks per clause_type
    pe_diligence_llm_clause_min_confidence: float = 0.50     # discard extracted clauses below this
    pe_diligence_llm_clause_min_semantic_similarity: float = 0.20  # drop hybrid chunks below this cosine similarity before LLM

    # PE diligence LLM numeric extraction (stage 5b)
    pe_diligence_llm_numeric_extraction_enabled: bool = True  # opt-in until validated
    pe_diligence_llm_numeric_max_chunks: int = 30              # max financial chunks sent to LLM
    pe_diligence_llm_numeric_min_confidence: float = 0.50      # discard extracted metrics below this

    # PE diligence per-document LLM analysis (runs for every classified doc)
    pe_diligence_per_doc_analysis_top_k: int = 12            # chunks sent to LLM after reranking (was 8)
    pe_diligence_per_doc_rerank_fetch_k: int = 20            # chunks fetched before reranking (headroom)
    pe_diligence_per_doc_analysis_concurrency: int = 5       # parallel LLM calls cap

    # PE diligence LLM findings synthesis (cross-doc, stage 7)
    pe_diligence_llm_findings_synthesis_enabled: bool = True  # opt-in until validated
    pe_diligence_llm_findings_max_input_chars: int = 30000     # max chars assembled for synthesis prompt

    # PE diligence LLM summary generation (stage 9 upgrade)
    pe_diligence_llm_summary_generation_enabled: bool = True  # opt-in until validated
    pe_diligence_llm_summary_max_input_chars: int = 40000      # max chars assembled for summary prompt

    # ===== CHAT MEMORY SETTINGS =====
    # Number of most recent messages (user+assistant turns) to include verbatim
    # Increased from 4 to 6 — gives 3 full user-assistant turns when history is included
    chat_verbatim_message_count: int = 6
    # Compact conversation history when (summary + recent messages) exceed this char count.
    # Keeps conversation portion of the prompt under budget so chunks are never trimmed.
    # Budget breakdown: total=50k, chunks=~30k, instructions=~1.7k → ~15k for conversation.
    chat_conversation_char_budget: int = 15_000
    # Minimum number of messages before we even consider summarization
    chat_summary_min_messages: int = 8
    # Hard cap on total messages examined when building context (for safety)
    chat_max_history_messages: int = 150
    # Maximum user message length enforced at API/UI layer (documentation only here)
    chat_max_user_chars: int = 10_000
    # Chat-specific prompt budget (chars) separate from global llm_max_input_chars
    # This is the maximum total characters we will pack (context + history + user message) BEFORE reserving
    chat_max_input_chars: int = 60_000
    # Reserved headroom for the model's own completion to avoid truncation (chars)
    chat_answer_reserve_chars: int = 10_000
    # Cache TTL for conversation summaries (seconds). If 0 or negative, caching disabled.
    chat_summary_cache_ttl_seconds: int = 86_400
    # Warn user after N user messages (round-trip count) - recommend new session
    chat_max_turns_before_warning: int = 30

    # Celery / Task Queue
    use_celery: bool = False  # Toggle to enable Celery task pipeline
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # Cache backend selection
    # If enabled, DocumentCache will use Redis instead of file-backed JSON files
    use_redis_cache: bool = True
    redis_url: str = "redis://localhost:6379/1"

    # Chunking Settings
    enable_chunking: bool = True  # Enable multi-stage LLM processing with chunking
    chunk_batch_size: int = 10  # Number of narrative chunks to process per cheap LLM call
    chunk_overlap_paragraphs: int = 1  # Paragraphs to repeat from previous chunk (structured docs)
    chunk_overlap_sentences: int = 2   # Sentences to repeat from previous chunk (unstructured/fallback docs)

    # ===== EMBEDDINGS CONFIGURATION =====
    # Embedding provider: "openai" (API) or "sentence-transformer" (local, not currently used)
    embedding_provider: str = "openai"

    # OpenAI settings (active embedding provider)
    openai_api_key: str = ""  # Required if using OpenAI embeddings
    openai_embedding_model: str = "text-embedding-3-small"  # $0.02 per 1M tokens
    # Other options: "text-embedding-3-large" (higher quality, 2x price)
    openai_embedding_dimensions: int = 768  # Reduced from default 1536 via Matryoshka dimensionality reduction

    # Vector dimension (must match embedding model output)
    # text-embedding-3-small with dimensions=768: 768, all-MiniLM-L6-v2: 384
    embedding_dimension: int = 768

    # ===== RAG HYBRID SEARCH SETTINGS =====
    # Combines semantic (vector) search with keyword (BM25/FTS) search
    # using Reciprocal Rank Fusion (RRF) for improved retrieval quality

    # RRF constant (k parameter) - controls rank decay
    # Higher k = less emphasis on top ranks (typically 60)
    # Formula: RRF_score = Σ(1 / (k + rank)) across all retrievers
    rag_hybrid_rrf_k: int = 60

    # Number of candidates to retrieve from each search method before merging
    rag_retrieval_candidates: int = 15

    # Final number of chunks to return after re-ranking (Phase 2)
    # Reduced from 12 to 8 — research shows 6-9 chunks is quality sweet spot
    rag_final_top_k: int = 8

    # Tighter budgets for narrow single-document fact lookups.
    rag_scoped_retrieval_candidates: int = 10
    rag_scoped_final_top_k: int = 5

    # Semantic similarity floors (raw cosine similarity) for filtering low-signal hits
    rag_chat_semantic_similarity_floor: float = 0.12
    rag_workflow_semantic_similarity_floor: float = 0.06

    # ===== DOCUMENT COMPARISON SETTINGS =====
    # Schema-based comparison system for multi-document analysis
    comparison_enabled: bool = True  # Enable document comparison feature
    comparison_similarity_threshold: float = 0.40  # Min similarity for pairing chunks (0-1); tuned for embedding cosine (not cross-encoder)
    comparison_chunks_per_doc: int = 8  # Chunks to retrieve per document (reduced from 10)
    comparison_max_pairs: int = 8  # Max pairs/clusters to include in prompt
    comparison_max_documents: int = 3  # Max number of documents to compare (2-3)
    # Early-exit pairing/clustering when retrieval signal is weak
    # Set to 0 to disable score-based early-exit
    comparison_pairing_min_top_score: float = 0.00
    comparison_pairing_min_chunks_per_doc: int = 1

    # ===== RAG RE-RANKER SETTINGS =====
    # Cross-encoder re-ranking for improved relevance scoring

    # Enable re-ranker (set to False to skip re-ranking step)
    rag_use_reranker: bool = True

    # Cross-encoder model for re-ranking
    # Options: "cross-encoder/ms-marco-MiniLM-L-6-v2" (22M params, ~3-5x faster on CPU)
    #          "BAAI/bge-reranker-base" (110M params, higher quality, multilingual)
    rag_reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Batch size for re-ranking (process multiple query-doc pairs together)
    rag_reranker_batch_size: int = 8

    # Token limit for re-ranker input (most cross-encoders have 512 token limit)
    rag_reranker_token_limit: int = 512

    # Apply metadata boosting to re-ranker scores (gentle nudge for tables/narrative)
    rag_reranker_apply_metadata_boost: bool = True

    # Skip re-ranking when candidate pool is tiny (chat/general RAG)
    rag_reranker_min_candidates_chat: int = 6

    # Skip per-document re-ranking in comparison flow when candidate pool is tiny
    rag_reranker_min_candidates_comparison: int = 6

    # Per-mode reranker toggles.
    # Comparison: disabled — embedding cosine pairing handles relevance; reranker adds ~76s with no benefit.
    # Chat: enabled — improves precision for real-time queries (MiniLM-L-6 ~5-8s on CPU).
    # Workflow: enabled — background Celery task, blocking is fine, quality matters for report generation.
    rag_use_reranker_comparison: bool = False
    rag_use_reranker_chat: bool = True
    rag_use_reranker_workflow: bool = True

    # ===== CONTEXT EXPANSION SETTINGS =====
    # Expand retrieved chunks with related context (tables, narratives, parents)

    # Enable context expansion for all query types (not just comparison)
    rag_expansion_enabled: bool = True

    # Quality gate for expansion - only expand chunks above this rerank score (0.0-1.0)
    # Lowered from 0.4: MiniLM-L-6-v2 outputs lower raw scores than BAAI/bge-reranker-base
    # (top scores of ~0.35 are still genuinely relevant). 0.2 lets expansion run for most
    # queries while still filtering very low-confidence chunks.
    rag_expansion_rerank_floor: float = 0.2

    # Score inheritance factors for expanded chunks (0.0-1.0)
    # Lower = expanded chunks rank below original chunks
    rag_expansion_score_narrative: float = 0.90  # Table → linked narrative
    rag_expansion_score_table: float = 0.85      # Narrative → linked table
    rag_expansion_score_parent: float = 0.75     # Continuation → parent

    # ===== RAG CHUNK COMPRESSION SETTINGS =====
    # Handle chunks that exceed re-ranker token limits

    # Enable compression (set to False to use only truncation)
    rag_use_compression: bool = True

    # LLMLingua model for prompt compression
    # Options: "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank" (recommended),
    #          "microsoft/llmlingua-2-xlm-roberta-large-meetingbank" (better quality, slower)
    rag_compression_model: str = "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"

    # Compression rate (0.0 - 1.0) - lower = more compression
    # 0.5 = compress to 50% of original tokens
    rag_compression_rate: float = 0.5

    # Truncation strategy for chunks exceeding token limit
    # "head_tail": Keep first 60% and last 40% of tokens
    # "head": Keep only first N tokens
    # "tail": Keep only last N tokens
    rag_truncation_strategy: str = "head_tail"

    # Preserve section headings during compression/truncation
    rag_preserve_headings: bool = True

    # Paths
    log_dir: Path = Path("logs")
    raw_dir: Path = Path("logs/raw")
    parsed_dir: Path = Path("logs/parsed")
    cache_dir: Path = log_dir / "cache"
    raw_llm_dir: Path = log_dir / "raw_llm_response"

    # Chunking pipeline paths (for debugging multi-stage LLM processing)
    chunks_dir: Path = log_dir / "chunks"          # Chunker output
    summaries_dir: Path = log_dir / "summaries"    # Cheap LLM summaries
    combined_dir: Path = log_dir / "combined"      # Combined context for expensive LLM

    feedback_dir: Path = log_dir / "feedback"
    analytics_dir: Path = log_dir / "analytics" 
    
    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:5174"]
    @field_validator("cors_origins", mode="before")
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [v]
        return v
    
    # Environment
    environment: str = "development"  # development, production
    mock_mode: bool = False

    # ===== EXPORT / STORAGE SETTINGS =====
    # Cloudflare R2 (S3-compatible) storage for large export artifacts
    exports_use_r2: bool = False  # Enable R2 storage for exports instead of direct streaming
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    r2_endpoint_url: str = ""  # e.g. https://<accountid>.r2.cloudflarestorage.com
    r2_presign_expiry: int = 3600  # seconds for signed URL validity

    # ===== DOCUMENT STORAGE SETTINGS =====
    # Use R2 for document (PDF/Excel) storage instead of local filesystem
    use_r2_for_documents: bool = True  # Toggle R2 for document uploads
    documents_presign_expiry: int = 7200  # 2 hours (longer than exports for PDF viewing during template fill)

    # Storage backend type (used by storage_factory)
    # Options: "r2" or "local" - automatically determined by use_r2_for_documents
    storage_backend: str = "r2"  # Auto-set based on use_r2_for_documents

    # ===== WORKFLOW BUDGET SETTINGS =====
    # Maximum tokens and cost per workflow run (to prevent runaway costs)
    workflow_max_tokens_per_run: int = 200_000  # Max tokens (input + output) per workflow run
    workflow_max_cost_per_run_usd: float = 5.0  # Max USD cost per workflow run
    workflow_max_attempts: int = 3  # Max LLM generation attempts with retry
    workflow_context_max_chars: int = 150_000  # Max context characters per workflow run
    workflow_map_reduce_token_threshold: int = 10_000  # Tokens above which map-reduce is used
    
    class Config:
        # Point explicitly to backend/.env so scripts run from repo root still load variables
        # __file__ points to backend/app/config.py; we need the backend/.env (one directory up)
        env_file = Path(__file__).resolve().parent.parent / ".env"
        case_sensitive = False
        extra = "ignore"  # Allow future env vars without breaking startup

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create directories if they don't exist
        for directory in [
            self.log_dir, self.raw_dir, self.parsed_dir, self.cache_dir,
            self.feedback_dir, self.raw_llm_dir, self.chunks_dir,
            self.summaries_dir, self.combined_dir, self.analytics_dir
        ]:
            directory.mkdir(parents=True, exist_ok=True)

        if self.use_celery:
            # Basic sanity log (logger imported lazily to avoid circular import here)
            try:
                from app.utils.logging import logger
                logger.info("Celery enabled", extra={"broker": self.celery_broker_url})
            except Exception:
                pass

# Global settings instance
settings = Settings()
