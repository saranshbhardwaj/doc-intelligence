"""Unit tests for the underwriting calculator."""
import copy
import math

import pytest
from app.verticals.real_estate.underwriting.calculator import calculate, calculate_sensitivity
from app.verticals.real_estate.underwriting import calculator as calc_module
from app.verticals.real_estate.underwriting.verdict import evaluate
from app.verticals.real_estate.underwriting.schemas.self_storage import (
    SelfStorageInputs,
    ProjectDetails,
    AcquisitionInputs,
    OperationalInputs,
    FinancingInputs,
    ExitInputs,
    InvestmentCriteria,
    RentCompRow,
    RentPositionRow,
    UnitMixRow,
)


# Shared valid inputs fixture
VALID_INPUTS = SelfStorageInputs(
    project=ProjectDetails(name="Test Storage", asset_type="self_storage"),
    acquisition=AcquisitionInputs(purchase_price=5_000_000, closing_cost_pct=0.02),
    operational=OperationalInputs(
        gross_potential_rent_annual=600_000,
        vacancy_credit_loss_pct=0.10,
        mgmt_fee_pct=0.08,
        property_tax_annual=30_000,
        insurance_annual=20_000,
        payroll_annual=50_000,
        repairs_maintenance_annual=40_000,
        utilities_annual=30_000,
        marketing_annual=5_000,
        other_opex_annual=10_000,
        rent_growth_pct=0.03,
        opex_growth_pct=0.02,
    ),
    financing=FinancingInputs(
        ltv_pct=0.70,
        interest_rate_pct=0.065,
        amortization_years=25,
        loan_term_years=10,
    ),
    exit=ExitInputs(
        hold_period_years=10,
        exit_cap_rate=0.065,
        selling_cost_pct=0.03,
    ),
    criteria=InvestmentCriteria(
        target_irr=0.15,
        target_cash_on_cash=0.08,
        target_equity_multiple=2.0,
        max_ltv=0.80,
    ),
)


