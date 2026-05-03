"""Deterministic T-12 spreadsheet column totals.

This module does not classify arbitrary accounting labels broadly. It only
computes arithmetic from clear month-row spreadsheet tables, then reconciles
safe fields where the table columns map cleanly to current T-12 schema fields.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.utils.logging import logger


MONTH_PATTERN = re.compile(
    r"^(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|"
    r"aug|august|sep|sept|september|oct|october|nov|november|dec|december)"
    r"[\s\-']*\d{0,4}$",
    re.IGNORECASE,
)
YEAR_MONTH_PATTERN = re.compile(r"^\d{4}[-/]\d{1,2}$")
MONTH_YEAR_PATTERN = re.compile(r"^\d{1,2}[-/]\d{2,4}$")


@dataclass
class T12TableTotals:
    """Computed totals for one spreadsheet T-12 table."""

    source_token: str
    sheet_name: str
    row_start: int | None
    row_end: int | None
    monthly_row_count: int
    column_order: list[str]
    column_totals: dict[str, float]
    formula_total_row_blank: bool = False
    skipped_total_rows: int = 0

    def source_rows_label(self) -> str:
        if self.row_start is not None and self.row_end is not None:
            return f"rows {self.row_start}-{self.row_end}"
        return "visible monthly rows"


@dataclass
class T12TotalsResult:
    """All detected T-12 spreadsheet table totals for a document."""

    tables: list[T12TableTotals] = field(default_factory=list)

    @property
    def selected(self) -> T12TableTotals | None:
        """Return the only safe table for overrides, if there is exactly one."""
        return self.tables[0] if len(self.tables) == 1 else None

    @property
    def prompt_block(self) -> str:
        if not self.tables:
            return ""
        blocks = [_format_prompt_block(table) for table in self.tables]
        return "\n\n".join(blocks)

    def metadata(self) -> dict[str, Any]:
        return {
            "computed_from_spreadsheet": bool(self.tables),
            "table_count": len(self.tables),
            "selected_source_token": self.selected.source_token if self.selected else None,
            "tables": [
                {
                    "source_token": table.source_token,
                    "sheet_name": table.sheet_name,
                    "row_start": table.row_start,
                    "row_end": table.row_end,
                    "monthly_row_count": table.monthly_row_count,
                    "formula_total_row_blank": table.formula_total_row_blank,
                    "skipped_total_rows": table.skipped_total_rows,
                    "column_totals": table.column_totals,
                }
                for table in self.tables
            ],
        }


def _normalize_header(value: Any) -> str:
    text = str(value or "").strip().lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "", text)


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text or text in {"-", "—", "–"} or "%" in text:
        return None

    is_negative = text.startswith("(") and text.endswith(")")
    cleaned = text.strip("()").replace("$", "").replace(",", "").strip()
    try:
        parsed = float(cleaned)
    except ValueError:
        return None
    return -parsed if is_negative else parsed


def _is_total_row(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return not text or "total" in text or "summary" in text


def _looks_like_period_row(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or _is_total_row(text):
        return False
    return bool(
        MONTH_PATTERN.match(text)
        or YEAR_MONTH_PATTERN.match(text)
        or MONTH_YEAR_PATTERN.match(text)
    )


def _first_column(headers: list[str], rows: list[dict[str, Any]]) -> str | None:
    if headers:
        return headers[0]
    if rows:
        return next(iter(rows[0].keys()), None)
    return None


def _row_has_numeric_values(row: dict[str, Any], first_col: str | None) -> bool:
    for col, value in row.items():
        if col == first_col:
            continue
        if _parse_number(value) is not None:
            return True
    return False


def _source_token(sheet_name: str, source_index: int, row_start: int | None, row_end: int | None) -> str:
    if row_start is not None and row_end is not None:
        return f"S{source_index}:{sheet_name}!R{row_start}-R{row_end}"
    return f"S{source_index}:{sheet_name}"


def _decode_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return value


def _as_dict(value: Any) -> dict[str, Any]:
    decoded = _decode_json(value)
    return decoded if isinstance(decoded, dict) else {}


def _as_list(value: Any) -> list[Any]:
    decoded = _decode_json(value)
    if isinstance(decoded, list):
        return decoded
    if isinstance(decoded, dict):
        return [decoded]
    return []


def _table_rows_from_chunk(chunk: Any) -> list[dict[str, Any]]:
    tables = _as_list(getattr(chunk, "tables", None))
    if tables:
        table_dicts = [_as_dict(table) for table in tables]
        return [table for table in table_dicts if table.get("table_data")]

    metadata = _as_dict(getattr(chunk, "chunk_metadata", None))
    if metadata.get("table_data"):
        return [{
            "table_name": metadata.get("table_name"),
            "sheet_name": metadata.get("sheet_name"),
            "row_start": metadata.get("row_start"),
            "row_end": metadata.get("row_end"),
            "column_headers": metadata.get("column_headers"),
            "table_data": metadata.get("table_data"),
        }]
    return []


def compute_t12_table_totals(chunks: list[Any], source_index: int) -> T12TotalsResult:
    """Compute raw column totals from clear month-row spreadsheet chunks."""
    grouped: dict[str, dict[str, Any]] = {}

    for chunk in chunks:
        metadata = _as_dict(getattr(chunk, "chunk_metadata", None))
        if metadata.get("source_kind") != "spreadsheet" and not _as_list(getattr(chunk, "tables", None)):
            continue

        for table in _table_rows_from_chunk(chunk):
            rows = _as_list(table.get("table_data"))
            if not isinstance(rows, list) or not rows:
                continue

            sheet_name = str(
                table.get("sheet_name")
                or table.get("table_name")
                or metadata.get("sheet_name")
                or "Sheet"
            )
            headers = [
                str(h)
                for h in _as_list(table.get("column_headers") or metadata.get("column_headers"))
            ]
            first_col = _first_column(headers, rows)
            if not first_col:
                continue

            row_start = table.get("row_start") or metadata.get("row_start")
            try:
                row_start = int(row_start) if row_start is not None else None
            except (TypeError, ValueError):
                row_start = None

            group = grouped.setdefault(sheet_name, {
                "sheet_name": sheet_name,
                "headers": headers or list(rows[0].keys()),
                "rows": {},
                "total_rows": [],
            })

            for offset, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                row_num = (row_start + offset) if row_start is not None else offset + 1
                first_value = row.get(first_col)

                if _is_total_row(first_value):
                    group["total_rows"].append((row_num, row))
                    continue
                if not _looks_like_period_row(first_value):
                    continue
                group["rows"][(sheet_name, row_num)] = row

    analyses: list[T12TableTotals] = []
    for group in grouped.values():
        rows_by_key = group["rows"]
        if not rows_by_key:
            continue

        ordered_items = sorted(rows_by_key.items(), key=lambda item: item[0][1])
        headers = group["headers"]
        first_col = _first_column(headers, [row for _, row in ordered_items])
        if not first_col:
            continue

        totals: dict[str, float] = {}
        for _, row in ordered_items:
            for col, value in row.items():
                if col == first_col:
                    continue
                parsed = _parse_number(value)
                if parsed is None:
                    continue
                totals[col] = totals.get(col, 0.0) + parsed

        if not totals:
            continue

        row_numbers = [row_num for (_, row_num), _ in ordered_items]
        total_rows = group["total_rows"]
        formula_total_row_blank = any(
            not _row_has_numeric_values(row, first_col)
            for _, row in total_rows
        )
        sheet_name = group["sheet_name"]
        row_start = min(row_numbers)
        total_row_numbers = [row_num for row_num, _ in total_rows]
        row_end = max(row_numbers + total_row_numbers)

        analyses.append(T12TableTotals(
            source_token=_source_token(sheet_name, source_index, row_start, row_end),
            sheet_name=sheet_name,
            row_start=row_start,
            row_end=row_end,
            monthly_row_count=len(ordered_items),
            column_order=[col for col in headers if col != first_col and col in totals],
            column_totals=totals,
            formula_total_row_blank=formula_total_row_blank,
            skipped_total_rows=len(total_rows),
        ))

    return T12TotalsResult(tables=analyses)


def _format_money(value: float) -> str:
    return f"{value:,.0f}"


def _format_prompt_block(table: T12TableTotals) -> str:
    lines = [
        f"[{table.source_token}] (Verified Spreadsheet Totals)",
        "Verified Spreadsheet Totals - computed from visible monthly rows; formula total rows were blank or ignored.",
        f"Sheet: {table.sheet_name}",
        f"Rows used: {table.source_rows_label()}",
        f"Monthly rows summed: {table.monthly_row_count}",
        "Column totals:",
    ]
    ordered = table.column_order or list(table.column_totals.keys())
    for col in ordered:
        if col in table.column_totals:
            lines.append(f"- {col}: {_format_money(table.column_totals[col])}")
    return "\n".join(lines)


def _find_total(table: T12TableTotals, labels: set[str]) -> tuple[str, float] | None:
    normalized_labels = {_normalize_header(label) for label in labels}
    for header, value in table.column_totals.items():
        if _normalize_header(header) in normalized_labels:
            return header, value
    return None


FIELD_COLUMN_LABELS: dict[str, set[str]] = {
    "gpr_annual_actual": {"Rental Income", "Gross Rental Income", "Gross Potential Rent", "Scheduled Rent"},
    "noi_actual": {"NOI", "Net Operating Income", "Net Income from Operations"},
    "property_tax_annual": {"Property Taxes", "Property Tax", "Real Estate Taxes", "Tax Expense"},
    "insurance_annual": {"Property Insurance", "Insurance", "Casualty Insurance", "Hazard Insurance"},
    "payroll_annual": {"Payroll & Benefits", "Payroll and Benefits", "Payroll", "Salaries & Wages", "Labor"},
    "repairs_maintenance_annual": {"Repairs & Maintenance", "Repairs and Maintenance", "R&M", "Maintenance"},
    "utilities_annual": {"Utilities", "Utility Expense", "Electric", "Water Sewer Trash"},
    "marketing_annual": {"Marketing & Web Leads", "Marketing and Web Leads", "Marketing", "Advertising"},
}


def _field_source_text(table: T12TableTotals, detail: str) -> str:
    return f"{detail}. Computed from spreadsheet {table.source_rows_label()}."


def _nearly_equal(a: float | None, b: float, tolerance: float = 1.0) -> bool:
    if a is None:
        return False
    return abs(float(a) - b) <= tolerance


def reconcile_t12_with_computed_totals(
    *,
    t12: Any,
    field_citations: dict,
    totals_result: T12TotalsResult,
    run_id: str,
) -> dict[str, Any]:
    """Apply safe computed totals to a parsed T12Extraction model."""
    table = totals_result.selected
    metadata = totals_result.metadata()
    overrides: list[dict[str, Any]] = []

    if t12 is None or table is None:
        metadata["overrides"] = overrides
        return metadata

    def apply(field: str, value: float | int | None, detail: str) -> None:
        if value is None:
            return
        old_value = getattr(t12, field, None)
        if old_value is not None and _nearly_equal(float(old_value), float(value)):
            setattr(t12, field, value)
        else:
            logger.info(
                "T12 reconcile: overriding %s LLM=%s -> computed=%s from %s",
                field,
                old_value,
                value,
                table.source_token,
                extra={"run_id": run_id, "field": field, "source_token": table.source_token},
            )
            setattr(t12, field, value)
            overrides.append({"field": field, "llm_value": old_value, "computed_value": value})

        field_citations[field] = {
            "doc_type": "t12",
            "confidence": 1.0,
            "citations": [table.source_token],
            "source_text": _field_source_text(table, detail),
            "is_computed": True,
        }

    _MULTI_COLUMN_FIELDS: set[str] = {"utilities_annual", "repairs_maintenance_annual"}

    for field_name, labels in FIELD_COLUMN_LABELS.items():
        matched = _find_total(table, labels)
        if matched:
            header, value = matched
            apply(field_name, value, f"{header}: {_format_money(value)}")
            if field_name in _MULTI_COLUMN_FIELDS:
                logger.warning(
                    "T12 reconcile: %s matched single column '%s' (%s) — "
                    "verify this column covers the full expense category",
                    field_name,
                    header,
                    _format_money(value),
                    extra={"run_id": run_id, "field": field_name, "matched_column": header},
                )

    rental = _find_total(table, FIELD_COLUMN_LABELS["gpr_annual_actual"])
    total_income = _find_total(table, {"Total Income", "Effective Gross Income", "EGI"})
    if rental and total_income:
        other_income = total_income[1] - rental[1]
        if other_income >= 0:
            apply(
                "other_income_annual",
                other_income,
                f"{total_income[0]} {_format_money(total_income[1])} - {rental[0]} {_format_money(rental[1])}",
            )

    total_expenses = _find_total(table, {"Total Expenses", "Total Operating Expenses", "Operating Expenses"})
    if total_expenses and total_income and total_income[1] > 0:
        ratio = total_expenses[1] / total_income[1]
        apply(
            "expense_ratio_actual",
            ratio,
            f"{total_expenses[0]} {_format_money(total_expenses[1])} / {total_income[0]} {_format_money(total_income[1])}",
        )

    if 1 <= table.monthly_row_count <= 12:
        old_period = getattr(t12, "period_months", None)
        if old_period is None or int(old_period) != table.monthly_row_count:
            apply("period_months", table.monthly_row_count, f"{table.monthly_row_count} visible monthly rows")

    metadata["overrides"] = overrides
    return metadata
