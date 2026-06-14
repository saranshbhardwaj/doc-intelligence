"""Deduplicate exported promptfoo fixtures by benchmark question id.

Prefers the duplicate row whose exported context best matches the benchmark
annotation payload already embedded in the fixture vars.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def _normalize_text(value: str) -> str:
    collapsed = " ".join(value.lower().split())
    return re.sub(r"[,$]", "", collapsed)


def _load_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return [value.strip()]
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    if isinstance(parsed, str) and parsed.strip():
        return [parsed.strip()]
    return []


def _row_score(row: dict[str, Any]) -> tuple[int, int, int]:
    vars_ = row.get("vars") or {}
    context = str(vars_.get("context") or "")
    normalized_context = _normalize_text(context)

    expected_variants = [_normalize_text(item) for item in _load_json_list(vars_.get("benchmark_expected_answer_substrings"))]
    target_entities = [_normalize_text(item) for item in _load_json_list(vars_.get("benchmark_target_entities"))]

    expected_hits = sum(1 for item in expected_variants if item and item in normalized_context)
    entity_hits = sum(1 for item in target_entities if item and item in normalized_context)
    page_none_penalty = 0 if "pnone" not in normalized_context else -1

    # Prefer rows with more explicit expected-value evidence, then entity match,
    # then rows without page-less placeholder context.
    return (expected_hits, entity_hits, page_none_penalty)


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    passthrough: list[dict[str, Any]] = []

    for row in rows:
        qid = ((row.get("vars") or {}).get("benchmark_question_id"))
        if not qid:
            passthrough.append(row)
            continue
        grouped.setdefault(qid, []).append(row)

    deduped_rows: list[dict[str, Any]] = []
    for qid, candidates in grouped.items():
        best = max(
            enumerate(candidates),
            key=lambda item: (_row_score(item[1]), -item[0]),
        )[1]
        deduped_rows.append(best)

    return deduped_rows + passthrough


def main() -> None:
    parser = argparse.ArgumentParser(description="Deduplicate exported promptfoo fixtures by benchmark question id")
    parser.add_argument("input", help="Input JSONL fixture path")
    parser.add_argument("output", help="Output JSONL fixture path")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    rows = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    deduped_rows = dedupe_rows(rows)
    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in deduped_rows),
        encoding="utf-8",
    )

    print(f"SOURCE_ROWS {len(rows)}")
    print(f"DEDUPED_ROWS {len(deduped_rows)}")
    print(f"OUTPUT {output_path}")


if __name__ == "__main__":
    main()