class TestCalculatorHappyPath:
    """Happy path: typical underwriting scenario."""

    def test_calculate_returns_all_metrics(self):
        """Valid inputs → all 10 metrics populated, 10 projections."""
        result = calculate(VALID_INPUTS)

        # Check all metrics are non-None
        assert result.irr is not None
        assert result.cash_on_cash is not None
        assert result.equity_multiple is not None
        assert result.dscr_year_one is not None
        assert result.ltv is not None
        assert result.cap_rate_year_one is not None
        assert result.noi_year_one is not None
        assert result.monthly_cashflow is not None

        # Check capital structure
        assert result.capital_structure is not None
        assert result.capital_structure.purchase_price == 5_000_000
        assert result.capital_structure.loan_amount == 3_500_000  # 70% LTV
        assert result.capital_structure.down_payment == pytest.approx(1_500_000)

        # Check projections
        assert len(result.projections) == 10
        assert all(p.noi > 0 for p in result.projections)

        # Verify NOI = GPR - vacancy - opex (approx)
        year_1 = result.projections[0]
        expected_noi = year_1.egi - year_1.opex
        assert abs(year_1.noi - expected_noi) < 1  # Floating point tolerance

    def test_return_tooltip_metadata_explains_irr_and_cash_on_cash_bridges(self):
        result = calculate(VALID_INPUTS)

        irr_meta = result.formula_metadata["irr"]
        assert "annual cash-flow schedule and exit proceeds" in irr_meta.description

        coc_meta = result.formula_metadata["cash_on_cash"]
        assert coc_meta.computed_values.year1_noi == pytest.approx(result.projections[0].noi)
        assert coc_meta.computed_values.year1_cash_flow == pytest.approx(result.projections[0].cash_flow)
        assert coc_meta.computed_values.total_equity == pytest.approx(result.capital_structure.total_equity_invested)

    def test_projections_grow_by_rent_growth_pct(self):
        """Year-over-year GPR growth matches rent_growth_pct."""
        result = calculate(VALID_INPUTS)

        year_1_gpr = result.projections[0].gpr
        year_2_gpr = result.projections[1].gpr

        growth_rate = year_2_gpr / year_1_gpr
        expected_growth = 1.0 + VALID_INPUTS.operational.rent_growth_pct

        assert abs(growth_rate - expected_growth) < 0.0001

    def test_property_tax_growth_can_outpace_other_opex(self):
        baseline_inputs = VALID_INPUTS.model_copy(deep=True)
        baseline = calculate(baseline_inputs)

        taxed_inputs = VALID_INPUTS.model_copy(deep=True)
        taxed_inputs.operational.property_tax_growth_pct = 0.10
        taxed = calculate(taxed_inputs)

        year_two_opex_delta = taxed.projections[1].opex - baseline.projections[1].opex
        assert year_two_opex_delta == pytest.approx(2_400.0)

    def test_break_even_occupancy_is_calculated_for_levered_deal(self):
        result = calculate(VALID_INPUTS)
        fixed_opex = (
            VALID_INPUTS.operational.property_tax_annual
            + VALID_INPUTS.operational.insurance_annual
            + VALID_INPUTS.operational.payroll_annual
            + VALID_INPUTS.operational.repairs_maintenance_annual
            + VALID_INPUTS.operational.utilities_annual
            + VALID_INPUTS.operational.marketing_annual
            + VALID_INPUTS.operational.other_opex_annual
        )
        expected_break_even = (
            ((result.projections[0].debt_service + fixed_opex) / (1.0 - VALID_INPUTS.operational.mgmt_fee_pct))
            - VALID_INPUTS.operational.other_income_annual
        ) / VALID_INPUTS.operational.gross_potential_rent_annual

        assert result.break_even_occupancy_pct is not None
        assert result.break_even_occupancy_pct == pytest.approx(expected_break_even)

    def test_uses_expense_ratio_when_line_items_are_missing(self):
        """Expense ratio fallback prevents overstated NOI when line items are absent."""
        inputs = VALID_INPUTS.model_copy(deep=True)
        inputs.operational.property_tax_annual = 0
        inputs.operational.insurance_annual = 0
        inputs.operational.payroll_annual = 0
        inputs.operational.repairs_maintenance_annual = 0
        inputs.operational.utilities_annual = 0
        inputs.operational.marketing_annual = 0
        inputs.operational.other_opex_annual = 0
        inputs.operational.mgmt_fee_pct = 0
        inputs.operational.expense_ratio_t12 = 0.40
        inputs.operational.operating_statement_period = "t12"

        result = calculate(inputs)

        year_one = result.projections[0]
        assert result.expense_basis.source == "t12_expense_ratio"
        assert result.expense_basis.period == "t12"
        assert result.expense_basis.method == "expense_ratio"
        assert result.expense_basis.expense_ratio == pytest.approx(0.40)
        assert year_one.egi == pytest.approx(540_000)
        assert year_one.opex == pytest.approx(216_000)
        assert year_one.noi == pytest.approx(324_000)

    def test_ratio_fallback_respects_selected_operating_period(self):
        """When OM Year 1 is selected, ratio fallback uses Year 1 before other evidence."""
        inputs = VALID_INPUTS.model_copy(deep=True)
        inputs.operational.property_tax_annual = 0
        inputs.operational.insurance_annual = 0
        inputs.operational.payroll_annual = 0
        inputs.operational.repairs_maintenance_annual = 0
        inputs.operational.utilities_annual = 0
        inputs.operational.marketing_annual = 0
        inputs.operational.other_opex_annual = 0
        inputs.operational.mgmt_fee_pct = 0
        inputs.operational.expense_ratio_t12 = 0.40
        inputs.operational.expense_ratio_current = 0.35
        inputs.operational.expense_ratio_year1 = 0.30
        inputs.operational.expense_ratio_pro_forma = 0.25
        inputs.operational.operating_statement_period = "year1"

        result = calculate(inputs)

        year_one = result.projections[0]
        assert result.expense_basis.source == "om_year1_expense_ratio"
        assert result.expense_basis.period == "year1"
        assert result.expense_basis.method == "expense_ratio"
        assert result.expense_basis.expense_ratio == pytest.approx(0.30)
        assert year_one.egi == pytest.approx(540_000)
        assert year_one.opex == pytest.approx(162_000)
        assert year_one.noi == pytest.approx(378_000)

    def test_missing_property_tax_does_not_block_ratio_basis(self):
        """Missing property tax should not fail validation when ratio support exists."""
        inputs_data = VALID_INPUTS.model_dump()
        inputs_data["operational"]["property_tax_annual"] = None
        inputs_data["operational"]["expense_ratio_year1"] = 0.30
        inputs_data["operational"]["operating_statement_period"] = "year1"
        for field in (
            "insurance_annual",
            "payroll_annual",
            "repairs_maintenance_annual",
            "utilities_annual",
            "marketing_annual",
            "other_opex_annual",
        ):
            inputs_data["operational"][field] = 0
        inputs_data["operational"]["mgmt_fee_pct"] = 0

        inputs = SelfStorageInputs(**inputs_data)
        result = calculate(inputs)

        assert result.expense_basis.source == "om_year1_expense_ratio"
        assert result.expense_basis.method == "expense_ratio"
        assert result.projections[0].opex == pytest.approx(162_000)

    def test_mixed_line_items_prefer_coherent_ratio_basis(self):
        """Mixed-period line items should yield to a coherent expense ratio."""
        inputs = VALID_INPUTS.model_copy(deep=True)
        inputs.operational.expense_ratio_year1 = 0.30
        inputs.operational.operating_statement_period = "mixed"
        inputs.operational.operating_statement_warnings = [
            "Year 1 operating basis uses Current fallback for: property tax."
        ]

        result = calculate(inputs)

        assert result.expense_basis.source == "om_year1_expense_ratio"
        assert result.expense_basis.period == "year1"
        assert result.expense_basis.method == "expense_ratio"
        assert result.expense_basis.modeled_total_expenses == pytest.approx(162_000)
        assert result.expense_basis.year1_line_item_opex == pytest.approx(228_200)
        assert result.expense_basis.warnings == [
            "Year 1 operating basis uses Current fallback for: property tax."
        ]

    def test_mixed_period_ratio_basis_emits_senior_analyst_metadata(self):
        inputs = VALID_INPUTS.model_copy(deep=True)
        inputs.operational.expense_ratio_year1 = 0.2847
        inputs.operational.expense_ratio_pro_forma = 0.2778
        inputs.operational.operating_statement_period = "year1"
        inputs.operational.operating_statement_warnings = ["Property tax uses Current fallback."]

        result = calculate(inputs)

        assert result.expense_basis.source == "om_year1_expense_ratio"
        assert result.expense_basis.period == "year1"
        assert result.expense_basis.method == "expense_ratio"
        assert result.expense_basis.modeled_egi == pytest.approx(result.projections[0].egi)
        assert result.expense_basis.modeled_total_expenses == pytest.approx(result.projections[0].opex)
        assert result.expense_basis.modeled_noi == pytest.approx(result.projections[0].noi)
        assert result.expense_basis.expense_ratio == pytest.approx(0.2847)
        assert "expense_ratio_year1" in result.expense_basis.driver_fields
        assert "property_tax_annual" in result.expense_basis.inactive_fields
        assert result.expense_basis.warnings == ["Property tax uses Current fallback."]

    def test_rent_position_analysis_matches_unit_mix_to_comps(self):
        inputs = VALID_INPUTS.model_copy(deep=True)
        inputs.unit_mix = [
            UnitMixRow(section="NON-CLIMATE", size="10 x 10", standard_sqft=100.0, climate_type="NC", current_rent=110.0, market_rent=120.0, num_units=50, unit_category="storage"),
            UnitMixRow(section="CLIMATE CONTROL", size="10 x 10", standard_sqft=100.0, climate_type="CC", current_rent=140.0, market_rent=150.0, num_units=20, unit_category="storage"),
            UnitMixRow(section="UNCOVERED PARKING", size="10 x 20", current_rent=45.0, num_units=10, unit_category="parking"),
        ]
        inputs.rent_comps = [
            RentCompRow(size="10x10", standard_sqft=100.0, climate_type="NC", asking_rent=100.0),
            RentCompRow(size="10 X 10", standard_sqft=100.0, climate_type="NC", asking_rent=120.0),
            RentCompRow(size="10x10", standard_sqft=100.0, climate_type="CC", asking_rent=160.0),
        ]

        result = calculate(inputs)

        assert len(result.rent_position_analysis) == 2
        nc_row = next(row for row in result.rent_position_analysis if row.climate_type == "NC")
        cc_row = next(row for row in result.rent_position_analysis if row.climate_type == "CC")
        assert nc_row.comp_average_rent == pytest.approx(110.0)
        assert nc_row.comp_count == 2
        assert nc_row.current_vs_comp_ratio == pytest.approx(110.0 / 110.0)
        assert nc_row.market_vs_comp_ratio == pytest.approx(120.0 / 110.0)
        assert cc_row.comp_average_rent == pytest.approx(160.0)
        assert cc_row.comp_count == 1
        assert cc_row.current_vs_comp_ratio == pytest.approx(140.0 / 160.0)


