# backend/app/services/embeddings/__init__.py
"""
Embeddings module - Abstraction layer for different embedding providers.

Usage:
    from app.services.embeddings import get_embedding_provider

    # Get singleton instance (auto-configured from settings)
    embedder = get_embedding_provider()

    # Generate embeddings
    embedding = embedder.embed_text("Your text here")
    embeddings = embedder.embed_batch(["Text 1", "Text 2", "Text 3"])

To switch embedding providers, just change config:
    .env: EMBEDDING_PROVIDER=openai (instead of sentence-transformer)
"""
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.factory import get_embedding_provider, create_embedding_provider

__all__ = [
    "EmbeddingProvider",
    "get_embedding_provider",
    "create_embedding_provider",
]
