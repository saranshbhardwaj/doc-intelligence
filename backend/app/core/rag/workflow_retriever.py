"""
Workflow Retriever for RAG

Specialized retriever for workflow context assembly with:
- Multi-query retrieval per section
- Hybrid search (semantic + keyword)
- Cross-encoder re-ranking
- Section-specific preferences (tables vs narrative)
- Diversity filtering across documents
"""

from typing import List, Dict
import logging
from sqlalchemy.orm import Session
from app.core.rag.hybrid_retriever import HybridRetriever
from app.core.rag.reranker import Reranker
from app.config import settings

logger = logging.getLogger(__name__)


class WorkflowRetriever:
    """
    Retrieves and ranks content for workflow sections.

    Pipeline per section:
    1. Run multiple queries (3-5 per section)
    2. Hybrid retrieval for each query (semantic + keyword)
    3. Merge and deduplicate results
    4. Re-rank with cross-encoder (handles compression/truncation internally)
    5. Apply diversity filtering (max 50% from one doc)
    6. Return top-k chunks per section with citations

    Note: Uses same compression/re-ranking infrastructure as free-form chat (via Reranker).
    """

    def __init__(
        self,
        db: Session,
        use_reranker: bool = None,
        diversity_ratio: float = 0.5
    ):
        """
        Initialize workflow retriever.

        Args:
            db: SQLAlchemy database session
            use_reranker: Enable re-ranking (default from settings)
            diversity_ratio: Max ratio from single document (default: 0.5 = 50%)
        """
        self.db = db
        self.hybrid_retriever = HybridRetriever(db)
        self.diversity_ratio = diversity_ratio

        # Re-ranker (optional, handles compression internally)
        self.use_reranker = use_reranker if use_reranker is not None else settings.rag_use_reranker
        self.reranker = None
        if self.use_reranker:
            self.reranker = Reranker()

        logger.info(
            f"WorkflowRetriever initialized: reranker={self.use_reranker}, "
            f"diversity_ratio={self.diversity_ratio}"
        )

    def retrieve_section(
        self,
        section_spec: Dict,
        document_ids: List[str],
        doc_index_map: Dict[str, int]
    ) -> List[Dict]:
        """
        Retrieve and rank chunks for a single workflow section.

        Args:
            section_spec: Section specification with queries, preferences, max_chunks
            document_ids: List of document IDs to search
            doc_index_map: Mapping of doc_id to citation index (e.g., {doc_id: 1} -> D1)

        Returns:
            List of ranked chunks with citation labels
        """
        queries = section_spec.get("queries", [])
        prefer_tables = section_spec.get("prefer_tables", False)
        max_chunks = section_spec.get("max_chunks", 20)
        section_key = section_spec.get("key", "unknown")

        if not queries:
            logger.warning(f"No queries for section {section_key}")
            return []

        logger.debug(
            f"Retrieving section '{section_key}': {len(queries)} queries, "
            f"prefer_tables={prefer_tables}, max_chunks={max_chunks}"
        )

        # Step 1: Collect candidates from all queries
        all_candidates = {}  # chunk_id -> chunk_dict

        # Adaptive candidate sizing: favor tables for data-heavy sections
        # query_top_k = 2 # TODO: changed to 2 for testing
        query_top_k = 12 if prefer_tables else 10

        for query in queries:
            try:
                # Hybrid retrieval for this query
                candidates = self.hybrid_retriever.retrieve(
                    query=query,
                    collection_id=None,  # Use document_ids filter instead
                    top_k=query_top_k,  # Adaptive per section
                    document_ids=document_ids,
                    min_semantic_similarity=settings.rag_workflow_semantic_similarity_floor
                )

                # Merge into all_candidates (keep best hybrid_score)
                for chunk in candidates:
                    chunk_id = chunk["id"]
                    if chunk_id in all_candidates:
                        # Keep chunk with higher score
                        if chunk["hybrid_score"] > all_candidates[chunk_id]["hybrid_score"]:
                            all_candidates[chunk_id] = chunk
                    else:
                        all_candidates[chunk_id] = chunk

            except Exception as e:
                logger.warning(
                    f"Query failed for section {section_key}: {query[:50]}",
                    extra={"error": str(e)}
                )
                continue

        if not all_candidates:
            logger.warning(f"No candidates retrieved for section {section_key}")
            return []

        logger.debug(
            f"Section '{section_key}': {len(all_candidates)} unique candidates from {len(queries)} queries"
        )

        # Step 2: Re-rank candidates (if enabled)
        # Note: Reranker handles compression internally, no need to pre-compress
        candidates_list = list(all_candidates.values())

        if self.reranker and len(candidates_list) > 5:
            try:
                # Combine queries for re-ranking intent
                combined_query = " ".join(queries[:3])  # Use first 3 queries

                # Create query analysis hint based on prefer_tables
                query_analysis = {
                    "query_type": "data_query" if prefer_tables else "narrative_query",
                    "prefer_tables": prefer_tables,
                    "prefer_narrative": not prefer_tables
                }

                # Re-rank (Reranker handles compression/truncation internally)
                reranked = self.reranker.rerank(
                    query=combined_query,
                    chunks=candidates_list,
                    query_analysis=query_analysis,
                    top_k=max_chunks * 2  # Get 2x for diversity filtering
                )

                candidates_list = reranked
                logger.debug(
                    f"Section '{section_key}': Re-ranked to {len(candidates_list)} chunks"
                )

            except Exception as e:
                logger.error(
                    f"Re-ranking failed for section {section_key}: {e}",
                    exc_info=True
                )
                # Fall back to hybrid scores
                candidates_list = sorted(
                    candidates_list,
                    key=lambda x: x.get("hybrid_score", 0),
                    reverse=True
                )
        else:
            # No re-ranker: sort by hybrid_score
            candidates_list = sorted(
                candidates_list,
                key=lambda x: x.get("hybrid_score", 0),
                reverse=True
            )

        # Step 3: Apply diversity filtering
        final_chunks = self._apply_diversity_filter(
            candidates_list,
            max_chunks=max_chunks,
            document_ids=document_ids
        )

        # Step 4: Add citation labels and metadata
        # Production approach: Add citation info to both in-memory dict AND chunk_metadata
        # - In-memory dict: For immediate context assembly in tasks.py
        # - chunk_metadata: For future citation resolution (if chunks re-queried)
        for chunk in final_chunks:
            doc_id = chunk.get("document_id")
            page_num = chunk.get("page_number", 0)
            doc_index = doc_index_map.get(doc_id, 0)
            citation_token = f"[D{doc_index}:p{page_num}]"

            # Add to in-memory dict (for context assembly)
            chunk["citation"] = citation_token

            # Enhance chunk_metadata with citation info (preserve existing metadata from DB)
            # chunk_metadata should already have: document_filename, section_heading, first_sentence, etc.
            if "chunk_metadata" not in chunk or chunk["chunk_metadata"] is None:
                chunk["chunk_metadata"] = {}
            elif isinstance(chunk["chunk_metadata"], str):
                # Handle case where JSONB came as string (deserialize it)
                import json
                try:
                    chunk["chunk_metadata"] = json.loads(chunk["chunk_metadata"])
                except (json.JSONDecodeError, TypeError):
                    chunk["chunk_metadata"] = {}

            # Add runtime citation metadata (without overwriting DB metadata)
            chunk["chunk_metadata"]["citation_token"] = citation_token
            chunk["chunk_metadata"]["doc_index"] = doc_index
            chunk["chunk_metadata"]["runtime_document_id"] = doc_id

        logger.info(
            f"Section '{section_key}': Retrieved {len(final_chunks)} final chunks "
            f"(max={max_chunks}, diversity_filtered={len(candidates_list) - len(final_chunks)})"
        )

        return final_chunks

    def _apply_diversity_filter(
        self,
        chunks: List[Dict],
        max_chunks: int,
        document_ids: List[str]
    ) -> List[Dict]:
        """
        Apply diversity filtering to prevent over-representation from single document.

        Args:
            chunks: Sorted chunks (by relevance)
            max_chunks: Maximum chunks to return
            document_ids: List of all document IDs

        Returns:
            Filtered list with diversity constraints
        """
        max_per_doc = max(1, int(max_chunks * self.diversity_ratio))
        doc_counts = {doc_id: 0 for doc_id in document_ids}
        filtered = []

        for chunk in chunks:
            doc_id = chunk.get("document_id")

            # Skip if this document is over quota
            if doc_counts.get(doc_id, 0) >= max_per_doc:
                continue

            # Add chunk and increment counter
            filtered.append(chunk)
            doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1

            # Stop if we have enough
            if len(filtered) >= max_chunks:
                break

        return filtered

    def retrieve_all_sections(
        self,
        sections_spec: List[Dict],
        document_ids: List[str]
    ) -> Dict[str, List[Dict]]:
        """
        Retrieve chunks for all workflow sections.

        Args:
            sections_spec: List of section specifications
            document_ids: List of document IDs to search

        Returns:
            Dict mapping section_key -> list of chunks
        """
        # Build document index map for citations
        doc_index_map = {doc_id: i + 1 for i, doc_id in enumerate(document_ids)}

        sections_content = {}

        for spec in sections_spec:
            section_key = spec.get("key", "unknown")

            try:
                chunks = self.retrieve_section(
                    section_spec=spec,
                    document_ids=document_ids,
                    doc_index_map=doc_index_map
                )
                sections_content[section_key] = chunks

            except Exception as e:
                logger.error(
                    f"Failed to retrieve section {section_key}: {e}",
                    exc_info=True
                )
                sections_content[section_key] = []

        logger.info(
            f"Retrieved content for {len(sections_content)} sections, "
            f"total chunks: {sum(len(chunks) for chunks in sections_content.values())}"
        )

        return sections_content