class TestCalculatorEdgeCases:
    """Edge cases: zero debt, zero equity, zero exit cap, None fields."""

    def test_zero_ltv_no_debt(self):
        """LTV = 0 → no debt service, dscr_year_one = None."""
        inputs = VALID_INPUTS.model_copy(deep=True)
        inputs.financing.ltv_pct = 0.0

        result = calculate(inputs)

        assert result.capital_structure.loan_amount == 0
        assert result.dscr_year_one is None  # No debt service to cover
        assert result.capital_structure.total_equity_invested > 0

    def test_num_units_none_capex_defaults_to_zero(self):
        """num_units=None → capex_reserve=0 (no crash)."""
        inputs = VALID_INPUTS.model_copy(deep=True)
        inputs.project.num_units = None
        inputs.acquisition.capex_reserve_per_unit = 100

        result = calculate(inputs)

        assert result.capital_structure.capex_reserve_initial == 0
        # Should not crash

    def test_exit_cap_rate_zero_raises(self):
        """exit_cap_rate=0 → ValueError with a clear message."""
        inputs = VALID_INPUTS.model_copy(deep=True)
        inputs.exit.exit_cap_rate = 0.0

        with pytest.raises(ValueError, match="exit_cap_rate must be > 0"):
            calculate(inputs)

    def test_missing_purchase_price_raises(self):
        """purchase_price=None must fail instead of producing a $0 underwriting."""
        inputs = VALID_INPUTS.model_copy(deep=True)
        inputs.acquisition.purchase_price = None

        with pytest.raises(ValueError, match="purchase_price required and must be > 0"):
            calculate(inputs)

    def test_zero_purchase_price_raises(self):
        """purchase_price=0 must fail before capital-stack math."""
        inputs = VALID_INPUTS.model_copy(deep=True)
        inputs.acquisition.purchase_price = 0

        with pytest.raises(ValueError, match="purchase_price required and must be > 0"):
            calculate(inputs)

    def test_very_small_equity_invested(self):
        """Very small equity → shouldn't crash, ratios still computed."""
        inputs = VALID_INPUTS.model_copy(deep=True)
        inputs.financing.ltv_pct = 0.99  # Only 1% equity

        result = calculate(inputs)

        # May have extreme metrics, but no crash
        assert result.cash_on_cash is not None or result.equity_multiple is not None

    def test_calculate_sensitivity(self):
        """calculate_sensitivity() returns list of SensitivityPoints."""
        prices = [4_000_000, 5_000_000, 6_000_000]
        sensitivity = calculate_sensitivity(VALID_INPUTS, prices)

        assert len(sensitivity) == 3
        assert all(p.irr is not None for p in sensitivity)
        assert all(p.dscr_year_one is not None for p in sensitivity)

        # Lower purchase price → higher IRR
        assert sensitivity[0].irr > sensitivity[2].irr


