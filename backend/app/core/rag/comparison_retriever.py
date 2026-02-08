"""
Comparison Retriever for RAG

Retrieves and pairs chunks from multiple documents for side-by-side comparison.
Uses full retrieval pipeline (hybrid + boost + rerank) per document.

Pairing/Clustering uses cross-encoder model for accurate semantic similarity scoring,
ensuring high-quality matches between related content across documents.
"""

from typing import List, Dict, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass
import asyncio
import numpy as np
import logging

from app.core.rag.hybrid_retriever import HybridRetriever
from app.core.rag.reranker import Reranker
from app.core.rag.metadata_booster import MetadataBooster
from app.core.rag.context_expander import ContextExpander
from app.repositories.document_repository import DocumentRepository
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.core.rag.query_understanding import QueryUnderstanding

logger = logging.getLogger(__name__)


@dataclass
class ChunkPair:
    """Pair of semantically similar chunks from different documents"""
    chunk_a: Dict
    chunk_b: Dict
    similarity: float
    topic: str  # Inferred topic (e.g., "financials", "cap rate")


@dataclass
class ChunkCluster:
    """Cluster of semantically similar chunks from multiple documents (3+)"""
    chunks: Dict[str, Dict]  # doc_id -> chunk
    topic: str
    avg_similarity: float  # Average pairwise similarity within cluster


@dataclass
class DocumentInfo:
    """Document metadata for comparison"""
    id: str
    filename: str
    label: str  # Display label ("Document A", "Document B")


@dataclass
class ComparisonContext:
    """Context for document comparison with paired/clustered chunks"""
    documents: List[DocumentInfo]
    paired_chunks: List[ChunkPair]  # For 2-document comparison
    clustered_chunks: List[ChunkCluster]  # For 3+ document comparison
    unpaired_chunks: Dict[str, List[Dict]]  # doc_id -> chunks
    num_documents: int


