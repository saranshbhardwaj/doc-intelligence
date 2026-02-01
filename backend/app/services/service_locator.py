# backend/app/services/service_locator.py

from app.core.rag.reranker import Reranker  # Use NEW reranker (supports QueryUnderstanding)
from app.config import settings
from app.utils.logging import logger

_reranker: Reranker | None = None

def get_reranker() -> Reranker | None:
    """Get or create global reranker instance."""
    global _reranker
    
    if not settings.rag_use_reranker:
        return None
    
    if _reranker is None:
        logger.info("Initializing reranker (one-time load)...")
        _reranker = Reranker()
        logger.info("Reranker ready")
    
    return _reranker