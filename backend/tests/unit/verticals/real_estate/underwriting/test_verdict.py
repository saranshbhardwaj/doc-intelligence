"""Unit tests for the underwriting verdict engine."""
import pytest
from app.verticals.real_estate.underwriting.verdict import evaluate
from app.verticals.real_estate.underwriting.schemas.self_storage import (
    SelfStorageResult,
    InvestmentCriteria,
    CapitalStructure,
    TotalReturn,
    StressScenario,
    RolloverRisk,
    UnitMixRow,
)


@pytest.fixture
def passing_result():
    """SelfStorageResult that passes all criteria."""
    return SelfStorageResult(
        irr=0.18,
        cash_on_cash=0.10,
        equity_multiple=2.5,
        dscr_year_one=1.35,
        ltv=0.70,
        capital_structure=CapitalStructure(
            purchase_price=5_000_000,
            down_payment=1_500_000,
            loan_amount=3_500_000,
            closing_cost=100_000,
            capex_reserve_initial=0,
            total_equity_invested=1_600_000,
        ),
        total_return=TotalReturn(
            annual_cash_flows_sum=100_000,
            net_sale_price=4_000_000,
            loan_balance_at_exit=1_000_000,
            total_cash_received=4_100_000,
            total_cash_invested=-1_600_000,
            total_profit=2_500_000,
        ),
    )


@pytest.fixture
def default_criteria():
    """Standard investment criteria."""
    return InvestmentCriteria(
        target_irr=0.15,
        target_cash_on_cash=0.08,
        target_equity_multiple=2.0,
        max_ltv=0.80,
    )


class TestVerdictWorthPursuing:
    """Status: worth_pursuing when all criteria met."""

    def test_all_criteria_met(self, passing_result, default_criteria):
        """All criteria met → status='worth_pursuing', no failures."""
        verdict = evaluate(passing_result, default_criteria)

        assert verdict.status == "worth_pursuing"
        assert verdict.failures == []
        assert "All investment criteria met" in verdict.rationale


class TestVerdictSingleFailures:
    """Each metric can fail independently."""

    @pytest.mark.parametrize(
        "metric,value,target,expected_metric",
        [
            ("irr", 0.12, 0.15, "irr"),
            ("cash_on_cash", 0.06, 0.08, "cash_on_cash"),
            ("equity_multiple", 1.8, 2.0, "equity_multiple"),
            ("dscr_year_one", 1.20, 1.25, "dscr_year_one"),
            ("ltv", 0.85, 0.80, "ltv"),
        ],
    )
    def test_single_metric_failure(
        self, metric, value, target, expected_metric, passing_result, default_criteria
    ):
        """Each metric can fail independently."""
        result = passing_result.model_copy()
        setattr(result, metric, value)

        verdict = evaluate(result, default_criteria)

        assert verdict.status == "below_standards"
        assert len(verdict.failures) == 1
        assert verdict.failures[0].metric == expected_metric
        # LTV gap is positive when over limit (actual - target); all others are negative (below target)
        if expected_metric == "ltv":
            assert verdict.failures[0].gap > 0
        else:
            assert verdict.failures[0].gap < 0


class TestVerdictBoundaryConditions:
    """Test boundary conditions for pass/fail thresholds."""

    def test_dscr_exactly_at_boundary_1_25(self, passing_result, default_criteria):
        """DSCR exactly at 1.25 → passes (boundary is inclusive)."""
        result = passing_result.model_copy()
        result.dscr_year_one = 1.25

        verdict = evaluate(result, default_criteria)

        assert verdict.status == "worth_pursuing"
        assert len(verdict.failures) == 0

    def test_dscr_just_below_boundary(self, passing_result, default_criteria):
        """DSCR = 1.24 → fails."""
        result = passing_result.model_copy()
        result.dscr_year_one = 1.24

        verdict = evaluate(result, default_criteria)

        assert verdict.status == "below_standards"
        assert verdict.failures[0].metric == "dscr_year_one"

    def test_ltv_exactly_at_max(self, passing_result, default_criteria):
        """LTV exactly at max_ltv → passes."""
        result = passing_result.model_copy()
        result.ltv = 0.80

        verdict = evaluate(result, default_criteria)

        assert verdict.status == "worth_pursuing"

    def test_ltv_just_over_max(self, passing_result, default_criteria):
        """LTV just over max_ltv → fails."""
        result = passing_result.model_copy()
        result.ltv = 0.801

        verdict = evaluate(result, default_criteria)

        assert verdict.status == "below_standards"


class TestVerdictNoneMetrics:
    """None metrics skip checks without failing."""

    def test_none_irr_skips_check(self, passing_result, default_criteria):
        """result.irr = None → IRR check skipped, not a failure."""
        result = passing_result.model_copy()
        result.irr = None

        verdict = evaluate(result, default_criteria)

        # Should still pass because other metrics pass
        assert verdict.status == "worth_pursuing"
        assert not any(f.metric == "irr" for f in verdict.failures)


class TestVerdictMultipleFailures:
    """Multiple metrics failing together."""

    def test_multiple_failures_joined_by_semicolon(self, passing_result, default_criteria):
        """Multiple failures → joined in rationale by "; "."""
        result = passing_result.model_copy()
        result.irr = 0.12  # Fail
        result.cash_on_cash = 0.06  # Fail
        result.ltv = 0.85  # Fail

        verdict = evaluate(result, default_criteria)

        assert verdict.status == "below_standards"
        assert len(verdict.failures) == 3
        # Rationale should contain "Deal fails on: " prefix
        assert "Deal fails on:" in verdict.rationale


