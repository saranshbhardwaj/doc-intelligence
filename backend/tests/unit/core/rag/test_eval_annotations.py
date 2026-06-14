"""Unit tests for structured benchmark annotation helpers."""

import json

from app.core.rag.eval_annotations import (
    build_promptfoo_annotation_vars,
    get_expected_answer_substrings,
    load_benchmark_annotations,
    lookup_benchmark_annotation,
    normalize_question_key,
)


def test_load_benchmark_annotations_supports_legacy_map():
    annotations = load_benchmark_annotations(
        {
            "_comment": "legacy format",
            "What is the 2024 property tax for Point Blank Portfolio?": "$15,275",
        }
    )

    annotation = lookup_benchmark_annotation(
        annotations,
        "what is the 2024 property tax for point blank portfolio?",
    )

    assert annotation is not None
    assert get_expected_answer_substrings(annotation) == ["$15,275"]
    assert annotation["question"] == "What is the 2024 property tax for Point Blank Portfolio?"


def test_load_benchmark_annotations_supports_structured_questions():
    annotations = load_benchmark_annotations(
        {
            "schema_version": "2026-05-27",
            "questions": [
                {
                    "question_id": "pb-tax-2024",
                    "question": "What is the 2024 property tax for Point Blank Portfolio?",
                    "evaluation_slice": "table_factual",
                    "scope_type": "entity_scoped",
                    "table_heavy": True,
                    "target_entities": ["Point Blank Portfolio"],
                    "target_document_ids": ["doc-1"],
                    "expected_answer_substrings": ["15,275", "$15,275"],
                    "gold_evidence": [
                        {
                            "document_id": "doc-1",
                            "page": 18,
                            "evidence_type": "table",
                            "table_label": "operating_expenses",
                            "field_label": "property_taxes_2024",
                            "relevance": 3,
                        }
                    ],
                    "numeric_targets": [
                        {
                            "field_name": "property_taxes_2024",
                            "canonical_value": 15275.0,
                            "unit": "usd",
                            "accepted_surface_forms": ["$15,275", "15,275"],
                        }
                    ],
                }
            ],
        }
    )

    annotation = lookup_benchmark_annotation(
        annotations,
        "What is the 2024 property tax for Point Blank Portfolio?",
    )

    assert annotation is not None
    assert annotation["question_id"] == "pb-tax-2024"
    assert annotation["evaluation_slice"] == "table_factual"
    assert annotation["table_labels"] == ["operating_expenses"]
    assert annotation["numeric_targets"][0]["canonical_value"] == 15275.0


def test_build_promptfoo_annotation_vars_serializes_benchmark_fields():
    annotation = {
        "question_id": "tulsa-lot-size-income",
        "evaluation_slice": "table_factual",
        "scope_type": "entity_scoped",
        "table_heavy": True,
        "target_entities": ["Tulsa Storage Units & Parking"],
        "target_document_ids": ["doc-2"],
        "expected_answer_substrings": ["2.70 acres", "$59,300"],
        "gold_evidence": [{"document_id": "doc-2", "page": 10, "table_label": "site_description"}],
        "numeric_targets": [{"field_name": "lot_size", "canonical_value": 2.7, "unit": "acres"}],
        "table_labels": ["site_description"],
    }

    vars_ = build_promptfoo_annotation_vars(annotation)

    assert vars_["benchmark_question_id"] == "tulsa-lot-size-income"
    assert vars_["benchmark_eval_slice"] == "table_factual"
    assert json.loads(vars_["benchmark_table_heavy"]) is True
    assert json.loads(vars_["benchmark_target_entities"]) == ["Tulsa Storage Units & Parking"]
    assert json.loads(vars_["benchmark_numeric_targets"])[0]["unit"] == "acres"
    assert json.loads(vars_["benchmark_table_labels"]) == ["site_description"]


def test_normalize_question_key_repairs_leading_hat_typo():
    assert (
        normalize_question_key("hat are the 2025 land, improvement, and total values for 5200 Chicago Ave?")
        == "what are the 2025 land, improvement, and total values for 5200 chicago ave?"
    )


def test_lookup_benchmark_annotation_uses_exact_benchmark_question_wording():
    annotations = load_benchmark_annotations(
        {
            "schema_version": "2026-05-29",
            "questions": [
                {
                    "question_id": "bullard-tyler-population",
                    "question": "In Bullard Heights Storage About how many residents does the city of Tyler have?",
                    "evaluation_slice": "narrative",
                    "scope_type": "entity_scoped",
                    "table_heavy": False,
                    "target_entities": ["Bullard Heights Storage"],
                    "target_document_ids": ["doc-1"],
                    "expected_answer_substrings": ["108,000 residents"],
                    "gold_evidence": [
                        {
                            "document_id": "doc-1",
                            "page": 7,
                            "evidence_type": "narrative",
                            "field_label": "tyler_population",
                            "relevance": 3,
                        }
                    ],
                }
            ],
        }
    )

    annotation = lookup_benchmark_annotation(
        annotations,
        "In Bullard Heights Storage About how many residents does the city of Tyler have?",
    )

    assert annotation is not None
    assert annotation["question_id"] == "bullard-tyler-population"