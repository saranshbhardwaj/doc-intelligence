"""Custom promptfoo provider: rag_retrieval stage.

Calls the actual hybrid retrieval + reranking pipeline and returns
the retrieved chunks as JSON. Used to eval retrieval quality independently
of generation — if retrieval degrades, this catches it before generation evals do.

Vars expected (written by export_eval_dataset.py --stage rag_retrieval):
    user_question  – raw user query
    document_ids   – JSON array of document UUIDs to search within
    collection_id  – collection scope (used if document_ids is empty)

Output: JSON string with `chunks` array and `chunk_count`.
Each chunk includes `page` (resolved: bbox.page || page_number), `document_id`,
scores, and a text snippet.

Golden assertions use `expected_pages` (list of {document_id, page} pairs)
exported from the production io_log. Page-based matching is stable across
re-indexing — chunk IDs change but pages don't.

Reranker (~1.5GB CrossEncoder) is initialized once at module level as a
singleton, mirroring production behavior (loaded once at API/worker startup).
"""

import json
import os
import sys

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


def _get_page(chunk: dict) -> int:
    """Resolve physical page number, mirroring rag_service.py citation logic (line 938-940).

    Prefers bbox.page (Azure DI physical page) over chunk.page_number (anchor page).
    """
    metadata = chunk.get("chunk_metadata") or {}
    bbox = metadata.get("bbox", {})
    if isinstance(bbox, dict) and bbox:
        return bbox.get("page") or chunk.get("page_number", 1)
    return chunk.get("page_number", 1)


def call_api(prompt, options, context):
    from app.database import get_db
    from app.core.rag.hybrid_retriever import HybridRetriever
    from app.core.embeddings import get_embedding_provider
    from app.config import settings

    vars_ = context.get("vars", {})
    query = vars_.get("user_question", "")
    doc_ids = json.loads(vars_.get("document_ids", "[]"))
    collection_id = vars_.get("collection_id") or None

    if not query:
        return {"error": "Missing user_question in test vars"}
    if not doc_ids and not collection_id:
        return {"error": "Missing document_ids and collection_id in test vars"}

    db = next(get_db())
    try:
        embedding_provider = get_embedding_provider()
        retriever = HybridRetriever(db, embedding_provider)
        reranker = _get_reranker()

        # Both retrieve() and rerank() are sync
        candidates = retriever.retrieve(
            query=query,
            collection_id=collection_id,
            document_ids=doc_ids or None,
            top_k=settings.rag_retrieval_candidates,
        )

        reranked = reranker.rerank(
            query=query,
            chunks=candidates,
            top_k=settings.rag_final_top_k,
        )

        output = {
            "chunks": [
                {
                    "id": c["id"],
                    "text": c.get("text", "")[:500],
                    "page": _get_page(c),
                    "page_number": c.get("page_number"),
                    "bbox": (c.get("chunk_metadata") or {}).get("bbox"),
                    "section_type": c.get("section_type"),
                    "document_id": c.get("document_id"),
                    "hybrid_score": round(c.get("hybrid_score") or 0, 4),
                    "rerank_score": round(c["rerank_score"], 4) if c.get("rerank_score") is not None else None,
                }
                for c in reranked
            ],
            "chunk_count": len(reranked),
        }

        return {
            "output": json.dumps(output),
            "tokenUsage": {"total": 0, "prompt": 0, "completion": 0},
            "cost": 0,
        }
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        db.close()
