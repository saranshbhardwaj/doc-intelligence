# app/api/dependencies.py
from fastapi import Request
# from app.services.llm_client import LLMClient
from app.services.document_processor import DocumentProcessor
from app.services.cache import create_cache
from app.services.analytics import SimpleAnalytics
from app.repositories import ExtractionRepository
from app.config import settings

# Initialize services
cache = create_cache(
    cache_dir=settings.cache_dir,
    cache_ttl_hours=settings.cache_ttl
)

document_processor = DocumentProcessor(
    max_pages=settings.max_pages,
    max_file_size_bytes=settings.max_file_size_mb * 1024 * 1024
)

analytics = SimpleAnalytics(analytics_dir=settings.analytics_dir)

def get_client_ip(request: Request) -> str:
    """Extract client IP from request"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host or "unknown"