# backend/app/config.py
from pydantic_settings import BaseSettings
from pathlib import Path
from pydantic import field_validator

class Settings(BaseSettings):
    """Application settings from environment variables"""

    # API Keys
    anthropic_api_key: str
    admin_api_key: str = "change-this-in-production"  # For analytics endpoint access

    # Authentication (Clerk)
    clerk_secret_key: str = ""  # Get from https://dashboard.clerk.com
    clerk_publishable_key: str = ""  # Used by frontend

    # Database
    database_url: str = ""

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

    # ===== PARSER CONFIGURATION =====
    # Which parser to use for each tier + PDF type combination
    parser_free_digital: str = "pymupdf"
    parser_free_scanned: str = "none"  # "none" means not supported - will reject
    parser_pro_digital: str = "pymupdf"
    parser_pro_scanned: str = "none"  # Pro tier scanned PDF parser (e.g., "azure", "docai")
    parser_enterprise_digital: str = "pymupdf"
    parser_enterprise_scanned: str = "none"  # Enterprise tier scanned PDF parser

    # ===== PARSER TIMEOUTS =====
    parser_timeout_seconds: int = 300  # Generic parser timeout

    # ===== GOOGLE DOCUMENT AI (Optional) =====
    # Google Cloud settings for Document AI OCR
    google_cloud_project_id: str = ""
    google_application_credentials: str = ""
    document_ai_processor_id: str = ""
    document_ai_location: str = "us"
    gcs_bucket_name: str = ""  # Required for batch processing (>15 pages)

    # ===== TESTING OVERRIDES (Development Only - DO NOT USE IN PRODUCTION) =====
    # Force specific parser for all requests (overrides tier logic)
    # Example: FORCE_PARSER=llmwhisperer to test OCR
    force_parser: str = ""

    # Force specific user tier for all requests (overrides database lookup)
    # Example: FORCE_USER_TIER=pro to test pro tier features
    force_user_tier: str = ""

    document_ai_timeout_seconds: int = 900

    # File Upload Limits
    max_file_size_mb: int = 5
    max_pages: int = 200 # Maximum number of pages per document
    
    # LLM Settings - Expensive Model (Structured Extraction)
    llm_model: str = "claude-sonnet-4-5-20250929"
    llm_max_tokens: int = 16000
    llm_max_input_chars: int = 130000
    llm_timeout_seconds: int = 300  # 5 minutes timeout for API calls (large documents can take 2-3 min)

    # LLM Settings - Cheap Model (Chunk Summarization)
    cheap_llm_model: str = "claude-3-5-haiku-20241022"  # Much cheaper for summarization
    cheap_llm_max_tokens: int = 4000  # Summaries are shorter
    cheap_llm_timeout_seconds: int = 60  # Summaries are faster

    # ===== CHAT MEMORY SETTINGS =====
    # Number of most recent messages (user+assistant turns) to include verbatim
    chat_verbatim_message_count: int = 4
    # Ratio of estimated token usage (history + current user message) to max input
    # at which we trigger summarization of older history (0.50 - 0.60 per user guidance)
    chat_summary_trigger_ratio: float = 0.55
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

    # Celery / Task Queue
    use_celery: bool = False  # Toggle to enable Celery task pipeline
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # Cache backend selection
    # If enabled, DocumentCache will use Redis instead of file-backed JSON files
    use_redis_cache: bool = False
    redis_url: str = "redis://localhost:6379/1"

    # Chunking Settings
    enable_chunking: bool = True  # Enable multi-stage LLM processing with chunking
    chunk_batch_size: int = 10  # Number of narrative chunks to process per cheap LLM call

    # ===== EMBEDDINGS CONFIGURATION =====
    # Which embedding provider to use: "sentence-transformer" (free, local) or "openai" (paid, API)
    embedding_provider: str = "sentence-transformer"

    # Sentence Transformer settings (used if embedding_provider="sentence-transformer")
    sentence_transformer_model: str = "all-MiniLM-L6-v2"  # Fast, good quality, 384 dimensions
    # Other options: "all-mpnet-base-v2" (768d, slower but better), "multi-qa-MiniLM-L6-cos-v1" (384d, optimized for Q&A)

    # OpenAI settings (used if embedding_provider="openai")
    openai_api_key: str = ""  # Required if using OpenAI embeddings
    openai_embedding_model: str = "text-embedding-3-small"  # 1536 dimensions, $0.02 per 1M tokens
    # Other options: "text-embedding-3-large" (3072d, better quality, 2x price)

    # Vector dimension (auto-set based on model, but can override)
    # all-MiniLM-L6-v2: 384, all-mpnet-base-v2: 768, text-embedding-3-small: 1536
    embedding_dimension: int = 384

    # ===== RAG HYBRID SEARCH SETTINGS =====
    # Combines semantic (vector) search with keyword (BM25/FTS) search
    # for improved retrieval quality

    # Weight for semantic search in hybrid scoring (0.0 - 1.0)
    rag_hybrid_semantic_weight: float = 0.6

    # Weight for keyword search in hybrid scoring (0.0 - 1.0)
    rag_hybrid_keyword_weight: float = 0.4

    # Number of candidates to retrieve from each search method before merging
    rag_retrieval_candidates: int = 20

    # Final number of chunks to return after re-ranking (Phase 2)
    rag_final_top_k: int = 10

    # ===== RAG RE-RANKER SETTINGS =====
    # Cross-encoder re-ranking for improved relevance scoring

    # Enable re-ranker (set to False to skip re-ranking step)
    rag_use_reranker: bool = True

    # Cross-encoder model for re-ranking
    # Options: "cross-encoder/ms-marco-MiniLM-L-6-v2", "BAAI/bge-reranker-base", "BAAI/bge-reranker-large"
    rag_reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Batch size for re-ranking (process multiple query-doc pairs together)
    rag_reranker_batch_size: int = 8

    # Token limit for re-ranker input (most cross-encoders have 512 token limit)
    rag_reranker_token_limit: int = 512

    # Apply metadata boosting to re-ranker scores (gentle nudge for tables/narrative)
    rag_reranker_apply_metadata_boost: bool = True

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
    cors_origins: list[str] = ["http://localhost:5173"]
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

    # ===== WORKFLOW BUDGET SETTINGS =====
    # Maximum tokens and cost per workflow run (to prevent runaway costs)
    workflow_max_tokens_per_run: int = 200_000  # Max tokens (input + output) per workflow run
    workflow_max_cost_per_run_usd: float = 5.0  # Max USD cost per workflow run
    workflow_max_attempts: int = 3  # Max LLM generation attempts with retry
    workflow_context_max_chars: int = 150_000  # Max context characters per workflow run
    
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