class TestSchemaNewFields:
    """Test new fields added to RentCompRow and RentPositionRow."""

    def test_rent_comp_row_has_climate_type(self):
        row = RentCompRow(size="5x10", asking_rent=85.0, climate_type="CC")
        assert row.climate_type == "CC"

    def test_rent_comp_row_climate_type_defaults_none(self):
        row = RentCompRow(size="5x10", asking_rent=85.0)
        assert row.climate_type is None

    def test_rent_comp_row_has_standard_sqft(self):
        row = RentCompRow(size="5x10", asking_rent=85.0, standard_sqft=50.0)
        assert row.standard_sqft == 50.0

    def test_rent_position_row_has_bucket(self):
        row = RentPositionRow(
            size="5x10", climate_type="CC", comp_average_rent=90.0,
            comp_count=2, bucket="small"
        )
        assert row.bucket == "small"

    def test_rent_comp_row_standard_sqft_defaults_none(self):
        row = RentCompRow(size="5x10", asking_rent=85.0)
        assert row.standard_sqft is None

    def test_rent_position_row_bucket_defaults_none(self):
        row = RentPositionRow(
            size="5x10", climate_type="CC", comp_average_rent=90.0, comp_count=2
        )
        assert row.bucket is None



class TestSizeBucketUtilities:
    def test_parse_standard_sqft_dimension_string(self):
        assert calc_module._parse_standard_sqft("5x10") == pytest.approx(50.0)
        assert calc_module._parse_standard_sqft("10x20") == pytest.approx(200.0)
        assert calc_module._parse_standard_sqft("5 x 10") == pytest.approx(50.0)
        assert calc_module._parse_standard_sqft("5×10") == pytest.approx(50.0)

    def test_parse_standard_sqft_plain_number(self):
        assert calc_module._parse_standard_sqft("200") == pytest.approx(200.0)
        assert calc_module._parse_standard_sqft("200 sqft") == pytest.approx(200.0)

    def test_parse_standard_sqft_none_on_garbage(self):
        assert calc_module._parse_standard_sqft(None) is None
        assert calc_module._parse_standard_sqft("") is None
        assert calc_module._parse_standard_sqft("various") is None

    def test_parse_standard_sqft_ignores_trailing_text(self):
        # Should NOT match — trailing text after dimensions
        assert calc_module._parse_standard_sqft("5x10 (climate)") is None
        assert calc_module._parse_standard_sqft("5x10 ft2") is None

    def test_size_bucket_boundaries(self):
        assert calc_module._size_bucket(10) == "locker"
        assert calc_module._size_bucket(24.9) == "locker"
        assert calc_module._size_bucket(25) == "small"
        assert calc_module._size_bucket(50) == "small"
        assert calc_module._size_bucket(74.9) == "small"
        assert calc_module._size_bucket(75) == "medium"
        assert calc_module._size_bucket(100) == "medium"
        assert calc_module._size_bucket(149.9) == "medium"
        assert calc_module._size_bucket(150) == "large"
        assert calc_module._size_bucket(200) == "large"
        assert calc_module._size_bucket(299.9) == "large"
        assert calc_module._size_bucket(300) == "xlarge"
        assert calc_module._size_bucket(500) == "xlarge"


