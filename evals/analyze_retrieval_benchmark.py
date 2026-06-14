from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Hashable, Iterable


def _parse_json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list, bool, int, float)):
        return value
    if not isinstance(value, str) or not value.strip():
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _normalize_numeric_surface(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", (text or "").lower())


def _resolve_run_label(ablation_id: Any, fallback_label: str) -> str:
    if isinstance(ablation_id, str) and ablation_id.strip():
        return ablation_id.strip()

    match = re.search(r"(?:^|_)(A\d+)(?:_|$)", fallback_label or "")
    if match:
        return match.group(1)

    return fallback_label


def _numeric_surface_forms(target: dict[str, Any]) -> list[str]:
    forms = []
    for value in target.get("accepted_surface_forms") or []:
        if isinstance(value, str) and value.strip():
            forms.append(value.strip())

    raw_value = target.get("raw_value")
    if isinstance(raw_value, str) and raw_value.strip():
        forms.append(raw_value.strip())

    canonical_value = target.get("canonical_value")
    if canonical_value is not None:
        forms.extend(
            [
                str(canonical_value),
                f"{canonical_value:,.2f}",
                f"{canonical_value:g}",
            ]
        )

    seen: set[str] = set()
    normalized: list[str] = []
    for value in forms:
        key = _normalize_numeric_surface(value)
        if key and key not in seen:
            seen.add(key)
            normalized.append(key)
    return normalized


def _matches_numeric_target(text: str, target: dict[str, Any]) -> bool:
    normalized_text = _normalize_numeric_surface(text)
    if not normalized_text:
        return False
    return any(surface in normalized_text for surface in _numeric_surface_forms(target))


def _safe_mean(values: Iterable[float | int | None]) -> float | None:
    filtered = [float(value) for value in values if value is not None]
    if not filtered:
        return None
    return mean(filtered)


def _rate(values: Iterable[int | None]) -> float | None:
    filtered = [int(value) for value in values if value is not None]
    if not filtered:
        return None
    return sum(filtered) / len(filtered)


def _recall(expected: set[Hashable], observed: set[Hashable]) -> float | None:
    if not expected:
        return None
    hits = sum(1 for item in expected if item in observed)
    return hits / len(expected)


def _anchor_key(item: dict[str, Any], fallback_document_id: str | None = None) -> str | None:
    if not isinstance(item, dict):
        return None

    document_id = item.get("document_id") or fallback_document_id
    if not document_id:
        return None

    chunk_id = item.get("chunk_id")
    if chunk_id:
        return f"{document_id}:chunk:{chunk_id}"

    page = item.get("page")
    if page is not None:
        try:
            return f"{document_id}:page:{int(page)}"
        except (TypeError, ValueError):
            return None

    return None


def _format_metric(value: float | None, percent: bool = False) -> str:
    if value is None:
        return "n/a"
    if percent:
        return f"{value * 100:.1f}%"
    return f"{value:.3f}"


def _resolve_scope_document_ids(vars_: dict[str, Any]) -> set[str]:
    fixture_doc_ids = {
        item for item in _parse_json_value(vars_.get("document_ids"), []) if isinstance(item, str)
    }
    if fixture_doc_ids:
        return fixture_doc_ids

    return {
        item
        for item in _parse_json_value(vars_.get("benchmark_target_document_ids"), [])
        if isinstance(item, str)
    }


def _resolve_table_gold_pages(
    gold_evidence: list[dict[str, Any]],
    answer_document_ids: set[str],
) -> set[tuple[str, int]]:
    table_pages = [
        item for item in gold_evidence if isinstance(item, dict) and item.get("evidence_type") == "table"
    ]
    if not table_pages:
        return set()

    raw_pages = {
        (item.get("document_id"), int(item.get("page")))
        for item in table_pages
        if item.get("document_id") and item.get("page") is not None
    }
    if raw_pages and {doc_id for doc_id, _ in raw_pages}.issubset(answer_document_ids):
        return raw_pages

    if len(answer_document_ids) == 1:
        scope_document_id = next(iter(answer_document_ids))
        return {
            (scope_document_id, int(item.get("page")))
            for item in table_pages
            if item.get("page") is not None
        }

    return raw_pages


def _resolve_table_gold_anchor_keys(
    gold_evidence: list[dict[str, Any]],
    answer_document_ids: set[str],
) -> set[str]:
    table_items = [
        item for item in gold_evidence if isinstance(item, dict) and item.get("evidence_type") == "table"
    ]
    if not table_items:
        return set()

    anchor_keys = {
        key
        for item in table_items
        for key in [_anchor_key(item)]
        if key
    }
    if anchor_keys:
        return anchor_keys

    if len(answer_document_ids) == 1:
        scope_document_id = next(iter(answer_document_ids))
        return {
            key
            for item in table_items
            for key in [_anchor_key(item, fallback_document_id=scope_document_id)]
            if key
        }

    return set()


def _resolve_effective_expected_anchor_keys(
    vars_: dict[str, Any],
    expected_pages: set[tuple[str, int]],
    expected_anchor_keys: set[str],
    gold_evidence: list[dict[str, Any]],
) -> set[str]:
    fixture_doc_ids = {
        item for item in _parse_json_value(vars_.get("document_ids"), []) if isinstance(item, str)
    }
    benchmark_gold_anchor_keys = {
        key
        for item in gold_evidence
        for key in [_anchor_key(item)]
        if key
    }
    benchmark_gold_usable = bool(fixture_doc_ids) and any(
        isinstance(item, dict)
        and item.get("document_id") in fixture_doc_ids
        for item in gold_evidence
    )

    if benchmark_gold_usable and benchmark_gold_anchor_keys:
        return benchmark_gold_anchor_keys
    if expected_anchor_keys:
        return expected_anchor_keys
    return {
        f"{document_id}:page:{page}" for document_id, page in expected_pages
    }


def _extract_cases(payload: dict[str, Any], provider_label: str | None, fallback_label: str) -> list[dict[str, Any]]:
    raw_results = ((payload.get("results") or {}).get("results") or [])
    cases: list[dict[str, Any]] = []

    for item in raw_results:
        provider = item.get("provider") or {}
        item_provider_label = provider.get("label") or provider.get("id") or ""
        if provider_label and item_provider_label != provider_label:
            continue

        test_case = item.get("testCase") or {}
        vars_ = test_case.get("vars") or {}
        response = item.get("response") or {}
        output_raw = response.get("output") or ""
        output_json = _parse_json_value(output_raw, {})
        if not isinstance(output_json, dict):
            output_json = {}

        chunks = output_json.get("chunks") or []
        if not isinstance(chunks, list):
            chunks = []

        text_output = output_json.get("text") if isinstance(output_json.get("text"), str) else ""

        expected_pages = {
            (item.get("document_id"), int(item.get("page")))
            for item in _parse_json_value(vars_.get("expected_pages"), [])
            if isinstance(item, dict) and item.get("document_id") and item.get("page") is not None
        }
        expected_anchors = _parse_json_value(vars_.get("expected_anchors"), [])
        expected_anchor_keys = {
            key
            for item in expected_anchors
            for key in [_anchor_key(item)]
            if key
        }
        if not expected_anchor_keys:
            expected_anchor_keys = {
                f"{document_id}:page:{page}" for document_id, page in expected_pages
            }
        answer_document_ids = {document_id for document_id, _ in expected_pages}
        if not answer_document_ids:
            answer_document_ids = {
                item.get("document_id")
                for item in expected_anchors
                if isinstance(item, dict) and item.get("document_id")
            }
        gold_evidence = _parse_json_value(vars_.get("benchmark_gold_evidence"), [])
        scope_document_ids = _resolve_scope_document_ids(vars_)
        effective_expected_anchor_keys = _resolve_effective_expected_anchor_keys(
            vars_=vars_,
            expected_pages=expected_pages,
            expected_anchor_keys=expected_anchor_keys,
            gold_evidence=gold_evidence,
        )
        table_gold_pages = _resolve_table_gold_pages(gold_evidence, answer_document_ids or scope_document_ids)
        table_gold_anchor_keys = _resolve_table_gold_anchor_keys(gold_evidence, answer_document_ids or scope_document_ids)
        retrieved_pages = {
            (chunk.get("document_id"), int(chunk.get("page")))
            for chunk in chunks
            if isinstance(chunk, dict) and chunk.get("document_id") and chunk.get("page") is not None
        }
        retrieved_anchor_keys = {
            key
            for chunk in chunks
            if isinstance(chunk, dict)
            for key in [_anchor_key({
                "document_id": chunk.get("document_id"),
                "page": chunk.get("page"),
                "chunk_id": chunk.get("chunk_id"),
            })]
            if key
        }
        target_document_ids = answer_document_ids or scope_document_ids
        numeric_targets = [
            item for item in _parse_json_value(vars_.get("benchmark_numeric_targets"), []) if isinstance(item, dict)
        ]

        any_in_scope = any(
            isinstance(chunk, dict) and chunk.get("document_id") in target_document_ids for chunk in chunks
        )
        top1_document_id = chunks[0].get("document_id") if chunks and isinstance(chunks[0], dict) else None
        scope_error = None
        if target_document_ids and chunks:
            scope_error = int((top1_document_id not in target_document_ids) or not any_in_scope)

        numeric_em = None
        if numeric_targets and text_output:
            numeric_em = int(all(_matches_numeric_target(text_output, target) for target in numeric_targets))

        ablation_id = vars_.get("ablation_id")
        run_label = _resolve_run_label(ablation_id, fallback_label)

        failures: list[str] = []
        page_recall = _recall(effective_expected_anchor_keys, retrieved_anchor_keys)

        table_recall = _recall(table_gold_pages, retrieved_pages)
        if table_recall is None:
            table_recall = _recall(table_gold_anchor_keys, retrieved_anchor_keys)
        if page_recall is not None and page_recall < 1.0:
            failures.append("missing_gold_pages")
        if table_recall is not None and table_recall < 1.0:
            failures.append("missing_table_pages")
        if scope_error == 1:
            failures.append("scope_error")
        if numeric_em == 0:
            failures.append("numeric_mismatch")

        cases.append(
            {
                "run_label": run_label,
                "provider": item_provider_label,
                "question_id": vars_.get("benchmark_question_id") or "",
                "question": vars_.get("user_question") or vars_.get("query") or "",
                "evaluation_slice": vars_.get("benchmark_eval_slice") or "",
                "scope_type": vars_.get("benchmark_scope_type") or "",
                "table_heavy": bool(_parse_json_value(vars_.get("benchmark_table_heavy"), False)),
                "latency_ms": item.get("latencyMs"),
                "cost": item.get("cost"),
                "page_recall": page_recall,
                "table_recall": table_recall,
                "numeric_em": numeric_em,
                "scope_error": scope_error,
                "page_recall_80": (item.get("namedScores") or {}).get("retrieval/page_recall_80"),
                "top1_document_id": top1_document_id,
                "target_document_ids": sorted(target_document_ids),
                "expected_pages": sorted(expected_pages),
                "retrieved_pages": sorted(retrieved_pages),
                "expected_anchors": sorted(expected_anchor_keys),
                "retrieved_anchors": sorted(retrieved_anchor_keys),
                "failures": failures,
            }
        )

    return cases


def _summarize_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cases": len(cases),
        "avg_latency_ms": _safe_mean(case.get("latency_ms") for case in cases),
        "avg_cost": _safe_mean(case.get("cost") for case in cases),
        "page_recall": _safe_mean(case.get("page_recall") for case in cases),
        "table_recall": _safe_mean(case.get("table_recall") for case in cases),
        "numeric_em": _rate(case.get("numeric_em") for case in cases),
        "scope_error_rate": _rate(case.get("scope_error") for case in cases),
        "page_recall_80_pass_rate": _rate(case.get("page_recall_80") for case in cases),
    }


