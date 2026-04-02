"""Export llm_io_log entries as promptfoo test fixtures.

Usage:
    cd backend
    python -m scripts.export_eval_dataset --output ../evals/datasets
    python -m scripts.export_eval_dataset --stage extract_schema_fields --limit 20 --output ../evals/datasets
    python -m scripts.export_eval_dataset --version v2 --output ../evals/datasets/v2

    # Golden dataset (value-level assertions for regression testing):
    python -m scripts.export_eval_dataset --golden --limit 1 --output ../evals/datasets/golden

Reads from llm_io_logs table (requires CAPTURE_LLM_IO_LOG=true on at least one fill run / chat session).
Datasets are gitignored — they contain actual offering memorandum text.
Golden datasets (--golden) are committed to git for regression baselines.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from app.database import get_db
from app.utils.logging import logger

import app.db_models          # noqa: F401
import app.db_models_users    # noqa: F401
import app.db_models_chat     # noqa: F401
import app.db_models_workflows  # noqa: F401
import app.db_models_documents  # noqa: F401
import app.db_models_templates  # noqa: F401
import app.db_models_io_logs    # noqa: F401

from app.db_models_io_logs import LLMIOLog
from app.core.rag.eval_contract import RAG_EVAL_CONTRACT_VERSION
from app.verticals.real_estate.template_filling.prompts import get_prompt_set

SUPPORTED_STAGES = [
    "detect_fields",
    "extract_schema_fields",
    "extract_table_values_rag",
    "extract_table_values_rag_single",
    "auto_map_fields",
    # RAG chat stages
    "rag_chat_comparison",  # raw comparison io_logs (stage stored in DB)
    "rag_retrieval",        # virtual: calls real retrieval pipeline, checks page recall
    "rag_generation",       # virtual: replays rag_chat prompts, context-faithfulness metrics
    "rag_comparison",       # virtual: replays rag_chat_comparison prompts, context metrics
]

# Maps each stage to the promptfoo provider label that evaluates it.
# Embedded in every test case so a single promptfooconfig.yaml runs
# all suites without cross-product routing errors.
STAGE_PROVIDER_LABEL: dict[str, str] = {
    "extract_schema_fields": "haiku-e2e-schema",
    "extract_table_values_rag": "haiku-e2e-tables",
    "extract_table_values_rag_single": "haiku-e2e-tables",
    "rag_retrieval": "haiku-retrieval",
    "rag_generation": "haiku-rag",
    "rag_comparison": "haiku-rag-comparison",
}

# Virtual stages read from a different DB stage name
VIRTUAL_STAGE_SOURCE: dict[str, str] = {
    "rag_retrieval": "rag_chat",
    "rag_generation": "rag_chat",
    "rag_comparison": "rag_chat_comparison",
}

# Structural assertions applied to every test case regardless of --golden
STRUCTURAL_ASSERTIONS = {
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
    "extract_table_values_rag": [
        {"type": "is-json"},
        {"type": "javascript", "value": "JSON.parse(output).results !== undefined"},
        {"type": "javascript", "value": "typeof JSON.parse(output).total_tables === 'number'"},
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
    "rag_retrieval": [
        {"type": "javascript", "value": "JSON.parse(output).chunk_count >= 1"},
        {"type": "javascript", "value": "JSON.parse(output).chunk_count <= 20"},
    ],
    "rag_generation": [
        # Output is JSON {text, context}
        {"type": "javascript", "value": "JSON.parse(output).text.length > 50"},
        {"type": "javascript", "value": "JSON.parse(output).text.length < 20000"},
        {
            "type": "javascript",
            "value": "/\\[D\\d+:p\\d+\\]/.test(JSON.parse(output).text)",
            "metric": "rag/has_citations",
        },
        # Use contextTransform so the judge sees the actual LLM-visible context (extracted
        # from the prompt by the provider), not the raw chunk_texts stored in io_log metadata.
        # Multi-doc RAG (10-15 chunks) naturally produces lower faithfulness — threshold 0.6
        # reflects realistic multi-source retrieval rather than single-source RAG.
        {
            "type": "context-faithfulness",
            "threshold": 0.6,
            "contextTransform": "JSON.parse(output).context",
            "metric": "gen/faithfulness",
        },
        {"type": "answer-relevance", "threshold": 0.7, "metric": "gen/answer_relevance"},
    ],
    "rag_comparison": [
        {"type": "javascript", "value": "JSON.parse(output).text.length > 100"},
        {"type": "javascript", "value": "JSON.parse(output).text.length < 30000"},
        # Comparison responses should reference multiple documents
        {
            "type": "javascript",
            "value": "(() => { const t = JSON.parse(output).text; return /Document [AB]|\\[D[12]/.test(t); })()",
            "metric": "comparison/multi_doc_reference",
        },
        # Should contain structured elements (table, bullets, or headers)
        {
            "type": "javascript",
            "value": "(() => { const t = JSON.parse(output).text; return /\\||\\n-|\\n\\*|#{2,}/.test(t); })()",
            "metric": "comparison/structured_output",
        },
        {
            "type": "context-faithfulness",
            "threshold": 0.6,
            "contextTransform": "JSON.parse(output).context",
            "metric": "comparison/faithfulness",
        },
        {"type": "answer-relevance", "threshold": 0.7, "metric": "comparison/answer_relevance"},
    ],
}

_REGULAR_CONTEXT_MARKER = "DOCUMENT EXCERPTS:\n\n"
_REGULAR_CONTEXT_END = "\n\nUSER QUESTION:"
_COMPARISON_CONTEXT_MARKERS = (
    "\n## Paired Content",
    "\n## Clustered Content",
    "\n## Extracted Facts by Document",
)
_COMPARISON_CONTEXT_END_MARKERS = (
    "\n## Comparison Focus",
    "\n" + "=" * 80,
)


def _extract_regular_prompt_context(prompt_text: str) -> str:
    """Extract model-visible RAG context from the stored prompt text."""
    if not prompt_text:
        return ""

    start = prompt_text.find(_REGULAR_CONTEXT_MARKER)
    if start == -1:
        return ""

    start += len(_REGULAR_CONTEXT_MARKER)
    end = prompt_text.find(_REGULAR_CONTEXT_END, start)
    if end == -1:
        return prompt_text[start:].strip()

    return prompt_text[start:end].strip()


def _extract_comparison_prompt_context(prompt_text: str) -> str:
    """Extract prompt-visible comparison evidence from the stored prompt text."""
    if not prompt_text:
        return ""

    for marker in _COMPARISON_CONTEXT_MARKERS:
        start = prompt_text.find(marker)
        if start == -1:
            continue

        start += len(marker)
        end_candidates = [
            prompt_text.find(end_marker, start)
            for end_marker in _COMPARISON_CONTEXT_END_MARKERS
            if prompt_text.find(end_marker, start) != -1
        ]
        end = min(end_candidates) if end_candidates else len(prompt_text)
        return prompt_text[start:end].strip()

    return ""


def _build_prompt_visible_context(entry: LLMIOLog, export_stage: str) -> str:
    """Derive context from the actual stored prompt instead of metadata snapshots."""
    if export_stage == "rag_generation":
        return _extract_regular_prompt_context(entry.user_message or "") or _extract_regular_prompt_context(entry.system_prompt or "")

    if export_stage == "rag_comparison":
        return _extract_comparison_prompt_context(entry.system_prompt or "")

    return ""


def _validate_rag_export_entry(
    entry: LLMIOLog,
    export_stage: str,
    system_prompt: str,
    e2e_vars: dict,
) -> tuple[bool, list[str]]:
    """Validate that a RAG row is complete enough for reliable replay evals."""
    metadata = entry.metadata_ or {}
    reasons: list[str] = []

    if metadata.get("rag_eval_contract_version") != RAG_EVAL_CONTRACT_VERSION:
        reasons.append(
            f"missing_or_old_contract_version={metadata.get('rag_eval_contract_version')!r}"
        )

    if export_stage == "rag_retrieval":
        if not metadata.get("user_question"):
            reasons.append("missing_user_question")
        if not metadata.get("document_ids") and not metadata.get("collection_id"):
            reasons.append("missing_document_scope")
        if not metadata.get("chunk_scores"):
            reasons.append("missing_chunk_scores")
        if not json.loads(e2e_vars.get("expected_pages", "[]")):
            reasons.append("missing_expected_pages")

    elif export_stage == "rag_generation":
        if not system_prompt:
            reasons.append("missing_system_prompt")
        if not entry.user_message:
            reasons.append("missing_user_message")
        if not e2e_vars.get("context"):
            reasons.append("missing_prompt_visible_context")

    elif export_stage == "rag_comparison":
        if not system_prompt:
            reasons.append("missing_comparison_prompt")
        if len(metadata.get("document_ids", [])) < 2:
            reasons.append("insufficient_document_ids")
        if not metadata.get("document_names"):
            reasons.append("missing_document_names")
        if not metadata.get("chunk_scores"):
            reasons.append("missing_chunk_scores")
        if not metadata.get("query_understanding"):
            reasons.append("missing_query_understanding")
        if not e2e_vars.get("context"):
            reasons.append("missing_prompt_visible_context")

    return not reasons, reasons


def _normalize_stage(stage: str) -> str:
    """Normalize auto_map_fields_batch_N -> auto_map_fields."""
    if stage.startswith("auto_map_fields"):
        return "auto_map_fields"
    return stage


def _escape_js_string(s: str) -> str:
    """Escape a string for safe embedding in a JS string literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")


