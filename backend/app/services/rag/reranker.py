"""
Re-ranker for RAG

Uses cross-encoder models to re-rank hybrid retrieval results
for improved relevance scoring.

Cross-encoders take (query, document) pairs and output direct relevance scores,
making them more accurate than bi-encoder (embedding) based ranking.
"""

from typing import List, Dict, Optional
import logging
from sentence_transformers import CrossEncoder
from app.config import settings
from app.services.rag.metadata_booster import MetadataBooster

logger = logging.getLogger(__name__)


class Reranker:
    """
    Cross-encoder based re-ranker for document chunks.

    Pipeline:
    1. Takes query + list of chunks
    2. Optionally compresses chunks to fit token limits
    3. Scores each (query, chunk) pair with cross-encoder
    4. Optionally applies metadata boosting (gentle nudge for tables)
    5. Returns chunks sorted by relevance score
    """

    def __init__(
        self,
        model_name: str = None,
        batch_size: int = None,
        use_compression: bool = None,
        apply_metadata_boost: bool = None
    ):
        """
        Initialize re-ranker.

        Args:
            model_name: Cross-encoder model name (default from settings)
            batch_size: Batch size for scoring (default from settings)
            use_compression: Use chunk compression (default from settings)
            apply_metadata_boost: Apply metadata boosting to scores (default from settings)
        """
        self.model_name = model_name or settings.rag_reranker_model
        self.batch_size = batch_size or settings.rag_reranker_batch_size
        self.use_compression = use_compression if use_compression is not None else settings.rag_use_compression
        self.apply_metadata_boost = apply_metadata_boost if apply_metadata_boost is not None else settings.rag_reranker_apply_metadata_boost

        # Lazy-load compression if enabled
        self._compressor = None
        if self.use_compression:
            from app.services.rag.chunk_compressor import ChunkCompressor
            self._compressor = ChunkCompressor()

        # Initialize metadata booster (gentler weights for re-ranker)
        self.metadata_booster = MetadataBooster.for_reranker()

        # Load cross-encoder model
        try:
            self.model = CrossEncoder(self.model_name, max_length=512)
            logger.info(
                f"Reranker initialized: model={self.model_name}, "
                f"batch_size={self.batch_size}, compression={self.use_compression}, "
                f"metadata_boost={self.apply_metadata_boost}"
            )
        except Exception as e:
            logger.error(f"Failed to load cross-encoder model {self.model_name}: {e}", exc_info=True)
            raise

    def rerank(
        self,
        query: str,
        chunks: List[Dict],
        query_analysis: Dict,
        top_k: Optional[int] = None
    ) -> List[Dict]:
        """
        Re-rank chunks based on relevance to query.

        Args:
            query: User's search query
            chunks: List of chunk dicts from hybrid retrieval
            query_analysis: Query analysis from QueryAnalyzer (for metadata boosting)
            top_k: Number of top chunks to return (default: return all, sorted)

        Returns:
            List of chunks sorted by rerank_score (descending)
        """
        if not chunks:
            logger.warning("No chunks provided for re-ranking")
            return []

        logger.debug(
            f"Re-ranking {len(chunks)} chunks",
            extra={
                "query": query[:50],
                "use_compression": self.use_compression,
                "query_type": query_analysis.get("query_type")
            }
        )

        # Step 1: Optionally compress chunks to fit token limits
        if self.use_compression and self._compressor:
            chunks = self._compressor.compress_chunks(chunks)
            text_field = "compressed_text"
        else:
            # Use original text (cross-encoder will truncate if needed)
            text_field = "text"

        # Step 2: Build query-document pairs
        pairs = []
        for chunk in chunks:
            text = chunk.get(text_field, chunk.get("text", ""))
            pairs.append([query, text])

        # Step 3: Score all pairs with cross-encoder
        try:
            # Cross-encoder returns relevance scores (higher = more relevant)
            scores = self.model.predict(
                pairs,
                batch_size=self.batch_size,
                show_progress_bar=False
            )

            # Add rerank scores to chunks
            for chunk, score in zip(chunks, scores):
                chunk["rerank_score"] = float(score)

            # Step 4: Optionally apply metadata boosting (gentle nudge)
            if self.apply_metadata_boost:
                chunks = self.metadata_booster.apply_boost(
                    chunks,
                    query_analysis,
                    score_field="rerank_score"
                )
                logger.debug("Applied metadata boosting to rerank scores")

            # Step 5: Sort by rerank score (descending)
            ranked_chunks = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)

            # Step 6: Return top-k if specified
            if top_k is not None:
                ranked_chunks = ranked_chunks[:top_k]

            logger.info(
                f"Re-ranking complete: {len(ranked_chunks)} chunks returned",
                extra={
                    "top_score": ranked_chunks[0]["rerank_score"] if ranked_chunks else 0,
                    "query": query[:50],
                    "query_type": query_analysis.get("query_type")
                }
            )

            return ranked_chunks

        except Exception as e:
            logger.error(f"Re-ranking failed: {e}", exc_info=True)
            # Fallback: return original chunks sorted by hybrid_score
            logger.warning("Falling back to hybrid scores (no re-ranking)")
            fallback_chunks = sorted(
                chunks,
                key=lambda x: x.get("hybrid_score", 0),
                reverse=True
            )
            return fallback_chunks[:top_k] if top_k else fallback_chunks