def _print_summary_table(run_to_cases: dict[str, list[dict[str, Any]]]) -> None:
    header = (
        f"{'Run':<18} {'Cases':>5} {'Latency':>10} {'PageR':>8} {'TableR':>8} "
        f"{'NumEM':>8} {'ScopeErr':>10} {'PR@80':>8}"
    )
    print(header)
    print("-" * len(header))
    for run_label in sorted(run_to_cases):
        summary = _summarize_cases(run_to_cases[run_label])
        print(
            f"{run_label:<18} "
            f"{summary['cases']:>5} "
            f"{_format_metric(summary['avg_latency_ms'] / 1000 if summary['avg_latency_ms'] is not None else None):>10} "
            f"{_format_metric(summary['page_recall'], percent=True):>8} "
            f"{_format_metric(summary['table_recall'], percent=True):>8} "
            f"{_format_metric(summary['numeric_em'], percent=True):>8} "
            f"{_format_metric(summary['scope_error_rate'], percent=True):>10} "
            f"{_format_metric(summary['page_recall_80_pass_rate'], percent=True):>8}"
        )


def _print_table_heavy_subset(cases: list[dict[str, Any]]) -> None:
    subsets = {
        "overall": cases,
        "table_heavy": [case for case in cases if case.get("table_heavy")],
        "non_table_heavy": [case for case in cases if not case.get("table_heavy")],
    }
    header = f"{'Subset':<18} {'Cases':>5} {'PageR':>8} {'TableR':>8} {'ScopeErr':>10}"
    print(header)
    print("-" * len(header))
    for label, subset_cases in subsets.items():
        summary = _summarize_cases(subset_cases)
        print(
            f"{label:<18} "
            f"{summary['cases']:>5} "
            f"{_format_metric(summary['page_recall'], percent=True):>8} "
            f"{_format_metric(summary['table_recall'], percent=True):>8} "
            f"{_format_metric(summary['scope_error_rate'], percent=True):>10}"
        )


