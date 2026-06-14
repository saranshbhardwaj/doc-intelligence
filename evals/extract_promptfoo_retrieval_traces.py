import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract parsed retrieval payloads from a promptfoo results JSON file."
    )
    parser.add_argument("--input", required=True, help="Path to promptfoo results JSON")
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write extracted JSONL records",
    )
    parser.add_argument(
        "--provider",
        default="haiku-retrieval",
        help="Provider label to extract from the promptfoo results",
    )
    return parser.parse_args()


def load_results(input_path: Path) -> dict:
    return json.loads(input_path.read_text(encoding="utf-8"))


def extract_records(payload: dict, provider_label: str) -> list[dict]:
    records = []
    results = payload.get("results", {}).get("results", [])

    for item in results:
        provider = item.get("provider", {})
        if provider.get("label") != provider_label:
            continue

        response_output = item.get("response", {}).get("output")
        if not response_output:
            continue

        parsed_output = json.loads(response_output)
        test_case_vars = item.get("testCase", {}).get("vars", {})

        records.append(
            {
                "benchmark_question_id": test_case_vars.get("benchmark_question_id"),
                "ablation_id": test_case_vars.get("ablation_id"),
                "provider_label": provider.get("label"),
                "success": item.get("success"),
                "score": item.get("score"),
                "query": test_case_vars.get("query") or parsed_output.get("query"),
                "document_ids": test_case_vars.get("document_ids"),
                "expected_pages": test_case_vars.get("expected_pages"),
                "expected_anchors": test_case_vars.get("expected_anchors"),
                "benchmark_gold_evidence": test_case_vars.get("benchmark_gold_evidence"),
                "benchmark_target_document_ids": test_case_vars.get(
                    "benchmark_target_document_ids"
                ),
                "chunk_count": parsed_output.get("chunk_count"),
                "candidate_trace_count": len(parsed_output.get("candidate_trace", [])),
                "output": parsed_output,
            }
        )

    return records


def write_jsonl(output_path: Path, records: list[dict]) -> None:
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    payload = load_results(input_path)
    records = extract_records(payload, args.provider)
    write_jsonl(output_path, records)

    print(f"records={len(records)}")
    for record in records:
        question_id = record.get("benchmark_question_id") or "unknown"
        trace_count = record.get("candidate_trace_count")
        print(f"{question_id}: candidate_trace_count={trace_count}")


if __name__ == "__main__":
    main()