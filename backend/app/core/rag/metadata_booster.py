"""
Metadata Booster for RAG

Shared utility for applying metadata-based boosting to chunk scores.
Used by both hybrid_retriever and re-ranker with configurable weights.
"""

from typing import List, Dict, Optional, Union, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from app.core.rag.query_understanding import QueryUnderstanding

logger = logging.getLogger(__name__)


class MetadataBooster:
    """
    Applies intelligent metadata-based boosting to chunk scores.

    Boost factors are MULTIPLICATIVE to the input score field.

    Supports query-adaptive boosting:
    - Data queries: boost tables, penalize/neutral narrative
    - Narrative queries: boost narrative, keep tables neutral
    """

    def __init__(
        self,
        table_boost_data_query: float = 1.2,
        key_value_boost_data_query: float = 1.25,
        narrative_penalty_data_query: float = 0.9,
        narrative_boost_narrative_query: float = 1.0,
        table_neutral_narrative_query: float = 1.0,
        key_value_neutral_narrative_query: float = 1.0,
        section_heading_boost: float = 1.05,
        first_pages_boost: float = 1.05,
        first_pages_threshold: int = 2,
        short_chunk_penalty: float = 0.9,
        short_chunk_threshold: int = 100,
        long_chunk_boost: float = 1.05,
        long_chunk_threshold: int = 1000
    ):
        """
        Initialize metadata booster with configurable weights.

        Args:
            table_boost_data_query: Boost for tables in data queries (default: 1.2)
            key_value_boost_data_query: Boost for key-value chunks in data queries (default: 1.25)
            narrative_penalty_data_query: Penalty for narrative in data queries (default: 0.9)
            narrative_boost_narrative_query: Boost for narrative in narrative queries (default: 1.0)
            table_neutral_narrative_query: Multiplier for tables in narrative queries (default: 1.0)
            key_value_neutral_narrative_query: Multiplier for key-value chunks in narrative queries (default: 1.0)
            section_heading_boost: Boost for chunks with section headings (default: 1.05)
            first_pages_boost: Boost for chunks on first N pages (default: 1.05)
            first_pages_threshold: Number of first pages to boost (default: 2)
            short_chunk_penalty: Penalty for very short chunks (default: 0.9)
            short_chunk_threshold: Character threshold for short chunks (default: 100)
            long_chunk_boost: Boost for comprehensive long chunks (default: 1.05)
            long_chunk_threshold: Character threshold for long chunks (default: 1000)
        """
        self.table_boost_data_query = table_boost_data_query
        self.key_value_boost_data_query = key_value_boost_data_query
        self.narrative_penalty_data_query = narrative_penalty_data_query
        self.narrative_boost_narrative_query = narrative_boost_narrative_query
        self.table_neutral_narrative_query = table_neutral_narrative_query
        self.key_value_neutral_narrative_query = key_value_neutral_narrative_query
        self.section_heading_boost = section_heading_boost
        self.first_pages_boost = first_pages_boost
        self.first_pages_threshold = first_pages_threshold
        self.short_chunk_penalty = short_chunk_penalty
        self.short_chunk_threshold = short_chunk_threshold
        self.long_chunk_boost = long_chunk_boost
        self.long_chunk_threshold = long_chunk_threshold

    def apply_boost(
        self,
        results: List[Dict],
        query_analysis: Union[Dict, 'QueryUnderstanding'],
        score_field: str = "hybrid_score"
    ) -> List[Dict]:
        """
        Apply metadata-based boosting to chunk scores.

        Args:
            results: List of chunks with scores
            query_analysis: Query analysis (Dict or QueryUnderstanding object)
            score_field: Field name containing the score to boost (e.g., "hybrid_score", "rerank_score")

        Returns:
            Results with boosted scores (modifies in-place and returns)
        """
        # Check if query_analysis is a QueryUnderstanding object
        if hasattr(query_analysis, 'table_boost'):
            # Use LLM-determined boost values from QueryUnderstanding
            table_boost_override = query_analysis.table_boost
            narrative_boost_override = query_analysis.narrative_boost
            query_type = "generic_query"  # Not used when overrides present
        else:
            # Legacy dict format
            table_boost_override = None
            narrative_boost_override = None
            query_type = query_analysis.get("query_type", "generic_query")

        for chunk in results:
            boost = 1.0

            # Determine chunk type (section_type preferred, metadata fallback)
            chunk_type = chunk.get("section_type")
            if not chunk_type:
                metadata = chunk.get("chunk_metadata") or {}
                if isinstance(metadata, dict):
                    chunk_type = metadata.get("chunk_type")

            is_key_value = chunk_type in ("key_value_pairs", "key_value")
            is_table = chunk.get("is_tabular") or chunk_type == "table"

            # 1. Content type boost (query-adaptive)
            if is_key_value:
                if query_type == "data_query":
                    boost *= self.key_value_boost_data_query
                else:
                    boost *= self.key_value_neutral_narrative_query
            elif is_table:
                if table_boost_override is not None:
                    # Use LLM-determined boost
                    boost *= table_boost_override
                elif query_type == "data_query":
                    # Data queries prefer tables
                    boost *= self.table_boost_data_query
                else:
                    # Narrative queries keep tables neutral
                    boost *= self.table_neutral_narrative_query
            else:
                # Non-tabular (narrative) content
                if narrative_boost_override is not None:
                    # Use LLM-determined boost
                    boost *= narrative_boost_override
                elif query_type == "data_query":
                    # Data queries penalize narrative (might be verbose/fluff)
                    boost *= self.narrative_penalty_data_query
                elif query_type == "narrative_query":
                    # Narrative queries prefer narrative content
                    boost *= self.narrative_boost_narrative_query
                # Generic queries: no boost (1.0)

            # 2. Section heading boost (structured content is often more relevant)
            if chunk.get("section_heading"):
                boost *= self.section_heading_boost

            # 3. Page number boost (first pages often have executive summaries)
            page_num = chunk.get("page_number")
            if page_num and page_num <= self.first_pages_threshold:
                boost *= self.first_pages_boost

            # 4. Chunk length consideration
            text = chunk.get("text", "")
            # Use compressed_text if available (for re-ranker)
            if "compressed_text" in chunk:
                text = chunk["compressed_text"]

            text_len = len(text)
            if text_len < self.short_chunk_threshold:
                # Very short chunks may lack context
                boost *= self.short_chunk_penalty
            elif text_len > self.long_chunk_threshold:
                # Long chunks are comprehensive
                boost *= self.long_chunk_boost

            # Apply boost to score
            original_score = chunk.get(score_field, 0)
            boosted_score = original_score * boost

            chunk[score_field] = boosted_score
            chunk["metadata_boost"] = boost

        return results

    @classmethod
    def for_hybrid_retriever(cls) -> "MetadataBooster":
        """
        Factory method for hybrid retriever boosting (stronger boosts).

        Returns:
            MetadataBooster configured for hybrid retrieval
        """
        return cls(
            table_boost_data_query=1.2,      # 20% boost for tables
            key_value_boost_data_query=1.25,  # 25% boost for key-value
            narrative_penalty_data_query=0.9,  # 10% penalty for narrative
            narrative_boost_narrative_query=1.0,  # Neutral for narrative
            table_neutral_narrative_query=1.0,    # Neutral for tables
            key_value_neutral_narrative_query=1.0,  # Neutral for key-value
            section_heading_boost=1.05,
            first_pages_boost=1.05,
            first_pages_threshold=2,
            short_chunk_penalty=0.9,
            short_chunk_threshold=100,
            long_chunk_boost=1.05,
            long_chunk_threshold=1000
        )

    @classmethod
    def for_reranker(cls) -> "MetadataBooster":
        """
        Factory method for re-ranker boosting (gentler nudges).

        Returns:
            MetadataBooster configured for re-ranking
        """
        return cls(
            table_boost_data_query=1.1,       # 10% boost for tables (gentler)
            key_value_boost_data_query=1.15,  # 15% boost for key-value (gentler)
            narrative_penalty_data_query=0.95,  # 5% penalty for narrative (gentler)
            narrative_boost_narrative_query=1.0,  # Neutral for narrative
            table_neutral_narrative_query=1.0,     # Neutral for tables
            key_value_neutral_narrative_query=1.0,  # Neutral for key-value
            section_heading_boost=1.03,       # Gentler boost (3%)
            first_pages_boost=1.03,           # Gentler boost (3%)
            first_pages_threshold=2,
            short_chunk_penalty=0.95,         # Gentler penalty (5%)
            short_chunk_threshold=100,
            long_chunk_boost=1.03,            # Gentler boost (3%)
            long_chunk_threshold=1000
        )
