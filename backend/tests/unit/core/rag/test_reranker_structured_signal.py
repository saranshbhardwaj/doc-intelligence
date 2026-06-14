"""Unit tests for structured evidence scoring in the reranker."""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.core.rag.query_understanding import QueryType


for _mod in ["sentence_transformers", "tiktoken"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


def _make_query_understanding(*data_fields: str):
    return SimpleNamespace(query_type=QueryType.DATA_EXTRACTION, data_fields=list(data_fields))


class TestStructuredEvidenceScore:
    def test_non_structured_chunk_gets_no_bonus(self):
        from app.core.rag.reranker import Reranker

        score = Reranker._compute_structured_evidence_score(
            query="what is the 2024 property tax",
            chunk={"text": "Narrative discussion of the asset", "section_type": "narrative"},
            query_understanding=_make_query_understanding("property tax"),
        )

        assert score == 0.0

    def test_structured_chunk_with_matching_field_and_year_scores_higher(self):
        from app.core.rag.reranker import Reranker

        score = Reranker._compute_structured_evidence_score(
            query="what is the 2024 property tax",
            chunk={
                "text": "Property Taxes 2024 $ 15,275",
                "section_type": "table",
                "section_heading": "Operating Expenses",
                "is_phrase_match": True,
            },
            query_understanding=_make_query_understanding("property tax"),
        )

        assert score > 0.7

    def test_matching_heading_contributes_even_without_phrase_match(self):
        from app.core.rag.reranker import Reranker

        score = Reranker._compute_structured_evidence_score(
            query="what is the asking price",
            chunk={
                "text": "$2,500,000",
                "section_type": "key_value_pairs",
                "section_heading": "Asking Price",
            },
            query_understanding=_make_query_understanding("asking price"),
        )

        assert score >= 0.45

    def test_exact_unit_row_scores_higher_than_resident_number_noise(self):
        from app.core.rag.reranker import Reranker

        query = "For unit 105 in Illinois_Institutional_Rent_Roll, what is the lease term and balance due?"
        query_understanding = _make_query_understanding("lease term", "balance due")

        exact_unit_chunk = {
            "text": (
                "Unit | Bldg | Lease Term (Mos) | Balance Due\n"
                "105 | 1 | 24 | 240\n"
            ),
            "section_type": "table",
            "section_heading": "Rent Roll",
        }
        resident_noise_chunk = {
            "text": (
                "Unit | Bldg | Lease Term (Mos) | Balance Due\n"
                "605 | 6 | 24 | 0 | Resident 105\n"
            ),
            "section_type": "table",
            "section_heading": "Rent Roll",
        }

        exact_score = Reranker._compute_structured_evidence_score(
            query=query,
            chunk=exact_unit_chunk,
            query_understanding=query_understanding,
        )
        noise_score = Reranker._compute_structured_evidence_score(
            query=query,
            chunk=resident_noise_chunk,
            query_understanding=query_understanding,
        )

        assert exact_score > noise_score