def _build_golden_assertions(normalized: str, output_raw: str) -> list:
    """Build value-level assertions from a reference output.

    These are layered on top of structural assertions and form the regression
    baseline: failing means the new prompt/model no longer produces equivalent
    output to the known-good reference.
    """
    assertions = []

    if normalized == "extract_schema_fields":
        try:
            output = json.loads(output_raw) if isinstance(output_raw, str) else output_raw
        except (json.JSONDecodeError, TypeError):
            return assertions

        total_found = output.get("total_found", 0)

        # Floor, not ceiling — finding more fields in the future is fine
        assertions.append({
            "type": "javascript",
            "value": f"JSON.parse(output).total_found >= {total_found}",
            "metric": "golden/total_found_floor",
        })

        # Coverage rate: at least 90% of the reference count
        min_found = max(1, int(total_found * 0.9))
        assertions.append({
            "type": "javascript",
            "value": f"JSON.parse(output).total_found >= {min_found}",
            "metric": "golden/coverage_rate_90pct",
        })

        # Spot-check: top 10 highest-confidence fields only (not all 50+)
        results = output.get("results", [])
        top_results = sorted(
            [r for r in results if r.get("value")],
            key=lambda r: r.get("confidence", 0),
            reverse=True,
        )[:10]

        for r in top_results:
            val = r.get("value")
            if not val:
                continue
            fid = _escape_js_string(r["field_id"])
            escaped_val = _escape_js_string(val)
            assertions.append({
                "type": "javascript",
                "value": (
                    f"(() => {{ const r = JSON.parse(output).results.find(x => x.field_id === '{fid}'); "
                    f"return r && r.value === '{escaped_val}'; }})()"
                ),
                "metric": f"golden/field/{r['field_id']}",
            })

    elif normalized == "auto_map_fields":
        try:
            output = json.loads(output_raw) if isinstance(output_raw, str) else output_raw
        except (json.JSONDecodeError, TypeError):
            return assertions

        total_mapped = output.get("total_mapped", 0)
        assertions.append({
            "type": "javascript",
            "value": f"JSON.parse(output).total_mapped >= {total_mapped}",
            "metric": "golden/total_mapped_no_regression",
        })
        mappings = [m for m in output.get("mappings", []) if m.get("confidence", 0) >= 0.9]
        for m in mappings[:10]:
            fid = _escape_js_string(m["pdf_field_id"])
            cell = _escape_js_string(m["excel_cell"])
            sheet = _escape_js_string(m["excel_sheet"])
            assertions.append({
                "type": "javascript",
                "value": (
                    f"JSON.parse(output).mappings.some(m => "
                    f"m.pdf_field_id === '{fid}' && m.excel_cell === '{cell}' && m.excel_sheet === '{sheet}')"
                ),
                "metric": f"golden/mapping/{m['pdf_field_id']}",
            })

    elif normalized in ("extract_table_values_rag", "extract_table_values_rag_single"):
        try:
            output = json.loads(output_raw) if isinstance(output_raw, str) else output_raw
        except (json.JSONDecodeError, TypeError):
            return assertions

        for table in output.get("results", []):
            tid = _escape_js_string(table.get("table_id", ""))
            rows = table.get("rows", [])
            row_count = len(rows)

            # Count filled cells (non-null values) in reference output for this table
            ref_filled_cells = sum(
                1 for row in rows
                for v in row.get("values", {}).values()
                if v is not None
            )

            # Row count floor per table
            assertions.append({
                "type": "javascript",
                "value": (
                    f"(() => {{ const t = JSON.parse(output).results.find(x => x.table_id === '{tid}'); "
                    f"return t && t.rows.length >= {row_count}; }})()"
                ),
                "metric": f"golden/table_rows/{table.get('table_id', 'unknown')}",
            })

            # Cell fill count floor — this is what actually maps to the 101-102 total
            # Each table contributes its share; summing across all test cases = total fill coverage
            assertions.append({
                "type": "javascript",
                "value": (
                    f"(() => {{"
                    f"const t = JSON.parse(output).results.find(x => x.table_id === '{tid}');"
                    f"if (!t) return false;"
                    f"const filled = t.rows.reduce((n, r) => n + Object.values(r.values).filter(v => v !== null).length, 0);"
                    f"return filled >= {ref_filled_cells};"
                    f"}})()"
                ),
                "metric": f"golden/table_cells_filled/{table.get('table_id', 'unknown')}",
            })

            # Spot-check: top 5 rows by confidence, top 3 non-null columns each
            top_rows = sorted(
                [r for r in rows if r.get("values")],
                key=lambda r: r.get("confidence", 0),
                reverse=True,
            )[:5]

            for row in top_rows:
                row_label = row.get("row_label")
                row_index = row.get("row_index", 0)

                # Pick top 3 columns that have a non-null value
                top_values = [
                    (col, val)
                    for col, val in row.get("values", {}).items()
                    if val is not None
                ][:3]

                for col, val in top_values:
                    escaped_col = _escape_js_string(str(col))
                    escaped_val = _escape_js_string(str(val))

                    if row_label:
                        # Match by row_label (more stable than index)
                        escaped_label = _escape_js_string(str(row_label))
                        check = (
                            f"(() => {{"
                            f"const t = JSON.parse(output).results.find(x => x.table_id === '{tid}');"
                            f"if (!t) return false;"
                            f"const r = t.rows.find(r => r.row_label === '{escaped_label}');"
                            f"return r && String(r.values['{escaped_col}']) === '{escaped_val}';"
                            f"}})()"
                        )
                        metric = f"golden/table_cell/{table.get('table_id', 'unknown')}/{escaped_label}/{escaped_col}"
                    else:
                        # Fall back to row_index
                        check = (
                            f"(() => {{"
                            f"const t = JSON.parse(output).results.find(x => x.table_id === '{tid}');"
                            f"if (!t) return false;"
                            f"const r = t.rows.find(r => r.row_index === {row_index});"
                            f"return r && String(r.values['{escaped_col}']) === '{escaped_val}';"
                            f"}})()"
                        )
                        metric = f"golden/table_cell/{table.get('table_id', 'unknown')}/row{row_index}/{escaped_col}"

                    assertions.append({
                        "type": "javascript",
                        "value": check,
                        "metric": metric,
                    })

    elif normalized == "rag_retrieval":
        # Golden: page+document recall ≥ 80%.
        # expected_pages is built from chunk_scores in the io_log metadata.
        # Page-based matching is stable across re-indexing (chunk IDs change, pages don't).
        assertions.append({
            "type": "javascript",
            "value": (
                "(() => {"
                "const expected = JSON.parse(context.vars.expected_pages);"
                "if (!expected || expected.length === 0) return true;"
                "const chunks = JSON.parse(output).chunks;"
                "const gotSet = new Set(chunks.map(c => c.document_id + ':' + c.page));"
                "const hits = expected.filter(e => gotSet.has(e.document_id + ':' + e.page)).length;"
                "return hits / expected.length >= 0.8;"
                "})()"
            ),
            "metric": "retrieval/page_recall_80",
        })

    elif normalized == "rag_generation":
        assertions.append({
            "type": "context-relevance",
            # Sanity check only: score is always near-zero for multi-chunk RAG because
            # context-relevance = required sentences / total sentences, and we retrieve
            # 10-15 chunks intentionally. Threshold 0.01 just ensures context isn't
            # completely off-topic (score would be 0.0 for totally irrelevant retrieval).
            "threshold": 0.01,
            "contextTransform": "JSON.parse(output).context",
            "metric": "gen/context_relevance",
        })
        assertions.append({
            "type": "llm-rubric",
            "value": (
                "The response is factually grounded in the document context. "
                "It directly addresses the user's question, includes at least one [Dn:pN] citation, "
                "and does not contain obvious hallucinations or fabricated facts."
            ),
            "metric": "golden/rag_quality",
        })

    elif normalized == "rag_comparison":
        assertions.append({
            "type": "llm-rubric",
            "value": (
                "The response provides a balanced comparison across all documents provided. "
                "It addresses the user's question, covers key similarities and differences, "
                "and does not hallucinate facts not present in the context."
            ),
            "metric": "golden/comparison_quality",
        })

    return assertions


