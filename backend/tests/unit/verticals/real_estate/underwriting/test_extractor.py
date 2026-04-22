"""Unit tests for RE underwriting extraction utilities."""
import pytest
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


def test_t12_extraction_period_months():
    t12 = T12Extraction(gpr_annual_actual=480000.0, period_months=6)
    assert t12.period_months == 6
    assert t12.gpr_annual_actual == 480000.0


def test_extracted_doc_result_error_field():
    result = ExtractedDocResult(run_id="r1", job_id="j1", doc_type="t12", error="timeout")
    assert result.error == "timeout"
    assert result.t12 is None
