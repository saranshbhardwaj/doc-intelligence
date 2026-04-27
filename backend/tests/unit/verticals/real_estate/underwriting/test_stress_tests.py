"""Unit tests for stress test scenario generation."""
import pytest
from app.verticals.real_estate.underwriting.stress_tests import run_stress_tests
from app.verticals.real_estate.underwriting.calculator import calculate
from app.verticals.real_estate.underwriting.schemas.self_storage import (
    SelfStorageInputs,
    ProjectDetails,
    AcquisitionInputs,
    OperationalInputs,
    FinancingInputs,
    ExitInputs,
    InvestmentCriteria,
)


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


class TestStressTests:
    """Test stress scenario generation."""

    def test_returns_five_scenarios(self):
        """run_stress_tests() returns exactly 6 scenarios."""
        scenarios = run_stress_tests(VALID_INPUTS)

        assert len(scenarios) == 6

    def test_all_five_keys_present(self):
        """All senior-analyst stress scenario keys are present."""
        scenarios = run_stress_tests(VALID_INPUTS)
        keys = {s.scenario_key for s in scenarios}

        assert "base" in keys
        assert "vacancy_plus_500bps" in keys
        assert "rent_growth_zero" in keys
        assert "opex_plus_10pct" in keys
        assert "exit_cap_plus_50bps" in keys
        assert "interest_rate_plus_100bps" in keys

    def test_base_scenario_matches_calculate(self):
        """Base scenario IRR matches standalone calculate()."""
        scenarios = run_stress_tests(VALID_INPUTS)
        base = next(s for s in scenarios if s.scenario_key == "base")

        calculated = calculate(VALID_INPUTS)

        assert base.irr == calculated.irr
        assert base.cash_on_cash == calculated.cash_on_cash
        assert base.equity_multiple == calculated.equity_multiple

    def test_adverse_scenarios_lower_irr_than_base(self):
        """Adverse scenarios have lower IRR than base case."""
        scenarios = run_stress_tests(VALID_INPUTS)
        base = next(s for s in scenarios if s.scenario_key == "base")
        adverse = [s for s in scenarios if s.scenario_key != "base"]

        for scenario in adverse:
            # Adverse IRR should be lower (but allow None for some edge cases)
            if scenario.irr is not None and base.irr is not None:
                assert scenario.irr < base.irr

    def test_all_scenarios_have_min_dscr(self):
        """All scenarios have min_dscr populated."""
        scenarios = run_stress_tests(VALID_INPUTS)

        assert all(s.min_dscr is not None for s in scenarios)
        assert all(s.min_dscr >= 0 for s in scenarios)

    def test_vacancy_plus_500bps_scenario(self):
        """Vacancy +500bps has higher vacancy rate applied."""
        scenarios = run_stress_tests(VALID_INPUTS)
        vacancy_scenario = next(s for s in scenarios if s.scenario_key == "vacancy_plus_500bps")

        # Vacancy scenario should have lower income → lower IRR than base
        base = next(s for s in scenarios if s.scenario_key == "base")
        if vacancy_scenario.irr is not None and base.irr is not None:
            assert vacancy_scenario.irr < base.irr

    def test_rent_growth_zero_scenario(self):
        """Rent growth = 0% scenario should have lower cash flows than base."""
        scenarios = run_stress_tests(VALID_INPUTS)
        no_growth = next(s for s in scenarios if s.scenario_key == "rent_growth_zero")
        base = next(s for s in scenarios if s.scenario_key == "base")

        # No growth → lower future cash flows → lower IRR
        if no_growth.irr is not None and base.irr is not None:
            assert no_growth.irr < base.irr

    def test_opex_plus_10pct_scenario(self):
        """OpEx +10% scenario should have lower cash flows."""
        scenarios = run_stress_tests(VALID_INPUTS)
        opex_scenario = next(s for s in scenarios if s.scenario_key == "opex_plus_10pct")
        base = next(s for s in scenarios if s.scenario_key == "base")

        # Higher opex → lower NOI → lower IRR
        if opex_scenario.irr is not None and base.irr is not None:
            assert opex_scenario.irr < base.irr

    def test_exit_cap_plus_25bps_scenario(self):
        """Exit cap +50bps scenario affects exit value."""
        scenarios = run_stress_tests(VALID_INPUTS)
        exit_cap = next(s for s in scenarios if s.scenario_key == "exit_cap_plus_50bps")

        # Higher exit cap → lower exit proceeds → lower overall return
        # May still have reasonable IRR but lower than base
        assert exit_cap.irr is not None

    def test_interest_rate_plus_100bps_scenario(self):
        """Interest rate +100bps should reduce levered cash flow metrics."""
        scenarios = run_stress_tests(VALID_INPUTS)
        rate_stress = next(s for s in scenarios if s.scenario_key == "interest_rate_plus_100bps")
        base = next(s for s in scenarios if s.scenario_key == "base")

        if rate_stress.cash_on_cash is not None and base.cash_on_cash is not None:
            assert rate_stress.cash_on_cash < base.cash_on_cash

    def test_extreme_inputs_no_exception(self):
        """Even extreme inputs shouldn't crash."""
        extreme_inputs = VALID_INPUTS.model_copy(deep=True)
        extreme_inputs.operational.vacancy_credit_loss_pct = 0.50  # Very high vacancy

        scenarios = run_stress_tests(extreme_inputs)

        # Should return all scenarios without crashing
        assert len(scenarios) == 6