def _get_system_prompt(entry: LLMIOLog, version: str) -> str:
    """Reconstruct system prompt from io_log entry."""
    stage = _normalize_stage(entry.stage)
    prompt_version = version or entry.prompt_version or "v1"

    # For stages where system prompt is stored directly (RAG, table extraction)
    if entry.system_prompt:
        return entry.system_prompt

    # For extract_schema_fields — reconstruct from prompt set
    if stage == "extract_schema_fields":
        try:
            prompts = get_prompt_set(prompt_version)
            # pdf_fields context is in user_message; pass empty list here
            return prompts.build_extract_schema_fields("[]", []).system_prompt
        except Exception as e:
            logger.warning(f"Could not reconstruct system_prompt for {entry.id}: {e}")
            return ""

    return ""


def _build_e2e_vars(entry: LLMIOLog, export_stage: str) -> dict:
    """Build vars needed by e2e providers.

    export_stage is the virtual stage name (e.g. 'rag_retrieval', 'rag_generation')
    rather than the raw DB stage name.
    """
    stage = _normalize_stage(entry.stage)
    metadata = entry.metadata_ or {}
    extra = {"prompt_version": entry.prompt_version or "v1"}

    if stage == "extract_schema_fields":
        extra["unmapped_fields_json"] = json.dumps(metadata.get("unmapped_fields", []), ensure_ascii=False)

    elif export_stage == "rag_retrieval":
        # Retrieval provider needs the raw query + document scope
        extra["user_question"] = metadata.get("user_question", "")
        extra["document_ids"] = json.dumps(metadata.get("document_ids", []), ensure_ascii=False)
        extra["collection_id"] = metadata.get("collection_id") or ""
        # Golden ground truth: page+doc pairs resolved same way as citations
        chunk_scores = metadata.get("chunk_scores", [])
        expected_pages = []
        seen = set()
        for cs in chunk_scores:
            doc_id = cs.get("document_id")
            page = cs.get("bbox_page") or cs.get("page_number")
            if doc_id and page is not None:
                key = f"{doc_id}:{page}"
                if key not in seen:
                    seen.add(key)
                    expected_pages.append({"document_id": doc_id, "page": page})
        extra["expected_pages"] = json.dumps(expected_pages, ensure_ascii=False)

    elif export_stage in ("rag_generation", "rag_comparison"):
        # Generation providers need the raw question and prompt-visible context for assertions.
        # This is intentionally derived from the stored prompt rather than metadata chunk_texts.
        extra["user_question"] = metadata.get("user_question", "")
        extra["context"] = _build_prompt_visible_context(entry, export_stage)

    return extra


