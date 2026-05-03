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


def test_spreadsheet_chunker_splits_dense_rows_by_token_budget():
    headers = ["Unit", "Tenant", "Notes"]
    dense_note = " ".join(f"token{i}" for i in range(120))
    rows = [headers] + [[f"A{i}", f"Tenant {i}", dense_note] for i in range(20)]

    chunker = SpreadsheetChunker()
    chunker.rows_per_chunk = 200
    chunker.max_chunk_tokens = 700

    output = chunker.chunk(_parser_output(rows))
    token_counts = [count_tokens(chunk.text) for chunk in output.chunks]

    assert len(output.chunks) > 1
    assert max(token_counts) <= 700
    assert all(chunk.metadata["token_count"] == count_tokens(chunk.text) for chunk in output.chunks)
