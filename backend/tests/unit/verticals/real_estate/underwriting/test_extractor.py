"""Unit tests for RE underwriting extraction utilities."""
import pytest
from unittest.mock import MagicMock
from app.verticals.real_estate.underwriting.extraction.extractor import (
    batch_chunks_by_chars,
    build_chunk_context,
    extract_document,
)
from app.config import settings
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


def test_t12_spreadsheet_totals_are_injected_and_reconciled():
    rows = [
        {"Month": "Apr-25", "Rental Income": "1000", "Total Income": "1100", "Total Expenses": "200", "NOI": "900"},
        {"Month": "May-25", "Rental Income": "2000", "Total Income": "2200", "Total Expenses": "400", "NOI": "1800"},
        {"Month": "T12 Total", "Rental Income": "", "Total Income": "", "Total Expenses": "", "NOI": ""},
    ]
    chunk = MagicMock()
    chunk.text = "Sheet: Seller T12 Export"
    chunk.page_number = None
    chunk.section_type = "table"
    chunk.source_filename = "seller_t12.xlsx"
    chunk.tables = [{
        "sheet_name": "Seller T12 Export",
        "table_name": "Seller T12 Export",
        "row_start": 2,
        "row_end": 4,
        "column_headers": ["Month", "Rental Income", "Total Income", "Total Expenses", "NOI"],
        "table_data": rows,
    }]
    chunk.chunk_metadata = {
        "source_kind": "spreadsheet",
        "sheet_name": "Seller T12 Export",
        "row_start": 2,
        "row_end": 4,
    }

    class FakeService:
        last_context = ""

        def extract_t12(self, context):
            self.last_context = context
            return {
                "scalars": {
                    "gpr_annual_actual": 1000.0,
                    "other_income_annual": 0.0,
                    "expense_ratio_actual": 0.1,
                    "noi_actual": 100.0,
                    "period_months": 12,
                },
                "field_citations": {},
            }

    service = FakeService()

    result = extract_document(
        run_id="run-1",
        job_id="job-1",
        doc_type="t12",
        chunks=[chunk],
        service=service,
        source_index=2,
        document_id="doc-1",
    )

    assert "Verified Spreadsheet Totals" in service.last_context
    assert "[S2:Seller T12 Export!R2-R4]" in service.last_context
    assert result.t12.gpr_annual_actual == 3000
    assert result.t12.other_income_annual == 300
    assert result.t12.expense_ratio_actual == 600 / 3300
    assert result.t12.noi_actual == 2700
    assert result.t12.period_months == 2
    assert result.field_citations["other_income_annual"]["citations"] == ["S2:Seller T12 Export!R2-R4"]
    assert result.extraction_metadata["t12_table_totals"]["computed_from_spreadsheet"] is True


def test_large_om_uses_selected_context_without_fallback(monkeypatch):
    monkeypatch.setattr(settings, "re_uw_om_two_call_enabled", False)
    monkeypatch.setattr(settings, "re_uw_om_context_selector_enabled", True)
    monkeypatch.setattr(settings, "re_uw_om_context_selector_min_chars", 50)
    monkeypatch.setattr(settings, "re_uw_om_context_max_chars", 400)
    chunks = [
        _make_chunk("Offering Memorandum cover", page=1),
        _make_chunk("Purchase price $2,500,000; 205 units; GPR $285,740", page=4),
        _make_chunk("Confidentiality disclaimer broker biography legal disclosure " + "x" * 200, page=8),
    ]

    class FakeService:
        def __init__(self):
            self.contexts = []

        def extract_om(self, context):
            self.contexts.append(context)
            return {
                "scalars": {
                    "purchase_price": 2_500_000.0,
                    "num_units": 205,
                    "gpr_annual_projected": 285_740.0,
                    "rentable_sqft": 21_017.0,
                    "market_cap_rate_purchase": 0.0811,
                    "vacancy_pct_projected": 0.1278,
                    "other_income_annual": 34_278.0,
                    "expense_ratio_pro_forma": 0.2778,
                    "noi_year_one_stated": 202_790.0,
                    "rent_comps": [],
                    "unit_mix": [],
                },
                "field_citations": {
                    "purchase_price": {"citations": ["S1:p4"], "confidence": 0.9, "source_text": "$2,500,000"},
                    "num_units": {"citations": ["S1:p4"], "confidence": 0.9, "source_text": "205 units"},
                    "gpr_annual_projected": {"citations": ["S1:p4"], "confidence": 0.9, "source_text": "GPR $285,740"},
                },
            }

    service = FakeService()
    result = extract_document("run-1", "job-1", "om", chunks, service)

    assert len(service.contexts) == 1
    assert "Purchase price" in service.contexts[0]
    assert "broker biography" not in service.contexts[0]
    assert result.om.purchase_price == 2_500_000.0
    assert result.extraction_metadata["om_context_selection"]["fallback_to_full_context"] is False


