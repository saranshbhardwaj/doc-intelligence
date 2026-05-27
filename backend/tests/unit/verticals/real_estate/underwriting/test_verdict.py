"""Unit tests for the underwriting verdict engine."""
import pytest
from app.schemas.user_thresholds import UserUnderwritingThresholds
from app.verticals.real_estate.underwriting.verdict import _DEFAULTS, evaluate
from app.verticals.real_estate.underwriting.schemas.self_storage import (
    SelfStorageResult,
    InvestmentCriteria,
    CapitalStructure,
    OperationalInputs,
    SelfStorageInputs,
    AcquisitionInputs,
    ExitInputs,
    FinancingInputs,
    ProjectDetails,
    TotalReturn,
    StressScenario,
    RolloverRisk,
    UnitMixRow,
    ExpenseBasis,
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
        assert "Passes the initial screen" in verdict.rationale


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
        """result.irr = None with equity invested → IRR non-convergence remains a hard failure."""
        result = passing_result.model_copy()
        result.irr = None

        verdict = evaluate(result, default_criteria)

        assert verdict.status == "below_standards"
        assert any(f.metric == "irr" for f in verdict.failures)


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

        assert not any(w.key == "rollover_concentration" for w in verdict.warnings)


class TestVerdictMixedRevenueWarning:
    """Mixed revenue rows in unit mix should produce a soft warning."""

    def test_mixed_revenue_warning_handles_dict_unit_mix_rows(self, passing_result, default_criteria):
        result = passing_result.model_copy()
        result.unit_mix = [
            {
                "unit_category": "storage",
                "num_units": 100,
            },
            {
                "unit_category": "parking",
                "num_units": 20,
            },
        ]

        verdict = evaluate(result, default_criteria)

        assert any(w.key == "mixed_revenue_unit_mix" for w in verdict.warnings)
        assert "20 of 120 units/spaces (17% of unit count)" in verdict.rationale


class TestVerdictEvidenceQualityWarning:
    """Short-period income statements should produce a non-fatal evidence-quality warning."""

    def test_t6_annualized_warning_appended_to_rationale(self, passing_result, default_criteria):
        verdict = evaluate(passing_result, default_criteria, income_statement_period_months=6)

        assert verdict.status == "needs_review"
        warning = next(w for w in verdict.warnings if w.key == "annualized_short_period_income")
        assert warning.severity == "warning"
        assert "trailing 6-month period, annualized" in verdict.rationale
        assert "-10% reduction to GPR" in warning.message

    @pytest.mark.parametrize("months", [7, 8, 9, 10, 11])
    def test_t7_through_t11_emit_annualized_warning_with_severity(self, passing_result, default_criteria, months):
        verdict = evaluate(passing_result, default_criteria, income_statement_period_months=months)

        warning = next(w for w in verdict.warnings if w.key == "annualized_short_period_income")
        assert warning.severity == "warning"
        assert f"trailing {months}-month period" in warning.message
        assert verdict.status == "needs_review"

    def test_period_under_three_months_emits_stronger_warning(self, passing_result, default_criteria):
        verdict = evaluate(passing_result, default_criteria, income_statement_period_months=2)

        warning = next(w for w in verdict.warnings if w.key == "very_short_period_income")
        assert warning.severity == "critical"

    def test_t3_period_emits_stronger_warning(self, passing_result, default_criteria):
        verdict = evaluate(passing_result, default_criteria, income_statement_period_months=3)

        warning = next(w for w in verdict.warnings if w.key == "very_short_period_income")
        assert warning.severity == "critical"

    def test_missing_expense_lines_requires_review(self, passing_result, default_criteria):
        inputs = SelfStorageInputs(
            project=ProjectDetails(name="Test Deal", asset_type="self_storage"),
            acquisition=AcquisitionInputs(purchase_price=5_000_000),
            operational=OperationalInputs(
                gross_potential_rent_annual=600_000,
                vacancy_credit_loss_pct=0.08,
                other_income_annual=20_000,
                property_tax_annual=0,
                insurance_annual=0,
                payroll_annual=0,
                repairs_maintenance_annual=0,
                utilities_annual=0,
                marketing_annual=0,
                other_opex_annual=0,
                mgmt_fee_pct=0.08,
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
            criteria=default_criteria,
        )

        verdict = evaluate(passing_result, default_criteria, inputs=inputs)

        assert verdict.status == "needs_review"
        expense_warning = next(w for w in verdict.warnings if w.key == "expenses_missing")
        assert expense_warning.severity == "critical"
        assert "analyst review is required" in verdict.rationale

    def test_low_expense_ratio_requires_review(self, passing_result, default_criteria):
        result = passing_result.model_copy(deep=True)
        result.expense_basis = ExpenseBasis(
            source="om_year1_line_items",
            label="Year 1 OM line items",
            ratio=0.27,
            period="year1",
            method="line_items",
            expense_ratio=0.27,
            reason="test",
        )
        inputs = SelfStorageInputs(
            project=ProjectDetails(name="Low OpEx Deal", asset_type="self_storage"),
            acquisition=AcquisitionInputs(purchase_price=5_000_000),
            operational=OperationalInputs(gross_potential_rent_annual=600_000),
            financing=FinancingInputs(),
            exit=ExitInputs(),
            criteria=default_criteria,
        )

        verdict = evaluate(result, default_criteria, inputs=inputs)

        warning = next(w for w in verdict.warnings if w.key == "expense_ratio_benchmark")
        assert verdict.status == "needs_review"
        assert "below the 30%" in warning.message

    def test_high_expense_ratio_requires_review(self, passing_result, default_criteria):
        result = passing_result.model_copy(deep=True)
        result.expense_basis = ExpenseBasis(
            source="om_year1_line_items",
            label="Year 1 OM line items",
            ratio=0.49,
            period="year1",
            method="line_items",
            expense_ratio=0.49,
            reason="test",
        )
        inputs = SelfStorageInputs(
            project=ProjectDetails(name="High OpEx Deal", asset_type="self_storage"),
            acquisition=AcquisitionInputs(purchase_price=5_000_000),
            operational=OperationalInputs(gross_potential_rent_annual=600_000),
            financing=FinancingInputs(),
            exit=ExitInputs(),
            criteria=default_criteria,
        )

        verdict = evaluate(result, default_criteria, inputs=inputs)

        warning = next(w for w in verdict.warnings if w.key == "expense_ratio_benchmark")
        assert verdict.status == "needs_review"
        assert "above the 45%" in warning.message

    def test_sqft_per_capita_supply_watch_requires_review(self, passing_result, default_criteria):
        inputs = SelfStorageInputs(
            project=ProjectDetails(
                name="Supply Watch Deal",
                asset_type="self_storage",
                storage_sqft_per_capita_3mi=6.9,
                nearby_storage_count_3mi=10,
            ),
            acquisition=AcquisitionInputs(purchase_price=5_000_000),
            operational=OperationalInputs(gross_potential_rent_annual=600_000),
            financing=FinancingInputs(),
            exit=ExitInputs(),
            criteria=default_criteria,
        )

        verdict = evaluate(passing_result, default_criteria, inputs=inputs)

        warning = next(w for w in verdict.warnings if w.key == "market_supply_watch")
        assert verdict.status == "needs_review"
        assert "6.9 sqft/capita" in warning.message
        assert "10 competitors" in warning.message


class TestVerdictOMNOIWarnings:
    """OM-NOI mode swaps missing-support warnings for a quick-screen warning."""

    def _om_noi_inputs(self, criteria):
        return SelfStorageInputs(
            project=ProjectDetails(name="OM Deal", asset_type="self_storage"),
            acquisition=AcquisitionInputs(purchase_price=8_000_000),
            operational=OperationalInputs(
                gross_potential_rent_annual=0.0,
                noi_current_stated=663_830.0,
            ),
            financing=FinancingInputs(
                ltv_pct=0.70,
                interest_rate_pct=0.065,
                amortization_years=25,
                loan_term_years=10,
            ),
            exit=ExitInputs(hold_period_years=5, exit_cap_rate=0.065, selling_cost_pct=0.03),
            criteria=criteria,
        )

    def test_om_noi_mode_suppresses_expenses_missing(self, passing_result, default_criteria):
        result = passing_result.model_copy(deep=True)
        result.expense_basis = ExpenseBasis(
            source="om_noi",
            label="OM-stated NOI quick screen",
            reason="test",
        )

        verdict = evaluate(result, default_criteria, inputs=self._om_noi_inputs(default_criteria))
        keys = [warning.key for warning in verdict.warnings]

        assert "expenses_missing" not in keys

    def test_om_noi_mode_suppresses_income_period_unknown(self, passing_result, default_criteria):
        result = passing_result.model_copy(deep=True)
        result.expense_basis = ExpenseBasis(
            source="om_noi",
            label="OM-stated NOI quick screen",
            reason="test",
        )

        verdict = evaluate(result, default_criteria, inputs=self._om_noi_inputs(default_criteria))
        keys = [warning.key for warning in verdict.warnings]

        assert "income_period_unknown" not in keys

    def test_om_noi_mode_adds_quick_screen_warning(self, passing_result, default_criteria):
        result = passing_result.model_copy(deep=True)
        result.expense_basis = ExpenseBasis(
            source="om_noi",
            label="OM-stated NOI quick screen",
            reason="test",
        )

        verdict = evaluate(result, default_criteria, inputs=self._om_noi_inputs(default_criteria))
        quick_screen = next(w for w in verdict.warnings if w.key == "om_noi_quick_screen")

        assert quick_screen.severity == "warning"

    def test_missing_basis_still_emits_expenses_missing(self, passing_result, default_criteria):
        result = passing_result.model_copy(deep=True)
        result.expense_basis = ExpenseBasis(
            source="missing",
            label="Missing expense support",
            reason="test",
        )

        verdict = evaluate(result, default_criteria, inputs=self._om_noi_inputs(default_criteria))
        keys = [warning.key for warning in verdict.warnings]

        assert "expenses_missing" in keys


class TestVerdictMixedRevenueWarning:
    """Mixed revenue rows in unit mix should produce a soft warning."""

    def test_mixed_revenue_warning_added_for_parking_and_residential_rows(self, passing_result, default_criteria):
        result = passing_result.model_copy()
        result.unit_mix = [
            UnitMixRow(unit_category="storage", num_units=133),
            UnitMixRow(unit_category="parking", num_units=68),
            UnitMixRow(unit_category="residential", num_units=2),
        ]

        verdict = evaluate(result, default_criteria)

        assert verdict.status == "needs_review"
        assert len(verdict.failures) == 0
        assert any(w.key == "mixed_revenue_material" for w in verdict.warnings)
        assert "Mixed revenue detected" in verdict.rationale
        assert "70 of 203 units/spaces (34% of unit count)" in verdict.rationale

    def test_material_mixed_revenue_by_scheduled_rent_requires_review(self, passing_result, default_criteria):
        result = passing_result.model_copy()
        result.unit_mix = [
            UnitMixRow(unit_category="storage", num_units=100, current_rent=50),
            UnitMixRow(unit_category="residential", num_units=1, current_rent=1_500),
        ]

        verdict = evaluate(result, default_criteria)

        warning = next(w for w in verdict.warnings if w.key == "mixed_revenue_material")
        assert verdict.status == "needs_review"
        assert "approximately 23% of scheduled rent" in warning.message

    def test_storage_only_unit_mix_has_no_mixed_revenue_warning(self, passing_result, default_criteria):
        result = passing_result.model_copy()
        result.unit_mix = [
            UnitMixRow(unit_category="storage", climate_type="NC", size="5 x 10", num_units=45),
            UnitMixRow(unit_category="storage", climate_type="CC", size="10 x 10", num_units=30),
        ]

        verdict = evaluate(result, default_criteria)

        assert not any(w.key == "mixed_revenue_unit_mix" for w in verdict.warnings)


class TestVerdictUserThresholds:
    """Per-user threshold overrides change pass/fail results; None thresholds use defaults."""

    def test_none_thresholds_uses_default_dscr_floor(self, passing_result, default_criteria):
        result = passing_result.model_copy()
        result.dscr_year_one = _DEFAULTS["dscr_year_one_floor"] - 0.01  # just below default

        verdict = evaluate(result, default_criteria, thresholds=None)

        assert verdict.status == "below_standards"
        assert any(f.metric == "dscr_year_one" for f in verdict.failures)
        assert any(f.target == _DEFAULTS["dscr_year_one_floor"] for f in verdict.failures)

    def test_custom_dscr_floor_overrides_default(self, passing_result, default_criteria):
        result = passing_result.model_copy()
        result.dscr_year_one = 1.20  # below default 1.25 but above custom 1.18

        criteria = default_criteria.model_copy(update={"dscr_year_one_floor": 1.18})
        verdict = evaluate(result, criteria)

        assert verdict.status == "worth_pursuing"
        assert not any(f.metric == "dscr_year_one" for f in verdict.failures)

    def test_custom_dscr_floor_still_fails_below_custom(self, passing_result, default_criteria):
        result = passing_result.model_copy()
        result.dscr_year_one = 1.10  # below both default and custom

        criteria = default_criteria.model_copy(update={"dscr_year_one_floor": 1.18})
        verdict = evaluate(result, criteria)

        assert verdict.status == "below_standards"
        failure = next(f for f in verdict.failures if f.metric == "dscr_year_one")
        assert failure.target == pytest.approx(1.18)

    def test_custom_stress_dscr_floor(self, passing_result, default_criteria):
        stress = [StressScenario(scenario_key="base", label="base", min_dscr=1.12)]  # below default 1.15, above custom 1.10
        criteria = default_criteria.model_copy(update={"stress_dscr_floor": 1.10})

        verdict = evaluate(passing_result, criteria, stress_scenarios=stress)

        assert not any(f.metric == "stress_dscr_floor" for f in verdict.failures)

    def test_default_stress_floor_fails_without_custom(self, passing_result, default_criteria):
        stress = [StressScenario(scenario_key="base", label="base", min_dscr=1.12)]  # below default 1.15

        verdict = evaluate(passing_result, default_criteria, stress_scenarios=stress, thresholds=None)

        assert any(f.metric == "stress_dscr_floor" for f in verdict.failures)

    def test_unset_threshold_fields_fall_back_to_defaults(self, passing_result, default_criteria):
        result = passing_result.model_copy()
        result.dscr_year_one = 1.20  # below default 1.25

        # thresholds with only stress floor set; dscr floor should still default to 1.25
        custom = UserUnderwritingThresholds(stress_dscr_floor=1.10)
        verdict = evaluate(result, default_criteria, thresholds=custom)

        assert any(f.metric == "dscr_year_one" for f in verdict.failures)
        assert any(f.target == pytest.approx(1.25) for f in verdict.failures)
