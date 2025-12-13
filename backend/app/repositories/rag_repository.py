"""Repository for RAG chunk retrieval operations.

Data Access Layer for DocumentChunk queries used in retrieval pipelines.

Pattern:
- Encapsulates all chunk-related database queries
- Used by HybridRetriever, WorkflowRetriever, and RAG services
- Provides clean interface for semantic and keyword search
- Makes testing easier with repository mocking
"""
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_, and_
from pgvector.sqlalchemy import Vector

from app.db_models_chat import DocumentChunk, CollectionDocument
from app.utils.logging import logger


class RAGRepository:
    """Repository for chunk retrieval database operations.

    Encapsulates all database access for chunk retrieval.
    Provides clean interface for semantic search, keyword search, and metadata queries.

    Usage:
        rag_repo = RAGRepository(db)
        results = rag_repo.semantic_search(embedding, document_ids, top_k=20)
        results = rag_repo.keyword_search(query, document_ids, top_k=20)
    """

    def __init__(self, db: Session):
        """Initialize repository with database session.

        Args:
            db: SQLAlchemy database session (injected by caller)
        """
        self.db = db

    # ============================================================================
    # SEMANTIC SEARCH (Vector Similarity)
    # ============================================================================

    def semantic_search(
        self,
        embedding: List[float],
        collection_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
        top_k: int = 20,
        distance_threshold: Optional[float] = None
    ) -> List[Dict]:
        """Semantic search using vector similarity.

        Args:
            embedding: Query embedding vector
            collection_id: Optional collection filter
            document_ids: Optional document IDs filter
            top_k: Number of results to return
            distance_threshold: Optional max distance threshold

        Returns:
            List of chunks with similarity scores, sorted by relevance
        """
        try:
            # Build query with pgvector cosine similarity
            if collection_id:
                # Filter by collection membership
                query = (
                    select(
                        DocumentChunk,
                        (1 - DocumentChunk.embedding.cosine_distance(embedding)).label("similarity")
                    )
                    .join(CollectionDocument, DocumentChunk.document_id == CollectionDocument.document_id)
                    .filter(CollectionDocument.collection_id == collection_id)
                )
            elif document_ids:
                # Filter by document IDs
                query = (
                    select(
                        DocumentChunk,
                        (1 - DocumentChunk.embedding.cosine_distance(embedding)).label("similarity")
                    )
                    .filter(DocumentChunk.document_id.in_(document_ids))
                )
            else:
                raise ValueError("Either collection_id or document_ids must be provided")

            # Apply distance threshold if specified
            if distance_threshold:
                query = query.filter(
                    DocumentChunk.embedding.cosine_distance(embedding) <= distance_threshold
                )

            # Order by similarity and limit
            query = query.order_by(func.desc("similarity")).limit(top_k)

            # Execute query
            results = self.db.execute(query).all()

            # Convert to dict format
            chunks = []
            for chunk, similarity in results:
                chunks.append({
                    "id": chunk.id,
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                    "narrative_text": chunk.narrative_text,
                    "tables": chunk.tables,
                    "chunk_index": chunk.chunk_index,
                    "page_number": chunk.page_number,
                    "section_type": chunk.section_type,
                    "section_heading": chunk.section_heading,
                    "is_tabular": chunk.is_tabular,
                    "token_count": chunk.token_count,
                    "chunk_metadata": chunk.chunk_metadata,
                    "similarity": float(similarity),
                    "semantic_rank": len(chunks) + 1  # 1-indexed rank
                })

            logger.debug(f"Semantic search returned {len(chunks)} chunks (top_k={top_k})")
            return chunks

        except Exception as e:
            logger.error(f"Semantic search failed: {e}", exc_info=True)
            return []

    # ============================================================================
    # KEYWORD SEARCH (Full-Text Search)
    # ============================================================================

    def keyword_search(
        self,
        query: str,
        collection_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
        top_k: int = 20,
        prefer_tables: bool = False
    ) -> List[Dict]:
        """Keyword search using PostgreSQL Full-Text Search.

        Args:
            query: Search query string
            collection_id: Optional collection filter
            document_ids: Optional document IDs filter
            top_k: Number of results to return
            prefer_tables: Boost table chunks in ranking

        Returns:
            List of chunks with BM25-like scores, sorted by relevance
        """
        try:
            # Convert query to tsquery (simple websearch syntax)
            ts_query = func.websearch_to_tsquery('english', query)

            # Build query with ts_rank_cd for BM25-like scoring
            if collection_id:
                # Filter by collection membership
                base_query = (
                    select(DocumentChunk)
                    .join(CollectionDocument, DocumentChunk.document_id == CollectionDocument.document_id)
                    .filter(
                        and_(
                            CollectionDocument.collection_id == collection_id,
                            DocumentChunk.text_search_vector.op('@@')(ts_query)
                        )
                    )
                )
            elif document_ids:
                # Filter by document IDs
                base_query = (
                    select(DocumentChunk)
                    .filter(
                        and_(
                            DocumentChunk.document_id.in_(document_ids),
                            DocumentChunk.text_search_vector.op('@@')(ts_query)
                        )
                    )
                )
            else:
                raise ValueError("Either collection_id or document_ids must be provided")

            # Add ranking with optional table boosting
            if prefer_tables:
                # Boost table chunks
                rank_expr = func.ts_rank_cd(
                    DocumentChunk.text_search_vector,
                    ts_query,
                    32  # normalization flag: divide by length
                ) * func.case(
                    (DocumentChunk.is_tabular == True, 1.5),  # noqa: E712
                    else_=1.0
                )
            else:
                # Standard ranking
                rank_expr = func.ts_rank_cd(
                    DocumentChunk.text_search_vector,
                    ts_query,
                    32  # normalization flag: divide by length
                )

            # Add rank and order by it
            query_with_rank = base_query.add_columns(rank_expr.label("rank"))
            query_with_rank = query_with_rank.order_by(func.desc("rank")).limit(top_k)

            # Execute query
            results = self.db.execute(query_with_rank).all()

            # Convert to dict format
            chunks = []
            for chunk, rank in results:
                chunks.append({
                    "id": chunk.id,
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                    "narrative_text": chunk.narrative_text,
                    "tables": chunk.tables,
                    "chunk_index": chunk.chunk_index,
                    "page_number": chunk.page_number,
                    "section_type": chunk.section_type,
                    "section_heading": chunk.section_heading,
                    "is_tabular": chunk.is_tabular,
                    "token_count": chunk.token_count,
                    "chunk_metadata": chunk.chunk_metadata,
                    "bm25_score": float(rank),
                    "keyword_rank": len(chunks) + 1  # 1-indexed rank
                })

            logger.debug(f"Keyword search returned {len(chunks)} chunks (top_k={top_k})")
            return chunks

        except Exception as e:
            logger.error(f"Keyword search failed: {e}", exc_info=True)
            return []

    # ============================================================================
    # UTILITY QUERIES
    # ============================================================================

    def count_chunks_for_documents(self, document_ids: List[str]) -> int:
        """Count total chunks for given documents.

        Uses actual chunk count from database (not cached metadata) to ensure accuracy.
        Used to validate documents are indexed before starting chat.

        Args:
            document_ids: List of document IDs to check

        Returns:
            Total number of chunks across all documents (0 if none found)
        """
        try:
            if not document_ids:
                return 0

            count = self.db.execute(
                select(func.count(DocumentChunk.id))
                .where(DocumentChunk.document_id.in_(document_ids))
            ).scalar()

            logger.debug(
                f"Counted {count} chunks for {len(document_ids)} documents",
                extra={"document_count": len(document_ids), "chunk_count": count}
            )

            return count or 0

        except Exception as e:
            logger.error(
                f"Failed to count chunks for documents: {e}",
                extra={"document_ids": document_ids[:5]},  # Log first 5 for debugging
                exc_info=True
            )
            return 0

    def get_chunk_by_id(self, chunk_id: str) -> Optional[Dict]:
        """Get a single chunk by ID.

        Args:
            chunk_id: Chunk ID

        Returns:
            Chunk dict or None if not found
        """
        try:
            chunk = self.db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
            if not chunk:
                return None

            return {
                "id": chunk.id,
                "document_id": chunk.document_id,
                "text": chunk.text,
                "narrative_text": chunk.narrative_text,
                "tables": chunk.tables,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "section_type": chunk.section_type,
                "section_heading": chunk.section_heading,
                "is_tabular": chunk.is_tabular,
                "token_count": chunk.token_count,
                "chunk_metadata": chunk.chunk_metadata
            }
        except Exception as e:
            logger.error(f"Failed to get chunk {chunk_id}: {e}", exc_info=True)
            return None

    def get_chunks_by_page(
        self,
        document_id: str,
        page_number: int,
        prefer_narrative: bool = True
    ) -> List[Dict]:
        """Get chunks for a specific page.

        Args:
            document_id: Document ID
            page_number: Page number
            prefer_narrative: Prefer narrative chunks over tables

        Returns:
            List of chunks for the page
        """
        try:
            query = self.db.query(DocumentChunk).filter(
                and_(
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.page_number == page_number
                )
            )

            if prefer_narrative:
                # Order narrative chunks first
                query = query.order_by(DocumentChunk.is_tabular.asc(), DocumentChunk.chunk_index.asc())
            else:
                query = query.order_by(DocumentChunk.chunk_index.asc())

            chunks = query.all()

            return [{
                "id": chunk.id,
                "document_id": chunk.document_id,
                "text": chunk.text,
                "narrative_text": chunk.narrative_text,
                "tables": chunk.tables,
                "chunk_index": chunk.chunk_index,
                "page_number": chunk.page_number,
                "section_type": chunk.section_type,
                "section_heading": chunk.section_heading,
                "is_tabular": chunk.is_tabular,
                "token_count": chunk.token_count,
                "chunk_metadata": chunk.chunk_metadata
            } for chunk in chunks]

        except Exception as e:
            logger.error(
                f"Failed to get chunks for page {page_number} in document {document_id}: {e}",
                exc_info=True
            )
            return []


__all__ = ['RAGRepository']
