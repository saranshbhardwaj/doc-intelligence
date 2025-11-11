# backend/app/api/chat/__init__.py
"""
Chat Mode API - Main router aggregator.

This module combines all Chat Mode sub-routers into a single router
with the /api/chat prefix.

Sub-modules:
- collections: Collection CRUD operations
- documents: Document upload/delete with async indexing
- progress: SSE progress tracking for document indexing
- messages: Chat messaging with SSE streaming responses
- sessions: Chat session management and history

Architecture:
- Each sub-module uses APIRouter() with NO prefix
- This __init__ aggregates them and applies the /api/chat prefix
- Import this router in main.py: from app.api.chat import router as chat_router
"""

from fastapi import APIRouter

# Import sub-routers
from app.api.chat.collections import router as collections_router
from app.api.chat.documents import router as documents_router
from app.api.chat.progress import router as progress_router
from app.api.chat.messages import router as messages_router
from app.api.chat.sessions import router as sessions_router

# Create main router with prefix and tags
router = APIRouter(prefix="/api/chat", tags=["Chat Mode"])

# Include all sub-routers (NO prefix needed - already on main router)
router.include_router(collections_router)
router.include_router(documents_router)
router.include_router(progress_router)
router.include_router(messages_router)
router.include_router(sessions_router)

__all__ = ["router"]
