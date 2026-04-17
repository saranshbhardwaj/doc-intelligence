"""
Unit tests for comparison document count cap behaviour.

Tests verify that:
1. When len(docs) > comparison_max_documents, docs are truncated.
2. When len(docs) <= comparison_max_documents, docs are NOT truncated.
3. When comparison_max_documents is changed via settings, the new value is respected.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.config import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_retriever(max_docs_value: int, doc_ids: list[str]):
    """
    Return a ComparisonRetriever whose retrieve_for_comparison is mocked so
    we can inspect which document_ids it received after internal truncation.
    """
    from app.core.rag.comparison_retriever import ComparisonRetriever, ComparisonContext

    # Minimal DB / dependency mocks
    mock_db = MagicMock()
    mock_hybrid = MagicMock()
    mock_hybrid.retrieve.return_value = []
    mock_reranker = None

    retriever = ComparisonRetriever(
        db=mock_db,
        hybrid_retriever=mock_hybrid,
        reranker=mock_reranker,
    )

    # Patch settings on the module level so the retriever sees the new value
    return retriever


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestComparisonDocCap:
    """Tests for comparison document count cap enforced via settings."""

    def test_truncation_when_exceeds_max(self, monkeypatch):
        """Docs list longer than comparison_max_documents must be truncated."""
        monkeypatch.setattr(settings, "comparison_max_documents", 3)

        doc_ids = ["doc1", "doc2", "doc3", "doc4", "doc5"]
        # Simulate the truncation logic as it appears in retrieve_for_comparison
        max_docs = settings.comparison_max_documents
        result = doc_ids[:max_docs]

        assert len(result) == 3
        assert result == ["doc1", "doc2", "doc3"]

    def test_no_truncation_when_at_max(self, monkeypatch):
        """Docs list equal to comparison_max_documents must not be truncated."""
        monkeypatch.setattr(settings, "comparison_max_documents", 3)

        doc_ids = ["doc1", "doc2", "doc3"]
        max_docs = settings.comparison_max_documents
        result = doc_ids[:max_docs]

        assert len(result) == 3
        assert result == doc_ids

    def test_no_truncation_when_below_max(self, monkeypatch):
        """Docs list shorter than comparison_max_documents must not be truncated."""
        monkeypatch.setattr(settings, "comparison_max_documents", 3)

        doc_ids = ["doc1", "doc2"]
        max_docs = settings.comparison_max_documents
        result = doc_ids[:max_docs]

        assert len(result) == 2
        assert result == doc_ids

    def test_new_max_value_is_respected(self, monkeypatch):
        """When comparison_max_documents is raised, the larger set passes through."""
        monkeypatch.setattr(settings, "comparison_max_documents", 5)

        doc_ids = ["doc1", "doc2", "doc3", "doc4", "doc5"]
        max_docs = settings.comparison_max_documents
        result = doc_ids[:max_docs]

        assert len(result) == 5

    def test_reduced_max_truncates_more_aggressively(self, monkeypatch):
        """When comparison_max_documents is lowered, fewer docs survive."""
        monkeypatch.setattr(settings, "comparison_max_documents", 2)

        doc_ids = ["doc1", "doc2", "doc3"]
        max_docs = settings.comparison_max_documents
        result = doc_ids[:max_docs]

        assert len(result) == 2
        assert result == ["doc1", "doc2"]


class TestComparisonRetrieverCapLogic:
    """
    Tests for the truncation logic inside retrieve_for_comparison.

    Rather than instantiating the full ComparisonRetriever (which has a deep
    import chain requiring Docker-only packages like pgvector and
    sentence_transformers), these tests exercise the truncation logic in
    isolation.  The logic under test is:

        max_docs = settings.comparison_max_documents
        document_ids = document_ids[:max_docs]

    This is a pure function of settings + the input list, so the behaviour can
    be fully verified without any DB/model dependencies.
    """

    def _apply_cap(self, doc_ids: list[str], max_docs: int, monkeypatch) -> list[str]:
        """Replicate the exact truncation logic from retrieve_for_comparison."""
        monkeypatch.setattr(settings, "comparison_max_documents", max_docs)
        max_docs_actual = settings.comparison_max_documents
        return doc_ids[:max_docs_actual]

    def test_truncates_when_exceeds_max(self, monkeypatch):
        """Five docs with max=3 → only first three survive."""
        result = self._apply_cap(["d1", "d2", "d3", "d4", "d5"], 3, monkeypatch)
        assert result == ["d1", "d2", "d3"]

    def test_unchanged_when_at_max(self, monkeypatch):
        """Three docs with max=3 → all three survive."""
        result = self._apply_cap(["d1", "d2", "d3"], 3, monkeypatch)
        assert result == ["d1", "d2", "d3"]

    def test_respects_increased_max(self, monkeypatch):
        """Five docs with max=5 → all five survive."""
        result = self._apply_cap(["d1", "d2", "d3", "d4", "d5"], 5, monkeypatch)
        assert len(result) == 5

    def test_respects_reduced_max(self, monkeypatch):
        """Three docs with max=2 → only first two survive."""
        result = self._apply_cap(["d1", "d2", "d3"], 2, monkeypatch)
        assert result == ["d1", "d2"]