def test_large_om_falls_back_to_full_context_when_core_fields_missing(monkeypatch):
    monkeypatch.setattr(settings, "re_uw_om_two_call_enabled", False)
    monkeypatch.setattr(settings, "re_uw_om_context_selector_enabled", True)
    monkeypatch.setattr(settings, "re_uw_om_context_selector_min_chars", 50)
    monkeypatch.setattr(settings, "re_uw_om_context_max_chars", 350)
    chunks = [
        _make_chunk("Offering Memorandum cover", page=1),
        _make_chunk("Purchase price $2,500,000", page=4),
        _make_chunk("Confidentiality disclaimer broker biography legal disclosure " + "x" * 200, page=8),
    ]

    class FakeService:
        def __init__(self):
            self.contexts = []

        def extract_om(self, context):
            self.contexts.append(context)
            if len(self.contexts) == 1:
                return {
                    "scalars": {"purchase_price": 2_500_000.0, "rent_comps": [], "unit_mix": []},
                    "field_citations": {},
                }
            return {
                "scalars": {
                    "purchase_price": 2_500_000.0,
                    "num_units": 205,
                    "gpr_annual_projected": 285_740.0,
                    "rentable_sqft": 21_017.0,
                    "market_cap_rate_purchase": 0.0811,
                    "vacancy_pct_projected": 0.1278,
                    "other_income_annual": 34_278.0,
                    "expense_ratio_pro_forma": 0.2778,
                    "noi_year_one_stated": 202_790.0,
                    "rent_comps": [],
                    "unit_mix": [],
                },
                "field_citations": {
                    "purchase_price": {"citations": ["S1:p4"], "confidence": 0.9, "source_text": "$2,500,000"},
                    "num_units": {"citations": ["S1:p4"], "confidence": 0.9, "source_text": "205 units"},
                    "gpr_annual_projected": {"citations": ["S1:p4"], "confidence": 0.9, "source_text": "GPR $285,740"},
                },
            }

    service = FakeService()
    result = extract_document("run-1", "job-1", "om", chunks, service)

    assert len(service.contexts) == 2
    assert "broker biography" not in service.contexts[0]
    assert "broker biography" in service.contexts[1]
    assert result.om.num_units == 205
    metadata = result.extraction_metadata["om_context_selection"]
    assert metadata["fallback_to_full_context"] is True
    assert "missing_units_or_sqft" in metadata["fallback_reasons"]