class TestRentPositionBucketMatching:
    def _make_unit_row(self, size, sqft, climate, current_rent, market_rent=None):
        from app.verticals.real_estate.underwriting.schemas.self_storage import UnitMixRow
        return UnitMixRow(
            size=size, standard_sqft=sqft, climate_type=climate,
            current_rent=current_rent, market_rent=market_rent,
            num_units=10, unit_category="storage",
        )

    def _make_comp_row(self, size, sqft, climate, asking_rent):
        from app.verticals.real_estate.underwriting.schemas.self_storage import RentCompRow
        return RentCompRow(
            size=size, standard_sqft=sqft, climate_type=climate, asking_rent=asking_rent,
        )

    def test_matching_by_bucket_and_climate(self):
        unit_mix = [self._make_unit_row("5x10", 50, "CC", 95.0)]
        comps = [
            self._make_comp_row("5x10", 50, "CC", 90.0),
            self._make_comp_row("5x10", 50, "CC", 100.0),
            self._make_comp_row("5x10", 50, "NC", 70.0),  # different climate — should not match
        ]
        result, _ = calc_module._build_rent_position_analysis(unit_mix, comps)
        assert len(result) == 1
        assert result[0].climate_type == "CC"
        assert result[0].comp_count == 2
        assert result[0].comp_average_rent == pytest.approx(95.0)
        assert result[0].bucket == "small"

    def test_no_comp_match_returns_no_row(self):
        unit_mix = [self._make_unit_row("10x20", 200, "CC", 150.0)]
        comps = [self._make_comp_row("5x10", 50, "CC", 90.0)]
        result, _ = calc_module._build_rent_position_analysis(unit_mix, comps)
        assert result == []

    def test_cc_and_nc_rows_matched_separately(self):
        unit_mix = [
            self._make_unit_row("5x10", 50, "CC", 95.0),
            self._make_unit_row("5x10", 50, "NC", 65.0),
        ]
        comps = [
            self._make_comp_row("5x10", 50, "CC", 90.0),
            self._make_comp_row("5x10", 50, "NC", 70.0),
        ]
        result, _ = calc_module._build_rent_position_analysis(unit_mix, comps)
        cc = next(r for r in result if r.climate_type == "CC")
        nc = next(r for r in result if r.climate_type == "NC")
        assert cc.comp_count == 1
        assert nc.comp_count == 1
        assert cc.comp_average_rent == pytest.approx(90.0)
        assert nc.comp_average_rent == pytest.approx(70.0)

    def test_different_size_labels_same_bucket_match(self):
        """5x10 and 50sqft both map to 'small' bucket — should match."""
        unit_mix = [self._make_unit_row("5x10", 50, "CC", 95.0)]
        comps = [self._make_comp_row("50 sqft", 50, "CC", 88.0)]
        result, _ = calc_module._build_rent_position_analysis(unit_mix, comps)
        assert len(result) == 1
        assert result[0].bucket == "small"

    def test_weighted_avg_across_same_bucket_cell(self):
        """Two NC rows in the same bucket use num_units-weighted avg, not first-match."""
        from app.verticals.real_estate.underwriting.schemas.self_storage import UnitMixRow, RentCompRow
        unit_mix = [
            UnitMixRow(size="5x5", standard_sqft=25.0, climate_type="NC", current_rent=50.0, num_units=10, unit_category="storage"),
            UnitMixRow(size="5x10", standard_sqft=50.0, climate_type="NC", current_rent=80.0, num_units=30, unit_category="storage"),
        ]
        comps = [RentCompRow(size="5x10", standard_sqft=50.0, climate_type="NC", asking_rent=70.0)]
        result, _ = calc_module._build_rent_position_analysis(unit_mix, comps)
        assert len(result) == 1
        # weighted avg: (50*10 + 80*30) / (10+30) = (500 + 2400) / 40 = 72.5
        assert result[0].subject_current_rent == pytest.approx(72.5)

    def test_unknown_comp_climate_count(self):
        """UNKNOWN climate comps are excluded and counted."""
        from app.verticals.real_estate.underwriting.schemas.self_storage import UnitMixRow, RentCompRow
        unit_mix = [
            UnitMixRow(size="5x10", standard_sqft=50.0, climate_type="NC", current_rent=80.0, num_units=10, unit_category="storage"),
        ]
        comps = [
            RentCompRow(size="5x10", standard_sqft=50.0, climate_type="NC", asking_rent=70.0),
            RentCompRow(size="5x10", standard_sqft=50.0, climate_type="UNKNOWN", asking_rent=65.0),
            RentCompRow(size="5x10", standard_sqft=50.0, climate_type=None, asking_rent=60.0),
        ]
        result, unknown_count = calc_module._build_rent_position_analysis(unit_mix, comps)
        assert unknown_count == 2
        assert len(result) == 1
        assert result[0].comp_count == 1  # only the NC comp matched


