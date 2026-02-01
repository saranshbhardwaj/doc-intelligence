"""RAG (Retrieval-Augmented Generation) module for Chat Mode.

Main components:
- RAGService: Real-time chat with vector similarity search

NOTE: Lazy import to avoid circular dependency with service_locator.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from app.core.rag.rag_service import RAGService as RAGService


def __getattr__(name: str):
	if name == "RAGService":
		from app.core.rag.rag_service import RAGService
		return RAGService
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["RAGService"]
