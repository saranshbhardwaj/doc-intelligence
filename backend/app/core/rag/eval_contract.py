"""Shared helpers for versioned RAG eval logging."""

from __future__ import annotations

from typing import Any, Dict, Optional


RAG_EVAL_CONTRACT_VERSION = "2026-04-01"


def serialize_query_understanding(query_understanding) -> Optional[Dict[str, Any]]:
    """Convert QueryUnderstanding into JSON-safe metadata."""
    if not query_understanding:
        return None

    return {
        "query_type": query_understanding.query_type.value,
        "reformulated_query": query_understanding.reformulated_query,
        "hypothetical_response": query_understanding.hypothetical_response,
        "comparison_aspects": list(getattr(query_understanding, "comparison_aspects", []) or []),
        "data_fields": list(getattr(query_understanding, "data_fields", []) or []),
        "table_boost": getattr(query_understanding, "table_boost", None),
        "narrative_boost": getattr(query_understanding, "narrative_boost", None),
        "needs_history": getattr(query_understanding, "needs_history", False),
        "rewritten_query": getattr(query_understanding, "rewritten_query", None),
        "confidence": getattr(query_understanding, "confidence", None),
        "entities": [
            {
                "name": entity.name,
                "entity_type": entity.entity_type,
                "confidence": entity.confidence,
            }
            for entity in getattr(query_understanding, "entities", [])
        ],
    }


def serialize_chunk_for_eval(chunk: Dict[str, Any]) -> Dict[str, Any]:
    """Build page-resolvable evidence metadata for exported evals."""
    metadata = chunk.get("chunk_metadata") or {}
    bbox = metadata.get("bbox") if isinstance(metadata.get("bbox"), dict) else None

    return {
        "id": chunk.get("id"),
        "document_id": chunk.get("document_id"),
        "page_number": chunk.get("page_number"),
        "bbox_page": bbox.get("page") if bbox else None,
        "bbox": bbox,
        "page_range": metadata.get("page_range"),
        "section_type": chunk.get("section_type"),
        "semantic_score": round(chunk.get("semantic_score") or 0, 4),
        "keyword_score": round(chunk.get("keyword_score") or 0, 4),
        "hybrid_score": round(chunk.get("hybrid_score") or 0, 4),
        "rerank_score": round(chunk["rerank_score"], 4) if chunk.get("rerank_score") is not None else None,
        "similarity": round(chunk["similarity"], 4) if chunk.get("similarity") is not None else None,
        "topic": chunk.get("topic"),
    }