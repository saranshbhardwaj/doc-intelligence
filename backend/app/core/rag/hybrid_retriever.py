"""
Hybrid Retriever for RAG

Combines semantic (vector) search with keyword (BM25/FTS) search
for improved retrieval quality.
"""

from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.db_models_chat import DocumentChunk, CollectionDocument
from app.core.embeddings import get_embedding_provider
from app.core.rag.query_analyzer import QueryAnalyzer
from app.core.rag.metadata_booster import MetadataBooster
from app.config import settings
from app.utils.logging import logger


class HybridRetriever:
    """
    Combines semantic (vector) + keyword (BM25) search using RRF

    Pipeline:
    1. Analyze query for content preferences
    2. Semantic search via pgvector (cosine similarity)
    3. Keyword search via PostgreSQL FTS (ts_rank_cd)
    4. Merge results using Reciprocal Rank Fusion (RRF)
    5. Apply metadata-based boosting
    6. Return top-k ranked chunks
    """

    def __init__(
        self,
        db: Session,
        rrf_k: int = None
    ):
        """
        Initialize hybrid retriever

        Args:
            db: SQLAlchemy database session
            rrf_k: RRF constant parameter (default from settings)
        """
        self.db = db
        self.embedder = get_embedding_provider()
        self.query_analyzer = QueryAnalyzer()
        self.metadata_booster = MetadataBooster.for_hybrid_retriever()

        # RRF configuration
        self.rrf_k = rrf_k or settings.rag_hybrid_rrf_k

        logger.info(
            f"HybridRetriever initialized: RRF merging with k={self.rrf_k}"
        )

    def retrieve(
        self,
        query: str,
        collection_id: Optional[str] = None,
        top_k: int = 20,
        document_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Hybrid retrieval combining vector + keyword search

        Args:
            query: User's search query
            collection_id: Optional collection to search within (if None, uses document_ids filter)
            top_k: Number of chunks to retrieve (for re-ranking)
            document_ids: Optional filter by specific documents (required if collection_id is None)

        Returns:
            List of chunks with hybrid scores, sorted by relevance
        """
        # 1. Analyze query for content preferences
        query_analysis = self.query_analyzer.analyze(query)

        logger.debug(
            f"Hybrid retrieval: query_type={query_analysis['query_type']}, top_k={top_k}",
            extra={"query": query[:50], "collection_id": collection_id}
        )

        # 2. Semantic search (vector similarity)
        semantic_results = self._semantic_search(
            query, collection_id, top_k=top_k, document_ids=document_ids
        )

        # 3. Keyword search (BM25/FTS)
        keyword_results = self._keyword_search(
            query, collection_id, top_k=top_k, document_ids=document_ids
        )

        # 4. Merge and normalize scores
        merged = self._merge_results(semantic_results, keyword_results)

        # 5. Apply metadata boosting
        boosted = self._apply_metadata_boost(merged, query_analysis)

        # 6. Sort by hybrid score and return top-k
        ranked = sorted(boosted, key=lambda x: x["hybrid_score"], reverse=True)[:top_k]

        logger.info(
            f"Hybrid retrieval complete: {len(ranked)} chunks, "
            f"semantic_candidates={len(semantic_results)}, "
            f"keyword_candidates={len(keyword_results)}",
            extra={
                "top_score": ranked[0]["hybrid_score"] if ranked else 0,
                "query_type": query_analysis["query_type"]
            }
        )

        return ranked

    def _semantic_search(
        self,
        query: str,
        collection_id: Optional[str],
        top_k: int,
        document_ids: Optional[List[str]]
    ) -> List[Dict]:
        """
        Semantic search using pgvector cosine similarity

        Returns:
            List of chunks with semantic_score (0-1, normalized)
        """
        # Embed query
        query_embedding = self.embedder.embed_text(query)

        # Build query with cosine distance
        distance_expr = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")

        stmt = select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.text,
            DocumentChunk.page_number,
            DocumentChunk.chunk_index,
            DocumentChunk.is_tabular,
            DocumentChunk.section_heading,
            DocumentChunk.section_type,
            DocumentChunk.chunk_metadata,
            distance_expr
        )

        # Filter by collection OR documents
        if collection_id:
            # Collection-based search (legacy)
            stmt = stmt.join(CollectionDocument, DocumentChunk.document_id == CollectionDocument.document_id)
            stmt = stmt.where(CollectionDocument.collection_id == collection_id)
            # Optional additional document filter
            if document_ids:
                stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
        elif document_ids:
            # Session-based search (direct document filter)
            stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
        else:
            raise ValueError("Either collection_id or document_ids must be provided")

        # Order by distance (ascending = most similar first)
        stmt = stmt.order_by(distance_expr).limit(top_k)

        # Execute query
        results = self.db.execute(stmt).all()

        if not results:
            logger.warning(f"No semantic results found for query: {query[:50]}")
            return []

        # Convert distance to similarity and normalize
        # Cosine distance: 0=identical, 1=orthogonal, 2=opposite
        # Similarity: 1 - distance (higher is better)
        max_sim = max([1.0 - r.distance for r in results])
        min_sim = min([1.0 - r.distance for r in results])
        sim_range = max_sim - min_sim if max_sim > min_sim else 1.0

        chunks = []
        for r in results:
            similarity = 1.0 - r.distance
            # Normalize to 0-1 range within this result set
            normalized_score = (similarity - min_sim) / sim_range if sim_range > 0 else 1.0

            chunks.append({
                "id": r.id,
                "document_id": r.document_id,
                "text": r.text,
                "page_number": r.page_number,
                "chunk_index": r.chunk_index,
                "is_tabular": r.is_tabular,
                "section_heading": r.section_heading,
                "section_type": r.section_type,
                "chunk_metadata": r.chunk_metadata,  # Include metadata with document_filename
                "semantic_score": normalized_score,
                "raw_similarity": similarity,
                "distance": r.distance
            })

        return chunks

    def _keyword_search(
        self,
        query: str,
        collection_id: Optional[str],
        top_k: int,
        document_ids: Optional[List[str]]
    ) -> List[Dict]:
        """
        Keyword search using PostgreSQL Full-Text Search (ts_rank_cd)

        Uses BM25-like ranking with document length normalization

        Returns:
            List of chunks with keyword_score (0-1, normalized)
        """
        # Convert query to tsquery
        tsquery = func.plainto_tsquery('english', query)

        # Use ts_rank_cd for ranking with document length normalization
        # Normalization flag 2: divide by document length (BM25-like behavior)
        rank_expr = func.ts_rank_cd(
            DocumentChunk.text_search_vector,
            tsquery,
            2  # Normalization: divide by document length (prevents length bias)
        ).label("rank")

        stmt = select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.text,
            DocumentChunk.page_number,
            DocumentChunk.chunk_index,
            DocumentChunk.is_tabular,
            DocumentChunk.section_heading,
            DocumentChunk.section_type,
            DocumentChunk.chunk_metadata,
            rank_expr
        )

        # Filter by collection OR documents
        if collection_id:
            # Collection-based search (legacy)
            stmt = stmt.join(CollectionDocument, DocumentChunk.document_id == CollectionDocument.document_id)
            stmt = stmt.where(CollectionDocument.collection_id == collection_id)
            # Optional additional document filter
            if document_ids:
                stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
        elif document_ids:
            # Session-based search (direct document filter)
            stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
        else:
            raise ValueError("Either collection_id or document_ids must be provided")

        # Match filter (full-text search)
        stmt = stmt.where(DocumentChunk.text_search_vector.op('@@')(tsquery))

        # Order by rank (descending = highest rank first)
        stmt = stmt.order_by(rank_expr.desc()).limit(top_k)

        # Execute query
        results = self.db.execute(stmt).all()

        if not results:
            logger.debug(f"No keyword matches found for query: {query[:50]}")
            return []

        # Normalize keyword scores to 0-1 range
        max_rank = max([r.rank for r in results])
        min_rank = min([r.rank for r in results])
        rank_range = max_rank - min_rank if max_rank > min_rank else 1.0

        chunks = []
        for r in results:
            # Normalize to 0-1 range
            normalized_score = (r.rank - min_rank) / rank_range if rank_range > 0 else 1.0

            chunks.append({
                "id": r.id,
                "document_id": r.document_id,
                "text": r.text,
                "page_number": r.page_number,
                "chunk_index": r.chunk_index,
                "is_tabular": r.is_tabular,
                "section_heading": r.section_heading,
                "section_type": r.section_type,
                "chunk_metadata": r.chunk_metadata,  # Include metadata with document_filename
                "keyword_score": normalized_score,
                "raw_rank": r.rank
            })

        return chunks

    def _merge_results(
        self,
        semantic_results: List[Dict],
        keyword_results: List[Dict]
    ) -> List[Dict]:
        """
        Merge semantic + keyword results using Reciprocal Rank Fusion (RRF).

        RRF Formula: RRF_score = Σ(1 / (k + rank))
        where k is a constant (default 60) and rank is 1-indexed position.

        Advantages:
        - Rank-based: More robust to score distribution differences
        - No normalization needed: Avoids min-max issues
        - Well-studied: Used by Elasticsearch, Vespa, etc.
        - Position-focused: Emphasizes top results naturally

        Returns:
            List of unique chunks with hybrid_score (RRF score)
        """
        # Build rank lookups (1-indexed positions)
        semantic_ranks = {r["id"]: idx + 1 for idx, r in enumerate(semantic_results)}
        keyword_ranks = {r["id"]: idx + 1 for idx, r in enumerate(keyword_results)}

        # Get all unique chunk IDs
        all_chunk_ids = set(semantic_ranks.keys()) | set(keyword_ranks.keys())

        # Build merged result dict
        merged_dict = {}

        for chunk_id in all_chunk_ids:
            # Find original chunk data (prefer semantic for metadata completeness)
            chunk_data = None
            for r in semantic_results:
                if r["id"] == chunk_id:
                    chunk_data = r.copy()
                    break

            if not chunk_data:
                for r in keyword_results:
                    if r["id"] == chunk_id:
                        chunk_data = r.copy()
                        break

            if not chunk_data:
                logger.warning(f"Chunk {chunk_id} not found in either result set (should not happen)")
                continue

            # Calculate RRF score
            rrf_score = 0.0

            # Add semantic contribution
            if chunk_id in semantic_ranks:
                rrf_score += 1.0 / (self.rrf_k + semantic_ranks[chunk_id])

            # Add keyword contribution
            if chunk_id in keyword_ranks:
                rrf_score += 1.0 / (self.rrf_k + keyword_ranks[chunk_id])

            # Store RRF score and rank metadata
            chunk_data["hybrid_score"] = rrf_score
            chunk_data["semantic_rank"] = semantic_ranks.get(chunk_id)
            chunk_data["keyword_rank"] = keyword_ranks.get(chunk_id)

            # Preserve normalized scores if available (for analysis/debugging)
            if "semantic_score" not in chunk_data:
                chunk_data["semantic_score"] = 0.0
            if "keyword_score" not in chunk_data:
                chunk_data["keyword_score"] = 0.0

            merged_dict[chunk_id] = chunk_data

        logger.debug(
            f"RRF merge: {len(semantic_results)} semantic + {len(keyword_results)} keyword "
            f"→ {len(merged_dict)} unique chunks (k={self.rrf_k})"
        )

        return list(merged_dict.values())

    def _apply_metadata_boost(
        self,
        results: List[Dict],
        query_analysis: Dict
    ) -> List[Dict]:
        """
        Apply intelligent metadata-based boosting using shared MetadataBooster.

        Args:
            results: Merged results with hybrid scores
            query_analysis: Query analysis results from QueryAnalyzer

        Returns:
            Results with boosted hybrid scores
        """
        return self.metadata_booster.apply_boost(
            results,
            query_analysis,
            score_field="hybrid_score"
        )
