# app/api/dependencies.py
from fastapi import Request
from app.services.llm_client import LLMClient
from app.services.document_processor import DocumentProcessor
from app.services.cache import DocumentCache
from app.services.rate_limiter import RateLimiter
from app.services.analytics import SimpleAnalytics
from app.services.extraction_pipeline import ExtractionPipeline
from app.repositories import ExtractionRepository
from app.config import settings

# Initialize services
cache = DocumentCache(
    cache_dir=settings.cache_dir,
    cache_ttl_hours=settings.cache_ttl
)

rate_limiter = RateLimiter(
    max_uploads=settings.rate_limit_uploads,
    window_hours=settings.rate_limit_window_hours
)

document_processor = DocumentProcessor(
    max_pages=settings.max_pages,
    max_file_size_bytes=settings.max_file_size_mb * 1024 * 1024
)

llm_client = LLMClient(
    api_key=settings.anthropic_api_key,
    model=settings.llm_model,
    max_tokens=settings.llm_max_tokens,
    max_input_chars=settings.llm_max_input_chars,
    timeout_seconds=settings.llm_timeout_seconds
)

# Extraction pipeline (orchestrates chunking + multi-stage LLM processing)
extraction_pipeline = ExtractionPipeline(llm_client=llm_client)

# Data access layer for extractions
extraction_repository = ExtractionRepository()

analytics = SimpleAnalytics(analytics_dir=settings.analytics_dir)

def get_client_ip(request: Request) -> str:
    """Extract client IP from request"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host or "unknown"