def test_om_two_call_uses_full_chunk_contexts_and_bypasses_selector(monkeypatch):
    monkeypatch.setattr(settings, "re_uw_om_two_call_enabled", True)
    monkeypatch.setattr(settings, "re_uw_om_context_selector_enabled", True)
    monkeypatch.setattr(settings, "re_uw_om_context_selector_min_chars", 1)
    monkeypatch.setattr(settings, "re_uw_om_context_max_chars", 20)
    monkeypatch.setattr(settings, "re_uw_full_text_max_chars", 50)

    chunks = [
        _make_chunk("Offering Memorandum cover with property overview", page=1),
        _make_chunk("Purchase price $2,500,000; 205 units; GPR $285,740", page=4, section_type="key_value"),
        _make_chunk("Confidentiality disclaimer broker biography legal disclosure " + "x" * 200, page=8),
    ]

    class FakeService:
        def __init__(self):
            self.calls = []

        def extract_om(self, context, supplemental_context=None, structure_context=None):
            self.calls.append({
                "context": context,
                "supplemental_context": supplemental_context,
                "structure_context": structure_context,
            })
            return {
                "scalars": {
                    "purchase_price": 2_500_000.0,
                    "num_units": 205,
                    "gpr_annual_projected": 285_740.0,
                    "rentable_sqft": 21_017.0,
                    "market_cap_rate_purchase": 0.0811,
                    "vacancy_pct_projected": 0.1278,
                    "other_income_annual": 34_278.0,
                    "expense_ratio_pro_forma": 0.2778,
                    "noi_year_one_stated": 202_790.0,
                    "rent_comps": [],
                    "unit_mix": [],
                },
                "field_citations": {
                    "purchase_price": {"citations": ["S1:p4"], "confidence": 0.9, "source_text": "$2,500,000"},
                    "num_units": {"citations": ["S1:p4"], "confidence": 0.9, "source_text": "205 units"},
                    "gpr_annual_projected": {"citations": ["S1:p4"], "confidence": 0.9, "source_text": "GPR $285,740"},
                },
            }

    service = FakeService()
    result = extract_document("run-1", "job-1", "om", chunks, service)

    assert len(service.calls) == 1
    call = service.calls[0]
    extraction_context = call["context"]
    structure_context = call["structure_context"]
    assert "Purchase price" in extraction_context
    assert "Offering Memorandum cover" in extraction_context
    assert "broker biography" not in extraction_context
    assert "Purchase price" in structure_context
    assert "Offering Memorandum cover" in structure_context
    assert "broker biography" in structure_context
    assert call["supplemental_context"] is None
    assert result.om.purchase_price == 2_500_000.0
    metadata = result.extraction_metadata["om_two_call_contexts"]
    assert metadata["source"] == "split_contexts"
    assert metadata["structure_used_fallback"] is True
    assert metadata["extraction_used_fallback"] is False
    assert metadata["structure_source_tokens"]
    assert metadata["extraction_source_tokens"]


def test_om_two_call_splits_structure_and_extraction_contexts(monkeypatch):
    monkeypatch.setattr(settings, "re_uw_om_two_call_enabled", True)

    chunks = [
        _make_chunk("Cover page property overview", page=1),
        _make_chunk("Purchase Price: $2,500,000", page=2, section_type="key_value"),
        _make_chunk("Operating Statement | Current | Year 1 | Pro Forma | NOI", page=4, is_tabular=True),
        _make_chunk("3-mile Population demographics household income square feet per capita", page=7),
    ]

    class FakeService:
        def __init__(self):
            self.calls = []

        def extract_om(self, context, supplemental_context=None, structure_context=None):
            self.calls.append({
                "context": context,
                "supplemental_context": supplemental_context,
                "structure_context": structure_context,
            })
            return {
                "scalars": {
                    "purchase_price": 2_500_000.0,
                    "num_units": 205,
                    "gpr_annual_projected": 285_740.0,
                    "rentable_sqft": 21_017.0,
                    "market_cap_rate_purchase": 0.0811,
                    "vacancy_pct_projected": 0.1278,
                    "other_income_annual": 34_278.0,
                    "expense_ratio_pro_forma": 0.2778,
                    "noi_year_one_stated": 202_790.0,
                    "rent_comps": [],
                    "unit_mix": [],
                },
                "field_citations": {
                    "purchase_price": {"citations": ["S1:p2"], "confidence": 0.9, "source_text": "$2,500,000"},
                    "noi_year_one_stated": {"citations": ["S1:p4"], "confidence": 0.9, "source_text": "NOI"},
                },
            }

    service = FakeService()
    result = extract_document("run-1", "job-1", "om", chunks, service)

    assert len(service.calls) == 1
    call = service.calls[0]
    assert "Operating Statement" in call["structure_context"]
    assert "Purchase Price" not in call["structure_context"]
    assert "Population demographics" not in call["structure_context"]
    assert "Operating Statement" in call["context"]
    assert "Purchase Price" in call["context"]
    assert "Cover page" in call["context"]
    assert "Population demographics" in call["context"]
    assert call["supplemental_context"] is None
    assert result.om.purchase_price == 2_500_000.0
    metadata = result.extraction_metadata["om_two_call_contexts"]
    assert metadata["source"] == "split_contexts"
    assert metadata["structure_chunk_count"] == 1
    assert metadata["extraction_chunk_count"] == 4
    assert metadata["structure_char_count"] > 0
    assert metadata["extraction_char_count"] > metadata["structure_char_count"]
    assert metadata["structure_used_fallback"] is False
    assert metadata["extraction_used_fallback"] is False


