import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


RUN_NAME_MAP = {
    "A0": "A0",
    "A2": "A2",
    "A5": "A5",
    "promptfoo_rag_retrieval_A6_after_year_filter": "A6",
}

FAILURE_ORDER = ["missing_gold_pages", "missing_table_pages", "scope_error"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a compact cross-run error taxonomy from saved retrieval analysis."
    )
    parser.add_argument("--input", required=True, help="Path to analysis_summary_after_year_filter.json")
    parser.add_argument("--output-json", required=True, help="JSON output path")
    parser.add_argument("--output-md", required=True, help="Markdown output path")
    return parser.parse_args()


def render_markdown(summary: dict) -> str:
    lines = [
        "# Error Taxonomy Summary",
        "",
        "## Run-Level Failure Counts",
        "",
        "| Run | Cases | Pass Rate | Missing Gold Pages | Missing Table Pages | Scope Error |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    for row in summary["runs"]:
        lines.append(
            f"| {row['label']} | {row['cases']} | {row['pass_rate']:.4f} | {row['failure_counts'].get('missing_gold_pages', 0)} | {row['failure_counts'].get('missing_table_pages', 0)} | {row['failure_counts'].get('scope_error', 0)} |"
        )

    lines.extend([
        "",
        "## Residual A6 Failures",
        "",
    ])

    residual = summary.get("a6_residual_failures", [])
    if residual:
        lines.extend([
            "| Question ID | Failure Labels |",
            "| --- | --- |",
        ])
        for row in residual:
            lines.append(f"| {row['question_id']} | {', '.join(row['failures'])} |")
    else:
        lines.append("No residual A6 failures recorded.")

    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))

    run_rows = []
    aggregated_failures: dict[str, Counter] = defaultdict(Counter)
    residual_a6 = []

    for raw_label, normalized in RUN_NAME_MAP.items():
        run_metrics = data["runs"][raw_label]
        run_rows.append(
            {
                "label": normalized,
                "cases": run_metrics["cases"],
                "pass_rate": run_metrics["page_recall_80_pass_rate"],
                "failure_counts": {},
            }
        )

    run_index = {row["label"]: row for row in run_rows}

    for row in data.get("failure_cases", []):
        raw_label = row.get("run_label")
        if raw_label not in RUN_NAME_MAP:
            continue
        normalized = RUN_NAME_MAP[raw_label]
        failures = row.get("failures", [])
        for failure in failures:
            aggregated_failures[normalized][failure] += 1
        if normalized == "A6":
            residual_a6.append(
                {
                    "question_id": row["question_id"],
                    "failures": failures,
                    "page_recall": row.get("page_recall"),
                    "scope_error": row.get("scope_error"),
                }
            )

    for row in run_rows:
        counts = aggregated_failures[row["label"]]
        row["failure_counts"] = {name: counts.get(name, 0) for name in FAILURE_ORDER if counts.get(name, 0)}

    summary = {
        "runs": run_rows,
        "a6_residual_failures": residual_a6,
    }

    Path(args.output_json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    Path(args.output_md).write_text(render_markdown(summary), encoding="utf-8")

    print(f"runs={len(run_rows)}")
    print(f"a6_residual_failures={len(residual_a6)}")


if __name__ == "__main__":
    main()