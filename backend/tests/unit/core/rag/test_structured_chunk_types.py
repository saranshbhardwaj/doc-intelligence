import sys
from unittest.mock import MagicMock

import pytest

for _mod in ("sentence_transformers", "tiktoken"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from app.core.rag.metadata_booster import MetadataBooster
from app.core.rag.reranker import Reranker


def _make_chunk(section_type: str) -> dict:
    return {
        "id": f"{section_type}-1",
        "section_type": section_type,
        "chunk_metadata": {},
        "hybrid_score": 1.0,
        "text": "Lot Size Apx. 2.70 Acres One Parcel with additional context for scoring.",
        "page_number": 3,
        "section_heading": None,
        "is_tabular": False,
    }


def test_table_block_gets_same_metadata_boost_as_table_for_data_queries():
    booster = MetadataBooster()
    table_chunk = _make_chunk("table")
    table_block_chunk = _make_chunk("table_block")

    booster.apply_boost(
        [table_chunk, table_block_chunk],
        {"query_type": "data_extraction"},
    )

    assert table_block_chunk["hybrid_score"] == pytest.approx(table_chunk["hybrid_score"])
    assert table_block_chunk["hybrid_score"] > 1.0


def test_table_block_is_treated_as_structured_for_reranker_signal_and_bypass():
    table_block_chunk = _make_chunk("table_block")

    assert Reranker._is_structured_chunk(table_block_chunk) is True
    assert Reranker._compute_structured_evidence_score(
        query="what is the lot size",
        chunk=table_block_chunk,
    ) > 0.0