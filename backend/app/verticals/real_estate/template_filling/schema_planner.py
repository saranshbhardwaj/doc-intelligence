"""Structure-gated schema target planning for template fill runs."""

from typing import Any, Dict, List, Optional

from app.verticals.real_estate.template_filling.source_map import (
    SKIP_REASON_VALUES,
    STRUCTURE_HIGH_CONFIDENCE,
    STRUCTURE_LOW_CONFIDENCE,
    as_list,
)


def compute_schema_counts(schema_obj: Any) -> Dict[str, Any]:
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


def get_structure_entry(structure: Dict[str, Any], dotted_key: str) -> Optional[Dict[str, Any]]:
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


def plan_schema_targets_for_structure(
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
                (fill_when, get_structure_entry(structure, f"section_presence.{fill_when}"))
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
                entry = get_structure_entry(structure, structure_key)
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


def build_yaml_cell_status(
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
