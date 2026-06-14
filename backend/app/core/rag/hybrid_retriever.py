"""
Hybrid Retriever for RAG

Combines semantic (vector) search with keyword (BM25/FTS) search
for improved retrieval quality.
"""

from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import case, select, func
import re
from app.db_models_chat import DocumentChunk, CollectionDocument
from app.core.embeddings import get_embedding_provider
from app.core.rag.query_analyzer import QueryAnalyzer
from app.core.rag.query_understanding import is_narrow_explicit_fact_lookup
from app.core.rag.metadata_booster import MetadataBooster
from app.core.rag.retrieval_query import RetrievalQuery
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
        rq: RetrievalQuery,
        collection_id: Optional[str] = None,
        top_k: int = 20,
        document_ids: Optional[List[str]] = None,
        query_understanding=None,  # QueryUnderstanding object (optional, for HyDE + metadata boost)
        min_semantic_similarity: Optional[float] = None,
        section_types: Optional[List[str]] = None,  # e.g. ["narrative"], ["table", "key_value_pairs"]
        use_semantic: bool = True,
        use_keyword: bool = True,
        apply_metadata_boost: bool = True,
    ) -> List[Dict]:
        """
        Hybrid retrieval combining vector + keyword search.

        Args:
            rq: Structured retrieval query with semantic text and lexical constraints.
            collection_id: Optional collection to search within (if None, uses document_ids filter).
            top_k: Number of chunks to retrieve (for re-ranking).
            document_ids: Optional filter by specific documents (required if collection_id is None).
            query_understanding: Optional QueryUnderstanding for HyDE and metadata boosting.

        Returns:
            List of chunks with hybrid scores, sorted by relevance.
        """
        if not use_semantic and not use_keyword:
            raise ValueError("At least one retrieval leg must be enabled")

        # 1. Analyze query for content preferences
        query_analysis = self.query_analyzer.analyze(rq.semantic_text)

        logger.debug(
            f"Hybrid retrieval: query_type={query_analysis['query_type']}, top_k={top_k}",
            extra={"query": rq.semantic_text[:50], "collection_id": collection_id}
        )

        # 2. Semantic search (vector similarity, with optional HyDE enhancement)
        semantic_results = (
            self._semantic_search(
                rq,
                collection_id,
                top_k=top_k,
                document_ids=document_ids,
                query_understanding=query_understanding,
                min_semantic_similarity=min_semantic_similarity,
                section_types=section_types,
            )
            if use_semantic
            else []
        )

        # 3. Keyword search (BM25/FTS) — uses structured lexical constraints from rq
        keyword_results = (
            self._keyword_search(
                rq, collection_id, top_k=top_k, document_ids=document_ids,
                section_types=section_types,
            )
            if use_keyword
            else []
        )

        # 4. Merge and normalize scores
        merged = self._merge_results(semantic_results, keyword_results)

        # 5. Apply metadata boosting
        # Use QueryUnderstanding if available for LLM-determined boost values, otherwise use QueryAnalyzer result
        if apply_metadata_boost:
            boost_input = query_understanding if query_understanding else query_analysis
            boosted = self._apply_metadata_boost(merged, boost_input)
        else:
            boosted = merged

        # 6. Sort by hybrid score and return top-k
        ranked = sorted(boosted, key=lambda x: x["hybrid_score"], reverse=True)[:top_k]

        # Log chunk type distribution for observability
        type_counts = {"table": 0, "key_value": 0, "narrative": 0, "unknown": 0}
        for chunk in ranked:
            chunk_type = chunk.get("section_type")
            if not chunk_type:
                metadata = chunk.get("chunk_metadata") or {}
                if isinstance(metadata, dict):
                    chunk_type = metadata.get("chunk_type")

            if chunk_type in {"table", "table_block"} or chunk.get("is_tabular"):
                type_counts["table"] += 1
            elif chunk_type in ("key_value_pairs", "key_value"):
                type_counts["key_value"] += 1
            elif chunk_type in {"narrative", "narrative_block"}:
                type_counts["narrative"] += 1
            else:
                type_counts["unknown"] += 1

        logger.info(
            f"Hybrid retrieval complete: {len(ranked)} chunks, "
            f"semantic_candidates={len(semantic_results)}, "
            f"keyword_candidates={len(keyword_results)}",
            extra={
                "top_score": ranked[0]["hybrid_score"] if ranked else 0,
                "query_type": query_analysis["query_type"],
                "chunk_type_counts": type_counts,
                "lexical_required": rq.lexical_required,
                "lexical_optional_count": len(rq.lexical_optional),
                "use_semantic": use_semantic,
                "use_keyword": use_keyword,
                "apply_metadata_boost": apply_metadata_boost,
            }
        )

        return ranked

    def _semantic_search(
        self,
        rq: RetrievalQuery,
        collection_id: Optional[str],
        top_k: int,
        document_ids: Optional[List[str]],
        query_understanding=None,
        min_semantic_similarity: Optional[float] = None,
        section_types: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Semantic search using pgvector cosine similarity.

        With optional HyDE (Hypothetical Document Embeddings) enhancement.

        Returns:
            List of chunks with semantic_score (0-1, normalized).
        """
        query = rq.semantic_text

        # Generate query embedding, optionally enhanced with HyDE
        use_hyde = (
            query_understanding
            and query_understanding.hypothetical_response
            and not is_narrow_explicit_fact_lookup(query_understanding)
        )

        if use_hyde:
            # HyDE: Average query embedding with hypothetical response embedding
            query_emb = self.embedder.embed_text(query)
            hyde_emb = self.embedder.embed_text(query_understanding.hypothetical_response)

            # Weighted average (query 40%, HyDE 60%)
            query_embedding = [
                0.4 * q + 0.6 * h
                for q, h in zip(query_emb, hyde_emb)
            ]

            logger.debug(
                "Using HyDE-enhanced embedding for semantic search",
                extra={"query": query[:50]}
            )
        else:
            if (
                query_understanding
                and query_understanding.hypothetical_response
                and is_narrow_explicit_fact_lookup(query_understanding)
            ):
                logger.info(
                    "HyDE disabled for narrow explicit fact lookup",
                    extra={"query": query[:50]}
                )
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
            DocumentChunk.tables,
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

        # Optional section_type filter (e.g. prefer narrative or table chunks)
        if section_types:
            stmt = stmt.where(DocumentChunk.section_type.in_(section_types))

        # Order by distance (ascending = most similar first)
        stmt = stmt.order_by(distance_expr).limit(top_k)

        # Execute query
        results = self.db.execute(stmt).all()

        if not results:
            logger.warning(f"No semantic results found for query: {query[:50]}")
            return []

        # Apply semantic similarity floor (raw cosine similarity)
        if min_semantic_similarity and min_semantic_similarity > 0:
            total_before = len(results)
            filtered_results = [r for r in results if (1.0 - r.distance) >= min_semantic_similarity]
            total_after = len(filtered_results)
            top_raw = max([1.0 - r.distance for r in results]) if results else 0.0
            logger.info(
                "Applied semantic similarity floor",
                extra={
                    "query": query[:50],
                    "floor": min_semantic_similarity,
                    "before": total_before,
                    "after": total_after,
                    "top_raw_similarity": top_raw
                }
            )
            if filtered_results:
                results = filtered_results
            else:
                logger.info(
                    "Semantic floor removed all results; falling back to top-k unfiltered",
                    extra={
                        "query": query[:50],
                        "floor": min_semantic_similarity,
                        "before": total_before
                    }
                )

        if not results:
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

            # Extract bbox from chunk_metadata for PDF highlighting
            metadata = r.chunk_metadata or {}
            if isinstance(metadata, str):
                import json
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = {}

            chunks.append({
                "id": r.id,
                "document_id": r.document_id,
                "text": r.text,
                "page_number": r.page_number,
                "chunk_index": r.chunk_index,
                "is_tabular": r.is_tabular,
                "section_heading": r.section_heading,
                "section_type": r.section_type,
                "chunk_metadata": metadata,
                "tables": r.tables,
                # Extract bbox at top level for easy access
                "bbox": metadata.get("bbox"),
                "page_range": metadata.get("page_range"),
                "semantic_score": normalized_score,
                "raw_similarity": similarity,
                "distance": r.distance
            })

        return chunks

    def _build_tsqueries(self, rq: RetrievalQuery) -> Tuple:
        """
        Build (filter_tsquery, rank_tsquery) from a RetrievalQuery.

        filter_tsquery:
            Each required phrase is passed to phraseto_tsquery (ensures words appear
            adjacent in the correct order), then all phrases are AND'd together.
            This becomes the WHERE @@ predicate — only chunks matching ALL required
            phrases pass. None when lexical_required is empty (broad queries).

        rank_tsquery:
            Required phrases OR'd with optional terms (via plainto_tsquery).
            Used exclusively for ts_rank_cd scoring, never for filtering.
            Falls back to plainto_tsquery(semantic_text) when both lists are empty.
        """
        filter_q = None
        if rq.lexical_required:
            parts = [func.phraseto_tsquery("english", p) for p in rq.lexical_required]
            filter_q = parts[0]
            for p in parts[1:]:
                filter_q = filter_q.op("&&")(p)

        rank_parts = []
        for p in rq.lexical_required:
            rank_parts.append(func.phraseto_tsquery("english", p))
        for p in rq.lexical_optional:
            rank_parts.append(func.plainto_tsquery("english", p))

        if rank_parts:
            rank_q = rank_parts[0]
            for p in rank_parts[1:]:
                rank_q = rank_q.op("||")(p)
        else:
            rank_q = func.plainto_tsquery("english", rq.semantic_text)

        return filter_q, rank_q

    def _keyword_search(
        self,
        rq: RetrievalQuery,
        collection_id: Optional[str],
        top_k: int,
        document_ids: Optional[List[str]],
        section_types: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Keyword search using PostgreSQL Full-Text Search (ts_rank_cd).

        Uses a two-tsquery design:
          - filter_tsquery: strict phrase-AND filter for the WHERE clause.
            For narrow fact lookups this means only chunks containing the exact
            required phrases (e.g. "loan amount" adjacent) pass — preventing
            high-frequency doc-name tokens from flooding the result set.
          - rank_tsquery: lenient OR query for ts_rank_cd scoring, including
            synonyms and optional terms for recall boosting.

        Returns:
            List of chunks with keyword_score (0-1, normalized).
        """
        filter_q, rank_q = self._build_tsqueries(rq)

        # WHERE uses the strict filter when required phrases exist; otherwise the
        # rank query (broad OR) — same recall as before for non-narrow queries.
        match_q = filter_q if filter_q is not None else rank_q

        # Chunks returned under a filter_q matched ALL required phrases as adjacent
        # tokens. Flag them so callers can guarantee their inclusion past the reranker,
        # which under-scores structured table text (MS MARCO training distribution).
        is_phrase_match = filter_q is not None

        # ts_rank_cd with document length normalization (BM25-like behavior)
        rank_expr = func.ts_rank_cd(
            DocumentChunk.text_search_vector,
            rank_q,  # Always score with the lenient rank query
            2
        )

        identifier_boost = _build_identifier_match_boost(rq)
        if identifier_boost is not None:
            rank_expr = (rank_expr + identifier_boost)

        rank_expr = rank_expr.label("rank")

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
            DocumentChunk.tables,
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

        # Match filter: strict phrase filter for narrow queries, broad OR for general ones
        stmt = stmt.where(DocumentChunk.text_search_vector.op("@@")(match_q))

        # Optional section_type filter
        if section_types:
            stmt = stmt.where(DocumentChunk.section_type.in_(section_types))

        # Order by rank (descending = highest rank first)
        stmt = stmt.order_by(rank_expr.desc()).limit(top_k)

        # Execute query
        results = self.db.execute(stmt).all()

        if not results:
            logger.debug(f"No keyword matches found for query: {rq.semantic_text[:50]}")
            return []

        # Normalize keyword scores to 0-1 range
        max_rank = max([r.rank for r in results])
        min_rank = min([r.rank for r in results])
        rank_range = max_rank - min_rank if max_rank > min_rank else 1.0

        chunks = []
        for r in results:
            # Normalize to 0-1 range
            normalized_score = (r.rank - min_rank) / rank_range if rank_range > 0 else 1.0

            # Extract bbox from chunk_metadata for PDF highlighting
            metadata = r.chunk_metadata or {}
            if isinstance(metadata, str):
                import json
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = {}

            chunks.append({
                "id": r.id,
                "document_id": r.document_id,
                "text": r.text,
                "page_number": r.page_number,
                "chunk_index": r.chunk_index,
                "is_tabular": r.is_tabular,
                "section_heading": r.section_heading,
                "section_type": r.section_type,
                "chunk_metadata": metadata,
                "tables": r.tables,
                "bbox": metadata.get("bbox"),
                "page_range": metadata.get("page_range"),
                "keyword_score": normalized_score,
                "raw_rank": r.rank,
                "is_keyword_match": True,
                "is_phrase_match": is_phrase_match,
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

        # Build chunk data lookups for O(1) access (avoid O(N²) nested loops)
        semantic_dict = {r["id"]: r for r in semantic_results}
        keyword_dict = {r["id"]: r for r in keyword_results}

        # Build merged result dict
        merged_dict = {}

        for chunk_id in all_chunk_ids:
            # Prefer semantic for metadata completeness, fall back to keyword
            chunk_data = semantic_dict.get(chunk_id) or keyword_dict.get(chunk_id)

            if not chunk_data:
                logger.warning(f"Chunk {chunk_id} not found in either result set (should not happen)")
                continue

            chunk_data = chunk_data.copy()

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

            # Carry forward keyword-leg flags from the keyword result
            kw_chunk = keyword_dict.get(chunk_id)
            if kw_chunk:
                if not chunk_data.get("is_keyword_match") and kw_chunk.get("is_keyword_match"):
                    chunk_data["is_keyword_match"] = True
                if not chunk_data.get("is_phrase_match") and kw_chunk.get("is_phrase_match"):
                    chunk_data["is_phrase_match"] = True

            merged_dict[chunk_id] = chunk_data

        logger.debug(
            f"RRF merge: {len(semantic_results)} semantic + {len(keyword_results)} keyword "
            f"→ {len(merged_dict)} unique chunks (k={self.rrf_k})"
        )

        return list(merged_dict.values())

    def _apply_metadata_boost(
        self,
        results: List[Dict],
        query_input
    ) -> List[Dict]:
        """
        Apply intelligent metadata-based boosting using shared MetadataBooster.

        Args:
            results: Merged results with hybrid scores
            query_input: Query analysis (Dict from QueryAnalyzer or QueryUnderstanding object)

        Returns:
            Results with boosted hybrid scores
        """
        return self.metadata_booster.apply_boost(
            results,
            query_input,
            score_field="hybrid_score"
        )


def _build_identifier_match_boost(rq: RetrievalQuery):
    """Boost chunks containing exact identifier tokens that FTS ranks poorly in tables."""
    identifier_tokens = _extract_identifier_tokens(rq)
    if not identifier_tokens:
        return None

    boost_expr = None
    for token in identifier_tokens:
        token_pattern = rf"(^|[^0-9A-Za-z]){re.escape(token)}([^0-9A-Za-z]|$)"
        token_boost = case(
            (DocumentChunk.text.op("~*")(token_pattern), 0.35),
            else_=0.0,
        )
        boost_expr = token_boost if boost_expr is None else (boost_expr + token_boost)

    return boost_expr


def _extract_identifier_tokens(rq: RetrievalQuery) -> List[str]:
    tokens: List[str] = []
    for term in [*rq.lexical_required, *rq.lexical_optional]:
        for token in re.findall(r"[A-Za-z]*\d+[A-Za-z]*", term or ""):
            normalized = token.lower()
            if _should_boost_identifier_token(normalized):
                tokens.append(normalized)

    return list(dict.fromkeys(tokens))


def _should_boost_identifier_token(token: str) -> bool:
    if len(token) < 2:
        return False

    if token.isdigit() and len(token) == 4:
        year = int(token)
        if 1900 <= year <= 2099:
            return False

    return True
