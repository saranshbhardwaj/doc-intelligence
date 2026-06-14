from app.core.chunkers.spreadsheet_chunker import SpreadsheetChunker
from app.core.parsers.base import ParserOutput
from app.utils.token_utils import count_tokens


def _parser_output(rows: list[list[str]]) -> ParserOutput:
    return ParserOutput(
        text="spreadsheet summary",
        page_count=1,
        parser_name="spreadsheet",
        parser_version="1.0.0",
        processing_time_ms=0,
        cost_usd=0.0,
        pdf_type="spreadsheet",
        metadata={
            "source_kind": "spreadsheet",
            "sheets": [{
                "name": "CSV",
                "headers": rows[0],
                "rows": rows,
                "original_row_numbers": list(range(1, len(rows) + 1)),
                "row_count": len(rows),
                "column_count": len(rows[0]),
            }],
        },
    )


def test_spreadsheet_chunker_caps_dense_rows_to_token_budget():
    headers = ["Unit", "Tenant", "Notes"]
    dense_note = " ".join(f"token{i}" for i in range(600))
    rows = [headers] + [[f"A{i}", f"Tenant {i}", dense_note] for i in range(20)]

    chunker = SpreadsheetChunker()
    chunker.rows_per_chunk = 200
    chunker.max_chunk_tokens = 150

    output = chunker.chunk(_parser_output(rows))
    token_counts = [count_tokens(chunk.text) for chunk in output.chunks]

    assert len(output.chunks) >= 1
    assert max(token_counts) <= 150
    assert all(chunk.metadata["token_count"] == count_tokens(chunk.text) for chunk in output.chunks)


def test_spreadsheet_chunker_preserves_sheet_context_in_chunk_text():
    parser_output = ParserOutput(
        text="spreadsheet summary",
        page_count=1,
        parser_name="spreadsheet",
        parser_version="1.0.0",
        processing_time_ms=0,
        cost_usd=0.0,
        pdf_type="spreadsheet",
        metadata={
            "source_kind": "spreadsheet",
            "sheets": [{
                "name": "T12 Operating Statement",
                "headers": ["Account", "Oct-25", "Nov-25"],
                "rows": [
                    ["Account", "Oct-25", "Nov-25"],
                    ["Net Operating Income", "435100", "441197"],
                ],
                "original_row_numbers": [7, 8],
                "context_rows": [
                    ["Palm Vista Apartments"],
                    ["Tampa, Florida"],
                ],
                "context_row_numbers": [1, 2],
                "context_text": "Palm Vista Apartments\nTampa, Florida",
                "row_count": 2,
                "column_count": 3,
            }],
        },
    )

    output = SpreadsheetChunker().chunk(parser_output)

    assert len(output.chunks) == 1
    assert "Palm Vista Apartments" in output.chunks[0].text
    assert output.chunks[0].metadata["context_text"] == "Palm Vista Apartments\nTampa, Florida"


def test_spreadsheet_chunker_adds_overlap_and_neighbor_metadata():
    rows = [
        ["Unit", "Rent"],
        ["A1", "1000"],
        ["A2", "1100"],
        ["A3", "1200"],
        ["A4", "1300"],
    ]

    chunker = SpreadsheetChunker()
    chunker.rows_per_chunk = 2
    chunker.rows_overlap = 1
    chunker.max_chunk_tokens = 1000

    output = chunker.chunk(_parser_output(rows))

    assert [chunk.chunk_id for chunk in output.chunks] == [
        "spreadsheet_1_1",
        "spreadsheet_1_2",
        "spreadsheet_1_3",
    ]
    assert output.metadata["rows_overlap"] == 1

    first, second, third = output.chunks
    assert first.metadata["spreadsheet_prev_chunk_id"] is None
    assert first.metadata["spreadsheet_next_chunk_id"] == "spreadsheet_1_2"
    assert second.metadata["spreadsheet_prev_chunk_id"] == "spreadsheet_1_1"
    assert second.metadata["spreadsheet_next_chunk_id"] == "spreadsheet_1_3"
    assert third.metadata["spreadsheet_prev_chunk_id"] == "spreadsheet_1_2"
    assert third.metadata["spreadsheet_next_chunk_id"] is None

    assert first.metadata["row_start"] == 2
    assert second.metadata["row_start"] == 3
    assert third.metadata["row_start"] == 4
