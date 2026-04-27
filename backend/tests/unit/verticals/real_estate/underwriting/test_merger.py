"""Unit tests for CRE merge priority rules."""
import pytest
from app.verticals.real_estate.underwriting.extraction.merger import apply_plausibility_guards, merge_extractions
from app.verticals.real_estate.underwriting.extraction.schemas import (
    ExtractedDocResult,
    OMExtraction,
    T12Extraction,
    RentRollExtraction,
)
from app.verticals.real_estate.underwriting.schemas.self_storage import UnitMixRow


def _om_result(run_id="r1", **kwargs) -> ExtractedDocResult:
    return ExtractedDocResult(
        run_id=run_id, job_id="j1", doc_type="om",
        om=OMExtraction(**kwargs)
    )


def _t12_result(run_id="r1", **kwargs) -> ExtractedDocResult:
    return ExtractedDocResult(
        run_id=run_id, job_id="j1", doc_type="t12",
        t12=T12Extraction(**kwargs)
    )


def _rr_result(run_id="r1", **kwargs) -> ExtractedDocResult:
    return ExtractedDocResult(
        run_id=run_id, job_id="j1", doc_type="rent_roll",
        rent_roll=RentRollExtraction(**kwargs)
    )


# ── T-12 wins for operating figures ─────────────────────────────────────────

def test_t12_gpr_beats_om_projection():
    results = [
        _om_result(purchase_price=1_000_000.0, gpr_annual_projected=520_000.0),
        _t12_result(gpr_annual_actual=480_000.0, period_months=12),
    ]
    merged, _ = merge_extractions(results)
    assert merged["operational"]["gross_potential_rent_annual"] == 480_000.0


def test_om_gpr_used_when_no_t12():
    results = [_om_result(purchase_price=1_000_000.0, gpr_annual_projected=520_000.0)]
    merged, _ = merge_extractions(results)
    assert merged["operational"]["gross_potential_rent_annual"] == 520_000.0


# ── T-6 annualisation ────────────────────────────────────────────────────────

def test_t6_gpr_is_annualised():
    results = [
        _om_result(purchase_price=500_000.0),
        _t12_result(gpr_annual_actual=240_000.0, period_months=6),
    ]
    merged, _ = merge_extractions(results)
    # 240_000 * (12/6) = 480_000
    assert merged["operational"]["gross_potential_rent_annual"] == pytest.approx(480_000.0)


# ── OM wins for deal terms ───────────────────────────────────────────────────

def test_om_purchase_price_always_used():
    results = [_om_result(purchase_price=2_500_000.0, exit_cap_rate=0.065)]
    merged, _ = merge_extractions(results)
    assert merged["acquisition"]["purchase_price"] == 2_500_000.0
    assert merged["exit"]["exit_cap_rate"] == 0.065


# ── Rent Roll wins for unit count ────────────────────────────────────────────

def test_rent_roll_num_units_beats_om():
    results = [
        _om_result(purchase_price=1_000_000.0, num_units=200),
        _rr_result(num_units_actual=195),
    ]
    merged, _ = merge_extractions(results)
    assert merged["project"]["num_units"] == 195


