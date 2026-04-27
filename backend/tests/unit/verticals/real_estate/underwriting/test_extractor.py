"""Unit tests for RE underwriting extraction utilities."""
import pytest
from unittest.mock import MagicMock
from app.verticals.real_estate.underwriting.extraction.extractor import (
    batch_chunks_by_chars,
    build_chunk_context,
)
from app.verticals.real_estate.underwriting.extraction.schemas import (
    OMExtraction,
    T12Extraction,
    RentRollExtraction,
    ExtractedDocResult,
)


def test_om_extraction_all_optional():
    om = OMExtraction()
    assert om.purchase_price is None
    assert om.num_units is None
    assert om.rent_comps == []


def test_t12_extraction_period_months():
    t12 = T12Extraction(gpr_annual_actual=480000.0, period_months=6)
    assert t12.period_months == 6
    assert t12.gpr_annual_actual == 480000.0


def test_extracted_doc_result_error_field():
    result = ExtractedDocResult(run_id="r1", job_id="j1", doc_type="t12", error="timeout")
    assert result.error == "timeout"
    assert result.t12 is None


# ── batch_chunks_by_chars ────────────────────────────────────────────────────

def _make_chunk(content: str, page: int = 1, is_tabular: bool = False, section_type: str = "narrative"):
    c = MagicMock()
    c.content = content
    c.text = content
    c.page_number = page
    c.is_tabular = is_tabular
    if is_tabular:
        c.section_type = "table"
    elif section_type == "key_value":
        c.section_type = "key_value_pairs"
    else:
        c.section_type = section_type
    c.chunk_metadata = {"bbox": {"page": page}}
    return c


def test_batch_chunks_single_batch():
    chunks = [_make_chunk("a" * 1000) for _ in range(5)]
    batches = batch_chunks_by_chars(chunks, max_chars=10_000)
    assert len(batches) == 1
    assert sum(len(c.content) for c in batches[0]) == 5000


def test_batch_chunks_splits_on_budget():
    chunks = [_make_chunk("a" * 8000) for _ in range(3)]
    batches = batch_chunks_by_chars(chunks, max_chars=10_000)
    assert len(batches) == 3  # each 8K chunk starts a new batch


def test_batch_chunks_empty_input():
    assert batch_chunks_by_chars([], max_chars=20_000) == []


def test_batch_chunks_single_oversized_chunk_goes_alone():
    chunks = [_make_chunk("a" * 25_000)]
    batches = batch_chunks_by_chars(chunks, max_chars=20_000)
    assert len(batches) == 1  # oversized but nowhere else to go


# ── build_chunk_context ──────────────────────────────────────────────────────

def test_build_chunk_context_includes_citation():
    chunk = _make_chunk("GPR: $485,000", page=5)
    ctx = build_chunk_context([chunk], source_index=1)
    assert "[S1:p5]" in ctx
    assert "GPR: $485,000" in ctx


def test_build_chunk_context_labels_table():
    chunk = _make_chunk("Unit | Rent", page=3, is_tabular=True)
    ctx = build_chunk_context([chunk], source_index=2)
    assert "[S2:p3]" in ctx
    assert "Table Chunk" in ctx


def test_build_chunk_context_labels_kv():
    chunk = _make_chunk("Price: $1.2M", page=1, section_type="key_value")
    ctx = build_chunk_context([chunk], source_index=1)
    assert "KV Pair" in ctx