class TestOMNOIMode:
    """OM-only quick screen: stated NOI drives projections when detail is missing."""

    OM_NOI_INPUTS = SelfStorageInputs(
        project=ProjectDetails(name="Lone Star Storage", asset_type="self_storage", num_units=400),
        acquisition=AcquisitionInputs(purchase_price=8_000_000, closing_cost_pct=0.02),
        operational=OperationalInputs(
            gross_potential_rent_annual=0.0,
            noi_current_stated=663_830.0,
            rent_growth_pct=0.03,
            opex_growth_pct=0.02,
        ),
        financing=FinancingInputs(
            ltv_pct=0.70,
            interest_rate_pct=0.065,
            amortization_years=25,
            loan_term_years=10,
        ),
        exit=ExitInputs(hold_period_years=5, exit_cap_rate=0.065, selling_cost_pct=0.03),
        criteria=InvestmentCriteria(
            target_irr=0.15,
            target_cash_on_cash=0.08,
            target_equity_multiple=2.0,
            max_ltv=0.80,
        ),
    )

    def test_om_noi_mode_activates_when_detail_missing_and_noi_stated(self):
        result = calculate(self.OM_NOI_INPUTS)

        assert result.expense_basis.source == "om_noi"

    def test_om_noi_year1_noi_equals_stated_noi(self):
        result = calculate(self.OM_NOI_INPUTS)

        assert result.noi_year_one == pytest.approx(663_830.0, rel=1e-4)

    def test_om_noi_projects_with_rent_growth(self):
        result = calculate(self.OM_NOI_INPUTS)

        assert result.projections[1].noi == pytest.approx(663_830.0 * 1.03, rel=1e-4)

    def test_om_noi_does_not_backsolve_revenue_or_expenses(self):
        result = calculate(self.OM_NOI_INPUTS)
        year_one = result.projections[0]

        assert year_one.gpr == 0.0
        assert year_one.vacancy_loss == 0.0
        assert year_one.opex == 0.0
        assert result.break_even_occupancy_pct is None

    def test_om_noi_mode_not_triggered_when_gpr_and_expenses_present(self):
        inputs = self.OM_NOI_INPUTS.model_copy(deep=True)
        inputs.operational.gross_potential_rent_annual = 600_000.0
        inputs.operational.property_tax_annual = 60_000.0
        inputs.operational.insurance_annual = 20_000.0

        result = calculate(inputs)

        assert result.expense_basis.source == "om_year1_line_items"

    def test_om_noi_mode_wins_when_expenses_exist_but_revenue_missing(self):
        inputs = self.OM_NOI_INPUTS.model_copy(deep=True)
        inputs.operational.property_tax_annual = 60_000.0
        inputs.operational.insurance_annual = 20_000.0

        result = calculate(inputs)

        assert result.expense_basis.source == "om_noi"
        assert result.noi_year_one == pytest.approx(663_830.0, rel=1e-4)

    def test_om_noi_prefers_noi_year_one_stated_over_noi_current_stated(self):
        inputs = self.OM_NOI_INPUTS.model_copy(deep=True)
        inputs.operational.noi_year_one_stated = 700_000.0
        inputs.operational.noi_current_stated = 663_830.0

        result = calculate(inputs)

        assert result.noi_year_one == pytest.approx(700_000.0, rel=1e-4)

    def test_t12_expense_ratio_with_zero_gpr_does_not_trigger_om_noi(self):
        """T-12 expense ratio present but EGI=0 must NOT silently downgrade to om_noi.

        When a T-12 is uploaded and supplies expense_ratio_current but the OM has no
        GPR projection, ratio_opex cannot be computed (EGI=0). The fallback must land
        on 'missing' — not 'om_noi' — so the analyst knows to supply a GPR figure
        rather than silently receiving a quick screen backed by no real data.
        """
        inputs = self.OM_NOI_INPUTS.model_copy(deep=True)
        inputs.operational.expense_ratio_t12 = 0.40  # T-12 supplied this
        inputs.operational.operating_statement_period = "t12"

        result = calculate(inputs)

        assert result.expense_basis.source != "om_noi"
        assert result.expense_basis.source == "missing"

    def test_stated_om_noi_zero_does_not_fall_through_to_current(self):
        """noi_year_one_stated=0.0 is an explicit value and must not fall through to noi_current_stated."""
        inputs = self.OM_NOI_INPUTS.model_copy(deep=True)
        inputs.operational.noi_year_one_stated = 0.0
        inputs.operational.noi_current_stated = 663_830.0
        inputs.operational.gross_potential_rent_annual = 0.0

        # noi_year_one_stated=0.0 is falsy so om_noi won't activate;
        # the important thing is 0.0 is treated as "explicitly set to zero"
        # and does NOT fall through to noi_current_stated.
        from app.verticals.real_estate.underwriting import calculator as calc_module
        result_noi = calc_module._stated_om_noi(inputs)
        assert result_noi == 0.0  # returned 0.0, not 663_830


