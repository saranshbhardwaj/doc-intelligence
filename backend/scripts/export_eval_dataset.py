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
from app.core.rag.eval_annotations import (
    build_promptfoo_annotation_vars,
    get_expected_answer_substrings,
    load_benchmark_annotations,
    load_benchmark_annotations_from_path,
    lookup_benchmark_annotation,
)
from app.core.rag.eval_contract import RAG_EVAL_CONTRACT_VERSION

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
            # RAG prompt instructs the model to cite as [Sn:pN] (sequential source, page).
            "type": "javascript",
            "value": "/\\[S\\d+:p\\d+(?:,\\s*S\\d+:p\\d+)*\\]/.test(JSON.parse(output).text)",
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
        {"type": "answer-relevance", "threshold": 0.50, "metric": "gen/answer_relevance"},
    ],
    "rag_comparison": [
        {"type": "javascript", "value": "JSON.parse(output).text.length > 100"},
        {"type": "javascript", "value": "JSON.parse(output).text.length < 30000"},
        # Comparison responses should cite at least 2 distinct source numbers [S1:pN], [S2:pN], ...
        {
            "type": "javascript",
            "value": "(() => { const t = JSON.parse(output).text; const nums = new Set((t.match(/\\[S(\\d+):p\\d+\\]/g) || []).map(m => m.match(/S(\\d+)/)[1])); return nums.size >= 2; })()",
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
        {"type": "answer-relevance", "threshold": 0.50, "metric": "comparison/answer_relevance"},
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
        if not json.loads(e2e_vars.get("expected_anchors", "[]")):
            reasons.append("missing_expected_anchors")

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


def _build_golden_assertions(normalized: str, output_raw: str, annotations: dict | None = None, user_question: str = "") -> list:
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
        # Golden: retrieval anchor recall >= 80%.
        # Prefer curated benchmark gold evidence when available; fall back to captured
        # expected anchors/pages from the original session when benchmark metadata is absent.
        # PDFs use document+page anchors; spreadsheets use document+chunk_id anchors.
        assertions.append({
            "type": "javascript",
            "value": (
                "(() => {"
                "const benchmarkGold = JSON.parse(context.vars.benchmark_gold_evidence || '[]');"
                "const expectedAnchors = JSON.parse(context.vars.expected_anchors || context.vars.expected_pages || '[]');"
                "const candidateDocumentIds = new Set(JSON.parse(context.vars.document_ids || '[]'));"
                "const benchmarkGoldUsable = benchmarkGold.length > 0 && benchmarkGold.some(item => item && item.document_id && candidateDocumentIds.has(item.document_id));"
                "const expected = benchmarkGoldUsable ? benchmarkGold : expectedAnchors;"
                "const useSpreadsheetSheetFallback = !benchmarkGoldUsable;"
                "const keyForAnchor = (item) => {"
                "if (!item || !item.document_id) return null;"
                "if (item.chunk_id) {"
                "const sheetName = item.sheet_name || item.sheet;"
                "if (useSpreadsheetSheetFallback && sheetName) return item.document_id + ':sheet:' + String(sheetName).toLowerCase();"
                "return item.document_id + ':chunk:' + item.chunk_id;"
                "}"
                "const page = item.page ?? item.bbox_page ?? item.page_number;"
                "if (page === null || page === undefined) return null;"
                "return item.document_id + ':page:' + page;"
                "};"
                "const expectedKeys = expected.map(keyForAnchor).filter(Boolean);"
                "if (expectedKeys.length === 0) return true;"
                "const chunks = JSON.parse(output).chunks;"
                "const gotSet = new Set(chunks.map(keyForAnchor).filter(Boolean));"
                "const hits = expectedKeys.filter(key => gotSet.has(key)).length;"
                "return hits / expectedKeys.length >= 0.8;"
                "})()"
            ),
            "metric": "retrieval/page_recall_80",
        })

    elif normalized == "rag_generation":
        # Tier 3: inject expected-value assertions if benchmark annotations exist.
        annotation = lookup_benchmark_annotation(annotations, user_question)
        expected_variants = [
            str(expected).lower()
            for expected in get_expected_answer_substrings(annotation)
            if expected
        ]
        if expected_variants:
            assertions.append({
                "type": "javascript",
                "value": (
                    "(() => {"
                    "const text = JSON.parse(output).text.toLowerCase();"
                    "const normalizeValue = (value) => value.toLowerCase().replace(/[,$]/g, '');"
                    "const normalizedText = normalizeValue(text);"
                    f"const expectedVariants = {json.dumps(expected_variants)};"
                    "return expectedVariants.some(expected => text.includes(expected) || normalizedText.includes(normalizeValue(expected)));"
                    "})()"
                ),
                "metric": "golden/expected_value_any",
            })

        # context-relevance is intentionally omitted: we send 10-15 chunks per query
        # (dense financial PDFs need broad retrieval), so the ratio of "required sentences /
        # total context sentences" is always near 0 regardless of answer quality.
        # context-faithfulness is the meaningful grounding check instead.
        assertions.append({
            "type": "llm-rubric",
            "value": (
                "The response is factually grounded in the document context. "
                "It directly addresses the user's question, includes at least one [Sn:pN] citation, "
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
            from app.verticals.real_estate.template_filling.prompts import get_prompt_set
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
        extra["query_understanding"] = json.dumps(metadata.get("query_understanding") or {}, ensure_ascii=False)
        # Golden ground truth: page anchors for PDFs, chunk anchors for spreadsheets.
        chunk_scores = metadata.get("chunk_scores", [])
        expected_pages = []
        expected_anchors = []
        seen = set()
        for cs in chunk_scores:
            doc_id = cs.get("document_id")
            page = cs.get("bbox_page") or cs.get("page_number")
            chunk_id = cs.get("chunk_id")
            if doc_id and page is not None:
                key = f"{doc_id}:page:{page}"
                if key not in seen:
                    seen.add(key)
                    expected_pages.append({"document_id": doc_id, "page": page})
                    expected_anchors.append({"document_id": doc_id, "page": page})
            elif doc_id and chunk_id:
                key = f"{doc_id}:chunk:{chunk_id}"
                if key not in seen:
                    seen.add(key)
                    expected_anchors.append({
                        "document_id": doc_id,
                        "chunk_id": chunk_id,
                        "sheet_name": cs.get("sheet_name"),
                        "row_start": cs.get("row_start"),
                        "row_end": cs.get("row_end"),
                    })
        extra["expected_pages"] = json.dumps(expected_pages, ensure_ascii=False)
        extra["expected_anchors"] = json.dumps(expected_anchors, ensure_ascii=False)

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
    annotations: dict | None = None,
):
    """Export a list of io_log entries into the appropriate JSONL writers."""
    exported = 0
    for entry in entries:
        if normalized_stage not in STRUCTURAL_ASSERTIONS:
            continue

        system_prompt = _get_system_prompt(entry, version)
        e2e_vars = _build_e2e_vars(entry, normalized_stage)
        user_question = e2e_vars.get("user_question", "")
        benchmark_annotation = lookup_benchmark_annotation(annotations, user_question)
        benchmark_vars = build_promptfoo_annotation_vars(benchmark_annotation)

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
            assertions.extend(_build_golden_assertions(normalized_stage, entry.output, annotations, user_question))

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
                "query": user_question,
                **e2e_vars,
                **benchmark_vars,
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
                "benchmark_annotation": benchmark_annotation,
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
    annotations: dict | None = None,
    log_ids: list[str] | None = None,
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

            if log_ids:
                q = q.filter(LLMIOLog.id.in_(log_ids))
            elif source_id:
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

            n = export_entries(entries, target_stage, writers, golden, version, annotations)
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
    parser.add_argument(
        "--log-ids",
        default=None,
        help=(
            "Comma-separated list of llm_io_log primary key UUIDs to export. "
            "Use when you have specific log entries (e.g. from a verified Q&A session). "
            "Takes precedence over --source-id."
        ),
    )
    parser.add_argument(
        "--annotations",
        default=None,
        help=(
            "Path to a legacy flat annotations file or the structured benchmark annotation schema "
            "under evals/annotations/. For RAG generation golden exports, injects value assertions "
            "for each matched question."
        ),
    )
    args = parser.parse_args()

    annotations = None
    if args.annotations:
        annotations_path = Path(args.annotations)
        if not annotations_path.exists():
            logger.error(f"Annotations file not found: {annotations_path}")
            sys.exit(1)
        annotations = load_benchmark_annotations_from_path(annotations_path)
        logger.info(f"Loaded {len(annotations)} annotations from {annotations_path}")

    log_ids = [i.strip() for i in args.log_ids.split(",")] if args.log_ids else None

    run(
        stage=args.stage,
        limit=args.limit,
        output_dir=args.output,
        version=args.version,
        golden=args.golden,
        source_id=args.source_id,
        session_id=args.session_id,
        annotations=annotations,
        log_ids=log_ids,
    )


if __name__ == "__main__":
    main()
