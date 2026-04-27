"""Unit tests for the underwriting calculator."""
import pytest
from app.verticals.real_estate.underwriting.calculator import calculate, calculate_sensitivity
from app.verticals.real_estate.underwriting.schemas.self_storage import (
    SelfStorageInputs,
    ProjectDetails,
    AcquisitionInputs,
    OperationalInputs,
    FinancingInputs,
    ExitInputs,
    InvestmentCriteria,
    RentCompRow,
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
        inputs.operational.expense_ratio_current = 0.40

        result = calculate(inputs)

        year_one = result.projections[0]
        assert result.expense_basis.source == "expense_ratio_current"
        assert year_one.egi == pytest.approx(540_000)
        assert year_one.opex == pytest.approx(216_000)
        assert year_one.noi == pytest.approx(324_000)

    def test_rent_position_analysis_matches_unit_mix_to_comps(self):
        inputs = VALID_INPUTS.model_copy(deep=True)
        inputs.unit_mix = [
            UnitMixRow(section="NON-CLIMATE", size="10 x 10", standard_sqft=100.0, current_rent=110.0, market_rent=120.0, num_units=50),
            UnitMixRow(section="CLIMATE CONTROL", size="10 x 10", standard_sqft=100.0, current_rent=140.0, market_rent=150.0, num_units=20),
            UnitMixRow(section="UNCOVERED PARKING", size="10 x 20", current_rent=45.0, num_units=10),
        ]
        inputs.rent_comps = [
            RentCompRow(size="10x10", asking_rent=100.0),
            RentCompRow(size="10 X 10", asking_rent=120.0),
            RentCompRow(size="10x10", rent_per_sqft=1.6),
        ]

        result = calculate(inputs)

        assert len(result.rent_position_analysis) == 2
        nc_row = next(row for row in result.rent_position_analysis if row.climate_type == "NC")
        cc_row = next(row for row in result.rent_position_analysis if row.climate_type == "CC")
        assert nc_row.comp_average_rent == pytest.approx(126.6666666667)
        assert nc_row.comp_count == 3
        assert nc_row.current_vs_comp_ratio == pytest.approx(110.0 / 126.6666666667)
        assert nc_row.market_vs_comp_ratio == pytest.approx(120.0 / 126.6666666667)
        assert cc_row.comp_average_rent == pytest.approx(126.6666666667)
        assert cc_row.current_vs_comp_ratio == pytest.approx(140.0 / 126.6666666667)


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