def export_entries(
    entries: list,
    normalized_stage: str,
    writers: dict,
    golden: bool,
    version: str,
):
    """Export a list of io_log entries into the appropriate JSONL writers."""
    exported = 0
    for entry in entries:
        if normalized_stage not in STRUCTURAL_ASSERTIONS:
            continue

        system_prompt = _get_system_prompt(entry, version)
        e2e_vars = _build_e2e_vars(entry, normalized_stage)

        if normalized_stage in ("rag_retrieval", "rag_generation", "rag_comparison"):
            is_valid, reasons = _validate_rag_export_entry(entry, normalized_stage, system_prompt, e2e_vars)
            if not is_valid:
                logger.warning(
                    "Skipping incomplete RAG eval row",
                    extra={
                        "io_log_id": entry.id,
                        "export_stage": normalized_stage,
                        "reasons": reasons,
                    },
                )
                continue

        assertions = list(STRUCTURAL_ASSERTIONS[normalized_stage])

        if golden and entry.output:
            assertions.extend(_build_golden_assertions(normalized_stage, entry.output))

        # Parse output for metadata
        try:
            output_parsed = json.loads(entry.output) if entry.output else None
        except (json.JSONDecodeError, TypeError):
            output_parsed = entry.output

        provider_label = STAGE_PROVIDER_LABEL.get(normalized_stage)
        test_case = {
            **({"providers": [provider_label]} if provider_label else {}),
            "vars": {
                "system_prompt": system_prompt,
                "user_message": entry.user_message or "",
                "query": e2e_vars.get("user_question", ""),
                **e2e_vars,
            },
            "assert": assertions,
            "_metadata": {
                "io_log_id": entry.id,
                "source_type": entry.source_type,
                "source_id": entry.source_id,
                "stage": normalized_stage,
                "raw_stage": entry.stage,
                "prompt_version": entry.prompt_version,
                "reference_output": output_parsed,
                "input_tokens": entry.input_tokens,
                "output_tokens": entry.output_tokens,
                "duration_ms": entry.duration_ms,
                "golden": golden,
            },
        }

        writers[normalized_stage].write(json.dumps(test_case, ensure_ascii=False) + "\n")
        exported += 1
    return exported


