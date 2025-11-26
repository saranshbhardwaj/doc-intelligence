# backend/app/db_models_chat.py
"""SQLAlchemy database models for Chat Mode (RAG)"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import TSVECTOR
from pgvector.sqlalchemy import Vector  # pgvector extension for embeddings
from app.database import Base
import uuid


class Collection(Base):
    """
    A collection of documents for multi-document chat/RAG.

    Users can:
    - Upload multiple PDFs to a collection
    - Chat across all documents in the collection
    - Share documents across collections (future)
    """
    __tablename__ = "collections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(100), nullable=False, index=True)  # Clerk user ID

    name = Column(String(255), nullable=False)  # User-provided name
    description = Column(Text, nullable=True)  # Optional description

    # Cached stats (updated when documents added/removed)
    document_count = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)

    # Embedding configuration
    embedding_model = Column(String(100), nullable=True)  # all-MiniLM-L6-v2, etc.
    embedding_dimension = Column(Integer, nullable=True)  # 384, 768, 1536, etc.

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    document_links = relationship("CollectionDocument", back_populates="collection", cascade="all, delete-orphan")


class CollectionDocument(Base):
    """
    Link table between Collections and Documents.

    Pure join table - all metadata lives in canonical documents table.
    Multiple collections can reference the same document.
    """
    __tablename__ = "collection_documents"
    __table_args__ = (
        Index("idx_collection_documents_collection_id", "collection_id"),
        Index("idx_collection_documents_document_id", "document_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    collection_id = Column(String(36), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    # Link metadata
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    collection = relationship("Collection", back_populates="document_links")
    document = relationship("Document", back_populates="collection_links")


class DocumentChunk(Base):
    """
    Text chunks with embeddings for RAG retrieval.

    Each chunk belongs to a canonical document (not collection_document).
    Chunks can be queried across collections by joining through collection_documents.

    Supports hybrid search:
    - Semantic search via pgvector HNSW index on embeddings
    - Keyword search via PostgreSQL GIN index on text_search_vector
    """
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("idx_document_chunks_document_id", "document_id"),
        Index("idx_document_chunks_embedding", "embedding", postgresql_using="hnsw"),
        Index("idx_document_chunks_fts", "text_search_vector", postgresql_using="gin"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    # Chunk content
    text = Column(Text, nullable=False)
    narrative_text = Column(Text, nullable=True)
    tables = Column(Text, nullable=True)
    chunk_index = Column(Integer, nullable=False)  # Order within document (0, 1, 2, ...)

    # Full-text search vector (auto-generated from text column)
    # PostgreSQL tsvector for keyword/lexical search (BM25-like ranking)
    # Automatically maintained by PostgreSQL trigger (see migration)
    text_search_vector = Column(TSVECTOR, nullable=True)

    # Embedding vector (384 dimensions for all-MiniLM-L6-v2)
    # NOTE: If you change embedding models, you'll need a new migration
    embedding = Column(Vector(384), nullable=True)
    embedding_model = Column(String(100), nullable=True)  # Track which model created this embedding
    embedding_version = Column(String(20), nullable=True)  # Model version for gradual migration

    # Chunk metadata
    page_number = Column(Integer, nullable=True)
    section_type = Column(String(50), nullable=True)  # "narrative", "table", etc.
    section_heading = Column(Text, nullable=True)
    is_tabular = Column(Boolean, default=False)

    # Token count (for cost estimation)
    token_count = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("Document", back_populates="chunks")


class SessionDocument(Base):
    """
    Junction table linking chat sessions to documents.

    Allows sessions to have documents from any collection.
    Each session maintains its own document selection.
    """
    __tablename__ = "session_documents"
    __table_args__ = (
        Index("idx_session_documents_session_id", "session_id"),
        Index("idx_session_documents_document_id", "document_id"),
        # Unique constraint: same document can't be added twice to a session
        {'sqlite_autoincrement': True}
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("ChatSession", back_populates="document_links")
    document = relationship("Document")


class ChatSession(Base):
    """
    A chat conversation session.

    Sessions are independent and can contain documents from any collection.
    Each session maintains its own document selection.
    """
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("idx_chat_sessions_user_id", "user_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(100), nullable=False, index=True)  # Clerk user ID

    # Session metadata
    title = Column(String(255), nullable=True)  # Auto-generated or user-provided
    description = Column(Text, nullable=True)

    # Stats
    message_count = Column(Integer, default=0)  # Cached count

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    document_links = relationship("SessionDocument", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    """
    Individual messages in a chat session (user questions + AI responses).

    For each user question:
    1. Embed the question
    2. Vector search to find relevant chunks
    3. Send chunks + question to Claude
    4. Store both user question and AI response
    """
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("idx_chat_messages_session_id_index", "session_id", "message_index"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)

    # Message content
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    message_index = Column(Integer, nullable=False)  # Order within session

    # RAG metadata (for assistant messages)
    source_chunks = Column(Text, nullable=True)  # JSON array of chunk IDs
    retrieval_query = Column(Text, nullable=True)
    num_chunks_retrieved = Column(Integer, nullable=True)

    # LLM metadata
    model_used = Column(String(100), nullable=True)
    tokens_used = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("ChatSession", back_populates="messages")
