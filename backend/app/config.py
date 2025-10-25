# backend/app/config.py
from pydantic_settings import BaseSettings
from pathlib import Path
from pydantic import field_validator

class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    # API Keys
    anthropic_api_key: str
    
    # Rate Limiting
    rate_limit_uploads: int = 3
    rate_limit_window_hours: int = 24

    # cache ttl
    cache_ttl: int = 48
    
    # File Upload Limits
    max_file_size_mb: int = 5
    max_pages: int = 60
    
    # LLM Settings
    llm_model: str = "claude-sonnet-4-5-20250929"
    llm_max_tokens: int = 16000
    llm_max_input_chars: int = 100000
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
        env_file = ".env"
        case_sensitive = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Create directories if they don't exist
        # Create directories if they don't exist
        for directory in [self.log_dir, self.raw_dir, self.parsed_dir, self.cache_dir, self.feedback_dir, self.raw_llm_dir]:
            directory.mkdir(parents=True, exist_ok=True)

# Global settings instance
settings = Settings()