def run(
    stage: str,
    limit: int,
    output_dir: str,
    version: str,
    golden: bool,
    source_id: str | None = None,
    session_id: str | None = None,
):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # "all" skips virtual stages (they must be exported explicitly)
    if stage == "all":
        stages_to_export = [
            s for s in SUPPORTED_STAGES
            if s not in VIRTUAL_STAGE_SOURCE
        ]
    else:
        stages_to_export = [stage]

    writers = {}
    for s in stages_to_export:
        path = output_path / f"{s}.jsonl"
        writers[s] = open(path, "w", encoding="utf-8")
        logger.info(f"Writing to {path}")

    db = next(get_db())
    try:
        total_exported = 0

        for target_stage in stages_to_export:
            q = db.query(LLMIOLog)

            if source_id:
                q = q.filter(LLMIOLog.source_id == source_id)

            # Session-based filter: matches all QA pairs from one chat session
            if session_id:
                q = q.filter(LLMIOLog.metadata_["session_id"].astext == session_id)

            # Virtual stages read from a different DB stage name
            db_stage = VIRTUAL_STAGE_SOURCE.get(target_stage, target_stage)

            if db_stage == "auto_map_fields":
                q = q.filter(LLMIOLog.stage.like("auto_map_fields%"))
            else:
                q = q.filter(LLMIOLog.stage == db_stage)

            q = q.order_by(LLMIOLog.created_at.desc())
            if limit:
                q = q.limit(limit)

            entries = q.all()
            logger.info(f"Found {len(entries)} entries for stage={target_stage} (db_stage={db_stage})")

            n = export_entries(entries, target_stage, writers, golden, version)
            total_exported += n
            if n:
                logger.info(f"  Exported {n} test cases for stage={target_stage}")

        logger.info(f"Done. Total test cases exported: {total_exported}")
        if golden:
            logger.info(
                "Golden dataset written. Review the JSONL files and commit "
                "evals/datasets/golden/ to git as your regression baseline."
            )

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
    parser.add_argument("--limit", type=int, default=0, help="Max entries to export per stage (0 = no limit)")
    parser.add_argument("--output", default="../evals/datasets", help="Output directory for JSONL files")
    parser.add_argument(
        "--version",
        default="",
        help="Prompt version override for system prompt reconstruction (default: use version from entry)",
    )
    parser.add_argument(
        "--golden",
        action="store_true",
        default=False,
        help=(
            "Add value-level assertions from reference output. "
            "Creates a regression baseline. Suggest output to datasets/golden/."
        ),
    )
    parser.add_argument(
        "--source-id",
        default=None,
        help="Export from a specific source (fill_run_id or chat_message_id).",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help=(
            "Export all QA pairs from a specific chat session "
            "(filters by metadata.session_id). Use for RAG chat golden datasets."
        ),
    )
    args = parser.parse_args()

    run(
        stage=args.stage,
        limit=args.limit,
        output_dir=args.output,
        version=args.version,
        golden=args.golden,
        source_id=args.source_id,
        session_id=args.session_id,
    )


if __name__ == "__main__":
    main()