@pytest.fixture
def base_inputs():
    return VALID_INPUTS.model_copy(deep=True)


class TestDebtYield:
    def test_debt_yield_computed(self, base_inputs):
        """debt_yield = NOI_Y1 / loan_amount"""
        result = calculate(base_inputs)
        assert result.debt_yield is not None
        # Compute the loan amount independently from raw inputs (not from result)
        expected_loan = base_inputs.acquisition.purchase_price * base_inputs.financing.ltv_pct
        # Verify the formula holds: debt_yield == noi / loan (formula check, not value tautology)
        assert result.debt_yield == pytest.approx(result.projections[0].noi / expected_loan, abs=1e-6)
        # Sanity-check the result is in a plausible range for a real self-storage deal
        assert 0.04 < result.debt_yield < 0.30, "Debt yield outside plausible range for self-storage"
        assert math.isfinite(result.debt_yield)

    def test_debt_yield_none_when_no_loan(self, base_inputs):
        """Zero LTV → no loan → debt_yield is None"""
        base_inputs.financing.ltv_pct = 0.0
        result = calculate(base_inputs)
        assert result.debt_yield is None

    def test_sensitivity_point_includes_debt_yield(self, base_inputs):
        """Every sensitivity point has a debt_yield field"""
        prices = [4_000_000, 5_000_000, 6_000_000]
        sensitivity = calculate_sensitivity(base_inputs, prices)
        assert len(sensitivity) > 0
        for pt in sensitivity:
            assert hasattr(pt, "debt_yield")


class TestDebtYieldVerdict:
    def test_critical_below_7pct(self, base_inputs):
        """Debt yield < 7% → critical warning"""
        result = calculate(base_inputs)
        result = result.model_copy(update={"debt_yield": 0.065})
        verdict = evaluate(result, base_inputs.criteria)
        keys = [w.key for w in verdict.warnings]
        assert "debt_yield_critical" in keys

    def test_warning_7_to_8pct(self, base_inputs):
        """Debt yield 7–8% → warning"""
        result = calculate(base_inputs)
        result = result.model_copy(update={"debt_yield": 0.075})
        verdict = evaluate(result, base_inputs.criteria)
        keys = [w.key for w in verdict.warnings]
        assert "debt_yield_watch" in keys

    def test_no_warning_above_8pct(self, base_inputs):
        """Debt yield ≥ 8% → no debt yield warning"""
        result = calculate(base_inputs)
        result = result.model_copy(update={"debt_yield": 0.09})
        verdict = evaluate(result, base_inputs.criteria)
        keys = [w.key for w in verdict.warnings]
        assert "debt_yield_critical" not in keys
        assert "debt_yield_watch" not in keys

    def test_critical_triggers_needs_review(self, base_inputs):
        """debt_yield_critical → overall status degrades to needs_review"""
        result = calculate(base_inputs)
        result = result.model_copy(update={"debt_yield": 0.065})
        verdict = evaluate(result, base_inputs.criteria)
        assert verdict.status in ("needs_review", "fail", "below_standards")


from pydantic import ValidationError as PydanticValidationError
from app.verticals.real_estate.underwriting.extraction.tasks.tasks import (
    _describe_validation_error,
)


