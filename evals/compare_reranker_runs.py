import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two retrieval run summaries for reranker validation.")
    parser.add_argument("--a-label", required=True)
    parser.add_argument("--a-summary", required=True)
    parser.add_argument("--b-label", required=True)
    parser.add_argument("--b-summary", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    return parser.parse_args()


def load_single_run(summary_path: Path) -> dict:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    runs = payload.get("runs", {})
    if len(runs) != 1:
        raise ValueError(f"Expected exactly one run in summary: {summary_path}")
    return next(iter(runs.values()))


def pct(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value * 100.0, 2)


def fmt(value: float | int | None, decimals: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{decimals}f}"


def render_markdown(result: dict) -> str:
    a = result["a"]
    b = result["b"]
    rows = [
        ("cases", a["cases"], b["cases"], b["cases"] - a["cases"]),
        ("strict_pass_count", a["strict_pass_count"], b["strict_pass_count"], b["strict_pass_count"] - a["strict_pass_count"]),
        ("strict_pass_rate_pct", a["strict_pass_rate_pct"], b["strict_pass_rate_pct"], b["strict_pass_rate_pct"] - a["strict_pass_rate_pct"]),
        ("page_recall_pct", a["page_recall_pct"], b["page_recall_pct"], b["page_recall_pct"] - a["page_recall_pct"]),
        ("table_recall_pct", a["table_recall_pct"], b["table_recall_pct"], b["table_recall_pct"] - a["table_recall_pct"]),
        ("scope_error_rate_pct", a["scope_error_rate_pct"], b["scope_error_rate_pct"], b["scope_error_rate_pct"] - a["scope_error_rate_pct"]),
        ("avg_latency_ms", a["avg_latency_ms"], b["avg_latency_ms"], b["avg_latency_ms"] - a["avg_latency_ms"]),
    ]

    lines = [
        "# Cross-Reranker Comparison (A6)",
        "",
        f"Comparing `{a['label']}` vs `{b['label']}` on the same full-96 retrieval fixture.",
        "",
        "| Metric | " + a["label"] + " | " + b["label"] + " | Delta (" + b["label"] + " - " + a["label"] + ") |",
        "| --- | ---: | ---: | ---: |",
    ]
    for metric, av, bv, dv in rows:
        lines.append(f"| {metric} | {fmt(av)} | {fmt(bv)} | {fmt(dv)} |")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    a_run = load_single_run(Path(args.a_summary))
    b_run = load_single_run(Path(args.b_summary))

    a_cases = int(a_run.get("cases", 0))
    b_cases = int(b_run.get("cases", 0))
    a_rate = float(a_run.get("page_recall_80_pass_rate", 0.0))
    b_rate = float(b_run.get("page_recall_80_pass_rate", 0.0))

    result = {
        "a": {
            "label": args.a_label,
            "cases": a_cases,
            "strict_pass_count": round(a_rate * a_cases),
            "strict_pass_rate_pct": pct(a_rate),
            "page_recall_pct": pct(a_run.get("page_recall")),
            "table_recall_pct": pct(a_run.get("table_recall")),
            "scope_error_rate_pct": pct(a_run.get("scope_error_rate")),
            "avg_latency_ms": round(float(a_run.get("avg_latency_ms", 0.0)), 2),
        },
        "b": {
            "label": args.b_label,
            "cases": b_cases,
            "strict_pass_count": round(b_rate * b_cases),
            "strict_pass_rate_pct": pct(b_rate),
            "page_recall_pct": pct(b_run.get("page_recall")),
            "table_recall_pct": pct(b_run.get("table_recall")),
            "scope_error_rate_pct": pct(b_run.get("scope_error_rate")),
            "avg_latency_ms": round(float(b_run.get("avg_latency_ms", 0.0)), 2),
        },
    }

    Path(args.output_json).write_text(json.dumps(result, indent=2), encoding="utf-8")
    Path(args.output_md).write_text(render_markdown(result), encoding="utf-8")
    print("comparison_written")


if __name__ == "__main__":
    main()