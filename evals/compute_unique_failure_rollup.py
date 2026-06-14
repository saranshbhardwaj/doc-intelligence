import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute unique failed-question rollups from promptfoo retrieval result files."
    )
    parser.add_argument(
        "--run",
        action="append",
        nargs=2,
        metavar=("LABEL", "PATH"),
        required=True,
        help="Add a retrieval run as LABEL PATH; repeat for multiple runs.",
    )
    parser.add_argument("--reference", required=True, help="Reference run label for resolved/regressed comparisons")
    parser.add_argument("--output-json", required=True, help="JSON output path")
    parser.add_argument("--output-md", required=True, help="Markdown output path")
    return parser.parse_args()


def load_outcomes(path: Path) -> dict[str, bool]:
    data = json.loads(path.read_text(encoding="utf-8"))
    outcomes: dict[str, bool] = {}
    for row in data["results"]["results"]:
        if row.get("provider", {}).get("label") != "haiku-retrieval":
            continue
        question_id = row.get("testCase", {}).get("vars", {}).get("benchmark_question_id")
        if not question_id:
            continue
        outcomes[question_id] = bool(row.get("success"))
    return outcomes


def render_markdown(summary: dict) -> str:
    lines = [
        "# Unique Failure Rollup",
        "",
        "## Per-Run Unique Failed Questions",
        "",
        "| Run | Cases | Failed Questions | Fail Rate |",
        "| --- | ---: | ---: | ---: |",
    ]

    for row in summary["runs"]:
        lines.append(
            f"| {row['label']} | {row['cases']} | {row['failed_count']} | {row['failed_count'] / row['cases'] if row['cases'] else 0:.4f} |"
        )

    lines.extend(["", "## Reference Comparisons", ""])
    for comp in summary["reference_comparisons"]:
        lines.append(f"### {comp['run']} vs {summary['reference_run']}")
        lines.append("")
        lines.append(f"- resolved_by_{summary['reference_run']}: {len(comp['resolved_by_reference'])}")
        lines.append(f"- regressed_vs_{summary['reference_run']}: {len(comp['regressed_vs_reference'])}")
        lines.append("")

    lines.extend([
        "## Shared Failure Sets",
        "",
        f"- failures_shared_by_all_runs: {len(summary['shared_failures_all_runs'])}",
        f"- failures_shared_by_non_reference_runs: {len(summary['shared_failures_non_reference'])}",
        "",
    ])

    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    run_specs = [(label, Path(path)) for label, path in args.run]
    outcomes_by_run = {label: load_outcomes(path) for label, path in run_specs}

    if args.reference not in outcomes_by_run:
        raise SystemExit(f"Reference run '{args.reference}' is not present in --run inputs")

    # Verify question-id sets align.
    all_id_sets = {label: set(outcomes.keys()) for label, outcomes in outcomes_by_run.items()}
    first_label, first_ids = next(iter(all_id_sets.items()))
    for label, ids in all_id_sets.items():
        if ids != first_ids:
            raise SystemExit(
                f"Question-id mismatch: {label} differs from {first_label} "
                f"(missing={sorted(first_ids - ids)[:5]}, extra={sorted(ids - first_ids)[:5]})"
            )

    failed_ids_by_run = {
        label: sorted([qid for qid, passed in outcomes.items() if not passed])
        for label, outcomes in outcomes_by_run.items()
    }

    runs = []
    for label, outcomes in outcomes_by_run.items():
        failed_ids = failed_ids_by_run[label]
        runs.append(
            {
                "label": label,
                "cases": len(outcomes),
                "failed_count": len(failed_ids),
                "failed_question_ids": failed_ids,
            }
        )

    reference_outcomes = outcomes_by_run[args.reference]
    reference_comparisons = []
    for label, outcomes in outcomes_by_run.items():
        if label == args.reference:
            continue
        resolved = []
        regressed = []
        for qid in sorted(reference_outcomes.keys()):
            base_pass = outcomes[qid]
            ref_pass = reference_outcomes[qid]
            if not base_pass and ref_pass:
                resolved.append(qid)
            elif base_pass and not ref_pass:
                regressed.append(qid)
        reference_comparisons.append(
            {
                "run": label,
                "resolved_by_reference": resolved,
                "regressed_vs_reference": regressed,
            }
        )

    failure_sets = [set(v) for v in failed_ids_by_run.values()]
    shared_all = sorted(set.intersection(*failure_sets)) if failure_sets else []
    non_ref_sets = [
        set(failed_ids_by_run[label]) for label in failed_ids_by_run if label != args.reference
    ]
    shared_non_ref = sorted(set.intersection(*non_ref_sets)) if non_ref_sets else []

    summary = {
        "reference_run": args.reference,
        "runs": runs,
        "reference_comparisons": reference_comparisons,
        "shared_failures_all_runs": shared_all,
        "shared_failures_non_reference": shared_non_ref,
    }

    Path(args.output_json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    Path(args.output_md).write_text(render_markdown(summary), encoding="utf-8")

    print(f"runs={len(runs)}")
    print(f"reference={args.reference}")


if __name__ == "__main__":
    main()