class TestVerdictStressScenarios:
    """Stress DSCR floor: min_dscr across all scenarios >= 1.15."""

    def test_stress_dscr_floor_passes(self, passing_result, default_criteria):
        """min_dscr = 1.20 → passes (>= 1.15)."""
        stress_scenarios = [
            StressScenario(scenario_key="base", label="Base", min_dscr=1.20),
            StressScenario(scenario_key="adverse", label="Adverse", min_dscr=1.18),
        ]

        verdict = evaluate(passing_result, default_criteria, stress_scenarios)

        assert verdict.status == "worth_pursuing"

    def test_stress_dscr_floor_fails(self, passing_result, default_criteria):
        """min_dscr = 1.10 → fails (< 1.15)."""
        stress_scenarios = [
            StressScenario(scenario_key="base", label="Base", min_dscr=1.30),
            StressScenario(scenario_key="adverse", label="Adverse", min_dscr=1.10),
        ]

        verdict = evaluate(passing_result, default_criteria, stress_scenarios)

        assert verdict.status == "below_standards"
        assert verdict.failures[0].metric == "stress_dscr_floor"
        assert verdict.failures[0].actual == 1.10  # Lowest


class TestVerdictRolloverWarning:
    """Rollover risk > 40% 12-mo expiry → soft warning (not a failure)."""

    def test_rollover_warning_appended_to_rationale(self, passing_result, default_criteria):
        """pct_rent_expiring_12mo = 0.50 → warning appended but no failure."""
        result = passing_result.model_copy()
        result.rollover_risk = RolloverRisk(
            pct_rent_expiring_12mo=0.50,
            pct_rent_expiring_24mo=0.70,
            pct_rent_expiring_36mo=0.90,
        )

        verdict = evaluate(result, default_criteria)

        assert verdict.status == "worth_pursuing"  # Still passes other criteria
        assert len(verdict.failures) == 0  # No failure added
        assert "Warning:" in verdict.rationale
        assert "50.0%" in verdict.rationale

    def test_rollover_no_warning_under_40_percent(self, passing_result, default_criteria):
        """pct_rent_expiring_12mo = 0.35 → no warning."""
        result = passing_result.model_copy()
        result.rollover_risk = RolloverRisk(
            pct_rent_expiring_12mo=0.35,
            pct_rent_expiring_24mo=0.60,
            pct_rent_expiring_36mo=0.85,
        )

        verdict = evaluate(result, default_criteria)

        assert "Warning:" not in verdict.rationale


class TestVerdictMixedRevenueWarning:
    """Mixed revenue rows in unit mix should produce a soft warning."""

    def test_mixed_revenue_warning_handles_dict_unit_mix_rows(self, passing_result, default_criteria):
        result = passing_result.model_copy()
        result.unit_mix = [
            {
                "unit_category": "storage",
                "size": "10 x 10",
                "num_units": 100,
            },
            {
                "unit_category": "parking",
                "size": "Parking",
                "num_units": 20,
            },
        ]

        verdict = evaluate(result, default_criteria)

        assert any(w.key == "mixed_revenue_unit_mix" for w in verdict.warnings)
        assert "20 of 120 units/spaces" in verdict.rationale


class TestVerdictEvidenceQualityWarning:
    """Short-period income statements should produce a non-fatal evidence-quality warning."""

    def test_t6_annualized_warning_appended_to_rationale(self, passing_result, default_criteria):
        verdict = evaluate(passing_result, default_criteria, income_statement_period_months=6)

        assert verdict.status == "worth_pursuing"
        assert any(w.key == "annualized_short_period_income" for w in verdict.warnings)
        assert "trailing 6-month period, annualized" in verdict.rationale


class TestVerdictMixedRevenueWarning:
    """Mixed revenue rows in unit mix should produce a soft warning."""

    def test_mixed_revenue_warning_added_for_parking_and_residential_rows(self, passing_result, default_criteria):
        result = passing_result.model_copy()
        result.unit_mix = [
            UnitMixRow(unit_category="storage", size="10 x 10", num_units=133),
            UnitMixRow(unit_category="parking", size="Parking", num_units=68),
            UnitMixRow(unit_category="residential", size="Residential", num_units=2),
        ]

        verdict = evaluate(result, default_criteria)

        assert verdict.status == "worth_pursuing"
        assert len(verdict.failures) == 0
        assert any(w.key == "mixed_revenue_unit_mix" for w in verdict.warnings)
        assert "Mixed revenue detected" in verdict.rationale
        assert "70 of 203 units/spaces" in verdict.rationale

    def test_storage_only_unit_mix_has_no_mixed_revenue_warning(self, passing_result, default_criteria):
        result = passing_result.model_copy()
        result.unit_mix = [
            UnitMixRow(unit_category="storage", size="5 x 10", num_units=45),
            UnitMixRow(unit_category="storage", size="10 x 10", num_units=30),
        ]

        verdict = evaluate(result, default_criteria)

        assert not any(w.key == "mixed_revenue_unit_mix" for w in verdict.warnings)
