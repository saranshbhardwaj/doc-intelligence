# backend/app/config.py
from pydantic_settings import BaseSettings
from pathlib import Path
from pydantic import field_validator

class Settings(BaseSettings):
    """Application settings from environment variables"""

    # API Keys
    anthropic_api_key: str
    admin_api_key: str = "change-this-in-production"  # For analytics endpoint access
    llmwhisperer_api_key: str = ""  # Optional - for OCR support (Pro tier)

    # Database
    database_url: str = ""  # Leave empty for SQLite in development

    # Notifications (optional - leave empty to disable)
    slack_webhook_url: str = ""  # Get from: https://api.slack.com/messaging/webhooks

    # Email notifications (simpler for MVP - using Gmail SMTP)
    notification_email: str = ""  # Your email to receive feedback notifications
    gmail_app_password: str = ""  # Gmail App Password (not your regular password!)
    
    # Rate Limiting
    rate_limit_uploads: int = 3
    rate_limit_window_hours: int = 24

    # cache ttl
    cache_ttl: int = 48

    # ===== PARSER CONFIGURATION =====
    # Which parser to use for each tier + PDF type combination
    parser_free_digital: str = "pymupdf"
    parser_free_scanned: str = "none"  # "none" means not supported - will reject
    parser_pro_digital: str = "pymupdf"
    parser_pro_scanned: str = "llmwhisperer"
    parser_enterprise_digital: str = "llmwhisperer"
    parser_enterprise_scanned: str = "llmwhisperer"

    # ===== RATE LIMITS PER TIER =====
    # Free tier
    rate_limit_free_daily: int = 2
    rate_limit_free_monthly: int = 60
    # Pro tier
    rate_limit_pro_daily: int = 50
    rate_limit_pro_monthly: int = 1500
    # Enterprise tier (-1 means unlimited)
    rate_limit_enterprise_daily: int = -1
    rate_limit_enterprise_monthly: int = -1

    # ===== PARSER TIMEOUTS =====
    llmwhisperer_timeout_seconds: int = 300  # 5 minutes
    parser_timeout_seconds: int = 300  # Generic parser timeout

    # ===== LLMWHISPERER MODE =====
    # Processing mode for LLMWhisperer OCR (determines price per page)
    # Options: native_text ($0.001/page), low_cost ($0.005/page), high_quality ($0.010/page), form_elements ($0.015/page)
    llmwhisperer_mode: str = "low_cost"  # Recommended for testing and comparison

    # Output mode (FREE - just formatting)
    # Options: layout_preserving (optimized for LLMs), text (raw text)
    llmwhisperer_output_mode: str = "text"

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
    max_pages: int = 60
    
    # LLM Settings
    llm_model: str = "claude-sonnet-4-5-20250929"
    llm_max_tokens: int = 16000
    llm_max_input_chars: int = 130000
    llm_timeout_seconds: int = 300  # 5 minutes timeout for API calls (large documents can take 2-3 min)
    
    # Paths
    log_dir: Path = Path("logs")
    raw_dir: Path = Path("logs/raw")
    parsed_dir: Path = Path("logs/parsed")
    cache_dir: Path = log_dir / "cache" 
    raw_llm_dir: Path = log_dir / "raw_llm_response" 

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
        env_file = Path(__file__).parent / ".env"
        case_sensitive = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create directories if they don't exist
        # Create directories if they don't exist
        for directory in [self.log_dir, self.raw_dir, self.parsed_dir, self.cache_dir, self.feedback_dir, self.raw_llm_dir]:
            directory.mkdir(parents=True, exist_ok=True)

# Global settings instance
settings = Settings()