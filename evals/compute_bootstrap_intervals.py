from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from analyze_retrieval_benchmark import _extract_cases


def _quantile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        raise ValueError("Cannot compute quantile of an empty list")
    if p <= 0:
        return sorted_values[0]
    if p >= 1:
        return sorted_values[-1]

    index = (len(sorted_values) - 1) * p
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def _bootstrap_mean_ci(
    values: list[float],
    bootstrap_samples: int,
    rng: random.Random,
    alpha: float,
) -> dict[str, float]:
    n = len(values)
    if n == 0:
        return {
            "observed_mean": None,
            "ci_low": None,
            "ci_high": None,
        }

    observed_mean = sum(values) / n
    draws: list[float] = []
    for _ in range(bootstrap_samples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        draws.append(sum(sample) / n)

    draws.sort()
    low_q = _quantile(draws, alpha / 2.0)
    high_q = _quantile(draws, 1.0 - alpha / 2.0)
    return {
        "observed_mean": observed_mean,
        "ci_low": low_q,
        "ci_high": high_q,
    }


def _run_sort_key(label: str) -> tuple[int, str]:
    if label.startswith("A") and label[1:].isdigit():
        return (0, f"{int(label[1:]):03d}")
    return (1, label)


def _build_markdown(summary: dict[str, Any], json_path: Path) -> str:
    lines = [
        "# Bootstrap Confidence Intervals (95%)",
        "",
        f"- Source summary: `{json_path.as_posix()}`",
        f"- Bootstrap samples: {summary['bootstrap_samples']}",
        f"- Alpha: {summary['alpha']}",
        f"- Random seed: {summary['seed']}",
        "",
        "| Run | Cases (page/table) | Page Recall Mean | Page Recall 95% CI | Table Recall Mean | Table Recall 95% CI |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    for row in summary["runs"]:
        page = row["metrics"]["page_recall"]
        table = row["metrics"]["table_recall"]

        page_mean = "n/a" if page["observed_mean"] is None else f"{page['observed_mean'] * 100:.2f}%"
        page_ci = (
            "n/a"
            if page["ci_low"] is None
            else f"[{page['ci_low'] * 100:.2f}%, {page['ci_high'] * 100:.2f}%]"
        )
        table_mean = "n/a" if table["observed_mean"] is None else f"{table['observed_mean'] * 100:.2f}%"
        table_ci = (
            "n/a"
            if table["ci_low"] is None
            else f"[{table['ci_low'] * 100:.2f}%, {table['ci_high'] * 100:.2f}%]"
        )

        lines.append(
            f"| {row['run_label']} | {page['n']}/{table['n']} | {page_mean} | {page_ci} | {table_mean} | {table_ci} |"
        )

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute bootstrap confidence intervals for retrieval metrics.")
    parser.add_argument("results", nargs="+", help="Promptfoo result JSON files.")
    parser.add_argument(
        "--provider",
        default="haiku-retrieval",
        help="Provider label to analyze (default: haiku-retrieval).",
    )
    parser.add_argument(
        "--bootstrap-samples",
        type=int,
        default=10000,
        help="Number of bootstrap resamples (default: 10000).",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.05,
        help="Two-sided alpha for confidence intervals (default: 0.05 for 95%% CI).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260603,
        help="Random seed for reproducibility.",
    )
    parser.add_argument(
        "--json-output",
        default="evals/results/full_96_benchmark/bootstrap_intervals_summary.json",
        help="Path to write JSON summary.",
    )
    parser.add_argument(
        "--md-output",
        default="evals/results/full_96_benchmark/bootstrap_intervals_summary.md",
        help="Path to write Markdown summary.",
    )
    args = parser.parse_args()

    all_cases: list[dict[str, Any]] = []
    for path_str in args.results:
        path = Path(path_str)
        payload = json.loads(path.read_text(encoding="utf-8"))
        fallback_label = path.stem
        all_cases.extend(_extract_cases(payload, provider_label=args.provider, fallback_label=fallback_label))

    run_labels = sorted({case["run_label"] for case in all_cases}, key=_run_sort_key)
    rng = random.Random(args.seed)

    run_rows: list[dict[str, Any]] = []
    for run_label in run_labels:
        run_cases = [case for case in all_cases if case["run_label"] == run_label]
        page_values = [float(case["page_recall"]) for case in run_cases if case.get("page_recall") is not None]
        table_values = [float(case["table_recall"]) for case in run_cases if case.get("table_recall") is not None]

        page_stats = _bootstrap_mean_ci(page_values, args.bootstrap_samples, rng, args.alpha)
        page_stats["n"] = len(page_values)
        table_stats = _bootstrap_mean_ci(table_values, args.bootstrap_samples, rng, args.alpha)
        table_stats["n"] = len(table_values)

        run_rows.append(
            {
                "run_label": run_label,
                "cases": len(run_cases),
                "metrics": {
                    "page_recall": page_stats,
                    "table_recall": table_stats,
                },
            }
        )

    summary = {
        "provider": args.provider,
        "bootstrap_samples": args.bootstrap_samples,
        "alpha": args.alpha,
        "seed": args.seed,
        "runs": run_rows,
    }

    json_output = Path(args.json_output)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    md_output = Path(args.md_output)
    md_output.parent.mkdir(parents=True, exist_ok=True)
    md_output.write_text(_build_markdown(summary, json_output), encoding="utf-8")

    print(f"Wrote JSON summary: {json_output}")
    print(f"Wrote Markdown summary: {md_output}")


if __name__ == "__main__":
    main()
