"""Tests for deterministic T-12 spreadsheet totals."""

import json
from types import SimpleNamespace

from app.verticals.real_estate.underwriting.extraction.schemas import T12Extraction
from app.verticals.real_estate.underwriting.extraction.t12_table_totals import (
    compute_t12_table_totals,
    reconcile_t12_with_computed_totals,
)


HEADERS = [
    "Month",
    "Rental Income",
    "Tenant Insurance Income",
    "Late Fees",
    "Total Income",
    "Payroll & Benefits",
    "Property Taxes",
    "Total Expenses",
    "NOI",
]


def _chunk(
    rows,
    *,
    row_start=2,
    sheet_name="Seller T12 Export",
    metadata_rows=None,
):
    return SimpleNamespace(
        text="spreadsheet chunk",
        tables=[{
            "sheet_name": sheet_name,
            "table_name": sheet_name,
            "row_start": row_start,
            "row_end": row_start + len(rows) - 1,
            "column_headers": HEADERS,
            "table_data": rows,
        }],
        chunk_metadata={
            "source_kind": "spreadsheet",
            "sheet_name": sheet_name,
            "row_start": row_start,
            "row_end": row_start + len(rows) - 1,
            "column_headers": HEADERS,
            "table_data": metadata_rows or rows[:1],
        },
    )


def test_t12_totals_use_full_tables_before_preview_metadata():
    rows = [
        {
            "Month": "Apr-25",
            "Rental Income": "$1,000",
            "Tenant Insurance Income": "20",
            "Late Fees": "10",
            "Total Income": "$1,030",
            "Payroll & Benefits": "100",
            "Property Taxes": "50",
            "Total Expenses": "200",
            "NOI": "830",
        },
        {
            "Month": "May-25",
            "Rental Income": "2,000",
            "Tenant Insurance Income": "40",
            "Late Fees": "20",
            "Total Income": "2060",
            "Payroll & Benefits": "200",
            "Property Taxes": "100",
            "Total Expenses": "400",
            "NOI": "1660",
        },
        {
            "Month": "T12 Total",
            "Rental Income": "",
            "Tenant Insurance Income": "",
            "Late Fees": "",
            "Total Income": "",
            "Payroll & Benefits": "",
            "Property Taxes": "",
            "Total Expenses": "",
            "NOI": "",
        },
    ]

    result = compute_t12_table_totals([_chunk(rows, metadata_rows=rows[:1])], source_index=2)

    table = result.selected
    assert table is not None
    assert table.source_token == "S2:Seller T12 Export!R2-R4"
    assert table.monthly_row_count == 2
    assert table.formula_total_row_blank is True
    assert table.column_totals["Rental Income"] == 3000
    assert table.column_totals["Tenant Insurance Income"] == 60
    assert table.column_totals["Total Income"] == 3090
    assert "Verified Spreadsheet Totals" in result.prompt_block
    assert "[S2:Seller T12 Export!R2-R4]" in result.prompt_block


def test_t12_totals_falls_back_to_metadata_table_data():
    chunk = _chunk([])
    chunk.tables = []
    chunk.chunk_metadata["table_data"] = [
        {"Month": "Apr-25", "Rental Income": "(1,000)", "Total Income": "$1,200"},
        {"Month": "T12 Total", "Rental Income": "", "Total Income": ""},
    ]
    chunk.chunk_metadata["row_end"] = 3

    result = compute_t12_table_totals([chunk], source_index=1)

    assert result.selected is not None
    assert result.selected.column_totals["Rental Income"] == -1000
    assert result.selected.column_totals["Total Income"] == 1200


def test_t12_totals_handles_tables_stored_as_json_string():
    rows = [
        {"Month": "Apr-25", "Rental Income": "1000", "Total Income": "1100"},
        {"Month": "May-25", "Rental Income": "2000", "Total Income": "2200"},
        {"Month": "T12 Total", "Rental Income": "", "Total Income": ""},
    ]
    chunk = SimpleNamespace(
        text="spreadsheet chunk",
        tables=json.dumps([{
            "sheet_name": "Seller T12 Export",
            "row_start": 2,
            "row_end": 4,
            "column_headers": ["Month", "Rental Income", "Total Income"],
            "table_data": rows,
        }]),
        chunk_metadata={
            "source_kind": "spreadsheet",
            "sheet_name": "Seller T12 Export",
            "row_start": 2,
            "row_end": 4,
        },
    )

    result = compute_t12_table_totals([chunk], source_index=2)

    assert result.selected is not None
    assert result.selected.source_token == "S2:Seller T12 Export!R2-R4"
    assert result.selected.column_totals["Rental Income"] == 3000
    assert result.selected.column_totals["Total Income"] == 3300


