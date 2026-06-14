from app.core.parsers.spreadsheet_parser import _normalize_sheet_rows


def test_normalize_sheet_rows_skips_title_rows_before_monthly_header():
    rows = [
        ["Palm Vista Apartments"],
        ["Tampa, Florida"],
        ["318 Units"],
        ["Trailing 12-Month Operating Statement"],
        ["Account", "Jan-25", "Feb-25", "Mar-25", "Nov-25", "T12"],
        ["Gross Potential Rent", "100", "110", "120", "130", "1460"],
        ["Net Operating Income", "80", "90", "100", "441197", "1200"],
    ]
    original_row_numbers = [1, 2, 3, 4, 5, 6, 7]

    normalized_rows, normalized_row_numbers, headers, context_rows, context_row_numbers, context_text = _normalize_sheet_rows(rows, original_row_numbers)

    assert headers == ["Account", "Jan-25", "Feb-25", "Mar-25", "Nov-25", "T12"]
    assert normalized_row_numbers == [5, 6, 7]
    assert normalized_rows[0] == headers
    assert normalized_rows[1][0] == "Gross Potential Rent"
    assert context_rows == rows[:4]
    assert context_row_numbers == [1, 2, 3, 4]
    assert "Palm Vista Apartments" in context_text


def test_normalize_sheet_rows_keeps_simple_header_first():
    rows = [
        ["Unit", "Tenant", "Rent"],
        ["A1", "Tenant 1", "1000"],
        ["A2", "Tenant 2", "1100"],
    ]
    original_row_numbers = [1, 2, 3]

    normalized_rows, normalized_row_numbers, headers, context_rows, context_row_numbers, context_text = _normalize_sheet_rows(rows, original_row_numbers)

    assert headers == ["Unit", "Tenant", "Rent"]
    assert normalized_row_numbers == [1, 2, 3]
    assert normalized_rows == rows
    assert context_rows == []
    assert context_row_numbers == []
    assert context_text == ""