def _print_failure_cases(cases: list[dict[str, Any]], limit: int) -> None:
    failures = [case for case in cases if case.get("failures")]
    if not failures:
        print("No failure cases detected by the derived metrics.")
        return

    print("Question ID | Run | Failures | Top1 Doc | Expected Anchors | Retrieved Anchors")
    print("-" * 120)
    for case in failures[:limit]:
        expected = case.get("expected_anchors") or case.get("expected_pages")
        retrieved = case.get("retrieved_anchors") or case.get("retrieved_pages")
        print(
            f"{case['question_id']} | {case['run_label']} | {','.join(case['failures'])} | "
            f"{case['top1_document_id'] or 'n/a'} | {expected} | {retrieved[:8]}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze promptfoo RAG benchmark outputs.")
    parser.add_argument(
        "results",
        nargs="+",
        help="One or more promptfoo result JSON files.",
    )
    parser.add_argument(
        "--provider",
        default="haiku-retrieval",
        help="Provider label to analyze (default: haiku-retrieval). Use haiku-rag for generation outputs.",
    )
    parser.add_argument(
        "--failure-limit",
        type=int,
        default=10,
        help="Maximum number of failure rows to print.",
    )
    parser.add_argument(
        "--json-output",
        default=None,
        help="Optional path to write the structured summary as JSON.",
    )
    args = parser.parse_args()

    all_cases: list[dict[str, Any]] = []
    run_to_cases: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for raw_path in args.results:
        path = Path(raw_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        fallback_label = path.stem
        cases = _extract_cases(payload, args.provider, fallback_label)
        all_cases.extend(cases)
        for case in cases:
            run_to_cases[case["run_label"]].append(case)

    if not all_cases:
        raise SystemExit(f"No cases found for provider '{args.provider}'.")

    print("Run Summary")
    _print_summary_table(run_to_cases)
    print()
    print("Table-Heavy Subset")
    _print_table_heavy_subset(all_cases)
    print()
    print("Failure Cases")
    _print_failure_cases(all_cases, args.failure_limit)

    if args.json_output:
        output_payload = {
            "provider": args.provider,
            "runs": {label: _summarize_cases(cases) for label, cases in sorted(run_to_cases.items())},
            "table_heavy_subset": {
                "overall": _summarize_cases(all_cases),
                "table_heavy": _summarize_cases([case for case in all_cases if case.get("table_heavy")]),
                "non_table_heavy": _summarize_cases([case for case in all_cases if not case.get("table_heavy")]),
            },
            "failure_cases": [case for case in all_cases if case.get("failures")],
        }
        Path(args.json_output).write_text(json.dumps(output_payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()