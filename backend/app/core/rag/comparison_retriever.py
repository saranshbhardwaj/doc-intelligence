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
import functools
import numpy as np
import logging
import time

from app.core.rag.hybrid_retriever import HybridRetriever
from app.core.rag.reranker import Reranker
from app.services.service_locator import get_reranker
from app.config import settings
from app.core.rag.metadata_booster import MetadataBooster
from app.core.rag.context_expander import ContextExpander
from app.repositories.document_repository import DocumentRepository
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rag.query_understanding import QueryType

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
        if reranker is not None:
            self.reranker = reranker
        else:
            self.reranker = get_reranker() if settings.rag_use_reranker else None
        self.metadata_booster = metadata_booster or MetadataBooster.for_reranker()
        self.context_expander = context_expander or ContextExpander()
        self.document_repo = DocumentRepository()

    async def retrieve_for_comparison(
        self,
        query: str,
        document_ids: List[str],
        collection_id: Optional[str] = None,
        chunks_per_doc: int = 10,
        chunks_per_doc_map: Optional[Dict[str, int]] = None,  # Per-doc override (adaptive allocation)
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
        overall_start = time.monotonic()

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
            # Use per-doc allocation if provided (adaptive sizing by page count)
            doc_k = chunks_per_doc_map.get(doc_id, chunks_per_doc) if chunks_per_doc_map else chunks_per_doc
            chunks = await self._retrieve_single_doc(
                query=query,
                doc_id=doc_id,
                collection_id=collection_id,
                query_understanding=query_understanding,
                chunks_per_doc=doc_k,
                async_session=async_session
            )
            logger.debug(
                f"Retrieved {len(chunks)} chunks from document {doc_id}",
                extra={"doc_id": doc_id, "top_score": chunks[0].get('rerank_score') if chunks else 0}
            )
            return (doc_id, chunks)

        # Parallel retrieval - saves 1-2 seconds for multi-document comparisons
        retrieval_start = time.monotonic()
        results = await asyncio.gather(*[
            retrieve_doc(doc_id) for doc_id in document_ids
        ])
        retrieval_ms = round((time.monotonic() - retrieval_start) * 1000, 2)

        doc_chunks = dict(results)
        doc_signal = {}
        for doc_id, chunks in doc_chunks.items():
            top_score = max(
                (float(c.get("rerank_score", c.get("hybrid_score", 0.0)) or 0.0) for c in chunks),
                default=0.0
            )
            doc_signal[doc_id] = {
                "chunk_count": len(chunks),
                "top_score": top_score
            }

        logger.info(
            "Comparison retrieval stage complete",
            extra={
                "num_documents": num_docs,
                "retrieval_ms": retrieval_ms,
                "doc_signal": doc_signal
            }
        )

        # Step 2: Get document metadata
        documents = self._get_doc_metadata(document_ids)

        # Early-exit: skip expensive pairing/clustering if retrieval signal is weak
        min_top_score = max(0.0, float(getattr(settings, "comparison_pairing_min_top_score", 0.0)))
        min_chunks_per_doc = max(1, int(getattr(settings, "comparison_pairing_min_chunks_per_doc", 1)))
        low_signal_docs = [
            doc_id for doc_id, info in doc_signal.items()
            if info["chunk_count"] < min_chunks_per_doc
            or (min_top_score > 0.0 and info["top_score"] < min_top_score)
        ]
        if low_signal_docs:
            logger.info(
                "Comparison pairing early-exit: weak retrieval signal",
                extra={
                    "num_documents": num_docs,
                    "low_signal_docs": low_signal_docs,
                    "min_chunks_per_doc": min_chunks_per_doc,
                    "min_top_score": min_top_score,
                    "retrieval_ms": retrieval_ms,
                    "total_ms": round((time.monotonic() - overall_start) * 1000, 2)
                }
            )
            return ComparisonContext(
                documents=documents,
                paired_chunks=[],
                clustered_chunks=[],
                unpaired_chunks=doc_chunks,
                num_documents=num_docs
            )

        # Step 3: Pair or cluster chunks based on number of documents
        paired_chunks = []
        clustered_chunks = []
        pair_cluster_start = time.monotonic()

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
        pair_cluster_ms = round((time.monotonic() - pair_cluster_start) * 1000, 2)
        logger.info(
            "Comparison pairing/clustering stage complete",
            extra={
                "num_documents": num_docs,
                "paired_count": len(paired_chunks),
                "clustered_count": len(clustered_chunks),
                "pair_or_cluster_ms": pair_cluster_ms,
                "total_ms": round((time.monotonic() - overall_start) * 1000, 2)
            }
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
        retrieval_start = time.monotonic()
        candidates = self.hybrid_retriever.retrieve(
            query=query,
            collection_id=collection_id,
            document_ids=[doc_id],
            top_k=max(chunks_per_doc * 2, 20),  # Scale candidate pool with allocation
            query_understanding=query_understanding  # For HyDE enhancement
        )
        retrieval_ms = round((time.monotonic() - retrieval_start) * 1000, 2)

        if not candidates:
            logger.warning(
                f"No candidates found for document {doc_id}",
                extra={"doc_id": doc_id, "retrieval_ms": retrieval_ms}
            )
            return []

        # Step 2: Re-rank with cross-encoder (disabled for comparison by default).
        # Comparison pairs chunks by embedding cosine similarity after retrieval, so
        # the reranker adds ~76s of CPU inference with minimal benefit. Controlled by
        # rag_use_reranker_comparison (default False).
        rerank_min_candidates = max(1, settings.rag_reranker_min_candidates_comparison)
        if self.reranker and settings.rag_use_reranker_comparison and len(candidates) >= rerank_min_candidates:
            rerank_start = time.monotonic()
            loop = asyncio.get_running_loop()
            reranked = await loop.run_in_executor(
                None,
                functools.partial(
                    self.reranker.rerank,
                    query=query,
                    chunks=candidates,
                    query_understanding=query_understanding,
                    top_k=chunks_per_doc,
                )
            )
            rerank_ms = round((time.monotonic() - rerank_start) * 1000, 2)
            logger.debug(
                "Comparison doc rerank complete",
                extra={
                    "doc_id": doc_id,
                    "retrieval_ms": retrieval_ms,
                    "rerank_ms": rerank_ms,
                    "candidate_count": len(candidates),
                    "selected_count": len(reranked)
                }
            )
        else:
            reranked = candidates[:chunks_per_doc]
            logger.debug(
                "Skipping comparison doc rerank for tiny candidate pool",
                extra={
                    "doc_id": doc_id,
                    "retrieval_ms": retrieval_ms,
                    "candidate_count": len(candidates),
                    "min_candidates_for_rerank": rerank_min_candidates,
                    "selected_count": len(reranked)
                }
            )

        # Step 3: Expand context if async_session available.
        # Expansion runs BEFORE embedding cosine pairing so that expanded narrative chunks
        # pair correctly with narrative chunks from other documents (table ↔ narrative pairing
        # has lower raw cosine similarity than narrative ↔ narrative).
        if async_session and reranked:
            try:
                before_expansion = len(reranked)
                reranked = await self.context_expander.expand_with_batch(
                    chunks=reranked,
                    session=async_session,
                    max_expansion_per_chunk=2,
                    query_type=QueryType.COMPARISON
                )
                logger.debug(
                    f"Context expansion for {doc_id}: {len(reranked) - before_expansion} additional chunks"
                )
            except Exception as e:
                logger.warning(f"Context expansion failed for {doc_id}: {e}. Using original chunks.")
                # Continue with unexpanded chunks

        return reranked

    def _fetch_chunk_embeddings(self, chunk_ids: List[str]) -> Dict[str, List[float]]:
        """Fetch stored embedding vectors for a set of chunk IDs (single batch query)."""
        from app.db_models_chat import DocumentChunk as DC
        rows = (
            self.db.query(DC.id, DC.embedding)
            .filter(DC.id.in_(chunk_ids))
            .all()
        )
        return {str(row.id): row.embedding for row in rows if row.embedding is not None}

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
        Compute pairwise semantic similarities using stored embedding vectors.

        Cross-encoders are designed for (query, document) relevance scoring, not
        (document, document) similarity — using them for pairing was both semantically
        incorrect and ~2s per inference on CPU. Embedding cosine similarity is the
        right tool: vectors are already stored in the DB and comparison is O(microseconds).

        Falls back to Jaccard similarity if embeddings are missing (e.g. un-embedded chunks).

        Args:
            chunks_a: List of chunks from document A
            chunks_b: List of chunks from document B

        Returns:
            2D list of cosine similarity scores (0-1 range)
        """
        if not chunks_a or not chunks_b:
            logger.warning("No chunk pairs to score")
            return [[0.0] * len(chunks_b) for _ in chunks_a]

        # Collect all chunk IDs and batch-fetch their embedding vectors
        ids_a = [c["id"] for c in chunks_a]
        ids_b = [c["id"] for c in chunks_b]
        all_ids = list(set(ids_a + ids_b))

        try:
            emb_map = self._fetch_chunk_embeddings(all_ids)
            missing = [cid for cid in all_ids if cid not in emb_map]
            if missing:
                logger.warning(
                    f"Missing embeddings for {len(missing)} chunks, falling back to Jaccard",
                    extra={"missing_ids": missing[:5]}
                )
                return self._compute_jaccard_similarities(chunks_a, chunks_b)

            # Build (N_a, dim) and (N_b, dim) float32 matrices
            emb_a = np.array([emb_map[c["id"]] for c in chunks_a], dtype=np.float32)
            emb_b = np.array([emb_map[c["id"]] for c in chunks_b], dtype=np.float32)

            # L2-normalise rows, then dot product gives cosine similarity
            norm_a = np.linalg.norm(emb_a, axis=1, keepdims=True)
            norm_b = np.linalg.norm(emb_b, axis=1, keepdims=True)
            emb_a_norm = emb_a / np.maximum(norm_a, 1e-9)
            emb_b_norm = emb_b / np.maximum(norm_b, 1e-9)
            similarity_matrix = (emb_a_norm @ emb_b_norm.T).tolist()  # shape (N_a, N_b)

            n_pairs = len(chunks_a) * len(chunks_b)
            flat = [similarity_matrix[i][j] for i in range(len(chunks_a)) for j in range(len(chunks_b))]
            logger.debug(
                f"Computed {n_pairs} embedding cosine similarities for pairing",
                extra={
                    "avg_score": float(np.mean(flat)),
                    "max_score": float(np.max(flat))
                }
            )

            return similarity_matrix

        except Exception as e:
            logger.error(f"Embedding similarity computation failed: {e}", exc_info=True)
            logger.warning("Falling back to Jaccard similarity")
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
            if str(anchor_chunk["id"]) in used_chunks[anchor_doc_id]:
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
                    if str(other_chunk["id"]) in used_chunks[other_doc_id]:
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
                    used_chunks[doc_id].add(str(chunk["id"]))

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
        paired_a_ids = {str(p.chunk_a["id"]) for p in paired_chunks}
        paired_b_ids = {str(p.chunk_b["id"]) for p in paired_chunks}

        unpaired = {
            doc_ids[0]: [c for c in doc_chunks[doc_ids[0]] if str(c["id"]) not in paired_a_ids],
            doc_ids[1]: [c for c in doc_chunks[doc_ids[1]] if str(c["id"]) not in paired_b_ids]
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
            used_ids[doc_ids[0]] = {str(p.chunk_a["id"]) for p in paired_chunks}
            used_ids[doc_ids[1]] = {str(p.chunk_b["id"]) for p in paired_chunks}

        # From clusters (3+ doc comparison)
        for cluster in clustered_chunks:
            for doc_id, chunk in cluster.chunks.items():
                used_ids[doc_id].add(str(chunk["id"]))

        # Find unpaired
        unpaired = {}
        for doc_id, chunks in doc_chunks.items():
            unpaired[doc_id] = [c for c in chunks if str(c["id"]) not in used_ids.get(doc_id, set())]

        return unpaired
