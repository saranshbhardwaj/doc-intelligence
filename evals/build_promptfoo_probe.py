import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a promptfoo JSONL probe slice from a canonical source dataset."
    )
    parser.add_argument("--source", required=True, help="Source JSONL file")
    parser.add_argument("--output", required=True, help="Output JSONL file")
    parser.add_argument(
        "--question-id",
        dest="question_ids",
        action="append",
        required=True,
        help="Benchmark question id to include; pass multiple times to preserve order",
    )
    parser.add_argument(
        "--ablation-id",
        help="If set, override vars.ablation_id for every emitted row",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = Path(args.source)
    output_path = Path(args.output)

    rows = [
        json.loads(line)
        for line in source_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_question_id = {
        row.get("vars", {}).get("benchmark_question_id"): row for row in rows
    }

    selected_rows = []
    missing = []
    for question_id in args.question_ids:
        row = by_question_id.get(question_id)
        if row is None:
            missing.append(question_id)
            continue
        row = json.loads(json.dumps(row))
        if args.ablation_id:
            row.setdefault("vars", {})["ablation_id"] = args.ablation_id
        selected_rows.append(row)

    if missing:
        raise SystemExit(f"Missing question ids: {', '.join(missing)}")

    output_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in selected_rows) + "\n",
        encoding="utf-8",
    )

    print(f"rows={len(selected_rows)}")
    print("question_ids=" + ",".join(args.question_ids))


if __name__ == "__main__":
    main()