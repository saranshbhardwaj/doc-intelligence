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


def test_om_noi_projected_maps_to_noi_year_one_stated():
    results = [_om_result(purchase_price=1_000_000.0, noi_projected=275_000.0)]

    merged, citations = merge_extractions(results)

    assert merged["operational"]["noi_year_one_stated"] == 275_000.0
    assert citations["noi_year_one_stated"]["doc_type"] == "om"


def test_om_noi_year_one_stated_beats_projected_noi():
    results = [
        _om_result(
            purchase_price=1_000_000.0,
            noi_year_one_stated=300_000.0,
            noi_projected=275_000.0,
        )
    ]

    merged, _ = merge_extractions(results)

    assert merged["operational"]["noi_year_one_stated"] == 300_000.0


def test_t12_operating_actuals_still_win_when_om_noi_projected_exists():
    results = [
        _om_result(
            purchase_price=1_000_000.0,
            gpr_annual_projected=520_000.0,
            noi_projected=275_000.0,
        ),
        _t12_result(gpr_annual_actual=480_000.0, property_tax_annual=42_000.0, period_months=12),
    ]

    merged, _ = merge_extractions(results)

    assert merged["operational"]["gross_potential_rent_annual"] == 480_000.0
    assert merged["operational"]["property_tax_annual"] == 42_000.0
    assert merged["operational"]["noi_year_one_stated"] == 275_000.0


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


def test_missing_purchase_price_remains_none_not_zero_default():
    results = [_om_result(gpr_annual_projected=520_000.0)]

    merged, citations = merge_extractions(results)

    assert merged["acquisition"]["purchase_price"] is None
    assert "purchase_price" not in citations


def test_max_ltv_default_carries_default_citation():
    results = [_om_result(purchase_price=1_000_000.0)]

    merged, citations = merge_extractions(results)

    assert merged["criteria"]["max_ltv"] == 0.80
    assert citations["max_ltv"]["is_default"] is True


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
            property_tax_value_basis_amount=1_250_000.0,
            property_tax_assessed_value=137_500.0,
            property_tax_assessment_ratio=0.11,
            property_tax_millage_rate=111.61,
            property_tax_rate_per_assessed_dollar=0.11161,
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
    assert merged["operational"]["property_tax_value_basis_amount"] == 1_250_000.0
    assert merged["operational"]["property_tax_assessed_value"] == 137_500.0
    assert merged["operational"]["property_tax_assessment_ratio"] == 0.11
    assert merged["operational"]["property_tax_millage_rate"] == 111.61
    assert merged["operational"]["property_tax_rate_per_assessed_dollar"] == 0.11161
    assert merged["exit"]["market_cap_rate_sale"] == 0.0675


def test_computed_t12_expense_ratio_has_formula_metadata():
    results = [
        _om_result(purchase_price=1_000_000.0),
        _t12_result(
            gpr_annual_actual=1_000_000.0,
            other_income_annual=100_000.0,
            property_tax_annual=100_000.0,
            insurance_annual=50_000.0,
            payroll_annual=150_000.0,
            repairs_maintenance_annual=40_000.0,
            utilities_annual=30_000.0,
            marketing_annual=20_000.0,
            other_opex_annual=10_000.0,
            mgmt_fee_pct_actual=0.05,
            period_months=12,
        ),
    ]

    merged, citations = merge_extractions(results)

    assert merged["operational"]["expense_ratio_current"] == pytest.approx(455_000.0 / 1_100_000.0)
    citation = citations["expense_ratio_current"]
    assert citation["doc_type"] == "t12"
    assert citation["is_computed"] is True
    assert "formula" in citation
    assert "total revenue" in citation["formula"]


