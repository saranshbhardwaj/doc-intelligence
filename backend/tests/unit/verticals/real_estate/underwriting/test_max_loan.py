"""Unit tests for the max-loan calculator."""
import math

import pytest

from app.verticals.real_estate.underwriting.max_loan import calculate_max_loan


def _call(**overrides):
    """Build a sensible default call and override what each test cares about."""
    defaults = dict(
        noi_year_one=400_000.0,
        purchase_price=5_000_000.0,
        interest_rate_pct=0.065,
        amortization_years=25,
        dscr_floor=1.25,
        max_ltv=0.65,
        debt_yield_floor=0.08,
        current_loan=3_250_000.0,
    )
    defaults.update(overrides)
    return calculate_max_loan(**defaults)


class TestBindingConstraints:
    def test_dscr_binds_when_other_constraints_are_loose(self):
        # NOI = 400k, DSCR floor = 1.25 -> max annual DS = 320k
        # At 6.5%/25yr that supports roughly $2.6-2.8M, well below LTV (3.25M) and DY (5M).
        result = _call(max_ltv=0.95, debt_yield_floor=0.04)
        assert result.binding_constraint == "dscr"
        assert result.max_loan == pytest.approx(result.max_loan_by_dscr, rel=1e-6)
        assert result.max_loan_by_ltv > result.max_loan
        assert result.max_loan_by_debt_yield > result.max_loan
        assert result.implied_monthly_payment is not None
        assert result.implied_annual_debt_service == pytest.approx(
            result.implied_monthly_payment * 12, rel=1e-6
        )

    def test_ltv_binds_when_other_constraints_are_loose(self):
        # Force LTV to be tightest with a low max_ltv.
        result = _call(max_ltv=0.20, debt_yield_floor=0.001, dscr_floor=1.0)
        assert result.binding_constraint == "ltv"
        assert result.max_loan == pytest.approx(0.20 * 5_000_000.0)

    def test_debt_yield_binds_when_other_constraints_are_loose(self):
        # NOI 400k / DY floor 0.12 = 3.33M, lower than LTV (4.75M) and a loose DSCR.
        result = _call(max_ltv=0.95, dscr_floor=1.0, debt_yield_floor=0.12)
        assert result.binding_constraint == "debt_yield"
        assert result.max_loan == pytest.approx(400_000.0 / 0.12, rel=1e-6)


class TestEdgeCases:
    def test_noi_missing_returns_zero_with_sentinel(self):
        result = _call(noi_year_one=None)
        assert result.binding_constraint in {"noi_unavailable", "ltv"}
        if result.binding_constraint == "noi_unavailable":
            assert result.max_loan == 0.0
        assert result.max_loan_by_dscr is None
        assert result.max_loan_by_debt_yield is None

    def test_rate_missing_skips_dscr_other_constraints_still_compute(self):
        result = _call(interest_rate_pct=None)
        assert result.max_loan_by_dscr is None
        assert result.max_loan_by_ltv == pytest.approx(0.65 * 5_000_000.0)
        assert result.max_loan_by_debt_yield == pytest.approx(400_000.0 / 0.08)
        assert any("rate" in n.lower() or "amortization" in n.lower() for n in result.notes)
        assert result.binding_constraint in {"ltv", "debt_yield"}

    def test_amort_missing_skips_dscr(self):
        result = _call(amortization_years=None)
        assert result.max_loan_by_dscr is None
        assert result.binding_constraint in {"ltv", "debt_yield"}

    def test_purchase_price_missing_skips_ltv(self):
        result = _call(purchase_price=None)
        assert result.max_loan_by_ltv is None
        assert result.equity_required == 0.0
        assert result.max_loan_by_dscr is not None
        assert result.max_loan_by_debt_yield is not None

    def test_debt_yield_floor_zero_excludes_constraint(self):
        result = _call(debt_yield_floor=0.0)
        assert result.max_loan_by_debt_yield is None
        assert result.binding_constraint in {"dscr", "ltv"}

    def test_all_constraints_unavailable_defaults_to_current_loan(self):
        result = _call(
            noi_year_one=None,
            purchase_price=None,
            interest_rate_pct=None,
            amortization_years=None,
            current_loan=2_500_000.0,
        )
        assert result.binding_constraint in {"noi_unavailable", "none"}
        assert result.current_loan == 2_500_000.0

    def test_delta_vs_current_is_negative_when_overlevered(self):
        result = _call(max_ltv=0.20, dscr_floor=1.0, debt_yield_floor=0.001, current_loan=3_000_000.0)
        assert result.max_loan == pytest.approx(1_000_000.0)
        assert result.delta_vs_current == pytest.approx(-2_000_000.0)
        assert result.equity_required == pytest.approx(4_000_000.0)

    def test_noi_missing_and_no_ltv_returns_zero(self):
        """When NOI is absent and LTV cannot compute, the sentinel kicks in."""
        result = _call(noi_year_one=None, purchase_price=None)
        assert result.binding_constraint == "noi_unavailable"
        assert result.max_loan == 0.0

    def test_snapshot_representative_deal(self):
        """Stability snapshot - change only with intent."""
        result = _call()
        assert result.max_loan_by_debt_yield == pytest.approx(5_000_000.0, rel=1e-9)
        assert result.max_loan_by_ltv == pytest.approx(3_250_000.0, rel=1e-9)
        # DSCR-implied loan at 6.5%/25yr on $320k/yr DS is ~$3.95M.
        assert result.max_loan_by_dscr == pytest.approx(3_948_000.0, rel=2e-2)
        # LTV is the binding constraint with these inputs.
        assert result.binding_constraint == "ltv"
        assert result.max_loan == pytest.approx(3_250_000.0, rel=1e-9)