def test_t12_totals_reassembles_split_sheet_windows():
    first = _chunk([
        {"Month": "Apr-25", "Rental Income": "1000", "Total Income": "1100"},
        {"Month": "May-25", "Rental Income": "2000", "Total Income": "2200"},
    ], row_start=2)
    second = _chunk([
        {"Month": "Jun-25", "Rental Income": "3000", "Total Income": "3300"},
        {"Month": "T12 Total", "Rental Income": "", "Total Income": ""},
    ], row_start=4)

    result = compute_t12_table_totals([second, first], source_index=3)

    assert result.selected is not None
    assert result.selected.source_token == "S3:Seller T12 Export!R2-R5"
    assert result.selected.monthly_row_count == 3
    assert result.selected.column_totals["Rental Income"] == 6000
    assert result.selected.column_totals["Total Income"] == 6600


def test_reconcile_overrides_safe_t12_fields_and_citations():
    rows = [
        {
            "Month": "Apr-25",
            "Rental Income": "1000",
            "Tenant Insurance Income": "20",
            "Late Fees": "10",
            "Total Income": "1030",
            "Payroll & Benefits": "100",
            "Property Taxes": "50",
            "Total Expenses": "200",
            "NOI": "830",
        },
        {
            "Month": "May-25",
            "Rental Income": "2000",
            "Tenant Insurance Income": "40",
            "Late Fees": "20",
            "Total Income": "2060",
            "Payroll & Benefits": "200",
            "Property Taxes": "100",
            "Total Expenses": "400",
            "NOI": "1660",
        },
        {"Month": "T12 Total"},
    ]
    totals = compute_t12_table_totals([_chunk(rows)], source_index=2)
    t12 = T12Extraction(
        gpr_annual_actual=2900,
        other_income_annual=30,
        expense_ratio_actual=0.1,
        noi_actual=100,
        period_months=None,
    )
    field_citations = {}

    metadata = reconcile_t12_with_computed_totals(
        t12=t12,
        field_citations=field_citations,
        totals_result=totals,
        run_id="run-1",
    )

    assert t12.gpr_annual_actual == 3000
    assert t12.other_income_annual == 90
    assert t12.expense_ratio_actual == 600 / 3090
    assert t12.noi_actual == 2490
    assert t12.property_tax_annual == 150
    assert t12.payroll_annual == 300
    assert t12.period_months == 2
    assert field_citations["other_income_annual"]["citations"] == ["S2:Seller T12 Export!R2-R4"]
    assert field_citations["other_income_annual"]["is_computed"] is True
    assert metadata["overrides"]


def test_reconcile_returns_safely_when_t12_is_none():
    rows = [{"Month": "Apr-25", "Rental Income": "1000", "Total Income": "1100"}]
    totals = compute_t12_table_totals([_chunk(rows)], source_index=1)
    metadata = reconcile_t12_with_computed_totals(
        t12=None,
        field_citations={},
        totals_result=totals,
        run_id="run-1",
    )
    assert metadata["overrides"] == []


def test_reconcile_skips_overrides_when_multiple_tables_are_detected():
    first = _chunk([{"Month": "Apr-25", "Rental Income": "1000"}], sheet_name="T12 A")
    second = _chunk([{"Month": "Apr-25", "Rental Income": "2000"}], sheet_name="T12 B")
    totals = compute_t12_table_totals([first, second], source_index=1)
    t12 = T12Extraction(gpr_annual_actual=123)

    metadata = reconcile_t12_with_computed_totals(
        t12=t12,
        field_citations={},
        totals_result=totals,
        run_id="run-1",
    )

    assert len(totals.tables) == 2
    assert t12.gpr_annual_actual == 123
    assert metadata["overrides"] == []
