import argparse
import json
import math
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute Wilson intervals and paired McNemar tests from promptfoo retrieval outputs."
    )
    parser.add_argument(
        "--run",
        action="append",
        nargs=2,
        metavar=("LABEL", "PATH"),
        required=True,
        help="Add a retrieval run as LABEL PATH; repeat for multiple runs.",
    )
    parser.add_argument(
        "--compare",
        action="append",
        nargs=2,
        metavar=("BASELINE", "TARGET"),
        required=True,
        help="Add a paired comparison BASELINE TARGET; repeat for multiple comparisons.",
    )
    parser.add_argument("--output-json", required=True, help="JSON output path")
    parser.add_argument("--output-md", required=True, help="Markdown output path")
    return parser.parse_args()


def load_run(path: Path) -> dict[str, bool]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: dict[str, bool] = {}
    for result in data["results"]["results"]:
        provider_label = result.get("provider", {}).get("label")
        if provider_label != "haiku-retrieval":
            continue
        test_case = result.get("testCase", {})
        vars_data = test_case.get("vars", {})
        question_id = vars_data.get("benchmark_question_id")
        if not question_id:
            continue
        passed = bool(result.get("success"))
        rows[question_id] = passed
    return rows


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt((p * (1 - p) / total) + (z * z / (4 * total * total)))
        / denominator
    )
    return (center - margin, center + margin)


def binomial_cdf(k: int, n: int, p: float) -> float:
    return sum(math.comb(n, i) * (p**i) * ((1 - p) ** (n - i)) for i in range(k + 1))


def mcnemar_exact_p_value(improved: int, regressed: int) -> float:
    discordant = improved + regressed
    if discordant == 0:
        return 1.0
    tail = binomial_cdf(min(improved, regressed), discordant, 0.5)
    return min(1.0, 2 * tail)


def render_markdown(summary: dict) -> str:
    lines = [
        "# Paired Significance Summary",
        "",
        "## Run-Level Wilson Intervals",
        "",
        "| Run | Cases | Passes | Pass Rate | Wilson 95% CI |",
        "| --- | ---: | ---: | ---: | --- |",
    ]

    for row in summary["runs"]:
        lines.append(
            f"| {row['label']} | {row['cases']} | {row['passes']} | {row['pass_rate']:.4f} | [{row['wilson_low']:.4f}, {row['wilson_high']:.4f}] |"
        )

    lines.extend(
        [
            "",
            "## Paired McNemar Tests",
            "",
            "| Comparison | Improved | Regressed | Discordant | Exact p-value |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )

    for row in summary["comparisons"]:
        lines.append(
            f"| {row['baseline']} vs {row['target']} | {row['improved']} | {row['regressed']} | {row['discordant']} | {row['exact_p_value']:.6f} |"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    run_specs = [(label, Path(path)) for label, path in args.run]
    compare_specs = [(baseline, target) for baseline, target in args.compare]

    loaded_runs = {label: load_run(path) for label, path in run_specs}

    run_rows = []
    for label, _path in run_specs:
        outcomes = loaded_runs[label]
        passes = sum(1 for passed in outcomes.values() if passed)
        cases = len(outcomes)
        wilson_low, wilson_high = wilson_interval(passes, cases)
        run_rows.append(
            {
                "label": label,
                "cases": cases,
                "passes": passes,
                "pass_rate": passes / cases if cases else 0.0,
                "wilson_low": wilson_low,
                "wilson_high": wilson_high,
            }
        )

    comparison_rows = []
    for baseline, target in compare_specs:
        baseline_run = loaded_runs[baseline]
        target_run = loaded_runs[target]
        baseline_ids = set(baseline_run)
        target_ids = set(target_run)
        if baseline_ids != target_ids:
            missing_from_target = sorted(baseline_ids - target_ids)
            missing_from_baseline = sorted(target_ids - baseline_ids)
            raise SystemExit(
                "Run question-id mismatch for "
                f"{baseline} vs {target}: missing_from_target={missing_from_target[:5]} "
                f"missing_from_baseline={missing_from_baseline[:5]}"
            )

        improved = 0
        regressed = 0
        for question_id in sorted(baseline_ids):
            baseline_pass = baseline_run[question_id]
            target_pass = target_run[question_id]
            if not baseline_pass and target_pass:
                improved += 1
            elif baseline_pass and not target_pass:
                regressed += 1

        comparison_rows.append(
            {
                "baseline": baseline,
                "target": target,
                "improved": improved,
                "regressed": regressed,
                "discordant": improved + regressed,
                "exact_p_value": mcnemar_exact_p_value(improved, regressed),
            }
        )

    summary = {
        "runs": run_rows,
        "comparisons": comparison_rows,
    }

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    output_md.write_text(render_markdown(summary), encoding="utf-8")

    print(f"runs={len(run_rows)}")
    print(f"comparisons={len(comparison_rows)}")


if __name__ == "__main__":
    main()