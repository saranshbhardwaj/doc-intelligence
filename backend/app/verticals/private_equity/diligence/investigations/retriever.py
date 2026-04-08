"""Evidence retrieval utilities for diligence investigations."""
from __future__ import annotations

from typing import Dict, List, Sequence

from sqlalchemy.orm import Session

from app.core.rag.hybrid_retriever import HybridRetriever
from app.utils.logging import logger


def route_candidate_documents(
    *,
    room_documents: Sequence[dict],
    doc_info_by_id: Dict[str, dict],
    doc_type_hints: Sequence[str],
    filename_hints: Sequence[str],
) -> List[str]:
    """Select candidate document IDs for investigation retrieval.

    Routing strategy (avoids false negatives from misclassification):
      1. Primary tier: documents matching type hints or filename hints.
      2. Safety tier: documents classified as "other", unclassified, or
         flagged ``needs_review`` — these may be misclassified contracts.

    Both tiers are merged (primary first for retriever ranking bias).
    A document is never silently excluded unless it has a confident
    non-matching classification AND a non-matching filename.
    """
    primary: List[str] = []
    safety: List[str] = []

    filename_tokens = [t.lower().strip() for t in filename_hints if t]
    type_hints = set(doc_type_hints or [])

    for row in room_documents:
        document_id = row.get("document_id")
        if not document_id:
            continue

        metadata = row.get("metadata_json") if isinstance(row.get("metadata_json"), dict) else {}
        classification = metadata.get("document_classification")
        classification = classification if isinstance(classification, dict) else {}
        doc_type = classification.get("document_type")
        needs_review = classification.get("needs_review", False)
        has_classification = bool(doc_type)

        filename = (doc_info_by_id.get(document_id, {}) or {}).get("filename", "")
        filename_l = str(filename).lower()
        filename_match = any(token in filename_l for token in filename_tokens)
        type_match = bool(doc_type and doc_type in type_hints)

        if type_match or filename_match:
            # Confident match — primary tier.
            primary.append(document_id)
        elif not has_classification or doc_type == "other" or needs_review:
            # Unclassified, "other", or flagged for review — safety tier.
            # These could be misclassified contracts; include to avoid
            # false negatives.
            safety.append(document_id)

    # Primary first (better ranking signal), then safety net.
    merged = primary + safety
    return list(dict.fromkeys(merged))


def search_evidence_chunks(
    *,
    db: Session,
    queries: Sequence[str],
    document_ids: Sequence[str],
    top_k_per_query: int = 20,
    max_results: int = 40,
) -> List[dict]:
    """Retrieve evidence chunks across one or more queries."""
    if not document_ids or not queries:
        return []

    retriever = HybridRetriever(db)
    by_chunk_id: Dict[str, dict] = {}

    for query in queries:
        try:
            results = retriever.retrieve(
                query=query,
                collection_id=None,
                document_ids=list(document_ids),
                top_k=top_k_per_query,
            )
        except Exception as exc:
            logger.warning(
                "Investigation retrieval query failed",
                extra={"query": query[:80], "error": str(exc)},
            )
            continue

        for row in results:
            chunk_id = str(row.get("id") or "")
            if not chunk_id:
                continue
            prev = by_chunk_id.get(chunk_id)
            if not prev or float(row.get("hybrid_score", 0.0)) > float(prev.get("hybrid_score", 0.0)):
                by_chunk_id[chunk_id] = row

    ranked = sorted(by_chunk_id.values(), key=lambda r: float(r.get("hybrid_score", 0.0)), reverse=True)
    return ranked[:max_results]


def to_evidence_search_rows(chunks: Sequence[dict], top_k: int) -> List[dict]:
    out: List[dict] = []
    for row in chunks[:top_k]:
        text = str(row.get("text") or "")
        quote = text.strip().replace("\n", " ")
        if len(quote) > 420:
            quote = quote[:417] + "..."
        out.append(
            {
                "chunk_id": str(row.get("id")),
                "document_id": str(row.get("document_id")),
                "page_number": row.get("page_number"),
                "page_range": row.get("page_range") or [],
                "quote": quote,
                "hybrid_score": float(row.get("hybrid_score", 0.0)),
                "bbox": row.get("bbox") if isinstance(row.get("bbox"), dict) else None,
                "metadata": row.get("chunk_metadata") if isinstance(row.get("chunk_metadata"), dict) else {},
            }
        )
    return out