def _make_validation_error(missing_fields: list[tuple[str, ...]]) -> PydanticValidationError:
    """Build a real ValidationError by constructing SelfStorageInputs with bad data."""
    from app.verticals.real_estate.underwriting.schemas.self_storage import (
        SelfStorageInputs,
        ProjectDetails,
        AcquisitionInputs,
        FinancingInputs,
        ExitInputs,
        InvestmentCriteria,
    )
    import pytest
    data = {
        "project": ProjectDetails(name="T", asset_type="self_storage"),
        "acquisition": AcquisitionInputs(),
        "operational": {"gross_potential_rent_annual": None},  # forces float_type error
        "financing": FinancingInputs(),
        "exit": ExitInputs(),
        "criteria": InvestmentCriteria(),
    }
    with pytest.raises(PydanticValidationError) as exc_info:
        SelfStorageInputs(**data)
    return exc_info.value


def test_describe_validation_error_names_field():
    """Human-readable message includes the field name."""
    exc = _make_validation_error([])
    msg = _describe_validation_error(exc)
    assert "gross_potential_rent_annual" in msg


def test_describe_validation_error_is_string():
    """Always returns a non-empty string."""
    exc = _make_validation_error([])
    msg = _describe_validation_error(exc)
    assert isinstance(msg, str) and len(msg) > 0


def test_describe_validation_error_mentions_manual_entry():
    """Should guide the user toward the wizard for manual entry."""
    exc = _make_validation_error([])
    msg = _describe_validation_error(exc)
    assert "wizard" in msg.lower() or "manually" in msg.lower() or "enter" in msg.lower()


def test_describe_validation_error_multiple_fields():
    """When multiple fields are missing, all are listed."""
    from app.verticals.real_estate.underwriting.schemas.self_storage import (
        SelfStorageInputs,
        ProjectDetails,
        AcquisitionInputs,
        FinancingInputs,
        ExitInputs,
        InvestmentCriteria,
    )
    import pytest
    data = {
        "project": ProjectDetails(name="T", asset_type="self_storage"),
        "acquisition": AcquisitionInputs(),
        "operational": {
            "gross_potential_rent_annual": None,
            "vacancy_credit_loss_pct": None,
        },
        "financing": FinancingInputs(),
        "exit": ExitInputs(),
        "criteria": InvestmentCriteria(),
    }
    with pytest.raises(PydanticValidationError) as exc_info:
        SelfStorageInputs(**data)
    msg = _describe_validation_error(exc_info.value)
    assert "gross_potential_rent_annual" in msg
    assert "vacancy_credit_loss_pct" in msg


def test_re_calculate_task_validation_error_message(monkeypatch):
    """ValidationError in re_calculate_underwriting_task produces a user-friendly SSE message."""
    from unittest.mock import MagicMock, patch
    from pydantic import ValidationError as PydanticValidationError
    from app.verticals.real_estate.underwriting.extraction.tasks import tasks as task_module

    # Patch SelfStorageInputs to raise a real ValidationError
    from app.verticals.real_estate.underwriting.schemas.self_storage import (
        SelfStorageInputs,
        ProjectDetails,
        AcquisitionInputs,
        FinancingInputs,
        ExitInputs,
        InvestmentCriteria,
    )
    import pytest

    with pytest.raises(PydanticValidationError) as exc_info:
        SelfStorageInputs(
            project=ProjectDetails(name="T", asset_type="self_storage"),
            acquisition=AcquisitionInputs(),
            operational={"gross_potential_rent_annual": None},
            financing=FinancingInputs(),
            exit=ExitInputs(),
            criteria=InvestmentCriteria(),
        )
    real_exc = exc_info.value

    captured_error_message = {}

    def fake_mark_error(error_stage, error_message, internal_error="", error_type="", is_retryable=False):
        captured_error_message["error_message"] = error_message

    mock_tracker = MagicMock()
    mock_tracker.mark_error.side_effect = fake_mark_error

    mock_repo = MagicMock()
    mock_db = MagicMock()

    with (
        patch.object(task_module, "_get_db_session", return_value=mock_db),
        patch("app.verticals.real_estate.underwriting.extraction.tasks.tasks.JobProgressTracker", return_value=mock_tracker),
        patch("app.verticals.real_estate.underwriting.extraction.tasks.tasks.UnderwritingRunRepository", return_value=mock_repo),
        patch("app.verticals.real_estate.underwriting.extraction.tasks.tasks.SelfStorageInputs", side_effect=real_exc),
    ):
        with pytest.raises(PydanticValidationError):
            task_module.re_calculate_underwriting_task.run(
                {
                    "run_id": "test-run",
                    "job_id": "test-job",
                    "merged_inputs": {},
                    "doc_results": [],
                },
            )

    assert "gross_potential_rent_annual" in captured_error_message.get("error_message", "")
    assert "wizard" in captured_error_message.get("error_message", "").lower() or \
           "manually" in captured_error_message.get("error_message", "").lower() or \
           "enter" in captured_error_message.get("error_message", "").lower()
