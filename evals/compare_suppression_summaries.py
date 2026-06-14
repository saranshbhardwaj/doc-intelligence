import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare two structured-suppression summary JSON artifacts."
    )
    parser.add_argument("--a-label", required=True)
    parser.add_argument("--a-json", required=True)
    parser.add_argument("--b-label", required=True)
    parser.add_argument("--b-json", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    return parser.parse_args()


def load_summary(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dropped_ids(summary: dict) -> list[str]:
    return sorted(
        row["benchmark_question_id"]
        for row in summary.get("queries", [])
        if row.get("interpretation") == "Relevant structured evidence dropped from final selection"
    )


def downranked_retained_ids(summary: dict) -> list[str]:
    return sorted(
        row["benchmark_question_id"]
        for row in summary.get("queries", [])
        if row.get("interpretation") == "Relevant structured evidence downranked but retained"
    )


def pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def render_markdown(result: dict) -> str:
    a = result["a"]
    b = result["b"]
    lines = [
        "# Structured Suppression Comparison",
        "",
        f"Comparing `{a['label']}` vs `{b['label']}`.",
        "",
        "| Metric | " + a["label"] + " | " + b["label"] + " | Delta (" + b["label"] + " - " + a["label"] + ") |",
        "| --- | ---: | ---: | ---: |",
        f"| queries_total | {a['queries_total']} | {b['queries_total']} | {b['queries_total'] - a['queries_total']} |",
        f"| relevant_structured_found | {a['relevant_structured_found']} | {b['relevant_structured_found']} | {b['relevant_structured_found'] - a['relevant_structured_found']} |",
        f"| relevant_structured_dropped | {a['relevant_structured_dropped']} | {b['relevant_structured_dropped']} | {b['relevant_structured_dropped'] - a['relevant_structured_dropped']} |",
        f"| drop_rate_among_found_pct | {a['drop_rate_among_found_pct']} | {b['drop_rate_among_found_pct']} | {round(b['drop_rate_among_found_pct'] - a['drop_rate_among_found_pct'], 2)} |",
        f"| relevant_structured_retained | {a['relevant_structured_retained']} | {b['relevant_structured_retained']} | {b['relevant_structured_retained'] - a['relevant_structured_retained']} |",
        f"| downranked_retained_count | {a['downranked_retained_count']} | {b['downranked_retained_count']} | {b['downranked_retained_count'] - a['downranked_retained_count']} |",
        f"| downranked_retained_rate_among_found_pct | {a['downranked_retained_rate_among_found_pct']} | {b['downranked_retained_rate_among_found_pct']} | {round(b['downranked_retained_rate_among_found_pct'] - a['downranked_retained_rate_among_found_pct'], 2)} |",
        f"| without_relevant_structured_candidate | {a['without_relevant_structured_candidate']} | {b['without_relevant_structured_candidate']} | {b['without_relevant_structured_candidate'] - a['without_relevant_structured_candidate']} |",
        f"| missing_candidate_rate_pct | {a['missing_candidate_rate_pct']} | {b['missing_candidate_rate_pct']} | {round(b['missing_candidate_rate_pct'] - a['missing_candidate_rate_pct'], 2)} |",
        "",
        "## Dropped Relevant Structured IDs",
        "",
        f"- {a['label']}: " + (", ".join(f"`{qid}`" for qid in a["dropped_ids"]) if a["dropped_ids"] else "none"),
        f"- {b['label']}: " + (", ".join(f"`{qid}`" for qid in b["dropped_ids"]) if b["dropped_ids"] else "none"),
        "",
        "## Set Overlap",
        "",
        "- dropped_in_both: " + (
            ", ".join(f"`{qid}`" for qid in result["dropped_overlap"]) if result["dropped_overlap"] else "none"
        ),
        "- dropped_only_in_" + a["label"] + ": " + (
            ", ".join(f"`{qid}`" for qid in result["dropped_only_a"]) if result["dropped_only_a"] else "none"
        ),
        "- dropped_only_in_" + b["label"] + ": " + (
            ", ".join(f"`{qid}`" for qid in result["dropped_only_b"]) if result["dropped_only_b"] else "none"
        ),
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    a_summary = load_summary(Path(args.a_json))
    b_summary = load_summary(Path(args.b_json))

    a_direct = a_summary.get("direct_signal", {})
    b_direct = b_summary.get("direct_signal", {})

    a_dropped = dropped_ids(a_summary)
    b_dropped = dropped_ids(b_summary)
    a_downranked = downranked_retained_ids(a_summary)
    b_downranked = downranked_retained_ids(b_summary)

    a_found = a_direct.get("queries_with_relevant_structured_candidate", 0)
    b_found = b_direct.get("queries_with_relevant_structured_candidate", 0)
    a_total = a_direct.get("queries_total", 0)
    b_total = b_direct.get("queries_total", 0)

    result = {
        "a": {
            "label": args.a_label,
            "queries_total": a_total,
            "relevant_structured_found": a_found,
            "without_relevant_structured_candidate": a_direct.get("queries_without_relevant_structured_candidate", 0),
            "relevant_structured_dropped": a_direct.get("queries_where_relevant_structured_dropped", 0),
            "relevant_structured_retained": a_direct.get("queries_where_relevant_structured_retained", 0),
            "drop_rate_among_found_pct": pct(
                a_direct.get("queries_where_relevant_structured_dropped", 0), a_found
            ),
            "missing_candidate_rate_pct": pct(
                a_direct.get("queries_without_relevant_structured_candidate", 0), a_total
            ),
            "dropped_ids": a_dropped,
            "downranked_retained_ids": a_downranked,
            "downranked_retained_count": len(a_downranked),
            "downranked_retained_rate_among_found_pct": pct(len(a_downranked), a_found),
        },
        "b": {
            "label": args.b_label,
            "queries_total": b_total,
            "relevant_structured_found": b_found,
            "without_relevant_structured_candidate": b_direct.get("queries_without_relevant_structured_candidate", 0),
            "relevant_structured_dropped": b_direct.get("queries_where_relevant_structured_dropped", 0),
            "relevant_structured_retained": b_direct.get("queries_where_relevant_structured_retained", 0),
            "drop_rate_among_found_pct": pct(
                b_direct.get("queries_where_relevant_structured_dropped", 0), b_found
            ),
            "missing_candidate_rate_pct": pct(
                b_direct.get("queries_without_relevant_structured_candidate", 0), b_total
            ),
            "dropped_ids": b_dropped,
            "downranked_retained_ids": b_downranked,
            "downranked_retained_count": len(b_downranked),
            "downranked_retained_rate_among_found_pct": pct(len(b_downranked), b_found),
        },
        "dropped_overlap": sorted(set(a_dropped) & set(b_dropped)),
        "dropped_only_a": sorted(set(a_dropped) - set(b_dropped)),
        "dropped_only_b": sorted(set(b_dropped) - set(a_dropped)),
    }

    Path(args.output_json).write_text(json.dumps(result, indent=2), encoding="utf-8")
    Path(args.output_md).write_text(render_markdown(result), encoding="utf-8")
    print("comparison_written")


if __name__ == "__main__":
    main()