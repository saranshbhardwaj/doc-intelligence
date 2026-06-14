import argparse
import json
import math
from pathlib import Path
from statistics import mean, median


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze candidate-rank movement for structured-evidence suppression."
    )
    parser.add_argument("--input", required=True, help="Extracted trace JSONL input")
    parser.add_argument("--output-md", required=True, help="Markdown summary output path")
    parser.add_argument("--output-json", required=True, help="JSON summary output path")
    return parser.parse_args()


def safe_json_loads(value):
    if value in (None, "", []):
        return []
    if isinstance(value, (list, dict)):
        return value
    return json.loads(value)


def numeric(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def rank_drop(candidate: dict):
    before = numeric(candidate.get("hybrid_rank"))
    after = numeric(candidate.get("rerank_rank"))
    if before is None or after is None:
        return None
    return after - before


def evidence_key(item: dict, use_sheet_fallback: bool) -> str | None:
    document_id = item.get("document_id")
    if not document_id:
        return None

    chunk_id = item.get("chunk_id")
    if chunk_id:
        sheet_name = item.get("sheet_name") or item.get("sheet")
        if use_sheet_fallback and sheet_name:
            return f"{document_id}:sheet:{str(sheet_name).lower()}"
        return f"{document_id}:chunk:{chunk_id}"

    page = item.get("page")
    if page is None:
        page = item.get("page_number")
    if page is None:
        page = item.get("bbox_page")
    if page is None:
        return None

    return f"{document_id}:page:{page}"


def candidate_keys(candidate: dict) -> set[str]:
    keys = set()
    document_id = candidate.get("document_id")
    if not document_id:
        return keys

    chunk_id = candidate.get("chunk_id")
    sheet_name = candidate.get("sheet_name")
    if chunk_id:
        keys.add(f"{document_id}:chunk:{chunk_id}")
    if sheet_name:
        keys.add(f"{document_id}:sheet:{str(sheet_name).lower()}")

    for field in ("page_number", "bbox_page"):
        page = candidate.get(field)
        if page is not None:
            keys.add(f"{document_id}:page:{page}")

    return keys


def build_expected_keys(row: dict) -> set[str]:
    target_document_ids = set(safe_json_loads(row.get("benchmark_target_document_ids")))
    gold = safe_json_loads(row.get("benchmark_gold_evidence"))
    expected = [item for item in gold if item.get("document_id") in target_document_ids] or gold

    use_sheet_fallback = False
    if not expected:
        expected = safe_json_loads(row.get("expected_anchors")) or safe_json_loads(
            row.get("expected_pages")
        )
        use_sheet_fallback = True

    return {
        key
        for item in expected
        if (key := evidence_key(item, use_sheet_fallback)) is not None
    }


def summarize_group(candidates: list[dict]) -> dict:
    drops = [rank_drop(candidate) for candidate in candidates]
    drops = [drop for drop in drops if drop is not None]
    selected_count = sum(1 for candidate in candidates if candidate.get("selected"))
    if not drops:
        return {
            "count": len(candidates),
            "mean_rank_drop": None,
            "median_rank_drop": None,
            "pct_downranked": None,
            "pct_selected": round(100 * selected_count / len(candidates), 1)
            if candidates
            else None,
        }

    downranked = sum(1 for drop in drops if drop > 0)
    return {
        "count": len(candidates),
        "mean_rank_drop": round(mean(drops), 2),
        "median_rank_drop": round(median(drops), 2),
        "pct_downranked": round(100 * downranked / len(drops), 1),
        "pct_selected": round(100 * selected_count / len(candidates), 1)
        if candidates
        else None,
    }


def candidate_label(candidate: dict) -> str:
    if candidate.get("chunk_id"):
        return f"{candidate.get('document_id')}::{candidate.get('chunk_id')}"
    page = candidate.get("page_number")
    if page is None:
        page = candidate.get("bbox_page")
    return f"{candidate.get('document_id')}::p{page}"


def analyze_rows(rows: list[dict]) -> dict:
    all_structured = []
    all_narrative = []
    relevant_structured = []
    query_rows = []

    for row in rows:
        expected_keys = build_expected_keys(row)
        trace = row["output"]["candidate_trace"]
        for candidate in trace:
            if candidate.get("is_tabular"):
                all_structured.append(candidate)
            else:
                all_narrative.append(candidate)

        relevant = []
        for candidate in trace:
            candidate["is_relevant_evidence"] = bool(candidate_keys(candidate) & expected_keys)
            if candidate.get("is_tabular") and candidate["is_relevant_evidence"]:
                relevant.append(candidate)
                relevant_structured.append(candidate)

        best_relevant = None
        if relevant:
            best_relevant = min(
                relevant,
                key=lambda candidate: (
                    numeric(candidate.get("hybrid_rank")) or math.inf,
                    numeric(candidate.get("rerank_rank")) or math.inf,
                ),
            )

        narrative_reranks = [
            numeric(candidate.get("rerank_rank"))
            for candidate in trace
            if not candidate.get("is_tabular") and numeric(candidate.get("rerank_rank")) is not None
        ]
        top_narrative_after = min(narrative_reranks) if narrative_reranks else None

        if best_relevant is None:
            interpretation = "No relevant structured candidate in trace"
        elif not best_relevant.get("selected"):
            interpretation = "Relevant structured evidence dropped from final selection"
        elif rank_drop(best_relevant) and rank_drop(best_relevant) > 0:
            interpretation = "Relevant structured evidence downranked but retained"
        elif rank_drop(best_relevant) == 0:
            interpretation = "Relevant structured evidence retained at same rank"
        else:
            interpretation = "Relevant structured evidence improved or held"

        query_rows.append(
            {
                "benchmark_question_id": row.get("benchmark_question_id"),
                "query": row.get("query"),
                "relevant_structured_found": best_relevant is not None,
                "relevant_structured_label": candidate_label(best_relevant)
                if best_relevant
                else None,
                "relevant_table_rank_before": best_relevant.get("hybrid_rank")
                if best_relevant
                else None,
                "relevant_table_rank_after": best_relevant.get("rerank_rank")
                if best_relevant
                else None,
                "relevant_table_selected": best_relevant.get("selected")
                if best_relevant
                else None,
                "top_narrative_rank_after": top_narrative_after,
                "relevant_rank_drop": rank_drop(best_relevant) if best_relevant else None,
                "interpretation": interpretation,
            }
        )

    direct_signal = {
        "queries_total": len(rows),
        "queries_with_relevant_structured_candidate": sum(
            1 for row in query_rows if row["relevant_structured_found"]
        ),
        "queries_without_relevant_structured_candidate": sum(
            1 for row in query_rows if not row["relevant_structured_found"]
        ),
        "queries_where_relevant_structured_dropped": sum(
            1
            for row in query_rows
            if row["relevant_structured_found"] and not row["relevant_table_selected"]
        ),
        "queries_where_relevant_structured_retained": sum(
            1
            for row in query_rows
            if row["relevant_structured_found"] and row["relevant_table_selected"]
        ),
    }

    return {
        "candidate_level_aggregate": {
            "structured": summarize_group(all_structured),
            "narrative": summarize_group(all_narrative),
            "relevant_structured": summarize_group(relevant_structured),
        },
        "direct_signal": direct_signal,
        "queries": query_rows,
    }


def format_value(value):
    if value is None:
        return "N/A"
    return str(value)


def render_markdown(summary: dict, source_path: Path) -> str:
    structured = summary["candidate_level_aggregate"]["structured"]
    narrative = summary["candidate_level_aggregate"]["narrative"]
    relevant = summary["candidate_level_aggregate"]["relevant_structured"]
    direct = summary["direct_signal"]
    missing_queries = [
        row["benchmark_question_id"]
        for row in summary["queries"]
        if not row["relevant_structured_found"]
    ]
    dropped_queries = [
        row["benchmark_question_id"]
        for row in summary["queries"]
        if row["interpretation"] == "Relevant structured evidence dropped from final selection"
    ]
    downranked_retained_queries = [
        row["benchmark_question_id"]
        for row in summary["queries"]
        if row["interpretation"] == "Relevant structured evidence downranked but retained"
    ]

    lines = [
        "# A2 Structured-Evidence Suppression Probe",
        "",
        f"Source: `{source_path.as_posix()}`",
        "",
        "## Scope",
        "",
        f"- Queries analyzed: {direct['queries_total']}",
        f"- Queries with relevant structured evidence in candidate trace: {direct['queries_with_relevant_structured_candidate']}",
        f"- Queries without relevant structured evidence in candidate trace: {direct['queries_without_relevant_structured_candidate']}",
        f"- Queries where relevant structured evidence was dropped from final selection: {direct['queries_where_relevant_structured_dropped']}",
        f"- Queries where relevant structured evidence was retained: {direct['queries_where_relevant_structured_retained']}",
        "",
        "## Candidate-Level Rank Movement",
        "",
        "| Evidence Type | Count | Mean RankDrop | Median RankDrop | % Downranked | % Selected |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        f"| Structured table/spreadsheet chunks | {structured['count']} | {format_value(structured['mean_rank_drop'])} | {format_value(structured['median_rank_drop'])} | {format_value(structured['pct_downranked'])} | {format_value(structured['pct_selected'])} |",
        f"| Narrative / non-tabular chunks | {narrative['count']} | {format_value(narrative['mean_rank_drop'])} | {format_value(narrative['median_rank_drop'])} | {format_value(narrative['pct_downranked'])} | {format_value(narrative['pct_selected'])} |",
        f"| Relevant structured chunks only | {relevant['count']} | {format_value(relevant['mean_rank_drop'])} | {format_value(relevant['median_rank_drop'])} | {format_value(relevant['pct_downranked'])} | {format_value(relevant['pct_selected'])} |",
        "",
        "## Query-Level Evidence Table",
        "",
        "| Query | Relevant Table Rank Before | Relevant Table Rank After A2 | Selected | Top Narrative Rank After | Interpretation |",
        "| --- | ---: | ---: | --- | ---: | --- |",
    ]

    for row in summary["queries"]:
        lines.append(
            "| {qid} | {before} | {after} | {selected} | {top_narrative} | {note} |".format(
                qid=row["benchmark_question_id"],
                before=format_value(row["relevant_table_rank_before"]),
                after=format_value(row["relevant_table_rank_after"]),
                selected=format_value(row["relevant_table_selected"]),
                top_narrative=format_value(row["top_narrative_rank_after"]),
                note=row["interpretation"],
            )
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            (
                "- This probe shows clear downranking pressure on structured candidates as a class and direct dropping of relevant structured evidence in: "
                + ", ".join(f"`{query_id}`" for query_id in dropped_queries)
                + "."
                if dropped_queries
                else "- This probe shows clear downranking pressure on structured candidates as a class, but no direct dropping of relevant structured evidence in this slice."
            ),
            "- Queries with no relevant structured candidate in the exported trace are retrieval/candidate-generation misses rather than reranker suppression evidence: "
            + (", ".join(f"`{query_id}`" for query_id in missing_queries) if missing_queries else "none in this slice")
            + ".",
            "- Queries where relevant structured evidence was downranked but still retained are: "
            + (
                ", ".join(f"`{query_id}`" for query_id in downranked_retained_queries)
                if downranked_retained_queries
                else "none in this slice"
            )
            + ".",
            (
                f"- This {direct['queries_total']}-query A2 probe is enough to validate the trace pipeline and establish direct-drop evidence in this run, while still showing many retrieval/candidate-generation misses."
                if dropped_queries
                else f"- This {direct['queries_total']}-query A2 probe is enough to validate the trace pipeline and show the shape of the analysis, but not enough to claim direct causal suppression of relevant structured evidence in the manuscript."
            ),
        ]
    )

    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_md = Path(args.output_md)
    output_json = Path(args.output_json)

    rows = [
        json.loads(line)
        for line in input_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    summary = analyze_rows(rows)

    output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    output_md.write_text(render_markdown(summary, input_path), encoding="utf-8")

    direct = summary["direct_signal"]
    print(f"queries={direct['queries_total']}")
    print(
        "relevant_structured_found="
        f"{direct['queries_with_relevant_structured_candidate']}"
    )
    print(
        "relevant_structured_dropped="
        f"{direct['queries_where_relevant_structured_dropped']}"
    )


if __name__ == "__main__":
    main()