"""Export llm_io_log entries from completed fill runs as promptfoo test fixtures.

Usage:
    cd backend
    python -m scripts.export_eval_dataset --output ../evals/datasets
    python -m scripts.export_eval_dataset --stage extract_schema_fields --limit 20 --output ../evals/datasets
    python -m scripts.export_eval_dataset --version v2 --output ../evals/datasets/v2

The output directory will contain one JSONL file per stage. Each line is a promptfoo
test case with vars (system_prompt, user_message) and structural assertions.
Datasets are gitignored — they contain actual offering memorandum text.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, ".")

from app.database import get_db
from app.utils.logging import logger

import app.db_models  # noqa: F401
import app.db_models_users  # noqa: F401
import app.db_models_chat  # noqa: F401
import app.db_models_workflows  # noqa: F401
import app.db_models_documents  # noqa: F401
import app.db_models_templates  # noqa: F401

from app.db_models_templates import TemplateFillRun
from app.verticals.real_estate.template_filling.prompts import get_prompt_set

SUPPORTED_STAGES = [
    "detect_fields",
    "extract_schema_fields",
    "extract_table_values_rag_single",
    "auto_map_fields",
]

ASSERTIONS = {
    "detect_fields": [
        {"type": "is-json"},
        {"type": "javascript", "value": "JSON.parse(output).fields !== undefined"},
        {"type": "javascript", "value": "typeof JSON.parse(output).total_fields === 'number'"},
        {"type": "javascript", "value": "JSON.parse(output).fields.every(f => f.confidence >= 0 && f.confidence <= 1)"},
    ],
    "extract_schema_fields": [
        {"type": "is-json"},
        {"type": "javascript", "value": "JSON.parse(output).results !== undefined"},
        {"type": "javascript", "value": "typeof JSON.parse(output).total_found === 'number'"},
        {"type": "javascript", "value": "JSON.parse(output).results.every(r => r.confidence >= 0 && r.confidence <= 1)"},
    ],
    "extract_table_values_rag_single": [
        {"type": "is-json"},
        {"type": "javascript", "value": "JSON.parse(output).results !== undefined"},
        {"type": "javascript", "value": "typeof JSON.parse(output).total_tables === 'number'"},
    ],
    "auto_map_fields": [
        {"type": "is-json"},
        {"type": "javascript", "value": "JSON.parse(output).mappings !== undefined"},
        {"type": "javascript", "value": "typeof JSON.parse(output).total_mapped === 'number'"},
        {"type": "javascript", "value": "JSON.parse(output).mappings.every(m => m.confidence >= 0 && m.confidence <= 1)"},
    ],
}


def _normalize_stage(stage: str) -> str:
    """Normalize auto_map_fields_batch_N -> auto_map_fields."""
    if stage.startswith("auto_map_fields"):
        return "auto_map_fields"
    return stage


def _reconstruct_system_prompt(entry: dict, fill_run: TemplateFillRun, version: str) -> str:
    """Reconstruct system prompt from fill run data + versioned prompt set."""
    stage = _normalize_stage(entry["stage"])
    prompt_version = version or entry.get("prompt_version", "v1")
    prompts = get_prompt_set(prompt_version)

    if stage == "detect_fields":
        # system_prompt is empty for field detection (entire prompt is in user_message)
        return ""

    if stage == "extract_table_values_rag_single":
        # system_prompt stored directly in io_log (context_json is ephemeral)
        return entry.get("system_prompt", "")

    pdf_fields = (fill_run.field_mapping or {}).get("pdf_fields", [])
    pdf_fields_json = json.dumps(pdf_fields, ensure_ascii=False)

    if stage == "extract_schema_fields":
        return prompts.build_extract_schema_fields(pdf_fields_json, []).system_prompt

    if stage == "auto_map_fields":
        return prompts.build_auto_map_system(pdf_fields_json)

    return ""


def export_fill_run(fill_run: TemplateFillRun, target_stage: str, version: str, writers: dict):
    """Export io_log entries from a single fill run into the appropriate JSONL writers."""
    io_log = fill_run.llm_io_log
    if not io_log:
        return 0

    exported = 0
    for entry in io_log:
        raw_stage = entry.get("stage", "")
        normalized = _normalize_stage(raw_stage)

        if target_stage != "all" and normalized != target_stage:
            continue

        if normalized not in ASSERTIONS:
            continue

        try:
            system_prompt = _reconstruct_system_prompt(entry, fill_run, version)
        except Exception as e:
            logger.warning(f"Could not reconstruct system_prompt for {fill_run.id}/{raw_stage}: {e}")
            continue

        test_case = {
            "vars": {
                "system_prompt": system_prompt,
                "user_message": entry.get("user_message", ""),
            },
            "assert": ASSERTIONS[normalized],
            "_metadata": {
                "fill_run_id": fill_run.id,
                "stage": normalized,
                "raw_stage": raw_stage,
                "prompt_version": entry.get("prompt_version", "v1"),
                "reference_output": entry.get("output"),
                "input_tokens": entry.get("input_tokens"),
                "output_tokens": entry.get("output_tokens"),
                "duration_ms": entry.get("duration_ms"),
            },
        }

        writers[normalized].write(json.dumps(test_case, ensure_ascii=False) + "\n")
        exported += 1

    return exported


def run(stage: str, limit: int, output_dir: str, version: str):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    stages_to_export = SUPPORTED_STAGES if stage == "all" else [stage]

    writers = {}
    for s in stages_to_export:
        path = output_path / f"{s}.jsonl"
        writers[s] = open(path, "w", encoding="utf-8")
        logger.info(f"Writing to {path}")

    db = next(get_db())
    try:
        query = (
            db.query(TemplateFillRun)
            .filter(
                TemplateFillRun.status == "completed",
                TemplateFillRun.llm_io_log.isnot(None),
            )
            .order_by(TemplateFillRun.completed_at.desc())
        )
        if limit:
            query = query.limit(limit)

        fill_runs = query.all()
        logger.info(f"Found {len(fill_runs)} completed fill runs with io_log")

        total_exported = 0
        for fill_run in fill_runs:
            n = export_fill_run(fill_run, stage, version, writers)
            total_exported += n
            if n:
                logger.info(f"  {fill_run.id}: exported {n} entries")

        logger.info(f"Done. Total test cases exported: {total_exported}")

    finally:
        db.close()
        for w in writers.values():
            w.close()


def main():
    parser = argparse.ArgumentParser(description="Export llm_io_log entries as promptfoo test fixtures")
    parser.add_argument(
        "--stage",
        choices=["all"] + SUPPORTED_STAGES,
        default="all",
        help="Which stage to export (default: all)",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max fill runs to process (0 = no limit)")
    parser.add_argument("--output", default="../evals/datasets", help="Output directory for JSONL files")
    parser.add_argument(
        "--version",
        default="",
        help="Prompt version to use for system prompt reconstruction (default: use version from io_log entry)",
    )
    args = parser.parse_args()

    run(
        stage=args.stage,
        limit=args.limit,
        output_dir=args.output,
        version=args.version,
    )


if __name__ == "__main__":
    main()
