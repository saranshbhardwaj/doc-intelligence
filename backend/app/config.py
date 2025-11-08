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

    # Celery / Task Queue
    use_celery: bool = False  # Toggle to enable Celery task pipeline
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # Chunking Settings
    enable_chunking: bool = True  # Enable multi-stage LLM processing with chunking
    chunk_batch_size: int = 10  # Number of narrative chunks to process per cheap LLM call
    
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