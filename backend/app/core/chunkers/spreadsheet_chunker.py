"""Spreadsheet-aware chunker for Library indexing."""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.core.chunkers.base import Chunk, ChunkingOutput, ChunkStrategy, DocumentChunker
from app.core.parsers.base import ParserOutput
from app.utils.token_utils import count_tokens, truncate_to_token_limit


def _row_to_record(headers: list[str], row: list[str]) -> dict[str, str]:
    record: dict[str, str] = {}
    for idx, header in enumerate(headers):
        value = row[idx] if idx < len(row) else ""
        record[header or f"Column {idx + 1}"] = value
    return record


def _format_table_text(
    sheet_name: str,
    headers: list[str],
    rows: list[list[str]],
    row_start: int,
    row_end: int,
    context_text: str = "",
) -> str:
    lines = [
        f"Sheet: {sheet_name}",
        f"Rows: {row_start}-{row_end}",
    ]
    if context_text:
        lines.extend([
            "Context:",
            context_text,
        ])
    lines.extend([
        f"Headers: {', '.join(headers)}",
        "",
        " | ".join(headers),
    ])
    lines.extend(" | ".join((row + [""] * len(headers))[: len(headers)]) for row in rows)
    return "\n".join(lines).strip()


class SpreadsheetChunker(DocumentChunker):
    """Split spreadsheet rows into table chunks while preserving sheet/row anchors."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.rows_per_chunk = max(int(settings.spreadsheet_rows_per_chunk or 200), 1)
        self.rows_overlap = max(int(getattr(settings, "spreadsheet_rows_overlap", 0) or 0), 0)
        if self.rows_overlap >= self.rows_per_chunk:
            self.rows_overlap = max(self.rows_per_chunk - 1, 0)
        # OpenAI embedding models cap each input at 8192 tokens. Keep a buffer for
        # tokenizer differences and future metadata additions.
        self.max_chunk_tokens = max(int(settings.spreadsheet_max_chunk_tokens or 7000), 500)

    @property
    def name(self) -> str:
        return "spreadsheet_row_window"

    @property
    def strategy(self) -> ChunkStrategy:
        return ChunkStrategy.HYBRID

    def supports_parser(self, parser_name: str) -> bool:
        return parser_name == "spreadsheet"

    def _build_chunk(
        self,
        *,
        sheet_index: int,
        window_index: int,
        sheet_name: str,
        headers: list[str],
        window_rows: list[list[str]],
        window_original_rows: list[int],
        fallback_row_start: int,
        context_text: str,
        prev_chunk_id: str | None = None,
        next_chunk_id: str | None = None,
    ) -> Chunk:
        row_start = int(window_original_rows[0]) if window_original_rows else fallback_row_start
        row_end = int(window_original_rows[-1]) if window_original_rows else fallback_row_start + len(window_rows) - 1
        chunk_id = f"spreadsheet_{sheet_index}_{window_index}"
        text = _format_table_text(sheet_name, headers, window_rows, row_start, row_end, context_text)
        token_count = count_tokens(text)
        was_truncated = False

        if token_count > self.max_chunk_tokens:
            text = truncate_to_token_limit(text, self.max_chunk_tokens)
            token_count = count_tokens(text)
            was_truncated = True

        records = [_row_to_record(headers, row) for row in window_rows]
        table = {
            "table_id": chunk_id,
            "table_name": sheet_name,
            "sheet_name": sheet_name,
            "spreadsheet_window_index": window_index,
            "spreadsheet_prev_chunk_id": prev_chunk_id,
            "spreadsheet_next_chunk_id": next_chunk_id,
            "spreadsheet_neighbor_chunk_ids": [
                chunk_ref for chunk_ref in (prev_chunk_id, next_chunk_id) if chunk_ref
            ],
            "spreadsheet_rows_overlap": self.rows_overlap,
            "row_start": row_start,
            "row_end": row_end,
            "row_count": len(window_rows),
            "column_count": len(headers),
            "column_headers": headers,
            "table_data": records,
            "text": text,
        }

        chunk_metadata = {
            "chunk_id": chunk_id,
            "source_kind": "spreadsheet",
            "source_parser": "spreadsheet",
            "page_number": None,
            "section_type": "table",
            "section_heading": sheet_name,
            "is_tabular": True,
            "has_tables": True,
            "table_count": 1,
            "chunk_type": "table",
            "table_name": sheet_name,
            "sheet_name": sheet_name,
            "spreadsheet_window_index": window_index,
            "spreadsheet_prev_chunk_id": prev_chunk_id,
            "spreadsheet_next_chunk_id": next_chunk_id,
            "spreadsheet_neighbor_chunk_ids": [
                chunk_ref for chunk_ref in (prev_chunk_id, next_chunk_id) if chunk_ref
            ],
            "spreadsheet_rows_overlap": self.rows_overlap,
            "row_start": row_start,
            "row_end": row_end,
            "row_count": len(window_rows),
            "column_count": len(headers),
            "column_headers": headers,
            "table_data": records[:2],
            "context_text": context_text,
            "char_count": len(text),
            "token_count": token_count,
            "max_chunk_tokens": self.max_chunk_tokens,
            "was_truncated": was_truncated,
        }

        return Chunk(
            chunk_id=chunk_id,
            text=text,
            narrative_text="",
            tables=[table],
            metadata=chunk_metadata,
        )

    def _trim_overlap_to_budget(
        self,
        *,
        sheet_name: str,
        headers: list[str],
        candidate_rows: list[list[str]],
        candidate_original_rows: list[int],
        context_text: str,
    ) -> tuple[list[list[str]], list[int]]:
        trimmed_rows = list(candidate_rows)
        trimmed_original_rows = list(candidate_original_rows)

        while len(trimmed_rows) > 1:
            candidate_text = _format_table_text(
                sheet_name,
                headers,
                trimmed_rows,
                int(trimmed_original_rows[0]),
                int(trimmed_original_rows[-1]),
                context_text,
            )
            if count_tokens(candidate_text) <= self.max_chunk_tokens:
                break
            trimmed_rows = trimmed_rows[1:]
            trimmed_original_rows = trimmed_original_rows[1:]

        return trimmed_rows, trimmed_original_rows

    def chunk(self, parser_output: ParserOutput) -> ChunkingOutput:
        metadata = parser_output.metadata or {}
        sheets = metadata.get("sheets") or []
        chunks: list[Chunk] = []

        for sheet_index, sheet in enumerate(sheets, start=1):
            sheet_name = str(sheet.get("name") or f"Sheet {sheet_index}")
            headers = [str(h) for h in (sheet.get("headers") or [])]
            rows = sheet.get("rows") or []
            original_row_numbers = sheet.get("original_row_numbers") or []
            context_text = str(sheet.get("context_text") or "").strip()
            window_specs: list[dict[str, Any]] = []

            if not rows:
                continue

            data_rows = rows[1:] if len(rows) > 1 else rows
            data_original_rows = original_row_numbers[1:] if len(original_row_numbers) > 1 else original_row_numbers
            if not data_rows:
                data_rows = rows
                data_original_rows = original_row_numbers or [1]

            window_rows: list[list[str]] = []
            window_original_rows: list[int] = []
            window_index = 1

            for row_index, row in enumerate(data_rows):
                original_row = (
                    int(data_original_rows[row_index])
                    if row_index < len(data_original_rows)
                    else row_index + 1
                )
                candidate_rows = [*window_rows, row]
                candidate_original_rows = [*window_original_rows, original_row]
                candidate_text = _format_table_text(
                    sheet_name,
                    headers,
                    candidate_rows,
                    int(candidate_original_rows[0]),
                    int(candidate_original_rows[-1]),
                    context_text,
                )
                exceeds_row_limit = len(candidate_rows) > self.rows_per_chunk
                exceeds_token_limit = count_tokens(candidate_text) > self.max_chunk_tokens

                if window_rows and (exceeds_row_limit or exceeds_token_limit):
                    window_specs.append(
                        {
                            "window_index": window_index,
                            "window_rows": list(window_rows),
                            "window_original_rows": list(window_original_rows),
                            "fallback_row_start": row_index + 1,
                        }
                    )
                    window_index += 1
                    overlap_count = min(self.rows_overlap, len(window_rows))
                    overlap_rows = window_rows[-overlap_count:] if overlap_count else []
                    overlap_original_rows = window_original_rows[-overlap_count:] if overlap_count else []
                    next_rows = [*overlap_rows, row]
                    next_original_rows = [*overlap_original_rows, original_row]
                    window_rows, window_original_rows = self._trim_overlap_to_budget(
                        sheet_name=sheet_name,
                        headers=headers,
                        candidate_rows=next_rows,
                        candidate_original_rows=next_original_rows,
                        context_text=context_text,
                    )
                    continue

                window_rows = candidate_rows
                window_original_rows = candidate_original_rows

            if window_rows:
                window_specs.append(
                    {
                        "window_index": window_index,
                        "window_rows": list(window_rows),
                        "window_original_rows": list(window_original_rows),
                        "fallback_row_start": 1,
                    }
                )

            for spec_index, spec in enumerate(window_specs):
                prev_chunk_id = None
                if spec_index > 0:
                    prev_chunk_id = f"spreadsheet_{sheet_index}_{window_specs[spec_index - 1]['window_index']}"
                next_chunk_id = None
                if spec_index + 1 < len(window_specs):
                    next_chunk_id = f"spreadsheet_{sheet_index}_{window_specs[spec_index + 1]['window_index']}"

                chunks.append(
                    self._build_chunk(
                        sheet_index=sheet_index,
                        window_index=spec["window_index"],
                        sheet_name=sheet_name,
                        headers=headers,
                        window_rows=spec["window_rows"],
                        window_original_rows=spec["window_original_rows"],
                        fallback_row_start=spec["fallback_row_start"],
                        context_text=context_text,
                        prev_chunk_id=prev_chunk_id,
                        next_chunk_id=next_chunk_id,
                    )
                )

        if not chunks and parser_output.text:
            text = parser_output.text
            token_count = count_tokens(text)
            was_truncated = False
            if token_count > self.max_chunk_tokens:
                text = truncate_to_token_limit(text, self.max_chunk_tokens)
                token_count = count_tokens(text)
                was_truncated = True

            chunks.append(
                Chunk(
                    chunk_id="spreadsheet_summary_1",
                    text=text,
                    narrative_text=text,
                    tables=[],
                    metadata={
                        "chunk_id": "spreadsheet_summary_1",
                        "source_kind": "spreadsheet",
                        "source_parser": "spreadsheet",
                        "section_type": "narrative",
                        "section_heading": "Spreadsheet summary",
                        "is_tabular": False,
                        "has_tables": False,
                        "chunk_type": "narrative",
                        "char_count": len(text),
                        "token_count": token_count,
                        "max_chunk_tokens": self.max_chunk_tokens,
                        "was_truncated": was_truncated,
                    },
                )
            )

        return ChunkingOutput(
            chunks=chunks,
            strategy=self.strategy,
            metadata={
                "source_kind": "spreadsheet",
                "sheet_count": len(sheets),
                "rows_per_chunk": self.rows_per_chunk,
                "rows_overlap": self.rows_overlap,
                "max_chunk_tokens": self.max_chunk_tokens,
            },
        )