class ComparisonRetriever:
    """
    Retrieves and pairs chunks from multiple documents for comparison.

    Pipeline per document:
    1. Hybrid retrieval (semantic + BM25 + RRF) → 20 candidates
    2. Metadata boosting (query-adaptive)
    3. Re-ranking with cross-encoder → Top 10 chunks

    Then pairs chunks across documents by semantic similarity.
    """

    def __init__(
        self,
        db: Session,
        hybrid_retriever: HybridRetriever = None,
        reranker: Reranker = None,
        metadata_booster: MetadataBooster = None,
        context_expander: ContextExpander = None
    ):
        """
        Initialize comparison retriever

        Args:
            db: Database session
            hybrid_retriever: Optional custom hybrid retriever
            reranker: Optional custom reranker
            metadata_booster: Optional custom metadata booster
            context_expander: Optional custom context expander
        """
        self.db = db
        self.hybrid_retriever = hybrid_retriever or HybridRetriever(db)
        self.reranker = reranker or Reranker()
        self.metadata_booster = metadata_booster or MetadataBooster.for_reranker()
        self.context_expander = context_expander or ContextExpander()
        self.document_repo = DocumentRepository()

    async def retrieve_for_comparison(
        self,
        query: str,
        document_ids: List[str],
        collection_id: Optional[str] = None,
        chunks_per_doc: int = 10,
        similarity_threshold: float = 0.6,
        max_documents: int = 5,
        query_understanding=None,  # QueryUnderstanding object (optional, for HyDE)
        async_session: Optional[AsyncSession] = None  # For context expansion
    ) -> ComparisonContext:
        """
        Retrieve chunks from each document using FULL pipeline, then pair/cluster them.

        For 2 documents: Uses pairwise matching
        For 3+ documents: Uses clustering to find related chunks across all docs

        Args:
            query: User's comparison query
            document_ids: List of document IDs to compare (2-3 documents)
            collection_id: Optional collection filter
            chunks_per_doc: Number of chunks to retrieve per document
            similarity_threshold: Minimum similarity for pairing/clustering (0-1)
            max_documents: Maximum number of documents to compare
            query_understanding: Optional QueryUnderstanding object for HyDE enhancement
            async_session: Optional AsyncSession for context expansion (fetching linked chunks)

        Returns:
            ComparisonContext with paired/clustered chunks and document metadata
        """
        # Limit number of documents
        document_ids = document_ids[:max_documents]
        num_docs = len(document_ids)

        logger.info(
            f"Comparison retrieval: {num_docs} documents",
            extra={"query": query[:50], "document_ids": document_ids}
        )

        # Step 1: Retrieve from each document with full pipeline (in parallel)
        async def retrieve_doc(doc_id):
            """Helper to retrieve chunks for a single document."""
            chunks = await self._retrieve_single_doc(
                query=query,
                doc_id=doc_id,
                collection_id=collection_id,
                query_understanding=query_understanding,
                chunks_per_doc=chunks_per_doc,
                async_session=async_session
            )
            logger.debug(
                f"Retrieved {len(chunks)} chunks from document {doc_id}",
                extra={"doc_id": doc_id, "top_score": chunks[0].get('rerank_score') if chunks else 0}
            )
            return (doc_id, chunks)

        # Parallel retrieval - saves 1-2 seconds for multi-document comparisons
        results = await asyncio.gather(*[
            retrieve_doc(doc_id) for doc_id in document_ids
        ])

        doc_chunks = dict(results)

        # Step 2: Get document metadata
        documents = self._get_doc_metadata(document_ids)

        # Step 3: Pair or cluster chunks based on number of documents
        paired_chunks = []
        clustered_chunks = []

        if num_docs == 2:
            # Use pairwise matching for 2 documents
            paired_chunks = self._pair_chunks(doc_chunks, similarity_threshold)
            logger.info(
                f"Paired {len(paired_chunks)} chunk pairs (threshold={similarity_threshold})",
                extra={"doc_a_chunks": len(doc_chunks.get(document_ids[0], [])),
                       "doc_b_chunks": len(doc_chunks.get(document_ids[1], []))}
            )
        else:
            # Use clustering for 3+ documents
            clustered_chunks = self._cluster_chunks(doc_chunks, similarity_threshold)
            logger.info(
                f"Clustered {len(clustered_chunks)} chunk clusters across {num_docs} documents",
                extra={"avg_cluster_size": np.mean([len(c.chunks) for c in clustered_chunks]) if clustered_chunks else 0}
            )

        # Step 4: Get unpaired chunks
        unpaired = self._get_unpaired_multi(doc_chunks, paired_chunks, clustered_chunks)

        return ComparisonContext(
            documents=documents,
            paired_chunks=paired_chunks,
            clustered_chunks=clustered_chunks,
            unpaired_chunks=unpaired,
            num_documents=num_docs
        )

    async def _retrieve_single_doc(
        self,
        query: str,
        doc_id: str,
        collection_id: Optional[str],
        query_understanding: Optional['QueryUnderstanding'],
        chunks_per_doc: int,
        async_session: Optional[AsyncSession] = None
    ) -> List[Dict]:
        """
        Full retrieval pipeline for one document.

        Args:
            query: User's query
            doc_id: Document ID to retrieve from
            collection_id: Optional collection filter
            query_understanding: Optional QueryUnderstanding for HyDE and metadata boosting
            chunks_per_doc: Number of top chunks to return
            async_session: Optional AsyncSession for context expansion

        Returns:
            Top-k chunks with rerank scores, optionally expanded with related context
        """
        # Step 1: Hybrid retrieval (semantic + BM25 + RRF) with optional HyDE
        candidates = self.hybrid_retriever.retrieve(
            query=query,
            collection_id=collection_id,
            document_ids=[doc_id],
            top_k=20,  # Get 20 candidates for re-ranking
            query_understanding=query_understanding  # For HyDE enhancement
        )

        if not candidates:
            logger.warning(f"No candidates found for document {doc_id}")
            return []

        # Step 2: Re-rank with cross-encoder
        reranked = self.reranker.rerank(
            query=query,
            chunks=candidates,
            query_understanding=query_understanding,
            top_k=chunks_per_doc
        )

        # Step 3: Expand context if async_session available
        if async_session and reranked:
            try:
                reranked = await self.context_expander.expand(
                    chunks=reranked,
                    session=async_session,
                    max_expansion_per_chunk=2
                )
                logger.debug(
                    f"Context expansion for {doc_id}: {len(reranked) - chunks_per_doc} additional chunks"
                )
            except Exception as e:
                logger.warning(f"Context expansion failed for {doc_id}: {e}. Using original chunks.")
                # Continue with unexpanded chunks

        return reranked

    def _pair_chunks(
        self,
        doc_chunks: Dict[str, List[Dict]],
        similarity_threshold: float
    ) -> List[ChunkPair]:
        """
        Pair chunks from different documents by semantic similarity.

        Uses cross-encoder model for accurate semantic similarity scoring.

        Args:
            doc_chunks: Dict mapping doc_id to list of chunks
            similarity_threshold: Minimum similarity (0-1) to create pair

        Returns:
            List of ChunkPair objects, sorted by similarity (highest first)
        """
        if len(doc_chunks) < 2:
            logger.warning("Need at least 2 documents for pairing")
            return []

        doc_ids = list(doc_chunks.keys())
        chunks_a = doc_chunks[doc_ids[0]]
        chunks_b = doc_chunks[doc_ids[1]]

        if not chunks_a or not chunks_b:
            logger.warning("One or both documents have no chunks")
            return []

        # Compute all pairwise similarities using cross-encoder (batched)
        similarity_matrix = self._compute_cross_encoder_similarities(chunks_a, chunks_b)

        pairs = []
        used_b = set()

        # For each chunk in Doc A, find best match in Doc B
        for i, chunk_a in enumerate(chunks_a):
            best_match = None
            best_sim = 0.0

            for j, chunk_b in enumerate(chunks_b):
                if j in used_b:
                    continue

                sim = similarity_matrix[i][j]

                if sim > best_sim and sim >= similarity_threshold:
                    best_sim = sim
                    best_match = (j, chunk_b)

            if best_match:
                used_b.add(best_match[0])
                topic = self._infer_topic(chunk_a, best_match[1])

                pairs.append(ChunkPair(
                    chunk_a=chunk_a,
                    chunk_b=best_match[1],
                    similarity=best_sim,
                    topic=topic
                ))

        # Sort by similarity (highest first)
        pairs.sort(key=lambda p: p.similarity, reverse=True)

        logger.debug(
            f"Created {len(pairs)} pairs from {len(chunks_a)} x {len(chunks_b)} chunks using cross-encoder",
            extra={
                "avg_similarity": np.mean([p.similarity for p in pairs]) if pairs else 0,
                "top_similarity": pairs[0].similarity if pairs else 0
            }
        )

        return pairs

    def _compute_cross_encoder_similarities(
        self,
        chunks_a: List[Dict],
        chunks_b: List[Dict]
    ) -> List[List[float]]:
        """
        Compute pairwise semantic similarities using cross-encoder model.

        Creates all (chunk_a, chunk_b) pairs and scores them in batch.
        Returns matrix where similarity_matrix[i][j] = similarity(chunks_a[i], chunks_b[j])

        Args:
            chunks_a: List of chunks from document A
            chunks_b: List of chunks from document B

        Returns:
            2D list of similarity scores (normalized to 0-1 range)
        """
        # Build all pairs for batch scoring
        pairs = []
        pair_indices = []  # Track which (i, j) each pair corresponds to

        for i, chunk_a in enumerate(chunks_a):
            for j, chunk_b in enumerate(chunks_b):
                text_a = chunk_a.get('text', '')
                text_b = chunk_b.get('text', '')
                pairs.append([text_a, text_b])
                pair_indices.append((i, j))

        if not pairs:
            logger.warning("No chunk pairs to score")
            return [[0.0] * len(chunks_b) for _ in chunks_a]

        # Score all pairs with cross-encoder
        try:
            scores = self.reranker.model.predict(
                pairs,
                batch_size=self.reranker.batch_size,
                show_progress_bar=False
            )

            # Normalize scores to 0-1 range using sigmoid
            # Cross-encoder outputs can be negative, sigmoid maps to [0,1]
            normalized_scores = [1 / (1 + np.exp(-score)) for score in scores]

            # Build similarity matrix
            similarity_matrix = [[0.0] * len(chunks_b) for _ in chunks_a]
            for (i, j), score in zip(pair_indices, normalized_scores):
                similarity_matrix[i][j] = score

            logger.debug(
                f"Computed {len(pairs)} cross-encoder similarities for pairing",
                extra={
                    "avg_score": np.mean(normalized_scores),
                    "max_score": np.max(normalized_scores)
                }
            )

            return similarity_matrix

        except Exception as e:
            logger.error(f"Cross-encoder similarity computation failed: {e}", exc_info=True)
            logger.warning("Falling back to Jaccard similarity")
            # Fallback: use Jaccard similarity
            return self._compute_jaccard_similarities(chunks_a, chunks_b)

    def _compute_jaccard_similarities(
        self,
        chunks_a: List[Dict],
        chunks_b: List[Dict]
    ) -> List[List[float]]:
        """
        Fallback: Compute pairwise Jaccard similarities (word overlap).

        Args:
            chunks_a: List of chunks from document A
            chunks_b: List of chunks from document B

        Returns:
            2D list of Jaccard similarity scores
        """
        similarity_matrix = []

        for chunk_a in chunks_a:
            row = []
            text_a = chunk_a.get('text', '')
            words_a = set(text_a.lower().split())

            for chunk_b in chunks_b:
                text_b = chunk_b.get('text', '')
                words_b = set(text_b.lower().split())

                if not words_a or not words_b:
                    row.append(0.0)
                else:
                    intersection = len(words_a & words_b)
                    union = len(words_a | words_b)
                    jaccard = intersection / union if union > 0 else 0.0
                    row.append(jaccard)

            similarity_matrix.append(row)

        return similarity_matrix

    def _infer_topic(self, chunk_a: Dict, chunk_b: Dict) -> str:
        """
        Infer topic from paired chunks based on heading hierarchy, section headings, or content.

        Priority order:
        1. heading_hierarchy (if available and consistent)
        2. section_heading
        3. First few words of text
        """
        # Best: Use heading_hierarchy (e.g., ["Financial Summary", "Returns"])
        metadata_a = chunk_a.get('metadata', {})
        metadata_b = chunk_b.get('metadata', {})

        hierarchy_a = metadata_a.get('heading_hierarchy', [])
        hierarchy_b = metadata_b.get('heading_hierarchy', [])

        if hierarchy_a and hierarchy_b:
            # Use last 2 levels of hierarchy for topic
            topic_a = " > ".join(hierarchy_a[-2:]) if len(hierarchy_a) > 0 else ""
            topic_b = " > ".join(hierarchy_b[-2:]) if len(hierarchy_b) > 0 else ""

            if topic_a and topic_b == topic_a:
                return topic_a
            elif topic_a:
                return topic_a
            elif topic_b:
                return topic_b

        # Fallback: Try section headings (handle None values)
        heading_a = (chunk_a.get('section_heading') or '').strip()
        heading_b = (chunk_b.get('section_heading') or '').strip()

        if heading_a and heading_b and heading_a.lower() == heading_b.lower():
            return heading_a

        if heading_a:
            return heading_a
        if heading_b:
            return heading_b

        # Final fallback: extract first few words from chunk_a
        text = chunk_a.get('text', '')
        words = text.split()[:5]
        return ' '.join(words) + '...' if len(words) >= 5 else ' '.join(words)

    def _get_doc_metadata(self, document_ids: List[str]) -> List[DocumentInfo]:
        """Get document metadata for display"""
        docs = []
        labels = ['Document A', 'Document B', 'Document C']

        for i, doc_id in enumerate(document_ids):
            doc = self.document_repo.get_by_id(doc_id)

            if doc:
                docs.append(DocumentInfo(
                    id=doc.id,
                    filename=doc.filename,
                    label=labels[i] if i < len(labels) else f'Document {i+1}'
                ))
            else:
                logger.warning(f"Document {doc_id} not found in database")
                docs.append(DocumentInfo(
                    id=doc_id,
                    filename=f"Unknown ({doc_id[:8]})",
                    label=labels[i] if i < len(labels) else f'Document {i+1}'
                ))

        return docs

    def _cluster_chunks(
        self,
        doc_chunks: Dict[str, List[Dict]],
        similarity_threshold: float
    ) -> List[ChunkCluster]:
        """
        Cluster chunks from 3+ documents by semantic similarity.

        Greedy algorithm using cross-encoder for accurate semantic matching:
        1. Start with highest-ranked chunk from first document
        2. Find best matching chunk from each other document (above threshold)
        3. If at least 2 documents have a match, create cluster
        4. Mark chunks as used and continue

        Args:
            doc_chunks: Dict mapping doc_id to list of chunks
            similarity_threshold: Minimum similarity for clustering

        Returns:
            List of ChunkCluster objects
        """
        doc_ids = list(doc_chunks.keys())
        if len(doc_ids) < 3:
            logger.warning("Clustering requires at least 3 documents")
            return []

        # Track which chunks have been used
        used_chunks = {doc_id: set() for doc_id in doc_ids}
        clusters = []

        # Use first document as anchor
        anchor_doc_id = doc_ids[0]
        anchor_chunks = doc_chunks[anchor_doc_id]

        # Pre-compute similarities between anchor chunks and all other chunks
        # This is more efficient than computing on-demand
        similarity_cache = {}
        for other_doc_id in doc_ids[1:]:
            other_chunks = doc_chunks[other_doc_id]
            similarity_cache[other_doc_id] = self._compute_cross_encoder_similarities(
                anchor_chunks,
                other_chunks
            )

        for anchor_idx, anchor_chunk in enumerate(anchor_chunks):
            if id(anchor_chunk) in used_chunks[anchor_doc_id]:
                continue

            # Try to find matching chunk from each other document
            cluster_chunks = {anchor_doc_id: anchor_chunk}
            similarities = []

            for other_doc_id in doc_ids[1:]:
                best_match = None
                best_sim = 0.0
                best_idx = -1

                other_chunks = doc_chunks[other_doc_id]
                similarity_matrix = similarity_cache[other_doc_id]

                for other_idx, other_chunk in enumerate(other_chunks):
                    if id(other_chunk) in used_chunks[other_doc_id]:
                        continue

                    sim = similarity_matrix[anchor_idx][other_idx]

                    if sim > best_sim and sim >= similarity_threshold:
                        best_sim = sim
                        best_match = other_chunk
                        best_idx = other_idx

                if best_match:
                    cluster_chunks[other_doc_id] = best_match
                    similarities.append(best_sim)

            # Create cluster if we have chunks from at least 2 documents (including anchor)
            if len(cluster_chunks) >= 2:
                # Mark chunks as used
                for doc_id, chunk in cluster_chunks.items():
                    used_chunks[doc_id].add(id(chunk))

                # Infer topic from anchor chunk
                topic = self._infer_topic_from_chunk(anchor_chunk)

                clusters.append(ChunkCluster(
                    chunks=cluster_chunks,
                    topic=topic,
                    avg_similarity=np.mean(similarities) if similarities else 0.0
                ))

        logger.debug(
            f"Created {len(clusters)} clusters from {len(doc_ids)} documents using cross-encoder",
            extra={
                "avg_cluster_size": np.mean([len(c.chunks) for c in clusters]) if clusters else 0,
                "avg_similarity": np.mean([c.avg_similarity for c in clusters]) if clusters else 0
            }
        )

        return clusters

    def _infer_topic_from_chunk(self, chunk: Dict) -> str:
        """
        Infer topic from a single chunk.

        Priority order:
        1. heading_hierarchy (last 2 levels)
        2. section_heading
        3. First few words of text
        """
        metadata = chunk.get('metadata', {})

        # Best: Use heading_hierarchy
        hierarchy = metadata.get('heading_hierarchy', [])
        if hierarchy:
            # Use last 2 levels of hierarchy
            return " > ".join(hierarchy[-2:]) if len(hierarchy) > 0 else ""

        # Fallback: section_heading
        heading = (chunk.get('section_heading') or '').strip()
        if heading:
            return heading

        # Final fallback: Extract first few words
        text = chunk.get('text', '')
        words = text.split()[:5]
        return ' '.join(words) + '...' if len(words) >= 5 else ' '.join(words)

    def _get_unpaired(
        self,
        doc_chunks: Dict[str, List[Dict]],
        paired_chunks: List[ChunkPair]
    ) -> Dict[str, List[Dict]]:
        """
        Get chunks that weren't paired (for 2-document comparison)
        """
        if len(doc_chunks) < 2:
            return doc_chunks

        doc_ids = list(doc_chunks.keys())
        paired_a_ids = {id(p.chunk_a) for p in paired_chunks}
        paired_b_ids = {id(p.chunk_b) for p in paired_chunks}

        unpaired = {
            doc_ids[0]: [c for c in doc_chunks[doc_ids[0]] if id(c) not in paired_a_ids],
            doc_ids[1]: [c for c in doc_chunks[doc_ids[1]] if id(c) not in paired_b_ids]
        }

        return unpaired

    def _get_unpaired_multi(
        self,
        doc_chunks: Dict[str, List[Dict]],
        paired_chunks: List[ChunkPair],
        clustered_chunks: List[ChunkCluster]
    ) -> Dict[str, List[Dict]]:
        """
        Get chunks that weren't paired or clustered (for any number of documents)
        """
        # Collect all used chunk IDs
        used_ids = {}
        for doc_id in doc_chunks.keys():
            used_ids[doc_id] = set()

        # From pairs (2-doc comparison)
        if paired_chunks and len(doc_chunks) == 2:
            doc_ids = list(doc_chunks.keys())
            used_ids[doc_ids[0]] = {id(p.chunk_a) for p in paired_chunks}
            used_ids[doc_ids[1]] = {id(p.chunk_b) for p in paired_chunks}

        # From clusters (3+ doc comparison)
        for cluster in clustered_chunks:
            for doc_id, chunk in cluster.chunks.items():
                used_ids[doc_id].add(id(chunk))

        # Find unpaired
        unpaired = {}
        for doc_id, chunks in doc_chunks.items():
            unpaired[doc_id] = [c for c in chunks if id(c) not in used_ids.get(doc_id, set())]

        return unpaired