def test_om_only_run_uses_om_expense_lines_when_t12_missing():
    results = [
        _om_result(
            purchase_price=1_000_000.0,
            gpr_annual_projected=480_000.0,
            other_income_annual=24_000.0,
            expense_property_tax_annual_year1=52_000.0,
            expense_insurance_annual_year1=18_500.0,
            expense_payroll_annual=61_000.0,
            expense_repairs_maintenance_annual_year1=27_000.0,
            expense_utilities_annual_year1=15_500.0,
            expense_marketing_annual_year1=9_500.0,
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
    # marketing_annual is raised from 9_500 to the benchmark floor (3% of GPR = 14_400)
    assert merged["operational"]["marketing_annual"] == pytest.approx(14_400.0)
    assert merged["operational"]["other_opex_annual"] == 22_500.0
    assert merged["operational"]["mgmt_fee_pct"] == pytest.approx(0.05)
    # expense_ratio_current is derived from stated OM lines before floor adjustment
    assert merged["operational"]["expense_ratio_current"] == pytest.approx(0.4587301587)


def test_om_other_opex_uses_combined_component_citations():
    result = ExtractedDocResult(
        run_id="r1",
        job_id="j1",
        doc_type="om",
        om=OMExtraction(
            purchase_price=1_000_000.0,
            expense_office_admin_annual=8_000.0,
            expense_bank_fees_annual=2_500.0,
        ),
        field_citations={
            "expense_office_admin_annual": {
                "doc_type": "om",
                "confidence": 0.9,
                "citations": ["S1:p10"],
                "source_text": "Office & Admin $8,000",
            },
            "expense_bank_fees_annual": {
                "doc_type": "om",
                "confidence": 0.9,
                "citations": ["S1:p11"],
                "source_text": "Bank Fees $2,500",
            },
        },
    )

    merged, citations = merge_extractions([result])

    assert merged["operational"]["other_opex_annual"] == 10_500.0
    assert citations["other_opex_annual"]["doc_type"] == "om"
    assert citations["other_opex_annual"]["is_computed"] is True
    assert citations["other_opex_annual"]["citations"] == ["S1:p10", "S1:p11"]
    assert "is_uncited_extraction" not in citations["other_opex_annual"]


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


def test_uncited_extracted_t12_value_is_not_marked_default():
    results = [
        _om_result(purchase_price=1_000_000.0),
        _t12_result(other_opex_annual=70_105.0, period_months=12),
    ]

    merged, citations = merge_extractions(results)

    assert merged["operational"]["other_opex_annual"] == 70_105.0
    assert citations["other_opex_annual"]["doc_type"] == "t12"
    assert citations["other_opex_annual"]["is_default"] is False
    assert citations["other_opex_annual"]["is_uncited_extraction"] is True


def test_hardcoded_fallback_still_marked_default():
    merged, citations = merge_extractions([_om_result(purchase_price=1_000_000.0)])

    assert merged["operational"]["other_opex_annual"] == 0.0
    assert citations["other_opex_annual"]["is_default"] is True
    assert "is_uncited_extraction" not in citations["other_opex_annual"]


def test_om_extraction_has_year1_and_current_fields():
    """OMExtraction schema exposes both _year1 and _current variants."""
    from app.verticals.real_estate.underwriting.extraction.schemas import OMExtraction
    om = OMExtraction(
        expense_property_tax_annual_year1=15346.0,
        expense_property_tax_annual_current=6139.0,
        expense_insurance_annual_year1=11840.0,
        expense_insurance_annual_current=9867.0,
        expense_repairs_maintenance_annual_year1=2102.0,
        expense_repairs_maintenance_annual_current=1424.0,
        expense_marketing_annual_year1=4203.0,
        expense_marketing_annual_current=3847.0,
        expense_utilities_annual_year1=6868.0,
        expense_utilities_annual_current=8080.0,
    )
    assert om.expense_property_tax_annual_year1 == 15346.0
    assert om.expense_property_tax_annual_current == 6139.0
    assert om.expense_insurance_annual_year1 == 11840.0
    assert om.expense_insurance_annual_current == 9867.0
    assert om.expense_repairs_maintenance_annual_year1 == 2102.0
    assert om.expense_repairs_maintenance_annual_current == 1424.0
    assert om.expense_marketing_annual_year1 == 4203.0
    assert om.expense_marketing_annual_current == 3847.0
    assert om.expense_utilities_annual_year1 == 6868.0
    assert om.expense_utilities_annual_current == 8080.0


def test_om_extraction_old_single_fields_removed():
    """Old single-variant field names no longer exist on OMExtraction."""
    from app.verticals.real_estate.underwriting.extraction.schemas import OMExtraction
    om = OMExtraction()
    assert not hasattr(om, "expense_property_tax_annual")
    assert not hasattr(om, "expense_insurance_annual")
    assert not hasattr(om, "expense_repairs_maintenance_annual")
    assert not hasattr(om, "expense_marketing_annual")
    assert not hasattr(om, "expense_utilities_annual")
    assert not hasattr(om, "mil_rate")


# ── Property tax mechanics ─────────────────────────────────────────────────

def test_property_tax_om_year1_beats_computed_tax_mechanics():
    """OM Year-1 tax wins over computed mechanics when both are present."""
    results = [
        _om_result(
            property_tax_value_basis_amount=2_500_000.0,
            property_tax_assessment_ratio=0.11,
            property_tax_rate_per_assessed_dollar=0.11161,
            expense_property_tax_annual_year1=15346.0,
            expense_property_tax_annual_current=6139.0,
        )
    ]
    merged, citations = merge_extractions(results)
    assert merged["operational"]["property_tax_annual"] == pytest.approx(15346.0)
    assert citations["property_tax_annual"]["doc_type"] == "om"


def test_property_tax_t12_beats_computed():
    """T-12 actual property tax wins over OM and computed mechanics."""
    results = [
        _om_result(
            property_tax_value_basis_amount=2_500_000.0,
            property_tax_assessment_ratio=0.11,
            property_tax_millage_rate=111.61,
            expense_property_tax_annual_year1=15346.0,
        ),
        _t12_result(property_tax_annual=14000.0),
    ]
    merged, _ = merge_extractions(results)
    assert merged["operational"]["property_tax_annual"] == pytest.approx(14000.0)


def test_property_tax_computes_from_assessed_value_and_rate_per_assessed_dollar():
    """When Year-1 is absent, assessed value × rate computes tax."""
    results = [
        _om_result(
            property_tax_assessed_value=275_000.0,
            property_tax_rate_per_assessed_dollar=0.11161,
            expense_property_tax_annual_year1=None,
            expense_property_tax_annual_current=6139.0,
        )
    ]
    merged, citations = merge_extractions(results)
    assert merged["operational"]["property_tax_annual"] == pytest.approx(275_000.0 * 0.11161)
    assert citations["property_tax_annual"]["doc_type"] == "derived"
    assert "$275,000 assessed value" in citations["property_tax_annual"]["formula"]


def test_property_tax_computes_from_value_basis_assessment_ratio_and_millage():
    """When assessed value is absent, value basis × assessment ratio × millage computes tax."""
    results = [
        _om_result(
            property_tax_value_basis_amount=2_500_000.0,
            property_tax_assessment_ratio=0.11,
            property_tax_millage_rate=111.61,
            expense_property_tax_annual_year1=None,
            expense_property_tax_annual_current=6139.0,
        )
    ]
    merged, citations = merge_extractions(results)
    expected = 2_500_000.0 * 0.11 * (111.61 / 1000.0)
    assert merged["operational"]["property_tax_annual"] == pytest.approx(expected)
    assert citations["property_tax_annual"]["doc_type"] == "derived"
    assert "$2,500,000 value basis" in citations["property_tax_annual"]["formula"]
    assert "11.00% assessment ratio" in citations["property_tax_annual"]["formula"]
    assert "111.61 mills / 1,000" in citations["property_tax_annual"]["formula"]


def test_property_tax_millage_and_rate_per_assessed_dollar_are_equivalent():
    """111.61 mills and $0.11161 per assessed dollar normalize to the same tax rate."""
    rate_results = [
        _om_result(
            property_tax_assessed_value=275_000.0,
            property_tax_rate_per_assessed_dollar=0.11161,
            expense_property_tax_annual_year1=None,
        )
    ]
    millage_results = [
        _om_result(
            property_tax_assessed_value=275_000.0,
            property_tax_millage_rate=111.61,
            expense_property_tax_annual_year1=None,
        )
    ]
    rate_merged, _ = merge_extractions(rate_results)
    millage_merged, _ = merge_extractions(millage_results)
    assert rate_merged["operational"]["property_tax_annual"] == pytest.approx(
        millage_merged["operational"]["property_tax_annual"]
    )


def test_property_tax_does_not_compute_from_purchase_price_alone():
    """Purchase price is not automatically used as tax basis without explicit source mechanics."""
    results = [
        _om_result(
            purchase_price=2_500_000.0,
            property_tax_rate_per_assessed_dollar=0.11161,
            expense_property_tax_annual_year1=None,
            expense_property_tax_annual_current=6139.0,
        )
    ]
    merged, citations = merge_extractions(results)
    assert merged["operational"]["property_tax_annual"] == pytest.approx(6139.0)
    assert citations["property_tax_annual"]["doc_type"] == "om"


def test_property_tax_falls_back_to_current_when_explicit_mechanics_incomplete():
    """Without Year-1 or enough mechanics, falls back to current assessed."""
    results = [
        _om_result(
            expense_property_tax_annual_year1=None,
            expense_property_tax_annual_current=6139.0,
            property_tax_value_basis_amount=2_500_000.0,
            property_tax_assessment_ratio=None,
            property_tax_millage_rate=111.61,
        )
    ]
    merged, _ = merge_extractions(results)
    assert merged["operational"]["property_tax_annual"] == pytest.approx(6139.0)


# ── Year-1 preferred over current for other expenses ──────────────────────

def test_insurance_prefers_year1_over_current():
    results = [
        _om_result(
            rentable_sqft=21017.0,
            expense_insurance_annual_year1=11840.0,
            expense_insurance_annual_current=9867.0,
        )
    ]
    merged, citations = merge_extractions(results)
    assert merged["operational"]["insurance_annual"] == pytest.approx(11840.0)
    assert citations["insurance_annual"]["doc_type"] == "om"


def test_repairs_prefers_year1_over_current():
    results = [
        _om_result(
            rentable_sqft=21017.0,
            expense_repairs_maintenance_annual_year1=2102.0,
            expense_repairs_maintenance_annual_current=1424.0,
        )
    ]
    merged, _ = merge_extractions(results)
    assert merged["operational"]["repairs_maintenance_annual"] == pytest.approx(2102.0)


def test_marketing_prefers_year1_over_current():
    results = [
        _om_result(
            expense_marketing_annual_year1=4203.0,
            expense_marketing_annual_current=3847.0,
        )
    ]
    merged, _ = merge_extractions(results)
    assert merged["operational"]["marketing_annual"] == pytest.approx(4203.0)


def test_utilities_prefers_year1_over_current():
    results = [
        _om_result(
            rentable_sqft=21017.0,
            expense_utilities_annual_year1=6868.0,
            expense_utilities_annual_current=8080.0,
        )
    ]
    merged, _ = merge_extractions(results)
    assert merged["operational"]["utilities_annual"] == pytest.approx(6868.0)


# ── Benchmark floors ────────────────────────────────────────────────────────

def test_repairs_benchmark_floor_applied_when_below():
    """Repairs below $0.10/sqft floor are raised to the floor."""
    results = [
        _om_result(
            rentable_sqft=21017.0,
            expense_repairs_maintenance_annual_year1=1424.0,
            expense_repairs_maintenance_annual_current=1424.0,
        )
    ]
    merged, citations = merge_extractions(results)
    expected_floor = 21017.0 * 0.10
    assert merged["operational"]["repairs_maintenance_annual"] == pytest.approx(expected_floor, rel=1e-4)
    assert citations["repairs_maintenance_annual"]["doc_type"] == "benchmark"
    assert citations["repairs_maintenance_annual"]["original_value"] == pytest.approx(1424.0)


def test_repairs_benchmark_floor_not_applied_when_above():
    """Repairs above the floor are passed through unchanged."""
    results = [
        _om_result(
            rentable_sqft=21017.0,
            expense_repairs_maintenance_annual_year1=3000.0,
        )
    ]
    merged, citations = merge_extractions(results)
    assert merged["operational"]["repairs_maintenance_annual"] == pytest.approx(3000.0)
    assert citations["repairs_maintenance_annual"]["doc_type"] == "om"


def test_insurance_benchmark_floor_applied_when_below():
    """Insurance below $0.35/sqft floor is raised."""
    results = [
        _om_result(
            rentable_sqft=21017.0,
            expense_insurance_annual_year1=5000.0,  # below floor of 21017 * 0.35 = 7355.95
        )
    ]
    merged, citations = merge_extractions(results)
    expected_floor = 21017.0 * 0.35
    assert merged["operational"]["insurance_annual"] == pytest.approx(expected_floor, rel=1e-4)
    assert citations["insurance_annual"]["doc_type"] == "benchmark"


def test_t12_expenses_bypass_benchmark_floor():
    """T-12 actuals are trusted as-is — benchmark floor is not applied."""
    results = [
        _om_result(rentable_sqft=21017.0),
        _t12_result(repairs_maintenance_annual=500.0),  # well below floor
    ]
    merged, citations = merge_extractions(results)
    assert merged["operational"]["repairs_maintenance_annual"] == pytest.approx(500.0)
    assert citations["repairs_maintenance_annual"]["doc_type"] == "t12"
