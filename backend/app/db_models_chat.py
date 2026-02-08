# backend/app/db_models_chat.py
"""SQLAlchemy database models for Chat Mode (RAG)"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import TSVECTOR, JSONB
from pgvector.sqlalchemy import Vector  # pgvector extension for embeddings
from app.database import Base
import uuid
from typing import Optional, List, Dict, Any


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
    org_id = Column(String(64), nullable=False, index=True)  # Clerk org ID (tenant)
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
    file_path = Column(String(512), nullable=True)  # Original file path from upload
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

    Smart chunking metadata (chunk_metadata JSONB):
    - Chunk relationships (parent, siblings, linked chunks)
    - Section and sequence tracking
    - Rich context (heading hierarchy, table captions, etc.)
    """
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("idx_document_chunks_document_id", "document_id"),
        Index("idx_document_chunks_embedding", "embedding", postgresql_using="hnsw"),
        Index("idx_document_chunks_fts", "text_search_vector", postgresql_using="gin"),
        Index("idx_document_chunks_metadata_gin", "chunk_metadata", postgresql_using="gin"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    # Chunk content
    text = Column(Text, nullable=False)  # Unified searchable text (narrative OR table text)
    narrative_text = Column(Text, nullable=True)  # Narrative-only text (empty for table chunks)
    tables = Column(JSONB, nullable=True)  # Structured table metadata: [{"table_id": 0, "text": "...", "row_count": 2, "column_count": 3}]
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

    # Basic chunk metadata (backward compatible)
    page_number = Column(Integer, nullable=True)
    section_type = Column(String(50), nullable=True)  # "narrative", "table", etc.
    section_heading = Column(Text, nullable=True)
    is_tabular = Column(Boolean, default=False)

    # Token count (for cost estimation)
    token_count = Column(Integer, nullable=True)

    # Rich chunk metadata (JSONB) for smart chunking
    # Schema: {
    #   # Relationships
    #   "section_id": "sec_2",
    #   "parent_chunk_id": "chunk_123",
    #   "sibling_chunk_ids": ["chunk_123", "chunk_124"],
    #   "linked_narrative_id": "chunk_120",
    #   "linked_table_ids": ["chunk_125"],
    #
    #   # Sequence tracking
    #   "is_continuation": true,
    #   "chunk_sequence": 2,
    #   "total_chunks_in_section": 3,
    #
    #   # Context
    #   "heading_hierarchy": ["Main Report", "Section 2"],
    #   "paragraph_roles": ["sectionHeading", "content"],
    #   "page_range": [2, 3],
    #
    #   # Table-specific
    #   "table_caption": "Pro Forma Sources & Uses",
    #   "table_context": "Preceding paragraph...",
    #   "table_row_count": 15,
    #   "table_column_count": 4,
    #
    #   # Figure-specific
    #   "figure_id": "1.2",
    #   "figure_caption": "Corporate Structure",
    #
    #   # Content characteristics
    #   "has_figures": false,
    #   "content_type": "financial_table"
    # }
    chunk_metadata = Column(JSONB, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("Document", back_populates="chunks")

    # Helper methods for metadata access
    def get_section_id(self) -> Optional[str]:
        """Get section ID from metadata."""
        return self.chunk_metadata.get("section_id") if self.chunk_metadata else None

    def get_parent_chunk_id(self) -> Optional[str]:
        """Get parent chunk ID (for continuation chunks)."""
        return self.chunk_metadata.get("parent_chunk_id") if self.chunk_metadata else None

    def get_sibling_chunk_ids(self) -> List[str]:
        """Get sibling chunk IDs (chunks in same section)."""
        return self.chunk_metadata.get("sibling_chunk_ids", []) if self.chunk_metadata else []

    def get_linked_chunk_ids(self) -> List[str]:
        """Get all linked chunk IDs (narrative + tables)."""
        if not self.chunk_metadata:
            return []

        linked_ids = []
        if self.chunk_metadata.get("linked_narrative_id"):
            linked_ids.append(self.chunk_metadata["linked_narrative_id"])
        if self.chunk_metadata.get("linked_table_ids"):
            linked_ids.extend(self.chunk_metadata["linked_table_ids"])
        return linked_ids

    def is_continuation_chunk(self) -> bool:
        """Check if this is a continuation chunk."""
        return self.chunk_metadata.get("is_continuation", False) if self.chunk_metadata else False

    def get_heading_hierarchy(self) -> List[str]:
        """Get heading hierarchy breadcrumbs."""
        return self.chunk_metadata.get("heading_hierarchy", []) if self.chunk_metadata else []

    def get_table_context(self) -> Optional[str]:
        """Get table context (preceding narrative for table chunks)."""
        return self.chunk_metadata.get("table_context") if self.chunk_metadata else None

    def set_metadata(self, key: str, value: Any) -> None:
        """Set a metadata value (helper for building metadata)."""
        if self.chunk_metadata is None:
            self.chunk_metadata = {}
        self.chunk_metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get a metadata value with optional default."""
        if not self.chunk_metadata:
            return default
        return self.chunk_metadata.get(key, default)


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
        Index("idx_chat_sessions_org_id", "org_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    org_id = Column(String(64), nullable=False, index=True)  # Clerk org ID (tenant)
    user_id = Column(String(100), nullable=False, index=True)  # Clerk user ID

    # Session metadata
    title = Column(String(255), nullable=True)  # Auto-generated or user-provided
    description = Column(Text, nullable=True)

    # Stats
    message_count = Column(Integer, default=0)  # Cached count

    # Conversation summary persistence (progressive summarization)
    last_summary_text = Column(Text, nullable=True)  # Latest summary
    last_summary_key_facts = Column(JSONB, nullable=True, server_default='[]')  # Important preserved facts
    last_summarized_index = Column(Integer, nullable=True, server_default='0')  # Message index summarized up to
    last_summary_updated_at = Column(DateTime(timezone=True), nullable=True)  # When summary was last updated

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

    # Granular token tracking for observability
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    cache_read_tokens = Column(Integer, nullable=True)
    cache_write_tokens = Column(Integer, nullable=True)

    # Comparison metadata (for page refresh persistence)
    comparison_metadata = Column(Text, nullable=True)  # JSON serialized ComparisonContext

    # Citation metadata (for clickable citations in general chat)
    citation_metadata = Column(Text, nullable=True)  # JSON serialized citation context

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("ChatSession", back_populates="messages")
