"""Custom promptfoo provider: rag_retrieval stage.

Calls the production retrieval-selection pipeline and returns
the retrieved chunks as JSON. Used to eval retrieval quality independently
of generation — if retrieval degrades, this catches it before generation evals do.

Vars expected (written by export_eval_dataset.py --stage rag_retrieval):
    user_question  – raw user query
    document_ids   – JSON array of document UUIDs to search within
    collection_id  – collection scope (used if document_ids is empty)
    ablation_id    – optional A0..A6 retrieval study mode (defaults to A6)

Output: JSON string with `chunks` array and `chunk_count`.
Each chunk includes `page` for PDF-backed chunks when available, and spreadsheet
anchors (`chunk_id`, `sheet_name`, `row_start`, `row_end`) for sheet-based chunks.

Golden assertions use `expected_anchors` (page anchors for PDFs, chunk anchors for
spreadsheets) exported from the production io_log.

Reranker (~1.5GB CrossEncoder) is initialized once at module level as a
singleton, mirroring production behavior (loaded once at API/worker startup).
"""

import json
import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

# Module-level singleton — CrossEncoder loads ~1.5GB model on first call.
# Subsequent test cases in the same eval run reuse the loaded model.
_reranker = None


def _get_reranker():
    global _reranker
    if _reranker is None:
        from app.core.rag.reranker import Reranker
        _reranker = Reranker()
    return _reranker


def _get_page(chunk: dict) -> int | None:
    """Resolve physical page number, mirroring rag_service.py citation logic.

    Prefers bbox.page (Azure DI physical page) over chunk.page_number (anchor page).
    Returns None for spreadsheet chunks that do not have physical pages.
    """
    metadata = chunk.get("chunk_metadata") or {}
    bbox = metadata.get("bbox", {})
    if isinstance(bbox, dict) and bbox:
        return bbox.get("page") or chunk.get("page_number")
    return chunk.get("page_number")


def _deserialize_query_understanding(serialized_query_understanding: str):
    """Rebuild QueryUnderstanding from eval metadata when available."""
    if not serialized_query_understanding:
        return None

    try:
        payload = json.loads(serialized_query_understanding)
    except (TypeError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict) or not payload:
        return None

    from app.core.rag.query_understanding import QueryUnderstanding

    try:
        return QueryUnderstanding(**payload)
    except Exception:
        return None


def call_api(prompt, options, context):
    # Import all ORM models before any mapper initialization to avoid
    # SQLAlchemy "failed to locate a name" errors on relationship resolution.
    import app.db_models           # noqa: F401
    import app.db_models_users     # noqa: F401
    import app.db_models_documents # noqa: F401 — must be before db_models_chat (Document relationship)
    import app.db_models_chat      # noqa: F401
    import app.db_models_workflows # noqa: F401
    import app.db_models_templates # noqa: F401
    import app.db_models_io_logs   # noqa: F401

    from app.database import get_db
    from app.core.rag.hybrid_retriever import HybridRetriever
    from app.core.rag.query_understanding import is_narrow_explicit_fact_lookup
    from app.core.rag.rag_service import RAGService, RetrievalAblationConfig
    from app.core.rag.retrieval_query import RetrievalQuery
    from app.config import settings

    vars_ = context.get("vars", {})
    query = vars_.get("user_question", "")
    doc_ids = json.loads(vars_.get("document_ids", "[]"))
    collection_id = vars_.get("collection_id") or None
    serialized_query_understanding = vars_.get("query_understanding", "")
    ablation_id = vars_.get("ablation_id") or None

    if not query:
        return {"error": "Missing user_question in test vars"}
    if not doc_ids and not collection_id:
        return {"error": "Missing document_ids and collection_id in test vars"}

    db = next(get_db())
    try:
        ablation_config = RetrievalAblationConfig.from_id(ablation_id)
        query_understanding = _deserialize_query_understanding(serialized_query_understanding)
        if query_understanding is not None:
            rag_service = RAGService(db, reranker=_get_reranker())
            doc_info = rag_service.document_repo.get_doc_info_by_ids(doc_ids) if doc_ids else []
            doc_filenames = [d["filename"] for d in doc_info]
            retrieval_query = (
                query_understanding.rewritten_query
                if query_understanding.needs_history and query_understanding.rewritten_query
                else query_understanding.reformulated_query
            )
            selection_result = asyncio.run(
                rag_service.select_retrieval_context(
                    session_id="eval-rag-retrieval",
                    collection_id=collection_id,
                    user_message=query,
                    understanding=query_understanding,
                    retrieval_query=retrieval_query,
                    document_ids=doc_ids or None,
                    retrieval_candidates=settings.rag_retrieval_candidates,
                    final_top_k=settings.rag_final_top_k,
                    narrow_explicit_fact_lookup=is_narrow_explicit_fact_lookup(query_understanding),
                    doc_info=doc_info,
                    doc_filenames=doc_filenames,
                    ablation_config=ablation_config,
                )
            )
            final_chunks = selection_result["relevant_chunks"]
            candidate_trace = selection_result.get("candidate_trace", [])
        else:
            # Backward-compatible fallback for older fixtures that do not yet export
            # query_understanding. Research runs should regenerate fixtures so the
            # shared production path above is exercised.
            if ablation_config.ablation_id != "A6":
                return {"error": "ablation_id requires fixtures exported with query_understanding metadata"}
            retriever = HybridRetriever(db)
            reranker = _get_reranker()
            retrieval_query = RetrievalQuery.from_text(query)
            candidates = retriever.retrieve(
                rq=retrieval_query,
                collection_id=collection_id,
                document_ids=doc_ids or None,
                top_k=settings.rag_retrieval_candidates,
                query_understanding=None,
            )
            final_chunks = reranker.rerank(
                query=query,
                chunks=candidates,
                query_understanding=None,
                top_k=settings.rag_final_top_k,
            )
            candidate_trace = []

        output = {
            "chunks": [
                {
                    "id": c["id"],
                    "text": c.get("text", "")[:500],
                    "page": _get_page(c),
                    "page_number": c.get("page_number"),
                    "bbox": (c.get("chunk_metadata") or {}).get("bbox"),
                    "chunk_id": (c.get("chunk_metadata") or {}).get("chunk_id"),
                    "sheet_name": (c.get("chunk_metadata") or {}).get("sheet_name"),
                    "row_start": (c.get("chunk_metadata") or {}).get("row_start"),
                    "row_end": (c.get("chunk_metadata") or {}).get("row_end"),
                    "section_type": c.get("section_type"),
                    "document_id": c.get("document_id"),
                    "hybrid_score": round(c.get("hybrid_score") or 0, 4),
                    "rerank_score": round(c["rerank_score"], 4) if c.get("rerank_score") is not None else None,
                }
                for c in final_chunks
            ],
            "chunk_count": len(final_chunks),
            "candidate_trace": candidate_trace,
        }

        return {
            "output": json.dumps(output),
            "tokenUsage": {"total": 0, "prompt": 0, "completion": 0},
            "cost": None,
        }
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        db.close()