def test_om_two_call_call1_falls_back_when_no_tables(monkeypatch):
    monkeypatch.setattr(settings, "re_uw_om_two_call_enabled", True)

    chunks = [
        _make_chunk("Cover page property overview", page=1),
        _make_chunk("Purchase Price: $2,500,000", page=2, section_type="key_value"),
        _make_chunk("Population demographics household income square feet per capita", page=7),
    ]

    class FakeService:
        def __init__(self):
            self.calls = []

        def extract_om(self, context, supplemental_context=None, structure_context=None):
            self.calls.append((context, structure_context))
            return {
                "scalars": {
                    "purchase_price": 2_500_000.0,
                    "num_units": 205,
                    "gpr_annual_projected": 285_740.0,
                    "rentable_sqft": 21_017.0,
                    "market_cap_rate_purchase": 0.0811,
                    "vacancy_pct_projected": 0.1278,
                    "other_income_annual": 34_278.0,
                    "expense_ratio_pro_forma": 0.2778,
                    "noi_year_one_stated": 202_790.0,
                    "rent_comps": [],
                    "unit_mix": [],
                },
                "field_citations": {
                    "purchase_price": {"citations": ["S1:p2"], "confidence": 0.9, "source_text": "$2,500,000"},
                },
            }

    service = FakeService()
    result = extract_document("run-1", "job-1", "om", chunks, service)

    assert len(service.calls) == 1
    context, structure_context = service.calls[0]
    assert "Cover page" in structure_context
    assert "Purchase Price" in structure_context
    assert "Population demographics" in structure_context
    assert "Population demographics" not in context
    assert result.om.purchase_price == 2_500_000.0
    metadata = result.extraction_metadata["om_two_call_contexts"]
    assert metadata["structure_used_fallback"] is True


def test_om_two_call_excludes_generic_selected_geography_narrative(monkeypatch):
    monkeypatch.setattr(settings, "re_uw_om_two_call_enabled", True)

    chunks = [
        _make_chunk("Cover page property overview", page=1),
        _make_chunk("Purchase Price: $2,500,000", page=2, section_type="key_value"),
        _make_chunk("Operating Statement | Current | Year 1 | NOI", page=4, is_tabular=True),
        _make_chunk(
            "In 2023, the population in your selected geography is 153,689. "
            "The current year's average household income in your area is $65,499.",
            page=26,
        ),
        _make_chunk(
            "Within 3 miles, the population is 63,110 and average household income is $49,306.",
            page=27,
        ),
    ]

    class FakeService:
        def __init__(self):
            self.calls = []

        def extract_om(self, context, supplemental_context=None, structure_context=None):
            self.calls.append(context)
            return {
                "scalars": {
                    "purchase_price": 2_500_000.0,
                    "num_units": 205,
                    "gpr_annual_projected": 285_740.0,
                    "rentable_sqft": 21_017.0,
                    "market_cap_rate_purchase": 0.0811,
                    "vacancy_pct_projected": 0.1278,
                    "other_income_annual": 34_278.0,
                    "expense_ratio_pro_forma": 0.2778,
                    "noi_year_one_stated": 202_790.0,
                    "rent_comps": [],
                    "unit_mix": [],
                },
                "field_citations": {},
            }

    service = FakeService()
    result = extract_document("run-1", "job-1", "om", chunks, service)

    extraction_context = service.calls[0]
    assert "selected geography is 153,689" not in extraction_context
    assert "population is 63,110" in extraction_context
    metadata = result.extraction_metadata["om_two_call_contexts"]
    assert metadata["extraction_chunk_count"] == 4
