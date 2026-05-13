"""Celery tasks for Excel template filling pipeline.

Task Flow:
1. detect_fields_task: Analyze PDF to identify structured fields (LLM call 1)
2. auto_map_fields_task: Match PDF fields to Excel cells (LLM call 2)
3. extract_data_task: Extract values from PDF (LLM call 3)
4. fill_excel_task: Fill Excel template with data (openpyxl)
5. start_fill_run_chain: Orchestrate the full pipeline
"""

import asyncio
import copy
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from celery import chain, shared_task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.repositories.document_repository import DocumentRepository
from app.repositories.job_repository import JobRepository
from app.repositories.template_repository import TemplateRepository
from app.services.beta_limits import commit_shadow_credits, reverse_shadow_credits
from app.services.citations import normalize_citations
from app.services.job_tracker import JobProgressTracker
from app.core.storage.storage_factory import get_storage_backend
from app.utils.costs import compute_llm_cost
from app.utils.logging import logger
from app.utils.metrics_recorder import record_template_fill_completed, record_template_fill_failed
from app.utils.metrics import TEMPLATE_FILL_LATENCY_SECONDS
from app.verticals.real_estate.template_filling.excel_handler import ExcelHandler
from app.verticals.real_estate.template_filling.llm_service import TemplateFillLLMService
from app.verticals.real_estate.template_filling.excel.mapping_coordinator import coordinator as mapping_coordinator
from app.verticals.real_estate.template_filling.source_map import (
    SKIP_REASON_VALUES,
    STRUCTURE_HIGH_CONFIDENCE,
    STRUCTURE_LOW_CONFIDENCE,
    as_list,
    normalize_om_structure_with_pdf_fields,
)


def _get_db_session() -> Session:
    """Get a new database session."""
    return SessionLocal()


def _reverse_template_fill_shadow(fill_run_id: str, reason: str, stage: str) -> None:
    reverse_shadow_credits(
        operation_type="template_fill_run",
        reference_id=fill_run_id,
        reason=reason,
        metadata={"stage": stage},
    )


def _build_citation_context(detected_fields: list, document_filename: str) -> dict:
    """
    Build S{n}→{bbox, page, filename} lookup from detected fields.

    Parallel to rag_service._build_citation_context() for RAG chunks.
    Built once at detect_fields_task time and persisted to DB so the frontend
    can resolve [S{n}:p{N}] citation tokens → exact bbox without any array searching.

    Only includes non-targeted fields (targeted_schema entries are appended later
    in auto_map_fields_task after their bboxes are resolved).
    """
    citations = []
    for field in detected_fields:
        if field.get("source") == "targeted_schema":
            continue
        m = re.search(r'_(\d+)$', field.get("id", ""))
        if not m:
            continue
        bbox = field.get("bbox")
        citations.append({
            "source_index": int(m.group(1)),
            "field_id": field["id"],
            "page": (bbox or {}).get("page"),
            "filename": document_filename,
            "bbox": bbox,
        })
    return {"citations": citations}


LARGE_DOCUMENT_CONTEXT_WARNING = (
    "Large document: Basilfy used the most relevant extracted fields and tables for this template. "
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


def _context_priority(field: Dict[str, Any]) -> int:
    source = field.get("source")
    field_type = field.get("type")
    if source == "key_value_pairs":
        return 0
    if source in {"table", "table_block"} or field_type == "table":
        return 1
    if source == "narrative_block" or field_type == "narrative":
        return 2
    return 3


def _context_size(field: Dict[str, Any]) -> int:
    try:
        return len(json.dumps(field, ensure_ascii=False, default=str))
    except TypeError:
        return len(str(field))


def _trim_context_field(field: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, int]]:
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


