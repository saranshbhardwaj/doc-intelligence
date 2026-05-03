"""Tests for deterministic OM context selection."""

from unittest.mock import MagicMock

from app.verticals.real_estate.underwriting.extraction.om_context_selector import (
    select_om_context_chunks,
)


def _chunk(
    text: str,
    *,
    page: int,
    section_type: str = "narrative",
    chunk_id: str | None = None,
    metadata: dict | None = None,
):
    chunk = MagicMock()
    chunk.id = chunk_id
    chunk.chunk_id = chunk_id
    chunk.text = text
    chunk.page_number = page
    chunk.section_type = section_type
    chunk.section_heading = None
    chunk.chunk_metadata = {"bbox": {"page": page}, "page_number": page, **(metadata or {})}
    return chunk


def test_selector_keeps_high_signal_sections_and_drops_boilerplate():
    chunks = [
        _chunk("Tulsa Self Storage Offering Memorandum", page=1, chunk_id="c1"),
        _chunk("Confidentiality disclaimer broker biography contact legal disclosure", page=3, chunk_id="c2"),
        _chunk("Operating statement Year 1 GPR NOI expenses cap rate", page=4, section_type="table", chunk_id="c3"),
        _chunk("Population demographics household income storage sqft per capita", page=5, chunk_id="c4"),
        _chunk("Another legal disclaimer and non-binding offer text", page=6, chunk_id="c5"),
    ]

    selection = select_om_context_chunks(chunks, source_index=1, max_chars=500)

    selected_text = "\n".join(chunk.text for chunk in selection.selected_chunks)
    assert "Offering Memorandum" in selected_text
    assert "Operating statement" in selected_text
    assert "Population demographics" in selected_text
    assert "broker biography" not in selected_text
    assert selection.metadata["dropped_chunk_count"] == 2


def test_selector_preserves_original_chunk_order():
    chunks = [
        _chunk("Confidentiality disclaimer", page=3, chunk_id="c1"),
        _chunk("Purchase price $2,500,000", page=4, chunk_id="c2"),
        _chunk("Rent comp competition table", page=5, section_type="table", chunk_id="c3"),
    ]

    selection = select_om_context_chunks(chunks, source_index=1, max_chars=500)

    assert [chunk.chunk_id for chunk in selection.selected_chunks] == ["c2", "c3"]


def test_selector_honors_char_budget():
    chunks = [
        _chunk("Cover page " + "a" * 90, page=1, chunk_id="c1"),
        _chunk("Purchase price " + "b" * 90, page=3, chunk_id="c2"),
        _chunk("NOI operating statement " + "c" * 90, page=4, chunk_id="c3"),
    ]

    selection = select_om_context_chunks(chunks, source_index=1, max_chars=180)

    assert selection.metadata["selected_char_count"] <= 180


def test_selector_includes_linked_narrative_for_selected_table_when_budget_allows():
    chunks = [
        _chunk("Narrative paragraph introducing the following table", page=4, chunk_id="n1"),
        _chunk(
            "Operating statement table with GPR NOI expenses",
            page=5,
            section_type="table",
            chunk_id="t1",
            metadata={"linked_narrative_id": "n1"},
        ),
        _chunk("Legal disclaimer broker biography", page=6, chunk_id="b1"),
    ]

    selection = select_om_context_chunks(chunks, source_index=1, max_chars=500)

    assert [chunk.chunk_id for chunk in selection.selected_chunks] == ["n1", "t1"]
    assert selection.metadata["reason_counts"]["linked_narrative"] == 1
