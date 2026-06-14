"""
Re-ranker for RAG

Uses cross-encoder models to re-rank hybrid retrieval results
for improved relevance scoring.

Cross-encoders take (query, document) pairs and output direct relevance scores,
making them more accurate than bi-encoder (embedding) based ranking.

Cross-encoder token limit: 512 tokens
Chunks exceeding this limit are truncated for scoring only.
Original chunks are preserved and returned to caller.
"""

from typing import List, Dict, Optional, TYPE_CHECKING
import logging
import re
from sentence_transformers import CrossEncoder
from app.config import settings
from app.core.rag.metadata_booster import MetadataBooster
from app.utils.token_utils import count_tokens, truncate_to_token_limit

if TYPE_CHECKING:
    from app.core.rag.query_understanding import QueryUnderstanding

logger = logging.getLogger(__name__)


class Reranker:
    """
    Cross-encoder based re-ranker for document chunks.

    Pipeline:
    1. Takes query + list of chunks
    2. Truncates chunks > 512 tokens (for scoring only)
    3. Scores each (query, chunk) pair with cross-encoder
    4. Optionally applies metadata boosting (gentle nudge for tables)
    5. Returns ORIGINAL chunks sorted by relevance score

    Token limit: 512 tokens (cross-encoder max_length)
    Chunks > 512 tokens are truncated for scoring.
    Original chunks are preserved and returned.
    """

    CROSS_ENCODER_TOKEN_LIMIT = 512
    _STRUCTURED_CHUNK_TYPES = {"table", "table_block", "key_value_pairs", "key_value"}
    _QUERY_STOPWORDS = {
        "a", "an", "and", "are", "at", "be", "by", "for", "from", "how",
        "in", "is", "it", "of", "on", "or", "the", "to", "what", "when",
        "where", "which", "who", "with",
    }

    def __init__(
        self,
        model_name: str = None,
        batch_size: int = None,
        apply_metadata_boost: bool = None
    ):
        """
        Initialize re-ranker.

        Args:
            model_name: Cross-encoder model name (default from settings)
            batch_size: Batch size for scoring (default from settings)
            apply_metadata_boost: Apply metadata boosting to scores (default from settings)
        """
        self.model_name = model_name or settings.rag_reranker_model
        self.batch_size = batch_size or settings.rag_reranker_batch_size
        self.apply_metadata_boost = apply_metadata_boost if apply_metadata_boost is not None else settings.rag_reranker_apply_metadata_boost

        # Initialize metadata booster (gentler weights for re-ranker)
        self.metadata_booster = MetadataBooster.for_reranker()

        # Load cross-encoder model
        try:
            self.model = CrossEncoder(
                self.model_name,
                max_length=512,
                trust_remote_code=settings.rag_reranker_trust_remote_code,
            )
            logger.info(
                f"Reranker initialized: model={self.model_name}, "
                f"batch_size={self.batch_size}, "
                f"metadata_boost={self.apply_metadata_boost}, "
                f"trust_remote_code={settings.rag_reranker_trust_remote_code}"
            )
        except Exception as e:
            logger.error(f"Failed to load cross-encoder model {self.model_name}: {e}", exc_info=True)
            raise

    @staticmethod
    def _map_query_type_for_metadata_boost(query_understanding: 'QueryUnderstanding') -> str:
        """
        Map QueryUnderstanding.query_type to metadata booster's expected query_type.

        Args:
            query_understanding: QueryUnderstanding object

        Returns:
            One of: "data_query", "narrative_query", "generic_query"
        """
        from app.core.rag.query_understanding import QueryType

        if query_understanding.query_type == QueryType.DATA_EXTRACTION:
            return "data_query"
        elif query_understanding.query_type in (QueryType.SUMMARIZATION, QueryType.ENTITY_LOOKUP):
            return "narrative_query"
        else:
            # GENERAL_QA, COMPARISON, or unknown
            return "generic_query"

    def rerank(
        self,
        query: str,
        chunks: List[Dict],
        query_understanding: Optional['QueryUnderstanding'] = None,
        top_k: Optional[int] = None,
        apply_metadata_boost: Optional[bool] = None,
        apply_structured_signal: Optional[bool] = None,
    ) -> List[Dict]:
        """
        Re-rank chunks based on relevance to query.

        Args:
            query: User's search query
            chunks: List of chunk dicts from hybrid retrieval
            query_understanding: Optional QueryUnderstanding for metadata boosting
            top_k: Number of top chunks to return (default: return all, sorted)

        Returns:
            List of chunks sorted by rerank_score (descending)
        """
        if not chunks:
            logger.warning("No chunks provided for re-ranking")
            return []

        # Determine query type for logging
        query_type_str = "generic_query"
        if query_understanding:
            query_type_str = self._map_query_type_for_metadata_boost(query_understanding)

        logger.debug(
            f"Re-ranking {len(chunks)} chunks",
            extra={
                "query": query[:50],
                "query_type": query_type_str
            }
        )

        # Step 1: Prepare text for scoring
        # Truncate chunks > 512 tokens to fit cross-encoder limit (for scoring only)
        # We return ORIGINAL chunks to caller (not truncated)
        pairs = []
        for chunk in chunks:
            text = chunk.get("text", "")

            # Check token count
            token_count = count_tokens(text)

            # Truncate if > 512 tokens (for scoring only)
            if token_count > self.CROSS_ENCODER_TOKEN_LIMIT:
                text = truncate_to_token_limit(text, self.CROSS_ENCODER_TOKEN_LIMIT)
                logger.debug(
                    f"Truncated chunk for re-ranking: {token_count} → {self.CROSS_ENCODER_TOKEN_LIMIT} tokens"
                )

            pairs.append([query, text])

        # Step 2: Score all pairs with cross-encoder
        try:
            # Cross-encoder returns relevance scores (higher = more relevant)
            scores = self.model.predict(
                pairs,
                batch_size=self.batch_size,
                show_progress_bar=False
            )

            # Add rerank scores to ORIGINAL chunks (not compressed copies)
            for chunk, score in zip(chunks, scores):
                chunk["rerank_score"] = float(score)

            # Step 4: Optionally apply metadata boosting (gentle nudge)
            use_metadata_boost = self.apply_metadata_boost if apply_metadata_boost is None else apply_metadata_boost
            if use_metadata_boost:
                # Pass QueryUnderstanding directly if available, otherwise use basic dict
                boost_input = query_understanding if query_understanding else {"query_type": query_type_str}
                chunks = self.metadata_booster.apply_boost(
                    chunks,
                    boost_input,
                    score_field="rerank_score"
                )
                logger.debug("Applied metadata boosting to rerank scores")

            use_structured_signal = (
                settings.rag_reranker_structured_signal_enabled
                if apply_structured_signal is None
                else apply_structured_signal
            )
            if use_structured_signal:
                boosted_structured = 0
                for chunk in chunks:
                    structured_evidence_score = self._compute_structured_evidence_score(
                        query=query,
                        chunk=chunk,
                        query_understanding=query_understanding,
                    )
                    chunk["structured_evidence_score"] = structured_evidence_score
                    if structured_evidence_score > 0:
                        chunk["rerank_score"] += (
                            settings.rag_reranker_structured_signal_weight
                            * structured_evidence_score
                        )
                        boosted_structured += 1

                if boosted_structured:
                    logger.debug(
                        "Applied structured evidence bonus",
                        extra={
                            "boosted_structured_chunks": boosted_structured,
                            "query": query[:50],
                        },
                    )

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
                    "query_type": query_type_str
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

    @classmethod
    def _is_structured_chunk(cls, chunk: Dict) -> bool:
        chunk_type = chunk.get("section_type")
        if not chunk_type:
            metadata = chunk.get("chunk_metadata") or {}
            if isinstance(metadata, dict):
                chunk_type = metadata.get("chunk_type")
        return bool(chunk.get("is_tabular") or chunk_type in cls._STRUCTURED_CHUNK_TYPES)

    @classmethod
    def _tokenize_structured_signal(cls, text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", (text or "").lower())

    @classmethod
    def _extract_identifier_targets(cls, query: str) -> list[tuple[str, str]]:
        targets: list[tuple[str, str]] = []
        for label, value in re.findall(
            r"\b(unit|suite|apt|apartment|building)\s+([a-z0-9-]+)\b",
            (query or "").lower(),
        ):
            if value:
                targets.append((label, value))
        return targets

    @classmethod
    def _has_exact_structured_identifier_match(
        cls,
        chunk_text: str,
        label: str,
        value: str,
    ) -> bool:
        if label == "unit":
            return bool(
                re.search(rf"(?m)(?:^|\|)\s*{re.escape(value)}\s*\|", chunk_text)
            )

        return bool(
            re.search(rf"\b{re.escape(label)}\s*[:#-]?\s*{re.escape(value)}\b", chunk_text)
        )

    @classmethod
    def _salient_query_terms(cls, query: str, query_understanding: Optional['QueryUnderstanding']) -> list[str]:
        data_fields = [
            field.strip().lower()
            for field in (getattr(query_understanding, "data_fields", []) or [])
            if isinstance(field, str) and field.strip()
        ]
        if data_fields:
            return [
                token
                for field in data_fields
                for token in cls._tokenize_structured_signal(field)
                if len(token) > 2 and token not in cls._QUERY_STOPWORDS
            ]

        return [
            token
            for token in cls._tokenize_structured_signal(query)
            if len(token) > 2 and token not in cls._QUERY_STOPWORDS
        ]

    @classmethod
    def _compute_structured_evidence_score(
        cls,
        query: str,
        chunk: Dict,
        query_understanding: Optional['QueryUnderstanding'] = None,
    ) -> float:
        """Return a small, inspectable bonus for structured financial evidence."""
        if not cls._is_structured_chunk(chunk):
            return 0.0

        chunk_text = chunk.get("text", "") or ""
        chunk_text_lower = chunk_text.lower()
        heading = (chunk.get("section_heading") or "").lower()

        score = 0.2

        if chunk.get("is_phrase_match"):
            score += 0.15

        identifier_targets = cls._extract_identifier_targets(query)
        identifier_values = {value for _, value in identifier_targets}
        if identifier_targets:
            exact_identifier_match = any(
                cls._has_exact_structured_identifier_match(chunk_text_lower, label, value)
                for label, value in identifier_targets
            )
            if exact_identifier_match:
                score += 0.35

        query_numbers = set(re.findall(r"\d[\d,./%-]*", query or ""))
        if identifier_values:
            query_numbers = {number for number in query_numbers if number not in identifier_values}

        if query_numbers and any(number in chunk_text for number in query_numbers):
            score += 0.2

        salient_terms = cls._salient_query_terms(query, query_understanding)
        if salient_terms:
            term_hits = sum(1 for term in set(salient_terms) if term in chunk_text_lower)
            heading_hits = sum(1 for term in set(salient_terms) if term in heading)
            score += min(0.25, 0.08 * term_hits)
            score += min(0.15, 0.05 * heading_hits)

        data_fields = [
            field.strip().lower()
            for field in (getattr(query_understanding, "data_fields", []) or [])
            if isinstance(field, str) and field.strip()
        ]
        if data_fields and any(field in chunk_text_lower or field in heading for field in data_fields):
            score += 0.2

        return min(score, 1.0)

    def filter_noise(
        self,
        query: str,
        chunks: List[Dict],
        threshold: float,
    ) -> List[Dict]:
        """
        Score all chunks and drop those below threshold. No top-k cut.

        Used by ambient mode to remove genuinely irrelevant chunks (TOC pages,
        disclaimers, headers) while preserving all relevant chunks from all docs.

        Args:
            query: User query string
            chunks: Candidate chunks from hybrid retrieval
            threshold: Drop chunks with rerank_score below this value

        Returns:
            Chunks with rerank_score set, filtered to >= threshold, order preserved
        """
        if not chunks:
            return []

        pairs = []
        for chunk in chunks:
            text = chunk.get("text", "")
            token_count = count_tokens(text)
            if token_count > self.CROSS_ENCODER_TOKEN_LIMIT:
                text = truncate_to_token_limit(text, self.CROSS_ENCODER_TOKEN_LIMIT)
            pairs.append([query, text])

        try:
            scores = self.model.predict(
                pairs,
                batch_size=self.batch_size,
                show_progress_bar=False,
            )
            for chunk, score in zip(chunks, scores):
                chunk["rerank_score"] = float(score)

            passing = [c for c in chunks if c["rerank_score"] >= threshold]
            logger.info(
                f"Ambient noise filter: {len(passing)}/{len(chunks)} chunks passed threshold={threshold}",
            )
            return passing

        except Exception as e:
            logger.error(f"filter_noise failed: {e}", exc_info=True)
            # Fallback: return all chunks unfiltered
            return chunks
