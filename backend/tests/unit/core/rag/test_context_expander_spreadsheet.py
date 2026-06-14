import asyncio

from app.config import settings
from app.core.rag.context_expander import ContextExpander
from app.core.rag.query_understanding import QueryType


def test_expand_with_batch_adds_spreadsheet_neighbors():
    expander = ContextExpander()

    async def fake_batch_fetch(chunk_ids, _session):
        return {
            chunk_id: {
                "id": chunk_id,
                "document_id": "doc-1",
                "text": f"chunk {chunk_id}",
                "page_number": None,
                "is_tabular": True,
                "chunk_metadata": {"source_kind": "spreadsheet"},
                "metadata": {"source_kind": "spreadsheet"},
                "token_count": 10,
            }
            for chunk_id in chunk_ids
        }

    expander._batch_fetch_chunks = fake_batch_fetch

    base_chunk = {
        "id": "spreadsheet_1_2",
        "document_id": "doc-1",
        "text": "target row block",
        "page_number": None,
        "is_tabular": True,
        "rerank_score": 1.0,
        "chunk_metadata": {
            "source_kind": "spreadsheet",
            "spreadsheet_prev_chunk_id": "spreadsheet_1_1",
            "spreadsheet_next_chunk_id": "spreadsheet_1_3",
        },
        "metadata": {
            "source_kind": "spreadsheet",
            "spreadsheet_prev_chunk_id": "spreadsheet_1_1",
            "spreadsheet_next_chunk_id": "spreadsheet_1_3",
        },
    }

    expanded = asyncio.run(
        expander.expand_with_batch(
            chunks=[base_chunk],
            session=None,
            query_type=QueryType.DATA_EXTRACTION,
        )
    )

    assert [chunk["id"] for chunk in expanded] == [
        "spreadsheet_1_2",
        "spreadsheet_1_1",
        "spreadsheet_1_3",
    ]
    assert expanded[1]["_expansion_reason"] == "spreadsheet_neighbor"
    assert expanded[2]["_expansion_reason"] == "spreadsheet_neighbor"
    assert expanded[1]["rerank_score"] == settings.rag_expansion_score_spreadsheet_neighbor
    assert expanded[2]["rerank_score"] == settings.rag_expansion_score_spreadsheet_neighbor