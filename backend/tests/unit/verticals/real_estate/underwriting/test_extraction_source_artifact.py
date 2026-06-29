from app.verticals.real_estate.underwriting.extraction.schemas import ExtractedDocResult, OMExtraction
from app.verticals.real_estate.underwriting.extraction.tasks.tasks import _build_om_source_data


def test_om_source_data_preserves_source_only_financing_and_value_add_evidence():
    doc_results = [
        ExtractedDocResult(
            run_id="run-1",
            job_id="job-1",
            doc_type="om",
            om=OMExtraction(
                proposed_loan_amount=1_625_000,
                proposed_down_payment_amount=875_000,
                proposed_down_payment_pct=0.35,
                below_market_tenant_pct=0.36,
                below_market_monthly_variance=868,
                below_market_annual_upside=10_410,
                value_add_notes="Parking conversion could add $10,200/month or $122,400/year.",
            ),
        )
    ]

    om_data = _build_om_source_data(doc_results)

    assert om_data["proposed_loan_amount"] == 1_625_000
    assert om_data["proposed_down_payment_amount"] == 875_000
    assert om_data["proposed_down_payment_pct"] == 0.35
    assert om_data["below_market_tenant_pct"] == 0.36
    assert om_data["below_market_monthly_variance"] == 868
    assert om_data["below_market_annual_upside"] == 10_410
    assert om_data["value_add_notes"] == "Parking conversion could add $10,200/month or $122,400/year."
