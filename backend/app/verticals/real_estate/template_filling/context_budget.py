"""PDF field budgeting and trimming for LLM context windows."""

import json
from typing import Any, Dict, List, Tuple

from app.config import settings


LARGE_DOCUMENT_CONTEXT_WARNING = (
    "Large document: LatticeBlu used the most relevant extracted fields and tables for this template. "
    "Review unmapped cells manually."
)
TABLE_CONTEXT_TRIM_WARNING = (
    "A large table was partially reviewed for template fill. If key rows are missing, "
    "split the source or upload the rent roll separately."
)
TOO_LARGE_CONTEXT_ERROR = (
    "This document is too large or too broad for reliable Excel fill. Try uploading a focused source document, "
    "such as the OM, rent roll, or operating statement."
)


def context_priority(field: Dict[str, Any]) -> int:
    source = field.get("source")
    field_type = field.get("type")
    if source == "key_value_pairs":
        return 0
    if source in {"table", "table_block"} or field_type == "table":
        return 1
    if source == "narrative_block" or field_type == "narrative":
        return 2
    return 3


def context_size(field: Dict[str, Any]) -> int:
    try:
        return len(json.dumps(field, ensure_ascii=False, default=str))
    except TypeError:
        return len(str(field))


def trim_context_field(field: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, int]]:
    trimmed = dict(field)
    meta = {"table_blocks_trimmed": 0, "narrative_blocks_trimmed": 0}

    rows = trimmed.get("table_rows")
    if isinstance(rows, list) and len(rows) > settings.template_fill_max_table_rows_per_block:
        trimmed["table_rows"] = rows[: settings.template_fill_max_table_rows_per_block]
        trimmed["table_rows_original_count"] = len(rows)
        trimmed["table_rows_truncated"] = True
        meta["table_blocks_trimmed"] = 1

    full_text = trimmed.get("full_text")
    if isinstance(full_text, str) and len(full_text) > settings.template_fill_max_narrative_chars_per_block:
        trimmed["full_text"] = full_text[: settings.template_fill_max_narrative_chars_per_block]
        trimmed["full_text_original_chars"] = len(full_text)
        trimmed["full_text_truncated"] = True
        meta["narrative_blocks_trimmed"] = 1

    return trimmed, meta


def build_budgeted_pdf_fields(
    pdf_fields: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Prioritize extracted evidence before targeted LLM calls.

    The UI should never mention "context items" or token limits; this metadata is
    stored only so we can explain that a large source was narrowed for reliability.
    """
    item_limit = settings.template_fill_max_pdf_context_items
    char_limit = settings.template_fill_max_llm_context_chars

    llm_fields: List[Dict[str, Any]] = []
    narrative_fields: List[Dict[str, Any]] = []
    table_blocks_trimmed = 0
    narrative_blocks_trimmed = 0

    for field in pdf_fields:
        if not isinstance(field, dict):
            continue
        source = field.get("source")
        trimmed, meta = trim_context_field(field)
        if source == "narrative_block":
            narrative_blocks_trimmed += meta["narrative_blocks_trimmed"]
            narrative_fields.append(trimmed)
        else:
            table_blocks_trimmed += meta["table_blocks_trimmed"]
            llm_fields.append(trimmed)

    ordered_fields = sorted(enumerate(llm_fields), key=lambda item: (context_priority(item[1]), item[0]))
    selected_with_index: List[Tuple[int, Dict[str, Any]]] = []
    chars_used = 0

    for original_index, field in ordered_fields:
        if len(selected_with_index) >= item_limit:
            continue

        field_chars = context_size(field)
        if selected_with_index and chars_used + field_chars > char_limit:
            continue
        if not selected_with_index and field_chars > char_limit:
            continue

        selected_with_index.append((original_index, field))
        chars_used += field_chars

    selected_llm_fields = [field for _, field in sorted(selected_with_index, key=lambda item: item[0])]
    selected_fields = selected_llm_fields + narrative_fields

    context_budget_applied = (
        len(selected_llm_fields) != len(llm_fields)
        or table_blocks_trimmed > 0
        or narrative_blocks_trimmed > 0
    )
    warning_parts = []
    if context_budget_applied:
        warning_parts.append(LARGE_DOCUMENT_CONTEXT_WARNING)
    if table_blocks_trimmed:
        warning_parts.append(TABLE_CONTEXT_TRIM_WARNING)

    metadata = {
        "context_budget_applied": context_budget_applied,
        "context_items_original": len(llm_fields),
        "context_items_used": len(selected_llm_fields),
        "context_items_dropped": max(len(llm_fields) - len(selected_llm_fields), 0),
        "context_chars_used": chars_used,
        "context_chars_limit": char_limit,
        "context_items_limit": item_limit,
        "table_blocks_trimmed": table_blocks_trimmed,
        "narrative_blocks_trimmed": narrative_blocks_trimmed,
        "user_warning": " ".join(warning_parts) if warning_parts else None,
    }

    return selected_fields, metadata
