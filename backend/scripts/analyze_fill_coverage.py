"""Diagnose field coverage for a completed fill run.

Cross-references all fields/tables defined in re_investment_v1.yaml against
the llm_io_logs table to show exactly why each field was or wasn't filled:

    FOUND        – LLM returned a non-null value
    NULL         – LLM received the field but returned null (value absent from PDF)
    NOT_SENT     – Field was never included in an LLM request (routing/batching gap)
    ALIAS_MATCH  – Filled by deterministic alias matching in Stage 1 (no LLM needed)

Usage:
    cd backend
    python -m scripts.analyze_fill_coverage --fill-run-id <uuid>
    python -m scripts.analyze_fill_coverage --fill-run-id <uuid> --json > report.json
    python -m scripts.analyze_fill_coverage --fill-run-id <uuid> --stage extract_schema_fields
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

import app.db_models          # noqa: F401
import app.db_models_users    # noqa: F401
import app.db_models_chat     # noqa: F401
import app.db_models_workflows  # noqa: F401
import app.db_models_documents  # noqa: F401
import app.db_models_templates  # noqa: F401
import app.db_models_io_logs    # noqa: F401  — registers LLMIOLog with SQLAlchemy mapper

import yaml
from app.database import get_db
from app.db_models_templates import TemplateFillRun
from app.db_models_io_logs import LLMIOLog
from app.utils.logging import logger

SCHEMA_PATH = Path(__file__).parent.parent / (
    "app/verticals/real_estate/template_filling/excel/schema_based/schemas/re_investment_v1.yaml"
)

STATUS_FOUND = "FOUND"
STATUS_NULL = "NULL"
STATUS_NOT_SENT = "NOT_SENT"
STATUS_ALIAS_MATCH = "ALIAS_MATCH"


def load_schema() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _normalize_stage(stage: str) -> str:
    if stage.startswith("auto_map_fields"):
        return "auto_map_fields"
    return stage


def _parse_output(entry: LLMIOLog) -> dict:
    """Parse the output field from an io_log entry (stored as JSON string)."""
    if not entry.output:
        return {}
    try:
        return json.loads(entry.output)
    except (json.JSONDecodeError, TypeError):
        return {}


def analyze(fill_run: TemplateFillRun, io_logs: list[LLMIOLog], filter_stage: str | None) -> dict:
    schema = load_schema()
    schema_fields = {f["id"]: f for f in schema.get("fields", [])}
    schema_tables = {t["id"]: t for t in schema.get("tables", [])}

    field_mapping = fill_run.field_mapping or {}

    # -----------------------------------------------------------------------
    # Collect what Stage 1 alias-matched (deterministic, no LLM)
    # -----------------------------------------------------------------------
    alias_matched_field_ids: set[str] = set()
    schema_mappings = field_mapping.get("schema_mappings", {})
    for fid in schema_fields:
        if fid in schema_mappings:
            alias_matched_field_ids.add(fid)

    # -----------------------------------------------------------------------
    # Build field status from extract_schema_fields io_log entries
    # -----------------------------------------------------------------------
    # metadata_.unmapped_fields tells us which fields were sent to the LLM.
    # output.results tells us which fields came back with a non-null value.

    sent_field_ids: set[str] = set()
    found_field_ids: set[str] = set()

    for entry in io_logs:
        if _normalize_stage(entry.stage) != "extract_schema_fields":
            continue
        if filter_stage and filter_stage != "extract_schema_fields":
            continue

        metadata = entry.metadata_ or {}
        for uf in metadata.get("unmapped_fields", []):
            if fid := uf.get("id"):
                sent_field_ids.add(fid)

        output = _parse_output(entry)
        for r in output.get("results", []):
            if r.get("value"):
                found_field_ids.add(r["field_id"])

    # -----------------------------------------------------------------------
    # Build table status from extract_table_values_rag entries
    # -----------------------------------------------------------------------
    sent_table_ids: set[str] = set()
    found_table_ids: set[str] = set()
    table_row_counts: dict[str, int] = {}

    for entry in io_logs:
        stage = _normalize_stage(entry.stage)
        if stage not in ("extract_table_values_rag", "extract_table_values_rag_single"):
            continue
        if filter_stage and filter_stage not in ("extract_table_values_rag", "extract_table_values_rag_single"):
            continue

        output = _parse_output(entry)
        for t in output.get("results", []):
            tid = t.get("table_id", "")
            if not tid:
                continue
            sent_table_ids.add(tid)
            rows = t.get("rows", [])
            if rows:
                found_table_ids.add(tid)
            # Keep the highest row count if the same table_id appears in multiple entries
            table_row_counts[tid] = max(table_row_counts.get(tid, 0), len(rows))

    # -----------------------------------------------------------------------
    # Classify every schema field
    # -----------------------------------------------------------------------
    field_results: list[dict] = []
    counts = {STATUS_FOUND: 0, STATUS_NULL: 0, STATUS_NOT_SENT: 0, STATUS_ALIAS_MATCH: 0}

    for fid, fdef in schema_fields.items():
        if fid in alias_matched_field_ids:
            status = STATUS_ALIAS_MATCH
        elif fid in found_field_ids:
            status = STATUS_FOUND
        elif fid in sent_field_ids:
            status = STATUS_NULL
        else:
            status = STATUS_NOT_SENT

        counts[status] += 1
        field_results.append({
            "field_id": fid,
            "sheet": fdef.get("sheet"),
            "data_type": fdef.get("data_type"),
            "status": status,
            "aliases": fdef.get("pdf_aliases", []),
        })

    # -----------------------------------------------------------------------
    # Classify every schema table
    # -----------------------------------------------------------------------
    table_results: list[dict] = []
    for tid, tdef in schema_tables.items():
        if tid in found_table_ids:
            status = STATUS_FOUND
        elif tid in sent_table_ids:
            status = STATUS_NULL
        else:
            status = STATUS_NOT_SENT

        table_results.append({
            "table_id": tid,
            "sheet": tdef.get("sheet"),
            "status": status,
            "rows_returned": table_row_counts.get(tid, 0),
            "expected_rows": (
                (tdef.get("data_end_row", 0) or 0)
                - (tdef.get("data_start_row", 1) or 1)
                + 1
            ),
        })

    total_fields = len(schema_fields)
    total_tables = len(schema_tables)

    return {
        "fill_run_id": fill_run.id,
        "summary": {
            "fields": {
                "total": total_fields,
                **counts,
                "fill_rate_pct": round(
                    100 * (counts[STATUS_FOUND] + counts[STATUS_ALIAS_MATCH]) / max(total_fields, 1), 1
                ),
            },
            "tables": {
                "total": total_tables,
                "found": sum(1 for t in table_results if t["status"] == STATUS_FOUND),
                "null": sum(1 for t in table_results if t["status"] == STATUS_NULL),
                "not_sent": sum(1 for t in table_results if t["status"] == STATUS_NOT_SENT),
            },
        },
        "fields": field_results,
        "tables": table_results,
    }


def print_report(report: dict, filter_stage: str | None) -> None:
    s = report["summary"]
    fld = s["fields"]
    tbl = s["tables"]

    print(f"\n{'='*60}")
    print(f"Fill Run: {report['fill_run_id']}")
    print(f"{'='*60}")
    print(f"\nFIELD COVERAGE  ({fld['total']} total schema fields)")
    print(f"  {STATUS_ALIAS_MATCH:<12}  {fld[STATUS_ALIAS_MATCH]:>4}  (deterministic alias match, no LLM)")
    print(f"  {STATUS_FOUND:<12}  {fld[STATUS_FOUND]:>4}  (LLM extracted value)")
    print(f"  {STATUS_NULL:<12}  {fld[STATUS_NULL]:>4}  (LLM looked, value absent from PDF)")
    print(f"  {STATUS_NOT_SENT:<12}  {fld[STATUS_NOT_SENT]:>4}  (never sent to LLM — routing gap)")
    print(f"  {'TOTAL FILLED':<12}  {fld[STATUS_ALIAS_MATCH] + fld[STATUS_FOUND]:>4} / {fld['total']}  ({fld['fill_rate_pct']}%)")

    print(f"\nTABLE COVERAGE  ({tbl['total']} total schema tables)")
    print(f"  {STATUS_FOUND:<12}  {tbl['found']:>4}")
    print(f"  {STATUS_NULL:<12}  {tbl['null']:>4}  (sent but no rows returned)")
    print(f"  {STATUS_NOT_SENT:<12}  {tbl['not_sent']:>4}  (never sent to LLM)")

    not_sent = [f for f in report["fields"] if f["status"] == STATUS_NOT_SENT]
    if not_sent:
        print(f"\nNOT_SENT fields ({len(not_sent)}) — check routing/batching logic:")
        for f in not_sent:
            print(f"  [{f['sheet']}] {f['field_id']}  aliases={f['aliases'][:2]}")

    not_sent_tables = [t for t in report["tables"] if t["status"] == STATUS_NOT_SENT]
    if not_sent_tables:
        print(f"\nNOT_SENT tables ({len(not_sent_tables)}):")
        for t in not_sent_tables:
            print(f"  [{t['sheet']}] {t['table_id']}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Analyze field coverage for a fill run")
    parser.add_argument("--fill-run-id", required=True, help="TemplateFillRun UUID")
    parser.add_argument(
        "--stage",
        choices=["extract_schema_fields", "extract_table_values_rag", "extract_table_values_rag_single"],
        default=None,
        help="Focus on a specific stage (default: all stages)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        dest="json_output",
        help="Output machine-readable JSON instead of console summary",
    )
    args = parser.parse_args()

    db = next(get_db())
    try:
        fill_run = db.query(TemplateFillRun).filter(TemplateFillRun.id == args.fill_run_id).first()
        if not fill_run:
            print(f"Fill run not found: {args.fill_run_id}", file=sys.stderr)
            sys.exit(1)
        if fill_run.status != "completed":
            print(
                f"Warning: fill run status is '{fill_run.status}' (expected 'completed')",
                file=sys.stderr,
            )

        # Load io_logs from the dedicated table (source_id = fill_run_id)
        io_logs = (
            db.query(LLMIOLog)
            .filter(
                LLMIOLog.source_type == "template_fill",
                LLMIOLog.source_id == args.fill_run_id,
            )
            .order_by(LLMIOLog.created_at)
            .all()
        )

        if not io_logs:
            print(
                f"No io_log entries found for fill run {args.fill_run_id}.\n"
                "Make sure CAPTURE_LLM_IO_LOG=true was set when the fill ran.",
                file=sys.stderr,
            )
            sys.exit(1)

        logger.info(f"Loaded {len(io_logs)} io_log entries for fill run {args.fill_run_id}")

        report = analyze(fill_run, io_logs, args.stage)

        if args.json_output:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print_report(report, args.stage)

    finally:
        db.close()


if __name__ == "__main__":
    main()
