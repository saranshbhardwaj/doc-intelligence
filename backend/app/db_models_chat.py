# backend/app/db_models_chat.py
"""SQLAlchemy database models for Chat Mode (RAG)"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector  # pgvector extension for embeddings
from app.database import Base
import uuid


class Collection(Base):
    """
    A collection of documents for multi-document chat/RAG.

    Users can:
    - Upload multiple PDFs to a collection
    - Chat across all documents in the collection
    - Add existing extractions to a collection
    """
    __tablename__ = "collections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(100), nullable=False, index=True)  # Clerk user ID

    name = Column(String(255), nullable=False)  # User-provided name
    description = Column(Text, nullable=True)  # Optional description

    # Metadata
    document_count = Column(Integer, default=0)  # Cached count (updated on document add/remove)
    total_chunks = Column(Integer, default=0)  # Total chunks across all documents
    embedding_model = Column(String(100), nullable=True)  # Which embedding model was used
    embedding_dimension = Column(Integer, nullable=True)  # Vector dimension (384, 768, 1536, etc.)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    documents = relationship("CollectionDocument", back_populates="collection", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="collection", cascade="all, delete-orphan")


class CollectionDocument(Base):
    """
    Link between Collection and uploaded documents.

    Each document belongs to one collection (for now - could be many-to-many later).
    Can optionally link to an existing Extraction (if user adds extraction to collection).
    """
    __tablename__ = "collection_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    collection_id = Column(String(36), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True)
    extraction_id = Column(String(36), ForeignKey("extractions.id", ondelete="SET NULL"), nullable=True, index=True)

    # Document metadata
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=True)  # Path to uploaded PDF file
    file_size_bytes = Column(Integer, nullable=False)
    page_count = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=True, index=True)  # SHA256 for deduplication

    # Processing status
    status = Column(String(20), default="processing")  # processing, completed, failed
    error_message = Column(Text, nullable=True)

    # Stats
    chunk_count = Column(Integer, default=0)
    processing_time_ms = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    collection = relationship("Collection", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    """
    Text chunks with embeddings for RAG retrieval.

    Each chunk is a segment of a document with:
    - Text content
    - Embedding vector (for semantic search)
    - Metadata (page number, section, etc.)
    """
    __tablename__ = "document_chunks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("collection_documents.id", ondelete="CASCADE"), nullable=False, index=True)

    # Chunk content
    text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)  # Order within document (0, 1, 2, ...)

    # Embedding vector (dimension depends on model: 384, 768, 1536, etc.)
    # Dimension is set from config.embedding_dimension at runtime
    # Default to 384 (all-MiniLM-L6-v2) - can be overridden by setting EMBEDDING_DIMENSION in .env
    embedding = Column(Vector(None), nullable=True)  # None = dimension set dynamically

    # Chunk metadata (structure-aware chunking)
    page_number = Column(Integer, nullable=True)  # Which page this chunk is from
    section_type = Column(String(50), nullable=True)  # "narrative", "table", "balance_sheet", etc.
    section_heading = Column(Text, nullable=True)  # Section title if available
    is_tabular = Column(Boolean, default=False)  # Is this chunk a table?

    # Token count (for cost estimation)
    token_count = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("CollectionDocument", back_populates="chunks")

    # Indexes for fast vector search
    __table_args__ = (
        Index("idx_document_chunks_embedding", "embedding", postgresql_using="hnsw"),  # HNSW index for vector similarity
        Index("idx_document_chunks_document_id", "document_id"),
    )


class ChatSession(Base):
    """
    A chat conversation session within a collection.

    Users can have multiple chat sessions for the same collection
    (e.g., different analysis angles, comparisons, etc.)
    """
    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    collection_id = Column(String(36), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)  # Clerk user ID

    # Session metadata
    title = Column(String(255), nullable=True)  # Auto-generated or user-provided title
    description = Column(Text, nullable=True)

    # Stats
    message_count = Column(Integer, default=0)  # Cached count

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    collection = relationship("Collection", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


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

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)

    # Message content
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    message_index = Column(Integer, nullable=False)  # Order within session (0, 1, 2, ...)

    # RAG metadata (for assistant messages)
    source_chunks = Column(Text, nullable=True)  # JSON array of chunk IDs used for this response
    retrieval_query = Column(Text, nullable=True)  # The query used for vector search (might differ from user message)
    num_chunks_retrieved = Column(Integer, nullable=True)  # How many chunks were retrieved

    # LLM metadata
    model_used = Column(String(100), nullable=True)  # Claude model used
    tokens_used = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("ChatSession", back_populates="messages")

    # Index for message ordering
    __table_args__ = (
        Index("idx_chat_messages_session_id_index", "session_id", "message_index"),
    )
