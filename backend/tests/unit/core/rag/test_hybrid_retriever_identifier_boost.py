"""Unit tests for identifier-aware keyword boosts in hybrid retrieval."""

from app.core.rag.hybrid_retriever import _extract_identifier_tokens
from app.core.rag.retrieval_query import RetrievalQuery


def test_extract_identifier_tokens_keeps_numeric_row_ids():
    rq = RetrievalQuery(
        semantic_text="lease term and balance due for unit 105",
        lexical_required=[],
        lexical_optional=["lease term", "balance due", "unit 105", "suite B12"],
    )

    assert _extract_identifier_tokens(rq) == ["105", "b12"]


def test_extract_identifier_tokens_deduplicates_repeated_ids():
    rq = RetrievalQuery(
        semantic_text="unit 105 balance due",
        lexical_required=["unit 105"],
        lexical_optional=["105", "balance due", "unit 105"],
    )

    assert _extract_identifier_tokens(rq) == ["105"]


def test_extract_identifier_tokens_skips_plain_years():
    rq = RetrievalQuery(
        semantic_text="2024 property tax for point blank portfolio",
        lexical_required=[],
        lexical_optional=["2024 property tax", "property taxes", "2024", "tax year 2025", "suite B12"],
    )

    assert _extract_identifier_tokens(rq) == ["b12"]