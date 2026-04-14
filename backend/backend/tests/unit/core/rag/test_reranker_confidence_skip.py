"""Tests for reranker skip when QU confidence is below threshold."""
import pytest
from unittest.mock import MagicMock


def _make_settings(**overrides):
    s = MagicMock()
    s.rag_use_reranker_chat = True
    s.rag_reranker_min_candidates_chat = 6
    s.rag_reranker_skip_confidence_threshold = 0.4
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _should_rerank(confidence, num_candidates, is_ambient=False, has_reranker=True, settings_overrides=None):
    """Replicate the rag_service.py should_rerank logic for isolated testing."""
    settings = _make_settings(**(settings_overrides or {}))
    rerank_min_candidates = max(1, settings.rag_reranker_min_candidates_chat)
    return (
        not is_ambient
        and has_reranker
        and settings.rag_use_reranker_chat
        and num_candidates >= rerank_min_candidates
        and confidence >= settings.rag_reranker_skip_confidence_threshold
    )


class TestShouldRerank:
    def test_high_confidence_reranks(self):
        assert _should_rerank(confidence=0.8, num_candidates=10) is True

    def test_low_confidence_skips(self):
        assert _should_rerank(confidence=0.3, num_candidates=10) is False

    def test_exactly_at_threshold_reranks(self):
        assert _should_rerank(confidence=0.4, num_candidates=10) is True

    def test_just_below_threshold_skips(self):
        assert _should_rerank(confidence=0.39, num_candidates=10) is False

    def test_ambient_always_skips_regardless_of_confidence(self):
        assert _should_rerank(confidence=0.9, num_candidates=10, is_ambient=True) is False

    def test_too_few_candidates_skips(self):
        assert _should_rerank(confidence=0.9, num_candidates=3) is False