def test_additional_analyst_fields_merge_from_documents():
    results = [
        _om_result(
            purchase_price=1_000_000.0,
            market_cap_rate_purchase=0.0585,
            nearby_storage_count_1mi=4,
            nearby_storage_count_3mi=11,
            nearby_storage_count_5mi=19,
            population_3mi=84500,
            avg_household_income_3mi=78250.0,
            storage_sqft_per_capita_3mi=9.4,
            avg_market_rent_per_unit_monthly=142.0,
            expense_ratio_pro_forma=0.34,
            rent_growth_pct=0.04,
            opex_growth_pct=0.03,
            property_tax_growth_pct=0.05,
            mil_rate=28.4,
            market_cap_rate_sale=0.0675,
        ),
        _t12_result(
            expense_ratio_actual=0.41,
            bad_debt_annual=12_000.0,
            corrections_collections_annual=8_500.0,
        ),
        _rr_result(avg_in_place_rent_per_unit_monthly=118.0),
    ]

    merged, _ = merge_extractions(results)

    assert merged["acquisition"]["market_cap_rate_purchase"] == 0.0585
    assert merged["project"]["nearby_storage_count_1mi"] == 4
    assert merged["project"]["nearby_storage_count_3mi"] == 11
    assert merged["project"]["nearby_storage_count_5mi"] == 19
    assert merged["project"]["population_3mi"] == 84500
    assert merged["project"]["avg_household_income_3mi"] == 78250.0
    assert merged["project"]["storage_sqft_per_capita_3mi"] == 9.4
    assert merged["operational"]["avg_in_place_rent_per_unit_monthly"] == 118.0
    assert merged["operational"]["avg_market_rent_per_unit_monthly"] == 142.0
    assert merged["operational"]["expense_ratio_current"] == 0.41
    assert merged["operational"]["expense_ratio_pro_forma"] == 0.34
    assert merged["operational"]["bad_debt_annual"] == 12_000.0
    assert merged["operational"]["corrections_collections_annual"] == 8_500.0
    assert merged["operational"]["rent_growth_pct"] == 0.04
    assert merged["operational"]["opex_growth_pct"] == 0.03
    assert merged["operational"]["property_tax_growth_pct"] == 0.05
    assert merged["operational"]["mil_rate"] == 28.4
    assert merged["exit"]["market_cap_rate_sale"] == 0.0675


def test_om_only_run_uses_om_expense_lines_when_t12_missing():
    results = [
        _om_result(
            purchase_price=1_000_000.0,
            gpr_annual_projected=480_000.0,
            other_income_annual=24_000.0,
            expense_property_tax_annual=52_000.0,
            expense_insurance_annual=18_500.0,
            expense_payroll_annual=61_000.0,
            expense_repairs_maintenance_annual=27_000.0,
            expense_utilities_annual=15_500.0,
            expense_marketing_annual=9_500.0,
            expense_office_admin_annual=8_000.0,
            expense_bank_fees_annual=2_500.0,
            expense_contract_services_annual=5_500.0,
            expense_miscellaneous_annual=4_500.0,
            expense_telephone_annual=2_000.0,
            expense_mgmt_fee_annual=25_200.0,
        )
    ]

    merged, _ = merge_extractions(results)

    assert merged["operational"]["property_tax_annual"] == 52_000.0
    assert merged["operational"]["insurance_annual"] == 18_500.0
    assert merged["operational"]["payroll_annual"] == 61_000.0
    assert merged["operational"]["repairs_maintenance_annual"] == 27_000.0
    assert merged["operational"]["utilities_annual"] == 15_500.0
    assert merged["operational"]["marketing_annual"] == 9_500.0
    assert merged["operational"]["other_opex_annual"] == 22_500.0
    assert merged["operational"]["mgmt_fee_pct"] == pytest.approx(0.05)
    assert merged["operational"]["expense_ratio_current"] == pytest.approx(0.4587301587)


def test_plausibility_guards_drop_implausible_extracted_scalars():
    results = [
        _om_result(
            purchase_price=1_000_000.0,
            num_units=100,
            gpr_annual_projected=180_000.0,
            avg_in_place_rent_per_unit_monthly=18_000.0,
            avg_market_rent_per_unit_monthly=16_500.0,
            vacancy_pct_projected=1.6,
            market_cap_rate_purchase=0.65,
        )
    ]

    sanitized_results, plausibility_flags = apply_plausibility_guards(results)
    merged, _ = merge_extractions(results)

    om = sanitized_results[0].om
    assert om is not None
    assert om.avg_in_place_rent_per_unit_monthly is None
    assert om.avg_market_rent_per_unit_monthly is None
    assert om.vacancy_pct_projected is None
    assert om.market_cap_rate_purchase is None
    assert {flag["field"] for flag in plausibility_flags} >= {
        "avg_in_place_rent_per_unit_monthly",
        "avg_market_rent_per_unit_monthly",
        "vacancy_pct_projected",
        "market_cap_rate_purchase",
    }
    assert merged["operational"]["avg_in_place_rent_per_unit_monthly"] is None
    assert merged["operational"]["avg_market_rent_per_unit_monthly"] is None
    assert merged["operational"]["vacancy_credit_loss_pct"] == 0.10
    assert merged["acquisition"]["market_cap_rate_purchase"] is None


