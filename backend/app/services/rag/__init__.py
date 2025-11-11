# backend/app/services/rag/__init__.py
"""
RAG (Retrieval-Augmented Generation) module for Chat Mode.

Main components:
- RAGService: Real-time chat with vector similarity search
"""

from app.services.rag.rag_service import RAGService

__all__ = ["RAGService"]
