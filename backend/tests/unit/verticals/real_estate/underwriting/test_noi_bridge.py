"""Tests for the analyst-facing NOI bridge artifact."""

from app.verticals.real_estate.underwriting.calculator import calculate
from app.verticals.real_estate.underwriting.extraction.schemas import OMExtraction, T12Extraction
from app.verticals.real_estate.underwriting.noi_bridge import build_noi_bridge
from app.verticals.real_estate.underwriting.schemas.self_storage import (
    AcquisitionInputs,
    ExitInputs,
    FinancingInputs,
    InvestmentCriteria,
    OperationalInputs,
    ProjectDetails,
    SelfStorageInputs,
)


def _inputs(**operational_overrides) -> SelfStorageInputs:
    return SelfStorageInputs(
        project=ProjectDetails(name="Bridge Test", asset_type="self_storage"),
        acquisition=AcquisitionInputs(purchase_price=5_000_000),
        operational=OperationalInputs(
            gross_potential_rent_annual=600_000,
            vacancy_credit_loss_pct=0.10,
            other_income_annual=20_000,
            property_tax_annual=30_000,
            insurance_annual=20_000,
            payroll_annual=50_000,
            repairs_maintenance_annual=40_000,
            utilities_annual=30_000,
            marketing_annual=5_000,
            other_opex_annual=10_000,
            **operational_overrides,
        ),
        financing=FinancingInputs(),
        exit=ExitInputs(hold_period_years=5),
        criteria=InvestmentCriteria(),
    )


def _labels(bridge: dict) -> list[str]:
    return [row["label"] for row in bridge["rows"]]


def test_build_noi_bridge_om_only():
    inputs = _inputs(noi_year_one_stated=700_000)
    result = calculate(inputs)
    bridge = build_noi_bridge(inputs, OMExtraction(noi_year_one_stated=700_000), None, result)

    assert _labels(bridge) == ["OM Year-1 NOI", "Model Year-1 NOI"]
    assert bridge["rows"][0]["value"] == 700_000


def test_build_noi_bridge_om_and_t12():
    inputs = _inputs(noi_year_one_stated=700_000, income_basis_months=12)
    result = calculate(inputs)
    t12 = T12Extraction(noi_actual=650_000, period_months=12)

    bridge = build_noi_bridge(inputs, OMExtraction(noi_year_one_stated=700_000), t12, result)

    assert _labels(bridge) == ["OM Year-1 NOI", "T-12 actual NOI", "Model Year-1 NOI"]
    assert bridge["has_t12"] is True
    assert bridge["rows"][1]["source_field"] == "noi_actual"
    assert bridge["rows"][1]["delta_to_prior"]["amount"] == 50_000


def test_build_noi_bridge_annualizes_t6_t12_noi():
    inputs = _inputs(income_basis_months=6)
    result = calculate(inputs)
    t12 = T12Extraction(noi_actual=325_000, period_months=6)

    bridge = build_noi_bridge(inputs, None, t12, result)

    assert bridge["rows"][0]["label"] == "T-6 actual NOI annualized"
    assert bridge["rows"][0]["value"] == 650_000


def test_build_noi_bridge_handles_zero_period_months_without_annualizing():
    inputs = _inputs(income_basis_months=0)
    result = calculate(inputs)
    t12 = T12Extraction(noi_actual=650_000, period_months=0)

    bridge = build_noi_bridge(inputs, None, t12, result)

    assert bridge["rows"][0]["label"] == "Operating statement NOI"
    assert bridge["rows"][0]["value"] == 650_000


def test_build_noi_bridge_missing_source_noi_keeps_model_row():
    inputs = _inputs()
    result = calculate(inputs)

    bridge = build_noi_bridge(inputs, None, None, result)

    assert _labels(bridge) == ["Model Year-1 NOI"]


def test_build_noi_bridge_uses_preserved_artifact_on_manual_recalc():
    inputs = _inputs()
    result = calculate(inputs)
    artifact = {
        "om_data": {"noi_year_one_stated": 700_000},
        "t12_data": {"summary": {"noi_actual": 650_000, "period_months": 12}},
    }

    bridge = build_noi_bridge(inputs, None, None, result, source_artifact=artifact)

    assert _labels(bridge) == ["OM Year-1 NOI", "T-12 actual NOI", "Model Year-1 NOI"]
    assert bridge["rows"][1]["value"] == 650_000
