import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.export_eval_dataset import STRUCTURAL_ASSERTIONS, _build_golden_assertions


def test_rag_generation_citation_assertion_allows_grouped_source_citations():
    citation_assertion = next(
        assertion
        for assertion in STRUCTURAL_ASSERTIONS["rag_generation"]
        if assertion.get("metric") == "rag/has_citations"
    )

    assert "(?:,\\s*S\\d+:p\\d+)*" in citation_assertion["value"]


def test_build_golden_assertions_normalizes_numeric_value_matching_and_uses_source_citations():
    annotations = {
        "for unit 1-01 at legacy ranch apartments, what are the market rent and actual rent?": {
            "question_id": "legacyranch-unit101-market-actual",
            "question": "For unit 1-01 at Legacy Ranch Apartments, what are the market rent and actual rent?",
            "expected_answer_substrings": ["1583", "1458"],
        }
    }

    assertions = _build_golden_assertions(
        "rag_generation",
        output_raw="{}",
        annotations=annotations,
        user_question="For unit 1-01 at Legacy Ranch Apartments, what are the market rent and actual rent?",
    )

    expected_value_assertion = next(
        assertion for assertion in assertions if assertion.get("metric") == "golden/expected_value_any"
    )
    rubric_assertion = next(assertion for assertion in assertions if assertion.get("metric") == "golden/rag_quality")

    assert "normalizeValue" in expected_value_assertion["value"]
    assert "replace(/[,$]/g, '')" in expected_value_assertion["value"]
    assert "[Sn:pN]" in rubric_assertion["value"]


def test_rag_retrieval_assertion_prefers_benchmark_gold_evidence():
    assertions = _build_golden_assertions(
        "rag_retrieval",
        output_raw="{}",
        annotations=None,
        user_question="What was the total value in 2024 for 5880 Lochmoor Dr?",
    )

    retrieval_assertion = next(
        assertion for assertion in assertions if assertion.get("metric") == "retrieval/page_recall_80"
    )

    assert "benchmark_gold_evidence" in retrieval_assertion["value"]
    assert "benchmarkGoldUsable" in retrieval_assertion["value"]
    assert "candidateDocumentIds" in retrieval_assertion["value"]
    assert "useSpreadsheetSheetFallback" in retrieval_assertion["value"]
    assert "':sheet:'" in retrieval_assertion["value"]