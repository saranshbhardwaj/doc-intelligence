"""Shared helpers for versioned RAG eval logging."""

from __future__ import annotations

from typing import Any, Dict, Optional


RAG_EVAL_CONTRACT_VERSION = "2026-04-03"


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
        "data_field_synonyms": list(getattr(query_understanding, "data_field_synonyms", []) or []),
        "scope_mode": getattr(getattr(query_understanding, "scope_mode", None), "value", getattr(query_understanding, "scope_mode", None)),
        "target_property_names": list(getattr(query_understanding, "target_property_names", []) or []),
        "target_geo_city": getattr(query_understanding, "target_geo_city", None),
        "target_geo_state": getattr(query_understanding, "target_geo_state", None),
        "scope_confidence": getattr(query_understanding, "scope_confidence", None),
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
        "chunk_id": metadata.get("chunk_id"),
        "sheet_name": metadata.get("sheet_name"),
        "row_start": metadata.get("row_start"),
        "row_end": metadata.get("row_end"),
        "page_number": chunk.get("page_number"),
        "bbox_page": bbox.get("page") if bbox else None,
        "bbox": bbox,
        "page_range": metadata.get("page_range"),
        "section_type": chunk.get("section_type"),
        "semantic_score": round(chunk.get("semantic_score") or 0, 4),
        "keyword_score": round(chunk.get("keyword_score") or 0, 4),
        "hybrid_score": round(chunk.get("hybrid_score") or 0, 4),
        "hybrid_score_scope_adjusted": round(chunk.get("hybrid_score_scope_adjusted") or 0, 4),
        "rerank_score": round(chunk["rerank_score"], 4) if chunk.get("rerank_score") is not None else None,
        "structured_evidence_score": round(chunk.get("structured_evidence_score") or 0, 4),
        "rerank_score_scope_adjusted": round(chunk.get("rerank_score_scope_adjusted") or 0, 4),
        "similarity": round(chunk["similarity"], 4) if chunk.get("similarity") is not None else None,
        "entity_doc_match_score": round(chunk.get("entity_doc_match_score") or 0, 4),
        "property_name_exact_match": bool(chunk.get("property_name_exact_match", False)),
        "geo_match": bool(chunk.get("geo_match", False)),
        "requested_scope_match": bool(chunk.get("requested_scope_match", False)),
        "canonical_document_key": chunk.get("canonical_document_key"),
        "topic": chunk.get("topic"),
    }