"""Unit tests for Reranker.filter_noise() — ambient mode noise filtering."""
import sys
import pytest
from unittest.mock import MagicMock, patch
import numpy as np

# Stub heavy ML dependencies not installed in the unit-test environment
for _mod in ["sentence_transformers", "tiktoken"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


def _make_chunk(text: str, doc_id: str = "doc1") -> dict:
    return {"text": text, "document_id": doc_id, "hybrid_score": 0.5}


def _make_reranker_with_scores(scores: list):
    """Return a Reranker whose model.predict returns the given scores."""
    from app.core.rag.reranker import Reranker
    mock_model = MagicMock()
    mock_model.predict.return_value = np.array(scores)
    r = Reranker.__new__(Reranker)
    r.model = mock_model
    r.batch_size = 8
    r.apply_metadata_boost = False
    r.metadata_booster = MagicMock()
    return r


class TestFilterNoise:
    def test_drops_chunks_below_threshold(self):
        chunks = [
            _make_chunk("cap rate is 8.11%", "doc1"),
            _make_chunk("TABLE OF CONTENTS", "doc2"),  # noise
            _make_chunk("NOI is $500k", "doc3"),
        ]
        reranker = _make_reranker_with_scores([0.8, 0.02, 0.6])
        result = reranker.filter_noise(query="cap rate", chunks=chunks, threshold=0.05)
        assert len(result) == 2
        assert result[0]["text"] == "cap rate is 8.11%"
        assert result[1]["text"] == "NOI is $500k"

    def test_all_pass_when_above_threshold(self):
        chunks = [_make_chunk(f"relevant {i}") for i in range(3)]
        reranker = _make_reranker_with_scores([0.9, 0.7, 0.5])
        result = reranker.filter_noise(query="revenue", chunks=chunks, threshold=0.05)
        assert len(result) == 3

    def test_empty_input_returns_empty(self):
        reranker = _make_reranker_with_scores([])
        result = reranker.filter_noise(query="anything", chunks=[], threshold=0.05)
        assert result == []

    def test_rerank_score_set_on_passing_chunks(self):
        chunks = [_make_chunk("good content", "doc1")]
        reranker = _make_reranker_with_scores([0.75])
        result = reranker.filter_noise(query="good", chunks=chunks, threshold=0.05)
        assert result[0]["rerank_score"] == pytest.approx(0.75)

    def test_no_top_k_cut_preserves_all_passing_chunks(self):
        """filter_noise must NOT apply a top-k cut — all passing chunks survive."""
        chunks = [_make_chunk(f"chunk {i}", f"doc{i}") for i in range(15)]
        scores = [0.1 + i * 0.05 for i in range(15)]  # all >= 0.05, highest = 0.8
        reranker = _make_reranker_with_scores(scores)
        result = reranker.filter_noise(query="anything", chunks=chunks, threshold=0.05)
        assert len(result) == 15  # all pass, no top-k cut