# ── Defaults applied ─────────────────────────────────────────────────────────

def test_defaults_applied_when_no_values():
    results = [_om_result(purchase_price=1_000_000.0)]
    merged, _ = merge_extractions(results)
    assert merged["financing"]["ltv_pct"] == 0.70
    assert merged["operational"]["vacancy_credit_loss_pct"] == 0.10
    assert merged["criteria"]["target_irr"] == 0.15


# ── Lease records pass through ───────────────────────────────────────────────

def test_lease_records_from_rent_roll():
    from app.verticals.real_estate.underwriting.schemas.self_storage import LeaseRecord
    rr = RentRollExtraction(
        num_units_actual=10,
        lease_records=[LeaseRecord(monthly_rent=500.0, unit_id="A1")],
    )
    results = [
        _om_result(purchase_price=500_000.0),
        ExtractedDocResult(run_id="r1", job_id="j1", doc_type="rent_roll", rent_roll=rr),
    ]
    merged, _ = merge_extractions(results)
    assert len(merged["lease_records"]) == 1
    assert merged["lease_records"][0]["monthly_rent"] == 500.0


def test_om_unit_mix_passes_through_to_merged_inputs():
    results = [
        _om_result(
            purchase_price=1_250_000.0,
            unit_mix=[
                UnitMixRow(
                    section="NON-CLIMATE",
                    unit_type="NON-CLIMATE",
                    size="10 x 10",
                    num_units=64,
                    occupied_units=57,
                    occupancy_pct=57 / 64,
                    current_rent=110.0,
                    rent_per_sqft=1.10,
                    total_sqft=6400.0,
                )
            ],
        )
    ]

    merged, _ = merge_extractions(results)

    assert len(merged["unit_mix"]) == 1
    assert merged["unit_mix"][0]["section"] == "NON-CLIMATE"
    assert merged["unit_mix"][0]["size"] == "10 x 10"
    assert merged["unit_mix"][0]["num_units"] == 64
    assert merged["unit_mix"][0]["occupied_units"] == 57


def test_rent_roll_unit_mix_beats_om_unit_mix():
    results = [
        _om_result(
            purchase_price=1_250_000.0,
            unit_mix=[
                UnitMixRow(
                    section="NON-CLIMATE",
                    unit_type="10 x 10",
                    size="10 x 10",
                    num_units=64,
                    occupied_units=57,
                )
            ],
        ),
        _rr_result(
            num_units_actual=62,
            unit_mix=[
                UnitMixRow(
                    section="NON-CLIMATE",
                    unit_type="10 x 10",
                    size="10 x 10",
                    num_units=62,
                    occupied_units=59,
                    current_rent=118.0,
                )
            ],
        ),
    ]

    merged, _ = merge_extractions(results)

    assert len(merged["unit_mix"]) == 1
    assert merged["unit_mix"][0]["num_units"] == 62
    assert merged["unit_mix"][0]["occupied_units"] == 59
    assert merged["unit_mix"][0]["current_rent"] == 118.0


def test_om_rent_comps_pass_through_to_merged_inputs():
    results = [
        _om_result(
            purchase_price=1_250_000.0,
            rent_comps=[
                {
                    "facility": "U-Haul",
                    "size": "10 x 10",
                    "asking_rent": 79.0,
                    "rent_per_sqft": 0.79,
                    "distance_mi": 2.1,
                    "notes": "online special",
                }
            ],
        )
    ]

    merged, _ = merge_extractions(results)

    assert len(merged["rent_comps"]) == 1
    assert merged["rent_comps"][0]["facility"] == "U-Haul"
    assert merged["rent_comps"][0]["asking_rent"] == 79.0
    assert merged["rent_comps"][0]["rent_per_sqft"] == 0.79
    assert merged["rent_comps"][0]["distance_mi"] == 2.1


def test_empty_unit_mix_defaults_to_empty_list():
    merged, _ = merge_extractions([_om_result(purchase_price=900_000.0)])
    assert merged["unit_mix"] == []
