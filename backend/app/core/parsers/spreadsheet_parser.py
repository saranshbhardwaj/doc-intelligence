"""Spreadsheet parser for Library indexing.

Extracts workbook/CSV rows into a structured shape that a spreadsheet-aware
chunker can preserve as sheet and row-window context for RAG and underwriting.
"""
from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any

import openpyxl

from app.config import settings
from app.core.parsers.base import DocumentParser, ParserOutput


SPREADSHEET_TOO_LARGE_MESSAGE = (
    "This spreadsheet is too large to index reliably. "
    "Split it into focused files or remove unused sheets and try again."
)


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _is_non_empty_row(row: list[str]) -> bool:
    return any(cell.strip() for cell in row)


def _trim_trailing_empty_cells(row: list[str]) -> list[str]:
    trimmed = list(row)
    while trimmed and not trimmed[-1].strip():
        trimmed.pop()
    return trimmed


def _headers_for_rows(rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    first = rows[0]
    headers = []
    for idx, value in enumerate(first, start=1):
        headers.append(value if value else f"Column {idx}")
    return headers


def _rows_to_context_text(rows: list[list[str]], limit: int = 6) -> str:
    context_lines = []
    for row in rows[:limit]:
        non_empty = [cell for cell in row if str(cell).strip()]
        if non_empty:
            context_lines.append(" | ".join(non_empty))
    return "\n".join(context_lines)


def _count_non_empty_cells(row: list[str]) -> int:
    return sum(1 for cell in row if str(cell).strip())


def _select_header_row_index(rows: list[list[str]]) -> int:
    """Pick the most likely header row, skipping title/meta rows above the table."""
    if not rows:
        return 0

    header_cues = {
        "account", "description", "date", "current", "year", "pro forma", "total",
        "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    }

    best_index = 0
    best_score = -1
    for idx, row in enumerate(rows[:25]):
        non_empty = _count_non_empty_cells(row)
        if non_empty == 0:
            continue

        normalized_cells = [str(cell).strip().lower() for cell in row if str(cell).strip()]
        cue_score = sum(1 for cell in normalized_cells if any(cue in cell for cue in header_cues))
        multi_col_bonus = min(non_empty, 8)
        early_row_bonus = max(0, 5 - idx)
        score = (cue_score * 10) + (multi_col_bonus * 2) + early_row_bonus

        if score > best_score:
            best_score = score
            best_index = idx

    return best_index


def _normalize_sheet_rows(
    rows: list[list[str]],
    original_row_numbers: list[int],
) -> tuple[list[list[str]], list[int], list[str], list[list[str]], list[int], str]:
    """Rebase rows so the detected table header becomes row 0 for chunking."""
    if not rows:
        return rows, original_row_numbers, [], [], [], ""

    header_idx = _select_header_row_index(rows)
    leading_rows = rows[:header_idx]
    leading_row_numbers = original_row_numbers[:header_idx] if original_row_numbers else []
    normalized_rows = rows[header_idx:]
    normalized_row_numbers = original_row_numbers[header_idx:] if original_row_numbers else original_row_numbers

    if not normalized_rows:
        normalized_rows = rows
        normalized_row_numbers = original_row_numbers
        leading_rows = []
        leading_row_numbers = []

    headers = _headers_for_rows(normalized_rows)
    context_text = _rows_to_context_text(leading_rows)
    return normalized_rows, normalized_row_numbers, headers, leading_rows, leading_row_numbers, context_text


def _rows_to_preview(headers: list[str], rows: list[list[str]], limit: int = 5) -> str:
    preview_rows = rows[:limit]
    if not preview_rows:
        return ""
    lines = [" | ".join(headers)]
    lines.extend(" | ".join(row[: len(headers)]) for row in preview_rows)
    return "\n".join(lines)


class SpreadsheetParser(DocumentParser):
    """Parse XLSX/XLSM/CSV files into sheet-level structured metadata."""

    @property
    def name(self) -> str:
        return "spreadsheet"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def cost_per_page(self) -> float:
        return 0.0

    def supports_pdf_type(self, pdf_type: str) -> bool:
        return pdf_type == "spreadsheet"

    async def parse(self, file_path: str, pdf_type: str) -> ParserOutput:
        start = time.time()
        ext = Path(file_path).suffix.lower()

        if ext == ".csv":
            sheets = self._parse_csv(file_path)
        elif ext in {".xlsx", ".xlsm"}:
            sheets = self._parse_workbook(file_path)
        else:
            raise ValueError("Unsupported spreadsheet format. Upload XLSX, XLSM, or CSV.")

        text = self._build_summary_text(sheets)
        elapsed_ms = int((time.time() - start) * 1000)

        return ParserOutput(
            text=text,
            page_count=max(len(sheets), 1),
            parser_name=self.name,
            parser_version=self.version,
            processing_time_ms=elapsed_ms,
            cost_usd=0.0,
            pdf_type="spreadsheet",
            metadata={
                "source_kind": "spreadsheet",
                "file_extension": ext,
                "sheets": sheets,
                "sheet_count": len(sheets),
            },
        )

    def _parse_workbook(self, file_path: str) -> list[dict[str, Any]]:
        workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        try:
            if len(workbook.worksheets) > settings.spreadsheet_max_sheets:
                raise ValueError(SPREADSHEET_TOO_LARGE_MESSAGE)

            sheets: list[dict[str, Any]] = []
            total_cells = 0

            for worksheet in workbook.worksheets:
                rows: list[list[str]] = []
                original_row_numbers: list[int] = []

                for row_index, values in enumerate(worksheet.iter_rows(values_only=True), start=1):
                    cleaned = _trim_trailing_empty_cells([_clean_cell(value) for value in values])
                    if not _is_non_empty_row(cleaned):
                        continue

                    rows.append(cleaned)
                    original_row_numbers.append(row_index)
                    total_cells += len(cleaned)

                    if len(rows) > settings.spreadsheet_max_rows_per_sheet:
                        raise ValueError(SPREADSHEET_TOO_LARGE_MESSAGE)
                    if total_cells > settings.spreadsheet_max_total_cells:
                        raise ValueError(SPREADSHEET_TOO_LARGE_MESSAGE)

                if rows:
                    rows, original_row_numbers, headers, context_rows, context_row_numbers, context_text = _normalize_sheet_rows(rows, original_row_numbers)
                    sheets.append({
                        "name": worksheet.title,
                        "headers": headers,
                        "rows": rows,
                        "original_row_numbers": original_row_numbers,
                        "context_rows": context_rows,
                        "context_row_numbers": context_row_numbers,
                        "context_text": context_text,
                        "row_count": len(rows),
                        "column_count": max((len(row) for row in rows), default=0),
                    })

            return sheets
        finally:
            workbook.close()

    def _parse_csv(self, file_path: str) -> list[dict[str, Any]]:
        try:
            rows, original_row_numbers, _total_cells = self._read_csv_rows(file_path, "utf-8-sig")
        except UnicodeDecodeError:
            rows, original_row_numbers, _total_cells = self._read_csv_rows(file_path, "latin-1")

        if not rows:
            return []

        rows, original_row_numbers, headers, context_rows, context_row_numbers, context_text = _normalize_sheet_rows(rows, original_row_numbers)

        return [{
            "name": "CSV",
            "headers": headers,
            "rows": rows,
            "original_row_numbers": original_row_numbers,
            "context_rows": context_rows,
            "context_row_numbers": context_row_numbers,
            "context_text": context_text,
            "row_count": len(rows),
            "column_count": max((len(row) for row in rows), default=0),
        }]

    def _read_csv_rows(self, file_path: str, encoding: str) -> tuple[list[list[str]], list[int], int]:
        rows: list[list[str]] = []
        original_row_numbers: list[int] = []
        total_cells = 0

        with open(file_path, "r", encoding=encoding, newline="") as handle:
            reader = csv.reader(handle)
            for row_index, values in enumerate(reader, start=1):
                cleaned = _trim_trailing_empty_cells([_clean_cell(value) for value in values])
                if not _is_non_empty_row(cleaned):
                    continue

                rows.append(cleaned)
                original_row_numbers.append(row_index)
                total_cells += len(cleaned)

                if len(rows) > settings.spreadsheet_max_rows_per_sheet:
                    raise ValueError(SPREADSHEET_TOO_LARGE_MESSAGE)
                if total_cells > settings.spreadsheet_max_total_cells:
                    raise ValueError(SPREADSHEET_TOO_LARGE_MESSAGE)

        return rows, original_row_numbers, total_cells

    def _build_summary_text(self, sheets: list[dict[str, Any]]) -> str:
        if not sheets:
            return "Spreadsheet contains no readable rows."

        parts = []
        for sheet in sheets:
            headers = sheet.get("headers", [])
            rows = sheet.get("rows", [])
            preview = _rows_to_preview(headers, rows[1:] if len(rows) > 1 else rows)
            parts.append(
                "\n".join([
                    f"Sheet: {sheet.get('name')}",
                    f"Rows: {sheet.get('row_count', 0)}",
                    f"Columns: {sheet.get('column_count', 0)}",
                    f"Headers: {', '.join(headers)}",
                    "Preview:",
                    preview,
                ]).strip()
            )
        return "\n\n".join(parts)