def _build_budgeted_pdf_fields(pdf_fields: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
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
        trimmed, meta = _trim_context_field(field)
        if source == "narrative_block":
            narrative_blocks_trimmed += meta["narrative_blocks_trimmed"]
            narrative_fields.append(trimmed)
        else:
            table_blocks_trimmed += meta["table_blocks_trimmed"]
            llm_fields.append(trimmed)

    ordered_fields = sorted(enumerate(llm_fields), key=lambda item: (_context_priority(item[1]), item[0]))
    selected_with_index: List[tuple[int, Dict[str, Any]]] = []
    chars_used = 0

    for original_index, field in ordered_fields:
        if len(selected_with_index) >= item_limit:
            continue

        field_chars = _context_size(field)
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


def _extract_schema_table_row_labels(schema_obj: Any, workbook: Any) -> Dict[str, Any]:
    """
    Extract row labels for schema tables from the Excel template.

    Returns:
        Dict: {table_id: {"row_labels": [...], "start_row": int, "end_row": int}}
    """
    labels_by_table: Dict[str, Any] = {}
    if not schema_obj or not workbook:
        return labels_by_table

    for table in getattr(schema_obj, "tables", []) or []:
        table_id = table.get("id")
        sheet_name = table.get("sheet")
        row_id_col = table.get("row_identifier_column")
        start_row = table.get("data_start_row")
        end_row = table.get("data_end_row", start_row)

        if not table_id or not sheet_name or not row_id_col or not start_row:
            continue
        if sheet_name not in workbook.sheetnames:
            continue

        sheet = workbook[sheet_name]
        row_labels = []
        for row in range(start_row, (end_row or start_row) + 1):
            cell_value = sheet[f"{row_id_col}{row}"].value
            row_labels.append(str(cell_value).strip() if cell_value is not None else "")

        labels_by_table[table_id] = {
            "row_labels": row_labels,
            "start_row": start_row,
            "end_row": end_row,
        }

    return labels_by_table



def _get_table_batch_key(table_def: Dict[str, Any]) -> str:
    sheet = table_def.get("sheet") or "unknown"
    return sheet.lower()


def _parse_citation_pages(citations: List[Any]) -> List[int]:
    """Parse citation strings like '[S3:p15]' or 'Page 15' into page numbers."""
    pages: List[int] = []
    for cit in (citations or []):
        for m in re.finditer(r":p(\d+)|[Pp]age\s*(\d+)", str(cit)):
            pages.append(int(m.group(1) or m.group(2)))
    return pages


def _get_section_citation_pages(om_structure: Dict[str, Any], section_key: str) -> List[int]:
    """Return page numbers cited by the structure detection entry for a given section key."""
    if not om_structure:
        return []
    for bucket in ("section_presence", "column_map"):
        entry = (om_structure.get(bucket) or {}).get(section_key)
        if entry:
            return _parse_citation_pages(entry.get("citations") or [])
    return []


def _field_page(field: Dict[str, Any]) -> Optional[int]:
    """Return the page number for a raw pdf_field regardless of source type."""
    source = field.get("source")
    if source == "key_value_pairs":
        return (field.get("bbox") or {}).get("page") or field.get("page_number")
    return field.get("page_number")


def _get_scalar_batch_key(field_def: Dict[str, Any]) -> str:
    source_basis = field_def.get("source_basis") or "om_property_summary"
    fill_when = "|".join(str(value) for value in as_list(field_def.get("fill_when")) if value)
    return f"{source_basis}:{fill_when or 'always'}"


def _build_narrative_pdf_field(
    *,
    field_id_counter: int,
    narrative_text: str,
    section_heading: str,
    narrative_page: Optional[int],
) -> Dict[str, Any]:
    citation = f"[S{field_id_counter}:p{narrative_page}]"
    return {
        "id": f"narrative_block_{field_id_counter}",
        "name": f"narrative: {section_heading}" if section_heading else "narrative",
        "type": "narrative",
        "extracted_value": narrative_text[:300],
        "confidence": 0.8,
        "citations": [citation],
        "source": "narrative_block",
        "full_text": narrative_text,
        "section": section_heading,
        "page_number": narrative_page,
    }


def _build_scalar_context_for_batch(
    pdf_fields: List[Dict[str, Any]],
    om_structure: Dict[str, Any],
    batch_fields: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Build scalar extraction context from the full evidence pool.

    Structure-gated batches are routed to cited pages first, then budgeted.
    Always/static batches keep the full pool and only apply budget limits.
    """
    fill_when_keys: set[str] = set()
    for field_def in batch_fields or []:
        for fill_when in as_list(field_def.get("fill_when")):
            if fill_when and fill_when != "always":
                fill_when_keys.add(str(fill_when))

    citation_pages: List[int] = []
    for key in sorted(fill_when_keys):
        citation_pages.extend(_get_section_citation_pages(om_structure or {}, key))
    unique_citation_pages = sorted(set(citation_pages))

    routed_fields = pdf_fields
    routing_applied = False
    if unique_citation_pages:
        routing_applied = True
        routed_fields = [
            field
            for field in pdf_fields
            if (page := _field_page(field)) is None
            or any(abs(page - citation_page) <= 1 for citation_page in unique_citation_pages)
        ]

    budgeted_fields, budget_metadata = _build_budgeted_pdf_fields(routed_fields)
    budget_metadata = {
        **budget_metadata,
        "routing_applied": routing_applied,
        "citation_pages": unique_citation_pages,
        "source_field_count_before_routing": len(pdf_fields),
        "source_field_count_after_routing": len(routed_fields),
    }
    return budgeted_fields, budget_metadata


def _scalar_context_signature(context_fields: List[Dict[str, Any]]) -> tuple[str, ...]:
    """Build a stable exact-match signature from routed scalar context ids."""
    return tuple(str(field.get("id") or "") for field in context_fields or [])


def _consolidate_scalar_batches_by_context(
    prepared_batches: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge scalar batches only when their routed contexts are exactly identical."""
    consolidated_by_signature: Dict[tuple[str, ...], Dict[str, Any]] = {}
    consolidated_order: List[tuple[str, ...]] = []

    for prepared in prepared_batches or []:
        signature = _scalar_context_signature(prepared.get("context") or [])
        if signature not in consolidated_by_signature:
            consolidated_by_signature[signature] = {
                "context_signature": signature,
                "batch_keys": [],
                "fields": [],
                "context": prepared.get("context") or [],
                "budgets": [],
            }
            consolidated_order.append(signature)

        consolidated = consolidated_by_signature[signature]
        consolidated["batch_keys"].append(prepared.get("batch_key"))
        consolidated["fields"].extend(prepared.get("fields") or [])
        consolidated["budgets"].append(prepared.get("budget") or {})

    return [consolidated_by_signature[signature] for signature in consolidated_order]


def _compute_schema_counts(schema_obj: Any) -> Dict[str, Any]:
    fields = getattr(schema_obj, "fields", []) or []
    tables = getattr(schema_obj, "tables", []) or []
    total_table_cells = 0
    total_table_rows = 0
    total_table_columns = 0
    unknown_row_tables = 0

    for table in tables:
        columns = [c for c in (table.get("columns") or []) if c.get("excel_column")]
        col_count = len(columns)
        total_table_columns += col_count

        start_row = table.get("data_start_row")
        end_row = table.get("data_end_row")
        if start_row and end_row and end_row >= start_row:
            row_count = end_row - start_row + 1
            total_table_rows += row_count
            total_table_cells += row_count * col_count
        else:
            unknown_row_tables += 1

    return {
        "schema_id": getattr(schema_obj, "schema_id", None),
        "yaml_field_count": len(fields),
        "yaml_table_count": len(tables),
        "yaml_table_rows": total_table_rows,
        "yaml_table_columns": total_table_columns,
        "yaml_table_cells": total_table_cells,
        "yaml_tables_with_unknown_rows": unknown_row_tables,
        "total_yaml_fields": len(fields) + total_table_cells,
    }


def _iter_structure_entries(structure: Dict[str, Any]):
    for group_name in ("column_map", "section_presence"):
        group = structure.get(group_name) or {}
        for key, value in group.items():
            if isinstance(value, dict):
                yield f"{group_name}.{key}", value


def _build_structure_confidence_summary(structure: Dict[str, Any]) -> Dict[str, Any]:
    entries = list(_iter_structure_entries(structure or {}))
    confidences = [
        float(entry.get("confidence"))
        for _, entry in entries
        if entry.get("confidence") is not None
    ]
    if not confidences:
        return {
            "min_confidence": None,
            "mean_confidence": None,
            "low_confidence_keys": [],
        }
    return {
        "min_confidence": round(min(confidences), 4),
        "mean_confidence": round(sum(confidences) / len(confidences), 4),
        "low_confidence_keys": [
            key
            for key, entry in entries
            if float(entry.get("confidence") or 0) < STRUCTURE_LOW_CONFIDENCE
        ],
    }


def _build_om_structure_artifact(
    detected_structure: Dict[str, Any],
    model_name: str,
) -> Dict[str, Any]:
    """Build the stored Source Map artifact used by this fill run."""
    normalized_structure = copy.deepcopy(detected_structure)
    for bucket in ("column_map", "section_presence"):
        for entry in (normalized_structure.get(bucket) or {}).values():
            if isinstance(entry, dict):
                raw_citations = []
                for citation in entry.get("citations", []) or []:
                    citation_text = str(citation).strip()
                    if re.fullmatch(r"(?:S|D)\d+:p\d+", citation_text):
                        citation_text = f"[{citation_text}]"
                    raw_citations.append(citation_text)
                entry["citations"] = normalize_citations(raw_citations)
    return {
        "extractor_version": "template_om_structure_v1",
        "model_name": model_name,
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "edited": False,
        "original": copy.deepcopy(normalized_structure),
        "effective": copy.deepcopy(normalized_structure),
        "confidence_summary": _build_structure_confidence_summary(normalized_structure),
    }


def _fail_fill_run(
    repo: TemplateRepository,
    tracker: JobProgressTracker,
    fill_run_id: str,
    stage: str,
    exc: Exception,
    *,
    is_retryable: bool = False,
) -> None:
    """Persist a stage failure to the DB and emit SSE error+end so the frontend terminates."""
    repo.update_fill_run(
        fill_run_id,
        status="failed",
        error_stage=stage,
        error_message=str(exc),
    )
    tracker.mark_error(
        error_stage=stage,
        error_message=str(exc),
        error_type=f"{stage}_failed",
        is_retryable=is_retryable,
    )


# Keep the old name as a thin alias so existing callers and tests don't break.
def _mark_auto_mapping_exception(
    repo: TemplateRepository,
    tracker: JobProgressTracker,
    fill_run_id: str,
    exc: Exception,
) -> None:
    _fail_fill_run(repo, tracker, fill_run_id, "auto_mapping", exc)


def _get_structure_entry(structure: Dict[str, Any], dotted_key: str) -> Optional[Dict[str, Any]]:
    node: Any = structure or {}
    for part in dotted_key.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node if isinstance(node, dict) else None


def _target_status(target: Dict[str, Any], target_type: str, reason: str, **extra: Any) -> Dict[str, Any]:
    if reason not in SKIP_REASON_VALUES:
        raise ValueError(f"Unknown skip reason: {reason}")
    status = {
        "excel_sheet": target.get("sheet"),
        "excel_cell": target.get("value_cell"),
        "target_id": target.get("id"),
        "target_type": target_type,
        "skip_reason": reason,
    }
    protected = set(status)
    for key, value in extra.items():
        if key not in protected:
            status[key] = value
    return status


def _target_review_status(
    target: Dict[str, Any],
    target_type: str,
    reason: str,
    **extra: Any,
) -> Dict[str, Any]:
    status = {
        "excel_sheet": target.get("sheet"),
        "excel_cell": target.get("value_cell"),
        "target_id": target.get("id"),
        "target_type": target_type,
        "review_reason": reason,
    }
    protected = set(status)
    for key, value in extra.items():
        if key not in protected:
            status[key] = value
    return status


def _plan_schema_targets_for_structure(
    fields: List[Dict[str, Any]],
    tables: List[Dict[str, Any]],
    structure: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Apply Source Map gating before LLM extraction.

    This keeps cells with missing sections or unsafe structure confidence out of
    the extraction prompt. A skipped cell with a reason is better than a guessed
    cell value.
    """
    fields_to_extract: List[Dict[str, Any]] = []
    tables_to_extract: List[Dict[str, Any]] = []
    skipped_targets: List[Dict[str, Any]] = []
    review_required_targets: List[Dict[str, Any]] = []

    def plan_one(target: Dict[str, Any], target_type: str) -> bool:
        fill_when_values = [
            value for value in as_list(target.get("fill_when")) if value != "always"
        ]
        if fill_when_values:
            matching_sections = [
                (fill_when, _get_structure_entry(structure, f"section_presence.{fill_when}"))
                for fill_when in fill_when_values
            ]
            if not any(section and section.get("present") for _, section in matching_sections):
                skipped_targets.append(
                    _target_status(
                        target,
                        target_type,
                        "missing_section",
                        structure_key="|".join(
                            f"section_presence.{fill_when}" for fill_when in fill_when_values
                        ),
                    )
                )
                return False

        required_structure_keys = as_list(target.get("requires_structure"))
        if required_structure_keys:
            candidates = []
            for structure_key in required_structure_keys:
                entry = _get_structure_entry(structure, structure_key)
                confidence = float((entry or {}).get("confidence") or 0)
                if entry and entry.get("present"):
                    candidates.append((structure_key, entry, confidence))

            if not candidates:
                skipped_targets.append(
                    _target_status(
                        target,
                        target_type,
                        "structure_key_missing",
                        structure_key="|".join(required_structure_keys),
                    )
                )
                return False

            structure_key, _entry, confidence = max(candidates, key=lambda item: item[2])
            if confidence < STRUCTURE_LOW_CONFIDENCE:
                skipped_targets.append(
                    _target_status(
                        target,
                        target_type,
                        "low_structure_confidence",
                        structure_key=structure_key,
                        confidence=confidence,
                    )
                )
                return False
            if confidence < STRUCTURE_HIGH_CONFIDENCE:
                review_required_targets.append(
                    _target_review_status(
                        target,
                        target_type,
                        "mid_structure_confidence",
                        structure_key=structure_key,
                        confidence=confidence,
                    )
                )
        return True

    for field in fields or []:
        if plan_one(field, "field"):
            fields_to_extract.append(field)
    for table in tables or []:
        if plan_one(table, "table"):
            tables_to_extract.append(table)

    return {
        "fields_to_extract": fields_to_extract,
        "tables_to_extract": tables_to_extract,
        "skipped_targets": skipped_targets,
        "review_required_targets": review_required_targets,
    }


def _build_yaml_cell_status(
    schema_obj: Any,
    mappings: List[Dict[str, Any]],
    skipped_targets: Optional[List[Dict[str, Any]]] = None,
    review_required_targets: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    target_by_key: Dict[str, Dict[str, Any]] = {}
    unknown_row_tables: List[Dict[str, Any]] = []

    for field in getattr(schema_obj, "fields", []) or []:
        sheet_name = field.get("sheet")
        value_cell = field.get("value_cell")
        if not sheet_name or not value_cell:
            continue
        key = f"{sheet_name}::{value_cell}"
        target_by_key[key] = {
            "excel_sheet": sheet_name,
            "excel_cell": value_cell,
            "target_type": "field",
            "target_id": field.get("id"),
        }

    for table in getattr(schema_obj, "tables", []) or []:
        table_id = table.get("id")
        sheet_name = table.get("sheet")
        start_row = table.get("data_start_row")
        end_row = table.get("data_end_row")
        row_identifier_col = table.get("row_identifier_column")

        if not sheet_name:
            continue

        if not start_row or not end_row or end_row < start_row:
            unknown_row_tables.append({
                "table_id": table_id,
                "sheet": sheet_name,
            })
            continue

        table_columns = [
            c.get("excel_column")
            for c in (table.get("columns") or [])
            if c.get("excel_column") and c.get("excel_column") != row_identifier_col
        ]

        for row_num in range(start_row, end_row + 1):
            for excel_col in table_columns:
                excel_cell = f"{excel_col}{row_num}"
                key = f"{sheet_name}::{excel_cell}"
                target_by_key[key] = {
                    "excel_sheet": sheet_name,
                    "excel_cell": excel_cell,
                    "target_type": "table",
                    "target_id": table_id,
                }

    mapped_keys = set()
    for mapping in mappings or []:
        sheet_name = mapping.get("excel_sheet")
        excel_cell = mapping.get("excel_cell")
        if not sheet_name or not excel_cell:
            continue
        key = f"{sheet_name}::{excel_cell}"
        if key in target_by_key:
            mapped_keys.add(key)

    all_target_cells = list(target_by_key.values())
    mapped_cells = [target_by_key[k] for k in target_by_key if k in mapped_keys]
    unmapped_cells = [target_by_key[k] for k in target_by_key if k not in mapped_keys]

    return {
        "all_target_cells": all_target_cells,
        "mapped_cells": mapped_cells,
        "unmapped_cells": unmapped_cells,
        "skipped_cells": skipped_targets or [],
        "review_required_cells": review_required_targets or [],
        "unknown_row_tables": unknown_row_tables,
        "total_target_cells": len(all_target_cells),
        "mapped_target_cells": len(mapped_cells),
        "unmapped_target_cells": len(unmapped_cells),
    }

@shared_task(bind=True)
def detect_fields_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Detect structured fields from PDF using Azure DI key-value pairs and tables.

    This replaces expensive LLM field detection with FREE Azure DI extraction.
    Extracts fields from:
    1. Key-value chunks (section_type="key_value_pairs")
    2. Table chunks (section_type="table")

    Args:
        payload: {
            "fill_run_id": str,
            "document_id": str,
            "job_id": str
        }

    Returns:
        Updated payload with detected fields
    """
    fill_run_id = payload["fill_run_id"]
    document_id = payload["document_id"]
    job_id = payload["job_id"]

    db = _get_db_session()
    repo = TemplateRepository(db)
    tracker = JobProgressTracker(db, job_id)

    fill_run = repo.get_fill_run_with_data(fill_run_id)
    if not fill_run:
        raise ValueError(f"Fill run not found: {fill_run_id}")
    org_id = fill_run.org_id

    # Idempotency guard: skip if already past field detection (re-queued after worker restart)
    _DETECT_DONE_STATUSES = {"fields_detected", "mapping", "awaiting_review", "filling", "completed", "failed"}
    if fill_run.status in _DETECT_DONE_STATUSES:
        logger.warning(
            f"detect_fields_task skipped — fill_run={fill_run_id} already in status={fill_run.status!r}"
        )
        _idempotent_field_mapping = fill_run.fill_run_data.field_mapping if fill_run.fill_run_data else None
        db.close()
        return {**payload, "detection_result": {"fields": _idempotent_field_mapping.get("pdf_fields", []) if _idempotent_field_mapping else [], "total_fields": 0, "categories": []}}

    try:
        logger.info(f"Detecting fields for fill run: {fill_run_id}")

        tracker.update_progress(
            status="detecting_fields",
            current_stage="field_detection",
            progress_percent=20,
            message="Extracting fields from Azure DI key-value pairs and tables"
        )

        # Get document
        document_repo = DocumentRepository()
        document = document_repo.get_by_id(document_id, org_id)
        if not document:
            raise ValueError(f"Document not found: {document_id}")

        # Get template to count Excel schema cells (not PDF detected fields)
        template = repo.get_template(fill_run.template_id)
        schema_cell_count = 0
        if template and template.schema_metadata and template.schema_metadata.get("schema_summary"):
            schema_cell_count = template.schema_metadata.get("total_yaml_fields")

        start_time = time.time()

        # Get KV and table chunks from document
        chunks = document_repo.get_chunks_for_document(document_id)

        if not chunks:
            raise ValueError(f"No chunks found for document {document_id}. Document may not be fully processed.")
        detected_fields = []
        field_id_counter = 1

        # ========================================================================
        # Extract fields from KEY-VALUE chunks
        # ========================================================================
        kv_chunks = []
        table_chunks = []
        narrative_chunks = []

        for chunk in chunks:
            # Parse metadata
            metadata = chunk.chunk_metadata or {}
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}

            # section_type is a database COLUMN, not in metadata JSON
            section_type = chunk.section_type or ""

            if section_type == "key_value_pairs":
                kv_chunks.append((chunk, metadata))
            elif section_type == "table":
                table_chunks.append((chunk, metadata))
            else:
                narrative_chunks.append((chunk, metadata))


        logger.info(f"Found {len(kv_chunks)} key-value chunks, {len(table_chunks)} table chunks, and {len(narrative_chunks)} narrative chunks")

        # Process KV chunks
        for chunk, metadata in kv_chunks:
            kv_pairs = metadata.get("key_value_pairs", [])

            for kv in kv_pairs:
                key = kv.get("key", "")
                value = kv.get("value", "")
                confidence = kv.get("confidence", 0.95)
                # Use bbox page if available (physical PDF page from Azure DI bounding_regions)
                # This is more accurate than page_number which may contain document's internal numbering
                kv_bbox = kv.get("bbox", {})
                kv_page_number = (
                    (kv_bbox.get("page") if isinstance(kv_bbox, dict) and kv_bbox else None)
                    or kv.get("page_number")
                    or metadata.get("page_number")
                    or chunk.page_number
                )
                if isinstance(kv_page_number, str) and kv_page_number.isdigit():
                    kv_page_number = int(kv_page_number)
                citation = f"[S{field_id_counter}:p{kv_page_number}]"

                if not key:
                    continue

                field_data = {
                    "id": f"kv_{field_id_counter}",
                    "name": key,
                    "type": "text",
                    "extracted_value": value or "",
                    "confidence": confidence,
                    "citations": [citation],
                    "description": f"Key-value field from page {kv_page_number}",
                    "source": "key_value_pairs"
                }
                if kv_bbox:
                    field_data["bbox"] = kv_bbox

                # DEBUG: Log first field's bbox
                if field_id_counter == 1:
                    logger.info(f"[FIELD_DETECTION] First KV field: '{key}', "
                              f"page={kv_page_number}, has bbox: {kv_bbox is not None}, bbox={kv_bbox}")

                detected_fields.append(field_data)
                field_id_counter += 1

        # ========================================================================
        # Extract fields from TABLE chunks
        # ========================================================================
        for chunk, metadata in table_chunks:
            # Extract complete table dict from chunk.tables (primary source - has ALL data from Azure DI)
            # Handle both parsed (list) and stringified (JSON string) formats from DB
            table_dict = None
            if chunk.tables:
                tables_data = chunk.tables
                # If tables_data is a JSON string, parse it first
                if isinstance(tables_data, str):
                    try:
                        tables_data = json.loads(tables_data)
                    except (json.JSONDecodeError, TypeError):
                        tables_data = None

                # Extract first table dict from parsed list
                if isinstance(tables_data, list) and len(tables_data) > 0:
                    try:
                        table_dict = tables_data[0]
                    except (IndexError, TypeError):
                        pass

            # Fallback: build minimal table dict from metadata (limited to 2 rows)
            if not table_dict:
                table_dict = {
                    "table_name": metadata.get("table_name", ""),
                    "column_headers": metadata.get("column_headers", []),
                    "table_data": metadata.get("table_data", []),
                    "page_number": metadata.get("page_number"),
                }

            # Extract table metadata from table_dict (single source of truth)
            table_name = table_dict.get("table_name", "")
            column_headers = table_dict.get("column_headers", [])
            chunk_bbox = metadata.get("bbox", {})  # Bbox is metadata-specific for PDF highlighting

            # Determine table page for citations (prefer table_dict.page_number)
            table_page = table_dict.get("page_number")
            if not table_page:
                # Fallback: derive from metadata or chunk
                page_range = metadata.get("page_range", [])
                metadata_page = metadata.get("page_number")
                range_page = page_range[0] if isinstance(page_range, list) and page_range else None
                table_page = (
                    (chunk_bbox.get("page") if isinstance(chunk_bbox, dict) and chunk_bbox else None)
                    or metadata_page
                    or range_page
                    or chunk.page_number
                )
            if isinstance(table_page, str) and table_page.isdigit():
                table_page = int(table_page)
            citation = f"[S{field_id_counter}:p{table_page}]"

            # Extract table data for per-column fields (schema matching - Stage 1)
            table_data_rows = table_dict.get("table_data", [])

            # Create per-column fields for schema alias matching (Stage 1)
            for col_idx, col_header in enumerate(column_headers):
                if not col_header or col_header.lower() in ["", "none", "n/a"]:
                    continue

                # Get sample value from first row
                extracted_value = ""
                if table_data_rows and len(table_data_rows) > 0:
                    try:
                        if col_idx < len(table_data_rows[0]):
                            extracted_value = table_data_rows[0][col_idx]
                    except (ValueError, IndexError):
                        pass

                field_data = {
                    "id": f"tbl_{field_id_counter}",
                    "name": col_header,
                    "type": "text",
                    "extracted_value": extracted_value,
                    "confidence": 0.9,  # NOTE: Hardcoded for tables (Azure DI doesn't provide per-cell confidence)
                    "citations": [citation],
                    "description": f"Column from table '{table_name}' on page {table_page}",
                    "source": "table"
                }

                if chunk_bbox:
                    field_data["bbox"] = chunk_bbox

                detected_fields.append(field_data)
                field_id_counter += 1

            # Create one table_block field per table with full row data for LLM context (Stage 1.5)
            # Pass the complete table_dict from chunk.tables directly (already well-structured)
            if column_headers:
                detected_fields.append({
                    "id": f"tbl_block_{field_id_counter}",
                    "name": table_name or "Table",
                    "type": "table",
                    "extracted_value": "",
                    "confidence": 0.9,
                    "citations": [citation],
                    "source": "table_block",
                    "table_name": table_name,
                    "table_columns": column_headers,
                    "table_rows": table_data_rows,
                    "page_number": table_page,
                })
                field_id_counter += 1

        # ========================================================================
        # Extract fields from NARRATIVE chunks (for LLM context)
        # ========================================================================
        for chunk, metadata in narrative_chunks:
            narrative_text = chunk.text or ""
            if not narrative_text.strip():
                continue

            # Extract section heading from metadata
            metadata_dict = metadata if isinstance(metadata, dict) else {}
            section_heading = ""
            if isinstance(metadata_dict.get("heading_hierarchy"), list):
                section_heading = metadata_dict["heading_hierarchy"][-1] if metadata_dict["heading_hierarchy"] else ""

            # Get page number for citation
            narrative_page = metadata_dict.get("page_number") or chunk.page_number
            if isinstance(narrative_page, str) and narrative_page.isdigit():
                narrative_page = int(narrative_page)
            # Create one narrative_block field with full text for LLM context.
            # Narrative provides market/economic/demographic context for better field matching.
            detected_fields.append(
                _build_narrative_pdf_field(
                    field_id_counter=field_id_counter,
                    narrative_text=narrative_text,
                    section_heading=section_heading,
                    narrative_page=narrative_page,
                )
            )
            field_id_counter += 1

        elapsed_ms = int((time.time() - start_time) * 1000)

        # DEBUG: Count fields with bbox
        fields_with_bbox = sum(1 for f in detected_fields if "bbox" in f)
        kv_fields_with_bbox = sum(1 for f in detected_fields if f.get("source") == "key_value_pairs" and "bbox" in f)
        table_fields_with_bbox = sum(1 for f in detected_fields if f.get("source") == "table" and "bbox" in f)
        logger.info(f"[FIELD_DETECTION] Summary: {len(detected_fields)} total fields, "
                  f"{fields_with_bbox} with bbox ({kv_fields_with_bbox} KV + {table_fields_with_bbox} table)")

        # Build detection result in same format as LLM would return
        detection_result = {
            "fields": detected_fields,
            "total_fields": len(detected_fields),
            "categories": ["key_value_pairs", "tables"]
        }

        # Update fill run with detected fields
        field_mapping = {
            "pdf_fields": detected_fields,
            "mappings": []  # Empty initially, will be filled by auto-mapping
        }

        # Build citation context: S{n}→{bbox,page,filename} lookup for frontend PDF highlighting.
        # Parallel to rag_service._build_citation_context(). targeted_schema entries appended later.
        citation_context = _build_citation_context(detected_fields, document.filename)

        # Use schema cell count as total_fields_detected (Excel cells to fill, not PDF extracted fields)
        total_to_detect = schema_cell_count if schema_cell_count > 0 else len(detected_fields)

        repo.update_fill_run_data(fill_run_id, field_mapping=field_mapping, citation_context=citation_context)
        repo.update_fill_run(
            fill_run_id,
            total_fields_detected=total_to_detect,
            field_detection_completed=True,
            status="fields_detected",
            current_stage="field_detection",
        )

        db.close()

        logger.info(
            f"Field detection complete: {len(detected_fields)} fields detected "
            f"({len([f for f in detected_fields if f['source'] == 'key_value_pairs'])} from KV, "
            f"{len([f for f in detected_fields if f['source'] == 'table'])} from tables) "
            f"in {elapsed_ms}ms (Azure DI extraction - no LLM cost!)"
        )

        tracker.update_progress(
            status="fields_detected",
            current_stage="field_detection",
            progress_percent=40,
            message=f"Detected {len(detected_fields)} fields from PDF (Azure DI)"
        )

        payload["detection_result"] = detection_result
        payload["processing_time_ms"] = elapsed_ms
        return {"status": "completed", **payload}

    except SoftTimeLimitExceeded:
        logger.warning(f"detect_fields_task soft time limit exceeded for fill_run={fill_run_id}")
        repo.update_fill_run(fill_run_id, status="failed", error_stage="field_detection",
                             error_message="Task timed out (soft limit)")
        tracker.mark_error(error_stage="field_detection", error_message="Field detection timed out",
                           error_type="timeout", is_retryable=False)
        _reverse_template_fill_shadow(fill_run_id, "field_detection_timeout", "field_detection")
        db.close()
        return {"status": "failed", "error": "timeout", **payload}

    except Exception as e:
        logger.error(f"Field detection failed: {e}", exc_info=True)
        _fail_fill_run(repo, tracker, fill_run_id, "field_detection", e)
        _reverse_template_fill_shadow(fill_run_id, "field_detection_failed", "field_detection")
        db.close()
        return {"status": "failed", "error": str(e), **payload}


@shared_task(bind=True)
def auto_map_fields_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Auto-map PDF fields to Excel cells using schema-first, then LLM fallback.

    Workflow:
    1. Try schema-based mapping (deterministic, instant)
    2. Targeted LLM for unmapped YAML fields
    3. Merge results (schema takes priority)

    Args:
        payload: {
            "fill_run_id": str,
            "template_id": str,
            "detection_result": dict,
            "job_id": str,
            "status": str (optional, "failed" if previous task failed),
            "use_schema_only": bool (optional, default False - skip generic if True),
            "skip_schema": bool (optional, default False - skip schema if True)
        }

    Returns:
        Updated payload with mapping result
    """
    # Check if previous task failed
    if payload.get("status") == "failed":
        logger.warning(f"Skipping auto-mapping because field detection failed: {payload.get('error')}")
        return payload  # Pass through the failed status

    fill_run_id = payload["fill_run_id"]
    template_id = payload["template_id"]
    detection_result = payload["detection_result"]
    job_id = payload["job_id"]

    # skip_schema controls Stage 1 (schema alias matching) - Default: True (skip alias, send all YAML fields to LLM)
    skip_schema = payload.get("skip_schema", True)

    db = _get_db_session()
    repo = TemplateRepository(db)
    tracker = JobProgressTracker(db, job_id)

    # Idempotency guard: skip if already past auto-mapping (re-queued after worker restart)
    _fill_run_check = repo.get_fill_run_with_data(fill_run_id)
    _AUTO_MAP_DONE_STATUSES = {"awaiting_review", "filling", "completed", "failed"}
    if _fill_run_check and _fill_run_check.status in _AUTO_MAP_DONE_STATUSES:
        logger.warning(
            f"auto_map_fields_task skipped — fill_run={fill_run_id} already in status={_fill_run_check.status!r}"
        )
        db.close()
        _idempotent_fm = _fill_run_check.fill_run_data.field_mapping if _fill_run_check.fill_run_data else None
        return {**payload, "mapping_result": _idempotent_fm or {}}

    try:
        task_start_time = time.time()
        logger.info(f"Auto-mapping fields for fill run: {fill_run_id}")

        tracker.update_progress(
            status="mapping",
            current_stage="auto_mapping",
            progress_percent=50,
            message="Mapping PDF fields to Excel cells"
        )

        # Get template
        template = repo.get_template(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        excel_schema = template.schema_metadata
        if not excel_schema:
            raise ValueError(f"Template schema not found: {template_id}")

        # Keep the Azure DI evidence pool intact. Stage 2 adds virtual targeted
        # fields to `pdf_fields`, but routing/budgeting always starts from the
        # untouched originals below.
        all_pdf_fields = list(detection_result.get("fields", []))
        pdf_fields = list(all_pdf_fields)

        # Load citation_context built by detect_fields_task; we'll append targeted entries to it.
        # Reuse _fill_run_check already fetched above (avoids a second DB round-trip).
        fill_run_for_ctx = _fill_run_check
        citation_context = (fill_run_for_ctx.fill_run_data.citation_context or {"citations": []}) if (fill_run_for_ctx and fill_run_for_ctx.fill_run_data) else {"citations": []}
        # Fast lookup: source_index → bbox (for targeted_schema bbox resolution)
        _source_field_bbox: Dict[int, Dict] = {
            e["source_index"]: e["bbox"]
            for e in citation_context.get("citations", [])
            if e.get("bbox")
        }
        context_budget: Dict[str, Any] = {
            "context_budget_applied": False,
            "user_warning": None,
            "scalar_batches": {},
            "table_batches": {},
        }
        schema_mappings = []
        schema_id = None
        schema_obj = None
        schema_table_row_labels: Dict[str, Any] = {}
        schema_summary: Optional[Dict[str, Any]] = None

        # === STEP 1: Identify template schema (always, regardless of skip_schema) ===
        # Schema identification is separate from alias mapping creation.
        # We identify the schema for Stage 1.5 targeted LLM, but only create mappings if skip_schema=False.
        template_path = None
        workbook = None
        try:
            from openpyxl import load_workbook

            # Download template file from R2 to worker-local /tmp
            storage = get_storage_backend()
            template_path = storage.download_to_temp(template.file_path)

            # Load workbook for fingerprint check
            workbook = load_workbook(template_path, data_only=False)

            # Identify template (ALWAYS, regardless of skip_schema flag)
            schema_id = mapping_coordinator.identify_template(workbook)

            if schema_id:
                logger.info(f"✓ Template identified as: {schema_id}")
                # Extract row labels for schema tables (used in targeted table extraction)
                schema_obj_for_rows = mapping_coordinator.schema_loader.load_schema(schema_id)
                if schema_obj_for_rows:
                    schema_obj = schema_obj_for_rows
                    schema_table_row_labels = _extract_schema_table_row_labels(schema_obj_for_rows, workbook)
                    schema_summary = _compute_schema_counts(schema_obj_for_rows)
                    logger.info(
                        "YAML schema summary: fields=%s table_cells=%s total=%s",
                        schema_summary.get("yaml_field_count"),
                        schema_summary.get("yaml_table_cells"),
                        schema_summary.get("total_yaml_fields"),
                    )

                # === STEP 1a: Create schema mappings (only if skip_schema=False) ===
                if not skip_schema:
                    schema_mappings = mapping_coordinator.create_schema_mappings(schema_id, pdf_fields)

                    logger.info(f"Schema mapping: {len(schema_mappings)} fields mapped (confidence=0.98 baseline)")

                    # Log unmapped schema fields (diagnostics)
                    try:
                        from app.verticals.real_estate.template_filling.excel.schema_based import SchemaMapper

                        schema = mapping_coordinator.schema_loader.load_schema(schema_id)
                        if schema:
                            mapper = SchemaMapper(schema)
                            unmapped_field_ids = mapper.get_unmapped_schema_fields(schema_mappings)
                            if unmapped_field_ids:
                                logger.warning(
                                    f"Schema fields without PDF data ({len(unmapped_field_ids)}): "
                                    f"{', '.join(unmapped_field_ids[:10])}"
                                    f"{'...' if len(unmapped_field_ids) > 10 else ''}"
                                )
                    except Exception as e:
                        logger.debug(f"Could not check unmapped schema fields: {e}")

                    tracker.update_progress(
                        status="mapping",
                        current_stage="auto_mapping",
                        progress_percent=50,
                        message=f"Schema matched {len(schema_mappings)} fields by alias"
                    )
                else:
                    logger.info("Skipping alias mapping (skip_schema=True) — will use LLM only for schema fields")
            else:
                raise ValueError(
                    f"Template {template_id} does not match any known schema. "
                    "Only pre-defined master templates are supported."
                )

        except ValueError:
            raise
        except Exception as e:
            raise RuntimeError(f"Schema identification failed for template {template_id}: {e}") from e
        finally:
            # Always clean up — even if load_workbook or identify_template throws
            if workbook is not None:
                try:
                    workbook.close()
                except Exception:
                    pass
            if template_path:
                Path(template_path).unlink(missing_ok=True)

        # === STEP 1.5: Targeted LLM for unmapped YAML fields (Stage 2) ===
        # Ask LLM specifically: "find values for these 63 named fields in the Azure DI data"
        # Much cheaper and more accurate than the generic 6-batch sheet mapper for schema fields.
        # Always runs when schema is available
        llm_service_targeted = None
        om_structure_artifact: Optional[Dict[str, Any]] = None
        structure_plan: Dict[str, Any] = {
            "fields_to_extract": [],
            "tables_to_extract": [],
            "skipped_targets": [],
            "review_required_targets": [],
        }
        if schema_id:
            try:
                from app.verticals.real_estate.template_filling.excel.schema_based import SchemaMapper

                schema_obj = mapping_coordinator.schema_loader.load_schema(schema_id)
                if schema_obj:
                    mapper_for_unmapped = SchemaMapper(schema_obj)
                    unmapped_field_ids = mapper_for_unmapped.get_unmapped_schema_fields(schema_mappings)
                    unmapped_fields = [
                        schema_obj.get_field(fid)
                        for fid in unmapped_field_ids
                        if schema_obj.get_field(fid) is not None
                    ]

                    schema_tables = schema_obj.tables or []
                    source_pdf_fields_for_table_context = list(all_pdf_fields)

                    if unmapped_fields or schema_tables:
                        llm_service_targeted = TemplateFillLLMService(
                            prompt_version=settings.re_template_prompt_version,
                            capture_io_log=settings.capture_llm_io_log,
                            fill_run_id=fill_run_id,
                        )

                        tracker.update_progress(
                            status="mapping",
                            current_stage="auto_mapping",
                            progress_percent=52,
                            message="Detecting OM source map..."
                        )
                        detected_structure = asyncio.run(
                            llm_service_targeted.detect_om_structure(all_pdf_fields)
                        )
                        detected_structure = normalize_om_structure_with_pdf_fields(
                            detected_structure,
                            all_pdf_fields,
                        )
                        om_structure_artifact = _build_om_structure_artifact(
                            detected_structure,
                            llm_service_targeted.model,
                        )

                        repo.merge_fill_run_extracted_data(
                            fill_run_id,
                            {"om_structure": om_structure_artifact},
                        )

                        structure_plan = _plan_schema_targets_for_structure(
                            unmapped_fields,
                            schema_tables,
                            detected_structure,
                        )
                        unmapped_fields = structure_plan["fields_to_extract"]
                        schema_tables = structure_plan["tables_to_extract"]
                        logger.info(
                            "OM structure plan: extract fields=%s tables=%s skipped=%s review=%s",
                            len(unmapped_fields),
                            len(schema_tables),
                            len(structure_plan["skipped_targets"]),
                            len(structure_plan["review_required_targets"]),
                        )

                    if unmapped_fields:
                        logger.info(
                            f"🎯 Stage 2: {len(unmapped_fields)} unmapped YAML fields → targeted LLM"
                        )
                        tracker.update_progress(
                            status="mapping",
                            current_stage="auto_mapping",
                            progress_percent=55,
                            message=f"Finding values for {len(unmapped_fields)} schema fields..."
                        )

                        targeted_values: Dict[str, Any] = {}
                        scalar_batches: Dict[str, List[Dict[str, Any]]] = {}
                        for field_def in unmapped_fields:
                            scalar_batches.setdefault(_get_scalar_batch_key(field_def), []).append(field_def)

                        prepared_scalar_batches: List[Dict[str, Any]] = []
                        for batch_key, batch_fields in scalar_batches.items():
                            scalar_context, scalar_budget = _build_scalar_context_for_batch(
                                all_pdf_fields,
                                om_structure_artifact.get("effective") if om_structure_artifact else {},
                                batch_fields,
                            )
                            context_budget["scalar_batches"][batch_key] = scalar_budget
                            if scalar_budget.get("context_budget_applied"):
                                context_budget["context_budget_applied"] = True
                                if scalar_budget.get("user_warning"):
                                    context_budget["user_warning"] = scalar_budget["user_warning"]
                            logger.info(
                                "Scalar context prepared for batch %s: %s → %s fields (routing=%s, citation_pages=%s)",
                                batch_key,
                                scalar_budget["source_field_count_before_routing"],
                                len(scalar_context),
                                scalar_budget["routing_applied"],
                                scalar_budget["citation_pages"],
                            )
                            prepared_scalar_batches.append({
                                "batch_key": batch_key,
                                "fields": batch_fields,
                                "context": scalar_context,
                                "budget": scalar_budget,
                            })

                        consolidated_scalar_batches = _consolidate_scalar_batches_by_context(
                            prepared_scalar_batches
                        )
                        context_budget["scalar_batch_summary"] = {
                            "original_batch_count": len(prepared_scalar_batches),
                            "consolidated_call_count": len(consolidated_scalar_batches),
                        }
                        logger.info(
                            "Scalar LLM call consolidation: original_batches=%s consolidated_calls=%s",
                            len(prepared_scalar_batches),
                            len(consolidated_scalar_batches),
                        )

                        for consolidated_batch in consolidated_scalar_batches:
                            batch_keys = consolidated_batch["batch_keys"]
                            batch_fields = consolidated_batch["fields"]
                            scalar_context = consolidated_batch["context"]
                            if len(batch_keys) > 1:
                                logger.info(
                                    "Merged scalar batches with identical context: batches=%s fields=%s",
                                    batch_keys,
                                    len(batch_fields),
                                )
                            batch_values = asyncio.run(
                                llm_service_targeted.extract_schema_field_values(
                                    batch_fields,
                                    scalar_context,
                                    om_structure=(
                                        om_structure_artifact.get("effective")
                                        if om_structure_artifact
                                        else None
                                    ),
                                )
                            )
                            targeted_values.update(batch_values)

                        targeted_mappings = mapping_coordinator.create_targeted_schema_mappings(
                            unmapped_fields, targeted_values
                        )

                        # Inject virtual pdf_fields so fill_excel_task can look up extracted values.
                        # TemplateFiller looks up: llm_extracted[pdf_field_id] = {value: ...}
                        # fill_excel_task populates llm_extracted from pdf_fields[*].extracted_value
                        for field_def in unmapped_fields:
                            fid = field_def["id"]
                            if fid in targeted_values:
                                result = targeted_values[fid]
                                normalized_cits = normalize_citations(result.get("citations", []))

                                # Resolve exact bbox via citation_context lookup (S{n} → source field bbox).
                                # This is a direct index lookup, not a page-scan heuristic.
                                field_bbox = None
                                for cit in normalized_cits:
                                    cm = re.search(r'\[(?:S|D)(\d+):', cit)
                                    if cm:
                                        field_bbox = _source_field_bbox.get(int(cm.group(1)))
                                        if field_bbox:
                                            break

                                virtual_field = {
                                    "id": f"targeted_{fid}",
                                    "name": fid,
                                    "type": field_def.get("data_type", "text"),
                                    "extracted_value": result["value"],
                                    "confidence": result["confidence"],
                                    "citations": normalized_cits,
                                    "reasoning": result.get("reasoning"),
                                    "source": "targeted_schema",
                                }
                                if field_bbox:
                                    virtual_field["bbox"] = field_bbox
                                pdf_fields.append(virtual_field)

                        # Merge targeted mappings into schema_mappings so they're
                        # excluded from the Stage 3 generic pass automatically
                        schema_mappings = schema_mappings + targeted_mappings

                        # Celery heartbeat: yield to heartbeat handler between LLM calls
                        self.update_state(
                            state="PROGRESS",
                            meta={"stage": "targeted_schema_mapping_done"}
                        )

                        tracker.update_progress(
                            status="mapping",
                            current_stage="auto_mapping",
                            progress_percent=70,
                            message=(
                                f"Found {len(targeted_mappings)} additional fields via targeted LLM "
                                f"({len(schema_mappings)} schema total)"
                            )
                        )

                    if schema_tables:
                        logger.info(
                            f"🎯 Stage 2: {len(schema_tables)} schema tables → targeted LLM"
                        )
                        tracker.update_progress(
                            status="mapping",
                            current_stage="auto_mapping",
                            progress_percent=70,
                            message=f"Extracting values for {len(schema_tables)} schema tables..."
                        )

                        targeted_table_values = {}
                        table_batches: Dict[str, List[Dict[str, Any]]] = {}
                        for table_def in schema_tables:
                            table_id = table_def.get("id")
                            if not table_id:
                                continue
                            batch_key = _get_table_batch_key(table_def)
                            table_batches.setdefault(batch_key, []).append(table_def)

                        effective_om = (
                            om_structure_artifact.get("effective") if om_structure_artifact else None
                        )

                        for batch_key, batch_tables in table_batches.items():
                            if not source_pdf_fields_for_table_context:
                                logger.info(f"No pdf_fields available for table batch {batch_key}")
                                continue

                            # Collect citation pages for this batch's fill_when keys
                            fill_when_keys: set = set()
                            for tbl in batch_tables:
                                for k in (tbl.get("fill_when") or []):
                                    fill_when_keys.add(k)
                            citation_pages: List[int] = []
                            for key in fill_when_keys:
                                citation_pages.extend(
                                    _get_section_citation_pages(effective_om or {}, key)
                                )

                            if citation_pages:
                                filtered = [
                                    f for f in source_pdf_fields_for_table_context
                                    if (pg := _field_page(f)) is None
                                    or any(abs(pg - p) <= 1 for p in citation_pages)
                                ]
                                logger.info(
                                    "Table context filtered for batch %s: %s → %s fields (citation pages %s)",
                                    batch_key, len(source_pdf_fields_for_table_context),
                                    len(filtered), sorted(set(citation_pages)),
                                )
                            else:
                                filtered = source_pdf_fields_for_table_context

                            table_context_fields, table_budget = _build_budgeted_pdf_fields(filtered)
                            table_budget = {
                                **table_budget,
                                "routing_applied": bool(citation_pages),
                                "citation_pages": sorted(set(citation_pages)),
                                "source_field_count_before_routing": len(source_pdf_fields_for_table_context),
                                "source_field_count_after_routing": len(filtered),
                            }
                            context_budget["table_batches"][batch_key] = table_budget
                            if table_budget.get("context_budget_applied"):
                                context_budget["context_budget_applied"] = True
                                if table_budget.get("user_warning"):
                                    context_budget["user_warning"] = table_budget["user_warning"]
                            context_payload = llm_service_targeted._build_table_context_from_pdf_fields(table_context_fields)
                            table_context_json: Optional[str] = json.dumps(
                                context_payload, separators=(",", ":"), ensure_ascii=False
                            )

                            row_labels_by_table: Dict[str, List[str]] = {}

                            for table_def in batch_tables:
                                table_id = table_def.get("id")
                                if not table_id:
                                    continue
                                row_labels = schema_table_row_labels.get(table_id, {}).get("row_labels", [])
                                if row_labels and all(not str(lbl).strip() for lbl in row_labels):
                                    logger.info(
                                        f"Row labels empty for table {table_id}; using row_index order"
                                    )
                                    row_labels = []
                                row_labels_by_table[table_id] = row_labels

                            logger.info(
                                f"Table batch extraction: batch={batch_key} tables={len(batch_tables)}"
                            )

                            batch_result = asyncio.run(
                                llm_service_targeted.extract_schema_table_values_rag_batch(
                                    batch_tables,
                                    table_context_fields,
                                    row_labels_by_table=row_labels_by_table,
                                    prebuilt_context_json=table_context_json,
                                    om_structure=(
                                        om_structure_artifact.get("effective")
                                        if om_structure_artifact
                                        else None
                                    ),
                                )
                            )
                            if batch_result:
                                targeted_table_values.update(batch_result)

                        targeted_table_mappings = mapping_coordinator.create_targeted_schema_table_mappings(
                            schema_tables, targeted_table_values, schema_table_row_labels
                        )

                        for mapping in targeted_table_mappings:
                            extracted_value = mapping.get("extracted_value")
                            if extracted_value is None:
                                continue
                            pdf_fields.append({
                                "id": mapping.get("pdf_field_id"),
                                "name": mapping.get("pdf_field_name"),
                                "type": mapping.get("data_type", "text"),
                                "extracted_value": extracted_value,
                                "confidence": mapping.get("confidence", 0.7),
                                "citations": normalize_citations(mapping.get("citations", [])),
                                "reasoning": mapping.get("reasoning"),
                                "source": "targeted_schema",
                            })

                        schema_mappings = schema_mappings + targeted_table_mappings

                        tracker.update_progress(
                            status="mapping",
                            current_stage="auto_mapping",
                            progress_percent=70,
                            message=(
                                f"Found {len(targeted_table_mappings)} table cells via targeted LLM "
                                f"({len(schema_mappings)} schema total)"
                            )
                        )

                    if not unmapped_fields and not schema_tables:
                        logger.info("All YAML schema fields matched in Stage 1 — skipping Stage 2")
                        tracker.update_progress(
                            status="mapping",
                            current_stage="auto_mapping",
                            progress_percent=70,
                            message=f"All schema fields matched ({len(schema_mappings)} total)"
                        )
            except Exception:
                logger.error("Stage 2 targeted mapping failed", exc_info=True)
                raise

        # === STEP 2: Merge schema mappings (schema alias + targeted LLM) ===
        raw_mappings = schema_mappings

        # Deduplicate by Excel cell — schema alias beats targeted_schema beats any other source.
        def _tier_priority(mapping: dict) -> int:
            source = mapping.get("source")
            if source == "schema":
                return 2
            if source == "targeted_schema":
                return 1
            return 0

        best_by_cell: dict[str, dict] = {}
        for m in raw_mappings:
            excel_sheet = m.get("excel_sheet", "")
            excel_cell = m.get("excel_cell", "")
            if not excel_sheet or not excel_cell:
                continue

            cell_key = f"{excel_sheet}!{excel_cell}"
            current_best = best_by_cell.get(cell_key)
            current_best_tier = _tier_priority(current_best or {})
            candidate_tier = _tier_priority(m)
            current_best_conf = float((current_best or {}).get("confidence") or 0)
            candidate_conf = float(m.get("confidence") or 0)

            if (
                current_best is None
                or candidate_tier > current_best_tier
                or (candidate_tier == current_best_tier and candidate_conf > current_best_conf)
            ):
                best_by_cell[cell_key] = m

        mappings = list(best_by_cell.values())
        total_mapped_fields = len(mappings)

        # Count unique PDF fields that have at least one mapping
        unique_pdf_fields_mapped = len(set(m.get("pdf_field_id") for m in mappings if m.get("pdf_field_id")))

        targeted_count = sum(1 for m in mappings if m.get("source") == "targeted_schema")
        schema_count = sum(1 for m in mappings if m.get("source") == "schema")

        logger.info(
            f"Mapping deduplication: {len(raw_mappings)} raw → "
            f"{len(mappings)} after cell dedup "
            f"({unique_pdf_fields_mapped} unique PDF fields mapped to {len(mappings)} Excel cells) "
            f"[{schema_count} alias + {targeted_count} targeted_llm]"
        )

        mapping_result = {
            "mappings": mappings,
            "total_mapped": total_mapped_fields,
            "schema_mapped_count": schema_count,
            "targeted_schema_count": targeted_count,
            "high_confidence_count": sum(1 for m in mappings if m.get("confidence", 0) >= STRUCTURE_HIGH_CONFIDENCE)
        }

        field_mapping = {
            "pdf_fields": pdf_fields,
            "mappings": mappings,
        }
        if context_budget.get("context_budget_applied"):
            field_mapping["context_budget"] = context_budget
        if schema_obj:
            field_mapping["yaml_cell_status"] = _build_yaml_cell_status(
                schema_obj,
                mappings,
                skipped_targets=structure_plan.get("skipped_targets"),
                review_required_targets=structure_plan.get("review_required_targets"),
            )
        if schema_summary:
            field_mapping["schema_summary"] = schema_summary
        if om_structure_artifact:
            field_mapping["om_structure_summary"] = {
                "extractor_version": om_structure_artifact.get("extractor_version"),
                "confidence_summary": om_structure_artifact.get("confidence_summary"),
                "edited": om_structure_artifact.get("edited"),
            }

        # Persist metadata (mapping, token data, completion flag)
        # Progress updates via SSE (JobState)
        metadata_params = {
            "field_mapping": field_mapping,
            "total_fields_mapped": total_mapped_fields,
            "auto_mapped_count": total_mapped_fields,
            "user_edited_count": 0,
            "auto_mapping_completed": True,
        }

        metadata_params["status"] = "awaiting_review"
        metadata_params["current_stage"] = "auto_mapping"
        # Persist accumulated compute time (detect + full map task) so fill_excel_task can add to it.
        # task_start_time captures the entire auto_map_fields_task wall-clock including targeted LLM calls.
        map_elapsed_ms = int((time.time() - task_start_time) * 1000)
        metadata_params["processing_time_ms"] = payload.get("processing_time_ms", 0) + map_elapsed_ms
        blob_params = {k: metadata_params.pop(k) for k in ["field_mapping", "citation_context", "extracted_data"] if k in metadata_params}
        if blob_params:
            repo.update_fill_run_data(fill_run_id, **blob_params)
        repo.update_fill_run(fill_run_id, **metadata_params)

        db.close()

        logger.info(
            f"Auto-mapping complete: {len(mappings)} Excel cells mapped "
            f"(from {unique_pdf_fields_mapped} unique PDF fields) — "
            f"{schema_count} alias + {targeted_count} targeted LLM"
        )

        parts = []
        if schema_count:
            parts.append(f"{schema_count} alias")
        if targeted_count:
            parts.append(f"{targeted_count} targeted LLM")
        status_msg = (
            f"Mapped {len(mappings)} cells ({', '.join(parts)})"
            if parts
            else f"Mapped {len(mappings)} cells"
        )

        tracker.update_progress(
            status="awaiting_review",
            current_stage="auto_mapping",
            progress_percent=85,
            message=status_msg
        )

        payload["mapping_result"] = mapping_result
        payload["processing_time_ms"] = payload.get("processing_time_ms", 0) + map_elapsed_ms
        return {"status": "completed", **payload}

    except SoftTimeLimitExceeded:
        logger.warning(f"auto_map_fields_task soft time limit exceeded for fill_run={fill_run_id}")
        repo.update_fill_run(fill_run_id, status="failed", error_stage="auto_mapping",
                             error_message="Task timed out (soft limit)")
        tracker.mark_error(error_stage="auto_mapping", error_message="Auto-mapping timed out",
                           error_type="timeout", is_retryable=False)
        _reverse_template_fill_shadow(fill_run_id, "auto_mapping_timeout", "auto_mapping")
        db.close()
        return {"status": "failed", "error": "timeout", **payload}

    except Exception as e:
        logger.error(f"Auto-mapping failed: {e}", exc_info=True)

        _mark_auto_mapping_exception(repo, tracker, fill_run_id, e)
        _reverse_template_fill_shadow(fill_run_id, "auto_mapping_failed", "auto_mapping")

        db.close()
        return {"status": "failed", "error": str(e), **payload}


@shared_task(bind=True)
def fill_excel_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fill Excel template with data from Azure DI (extracted_value).

    Phase 5 (LLM extraction) has been removed - we use Azure DI values directly!

    Args:
        payload: {
            "fill_run_id": str,
            "template_id": str,
            "job_id": str
        }

    Returns:
        Updated payload with artifact info
    """
    # Check if previous task failed
    if payload.get("status") == "failed":
        logger.warning(f"Skipping Excel filling because previous task failed: {payload.get('error')}")
        return payload  # Pass through the failed status

    fill_run_id = payload["fill_run_id"]
    template_id = payload["template_id"]
    job_id = payload["job_id"]

    db = _get_db_session()
    repo = TemplateRepository(db)
    tracker = JobProgressTracker(db, job_id)

    # Idempotency guard: skip if already completed (re-queued after worker restart)
    _fill_run_check = repo.get_fill_run(fill_run_id)
    if _fill_run_check and _fill_run_check.status in ("completed", "failed"):
        logger.warning(
            f"fill_excel_task skipped — fill_run={fill_run_id} already in status={_fill_run_check.status!r}"
        )
        db.close()
        return {**payload, "status": _fill_run_check.status}

    # Start latency timer
    start_time = time.monotonic()

    try:
        logger.info(f"Filling Excel for fill run: {fill_run_id}")

        tracker.update_progress(
            status="filling",
            current_stage="excel_filling",
            progress_percent=90,
            message="Filling Excel template"
        )

        # Get fill run with field mapping and extracted data
        fill_run = repo.get_fill_run_with_data(fill_run_id)
        if not fill_run:
            raise ValueError(f"Fill run not found: {fill_run_id}")

        field_mapping = fill_run.fill_run_data.field_mapping if fill_run.fill_run_data else {}

        # Get template
        template = repo.get_template(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        # Get file extension from template (e.g., ".xlsx" or ".xlsm")
        file_ext = template.file_extension or ".xlsx"

        # Download template file from storage WITH CORRECT EXTENSION
        storage = get_storage_backend()
        template_local_path = f"/tmp/template_{template_id}{file_ext}"
        storage.download(template.file_path, template_local_path)

        # Prepare output path WITH CORRECT EXTENSION
        output_local_path = f"/tmp/filled_{fill_run_id}{file_ext}"

        # Get extracted_data in clean nested schema format
        # Schema: {
        #   "llm_extracted": {field_id: {...}, ...},
        #   "manual_edits": {sheet_name: {cell_address: {...}, ...}, ...}
        # }
        extracted_data = (fill_run.fill_run_data.extracted_data if fill_run.fill_run_data else {}) or {"llm_extracted": {}, "manual_edits": {}}

        llm_extracted = extracted_data.get("llm_extracted", {})
        manual_edits = extracted_data.get("manual_edits", {})

        # Validate manual_edits structure (protect against data corruption)
        if not isinstance(manual_edits, dict):
            logger.warning(f"manual_edits is not a dict (type: {type(manual_edits)}), resetting to empty dict")
            manual_edits = {}
        else:
            # Ensure all sheet values are dicts (clean up corrupted entries)
            cleaned_manual_edits = {}
            for sheet_name, cells in manual_edits.items():
                if isinstance(cells, dict):
                    cleaned_manual_edits[sheet_name] = cells
                else:
                    logger.warning(f"Skipping corrupted manual_edits entry: {sheet_name} (type: {type(cells)})")
            manual_edits = cleaned_manual_edits

        # Add LLM auto-mapped values as fallback (matches UI getCellValue)
        pdf_fields = field_mapping.get('pdf_fields', [])
        for pdf_field in pdf_fields:
            field_id = pdf_field.get('id')
            auto_mapped_value = pdf_field.get('extracted_value')

            # Only add if not already in llm_extracted (user edits take precedence).
            # Use `is not None` (not truthiness) so empty strings still populate the entry;
            # an empty extracted_value means Azure DI found the key but not the value —
            # the mapping confidence will reflect this via schema_mapper's has_value flag.
            if field_id and field_id not in llm_extracted and auto_mapped_value is not None:
                field_entry = {
                    'value': auto_mapped_value,
                    'confidence': pdf_field.get('confidence', 0.95),
                    'citations': pdf_field.get('citations', []),
                    'user_edited': False
                }
                # Include bbox for PDF highlighting if available
                if 'bbox' in pdf_field:
                    field_entry['bbox'] = pdf_field['bbox']

                llm_extracted[field_id] = field_entry

        user_edited_count = sum(len(cells) for cells in manual_edits.values())
        auto_mapped_count = len(llm_extracted) - sum(1 for data in llm_extracted.values() if data.get('user_edited'))

        # Prepare clean extracted_data for filling
        extracted_data = {
            "llm_extracted": llm_extracted,
            "manual_edits": manual_edits
        }

        logger.info(
            f"Prepared extracted_data for filling: {user_edited_count} user-edited + "
            f"{auto_mapped_count} LLM auto-mapped = {len(llm_extracted)} total"
        )

        # Initialize Excel handler
        handler = ExcelHandler()

        # Fill template
        fill_summary = handler.fill_template(
            template_path=template_local_path,
            output_path=output_local_path,
            field_mapping=field_mapping,
            extracted_data=extracted_data
        )

        # Generate storage key: fills/{YYYY}/{MM}/{DD}/{fill_run_id}_{template_name}_filled{ext}
        # Date-partitioned, consistent with workflow-artifacts. Readable in R2 browser.
        _now = datetime.now(timezone.utc)
        safe_template_name = template.name.replace("/", "_").replace("\\", "_")
        storage_key = (
            f"fills/{_now.year}/{_now.month:02d}/{_now.day:02d}"
            f"/{fill_run_id}_{safe_template_name}_filled{file_ext}"
        )
        storage.upload(output_local_path, storage_key)

        # Create artifact metadata WITH CORRECT EXTENSION
        artifact = {
            "backend": settings.storage_backend,
            "key": storage_key,
            "size": Path(output_local_path).stat().st_size,
            "filename": f"{safe_template_name}_filled{file_ext}"
        }

        # Update fill run
        repo.update_fill_run(
            fill_run_id,
            artifact=artifact,
            status="completed",
            filling_completed=True,
            completed_at=datetime.now(timezone.utc),
            total_fields_filled=fill_summary.get("total_cells_filled", 0),
            processing_time_ms=(fill_run.processing_time_ms or 0) + int((time.monotonic() - start_time) * 1000)
        )

        # Record metrics
        record_template_fill_completed(org_id=fill_run.org_id)

        # Record latency
        latency = time.monotonic() - start_time
        try:
            TEMPLATE_FILL_LATENCY_SECONDS.observe(latency)
        except Exception as e:
            logger.warning(f"Failed to record template fill latency: {e}", exc_info=True)

        db.close()

        logger.info(
            f"Excel filling complete: {fill_summary['total_cells_filled']} cells filled"
        )
        commit_shadow_credits(operation_type="template_fill_run", reference_id=fill_run_id)

        # Use mark_completed() to send proper SSE termination events ("complete" + "end")
        # NOT just update_progress() which only sends "progress" event
        # This ensures the SSE stream terminates properly and UI receives completion signal
        tracker.mark_completed()

        payload["artifact"] = artifact
        payload["fill_summary"] = fill_summary
        return {"status": "completed", **payload}

    except SoftTimeLimitExceeded:
        logger.warning(f"fill_excel_task soft time limit exceeded for fill_run={fill_run_id}")
        repo.update_fill_run(fill_run_id, status="failed", error_stage="excel_filling",
                             error_message="Task timed out (soft limit)")
        tracker.mark_error(error_stage="excel_filling", error_message="Excel filling timed out",
                           error_type="timeout", is_retryable=False)
        _reverse_template_fill_shadow(fill_run_id, "excel_filling_timeout", "excel_filling")
        db.close()
        return {"status": "failed", "error": "timeout", **payload}

    except Exception as e:
        logger.error(f"Excel filling failed: {e}", exc_info=True)

        repo.update_fill_run(
            fill_run_id,
            status="failed",
            error_stage="excel_filling",
            error_message=str(e)
        )

        # Record metrics
        record_template_fill_failed(org_id=fill_run.org_id if fill_run else None)

        # Record latency (even for failures)
        latency = time.monotonic() - start_time
        try:
            TEMPLATE_FILL_LATENCY_SECONDS.observe(latency)
        except Exception as e:
            logger.warning(f"Failed to record template fill latency: {e}", exc_info=True)

        # Use mark_error() to send proper SSE termination events ("error" + "end")
        # NOT just update_progress() which only sends "progress" event
        tracker.mark_error(
            error_stage="excel_filling",
            error_message="Failed to fill template — please try again.",
            internal_error=str(e)[:1000],
            error_type="fill_error",
            is_retryable=False
        )
        _reverse_template_fill_shadow(fill_run_id, "excel_filling_failed", "excel_filling")

        db.close()
        return {"status": "failed", "error": str(e), **payload}


@shared_task(bind=True)
def start_fill_run_chain(
    self,
    template_id: str,
    document_id: str,
    user_id: str,
    fill_run_name: str | None = None,
) -> str:
    """
    Orchestrate the full template filling pipeline.

    Pipeline:
    1. Detect PDF fields (LLM)
    2. Auto-map to Excel cells (LLM)
    3. Wait for user review/edits (pause point)
    4. Extract data (LLM) - triggered separately after user confirmation
    5. Fill Excel (openpyxl)

    Args:
        template_id: Excel template ID
        document_id: PDF document ID
        user_id: User ID

    Returns:
        Fill run ID
    """
    db = _get_db_session()
    repo = TemplateRepository(db)

    try:
        logger.info(
            f"Starting fill run chain: template={template_id}, document={document_id}"
        )

        # Get template
        template = repo.get_template(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        # Create fill run
        template_snapshot = {
            "name": template.name,
            "description": template.description,
            "schema_metadata": template.schema_metadata,
        }

        fill_run = repo.create_fill_run(
            template_id=template_id,
            document_id=document_id,
            org_id=template.org_id,
            user_id=user_id,
            template_snapshot=template_snapshot,
            name=fill_run_name,
        )

        fill_run_id = fill_run.id

        # Create JobState for progress tracking (linked to fill run)
        job_id = fill_run_id  # Use fill_run_id as job tracking ID
        job_repo = JobRepository()
        job_state = job_repo.create_job(
            entity_type="template_fill_run",
            entity_id=fill_run_id,
            status="queued",
            current_stage="initialization",
            progress_percent=5,
            job_id=job_id
        )
        if not job_state:
            raise ValueError("Failed to create job state for fill run")

        db.close()

        # Build task chain (steps 1-2, then pause for user review)
        # User will trigger steps 3-4 via separate API call after reviewing mappings
        task_chain = chain(
            detect_fields_task.s({
                "fill_run_id": fill_run_id,
                "template_id": template_id,
                "document_id": document_id,
                "job_id": job_id,
            }),
            auto_map_fields_task.s(),
        )

        # Execute chain
        task_chain.apply_async(queue='critical')

        logger.info(f"Fill run chain started: {fill_run_id} (queue=critical)")

        return fill_run_id

    except Exception as e:
        logger.error(f"Failed to start fill run chain: {e}", exc_info=True)
        db.close()
        raise


@shared_task(bind=True)
def continue_fill_run_chain(
    self,
    fill_run_id: str,
    job_id: str,
) -> Dict[str, Any]:
    """
    Continue fill run pipeline after user has reviewed mappings.

    Phase 5 (LLM extraction) has been removed!
    This now executes only step 3:
    3. Fill Excel template (openpyxl) using Azure DI sample values

    Args:
        fill_run_id: Fill run ID
        job_id: Job tracking ID

    Returns:
        Final result with artifact
    """
    db = _get_db_session()
    repo = TemplateRepository(db)
    tracker = JobProgressTracker(db, job_id)

    try:
        logger.info(f"Continuing fill run: {fill_run_id}")

        # Get fill run
        fill_run = repo.get_fill_run(fill_run_id)
        if not fill_run:
            raise ValueError(f"Fill run not found: {fill_run_id}")

        # Mark user review as completed
        repo.update_fill_run(
            fill_run_id,
            user_review_completed=True,
            status="filling"  # Go directly to filling (skip extraction)
        )

        db.close()

        # Execute fill task directly (no extraction needed!)
        # Phase 5 removed - we use Azure DI extracted_value directly
        fill_excel_task.apply_async(
            kwargs={
                "payload": {
                    "fill_run_id": fill_run_id,
                    "template_id": fill_run.template_id,
                    "job_id": job_id,
                }
            }
        )

        logger.info(f"Fill run continuation started (direct to filling): {fill_run_id}")

        return {"fill_run_id": fill_run_id, "status": "processing"}

    except Exception as e:
        logger.error(f"Failed to continue fill run: {e}", exc_info=True)

        tracker.update_progress(
            status="failed",
            current_stage="continuation",
            message=f"Failed to continue fill run: {str(e)}"
        )
        _reverse_template_fill_shadow(fill_run_id, "continue_fill_failed", "continuation")

        db.close()
        raise
