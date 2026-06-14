"""Helpers for structured RAG benchmark annotations used by eval exports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


BENCHMARK_ANNOTATION_SCHEMA_VERSION = "2026-05-29"


def normalize_question_key(question: Optional[str]) -> str:
    normalized = " ".join((question or "").strip().lower().split())
    normalized = normalized.lstrip("| ")

    if normalized.startswith("hat "):
        normalized = f"what {normalized[4:]}"

    return normalized


def _coerce_string_list(value: Any) -> List[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []

    if not isinstance(value, list):
        return []

    items: List[str] = []
    for item in value:
        if isinstance(item, str):
            stripped = item.strip()
            if stripped:
                items.append(stripped)
    return items


def _coerce_dict_list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _normalize_annotation_record(record: Dict[str, Any], fallback_question: Optional[str] = None) -> Dict[str, Any]:
    question = (record.get("question") or record.get("user_question") or fallback_question or "").strip()
    expected_substrings = _coerce_string_list(record.get("expected_answer_substrings"))

    expected_answer = record.get("expected_answer")
    if not expected_substrings and isinstance(expected_answer, str):
        expected_substrings = _coerce_string_list(expected_answer)
    elif isinstance(expected_answer, dict):
        expected_substrings.extend(_coerce_string_list(expected_answer.get("accepted_surface_forms")))
        raw_answer = expected_answer.get("raw_answer")
        if isinstance(raw_answer, str) and raw_answer.strip():
            expected_substrings.append(raw_answer.strip())

    gold_evidence = _coerce_dict_list(record.get("gold_evidence"))
    numeric_targets = _coerce_dict_list(record.get("numeric_targets"))
    target_entities = _coerce_string_list(record.get("target_entities"))
    target_document_ids = _coerce_string_list(record.get("target_document_ids"))
    table_labels = sorted(
        {
            item.get("table_label", "").strip()
            for item in gold_evidence
            if isinstance(item.get("table_label"), str) and item.get("table_label", "").strip()
        }
    )

    return {
        "schema_version": record.get("schema_version") or BENCHMARK_ANNOTATION_SCHEMA_VERSION,
        "question_id": record.get("question_id") or "",
        "question": question,
        "evaluation_slice": record.get("evaluation_slice") or "",
        "scope_type": record.get("scope_type") or "",
        "table_heavy": bool(record.get("table_heavy", False)),
        "target_entities": target_entities,
        "target_document_ids": target_document_ids,
        "expected_answer_substrings": list(dict.fromkeys(expected_substrings)),
        "gold_evidence": gold_evidence,
        "numeric_targets": numeric_targets,
        "table_labels": table_labels,
        "notes": record.get("notes") or "",
    }


def load_benchmark_annotations(raw: Any) -> Dict[str, Dict[str, Any]]:
    """Normalize legacy and structured annotation payloads into one lookup map."""
    if not isinstance(raw, dict):
        return {}

    records: Dict[str, Dict[str, Any]] = {}
    questions = raw.get("questions")

    if isinstance(questions, list):
        for item in questions:
            if not isinstance(item, dict):
                continue
            normalized = _normalize_annotation_record(item)
            key = normalize_question_key(normalized.get("question"))
            if key:
                records[key] = normalized
        return records

    for key, value in raw.items():
        if str(key).startswith("_"):
            continue

        if isinstance(value, str):
            normalized = _normalize_annotation_record({"expected_answer": value}, fallback_question=str(key))
        elif isinstance(value, dict):
            normalized = _normalize_annotation_record(value, fallback_question=str(key))
        else:
            continue

        lookup_key = normalize_question_key(normalized.get("question"))
        if lookup_key:
            records[lookup_key] = normalized

    return records


def load_benchmark_annotations_from_path(
    path: str | Path,
    _seen_paths: Optional[set[Path]] = None,
) -> Dict[str, Dict[str, Any]]:
    resolved_path = Path(path).resolve()
    seen_paths = _seen_paths or set()

    if resolved_path in seen_paths:
        raise ValueError(f"Circular benchmark annotation extends detected: {resolved_path}")

    seen_paths.add(resolved_path)

    with resolved_path.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    merged_records: Dict[str, Dict[str, Any]] = {}
    extends_value = raw.get("extends") if isinstance(raw, dict) else None

    extend_paths: List[str] = []
    if isinstance(extends_value, str) and extends_value.strip():
        extend_paths = [extends_value.strip()]
    elif isinstance(extends_value, list):
        extend_paths = [item.strip() for item in extends_value if isinstance(item, str) and item.strip()]

    for extend_path in extend_paths:
        candidate_path = Path(extend_path)
        if not candidate_path.is_absolute():
            candidate_path = (resolved_path.parent / candidate_path).resolve()
        merged_records.update(load_benchmark_annotations_from_path(candidate_path, seen_paths))

    merged_records.update(load_benchmark_annotations(raw))
    return merged_records


def lookup_benchmark_annotation(
    annotations: Optional[Dict[str, Dict[str, Any]]],
    user_question: Optional[str],
) -> Optional[Dict[str, Any]]:
    if not annotations:
        return None
    return annotations.get(normalize_question_key(user_question))


def get_expected_answer_substrings(annotation: Optional[Dict[str, Any]]) -> List[str]:
    if not annotation:
        return []
    return _coerce_string_list(annotation.get("expected_answer_substrings"))


def build_promptfoo_annotation_vars(annotation: Optional[Dict[str, Any]]) -> Dict[str, str]:
    if not annotation:
        return {}

    return {
        "benchmark_question_id": annotation.get("question_id") or "",
        "benchmark_eval_slice": annotation.get("evaluation_slice") or "",
        "benchmark_scope_type": annotation.get("scope_type") or "",
        "benchmark_table_heavy": json.dumps(bool(annotation.get("table_heavy", False))),
        "benchmark_target_entities": json.dumps(annotation.get("target_entities") or [], ensure_ascii=False),
        "benchmark_target_document_ids": json.dumps(annotation.get("target_document_ids") or [], ensure_ascii=False),
        "benchmark_expected_answer_substrings": json.dumps(
            annotation.get("expected_answer_substrings") or [],
            ensure_ascii=False,
        ),
        "benchmark_gold_evidence": json.dumps(annotation.get("gold_evidence") or [], ensure_ascii=False),
        "benchmark_numeric_targets": json.dumps(annotation.get("numeric_targets") or [], ensure_ascii=False),
        "benchmark_table_labels": json.dumps(annotation.get("table_labels") or [], ensure_ascii=False),
    }