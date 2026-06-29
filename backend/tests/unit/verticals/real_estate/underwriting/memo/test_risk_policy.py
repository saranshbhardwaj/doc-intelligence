"""Unit tests for deterministic IC memo risk policy."""
from __future__ import annotations

from app.verticals.real_estate.underwriting.memo.risk_policy import build_structured_risks
from app.verticals.real_estate.underwriting.memo.schemas import MemoContext


def _ctx(**overrides):
    base = dict(
        deal_name="Tulsa Deal 169",
        address="1540 North Yale Avenue Tulsa, OK 74115",
        asset_type="self_storage",
        year_built=2001,
        num_units=205,
        rentable_sqft=21_017,
        total_unit_count=205,
        storage_unit_count=133,
        non_storage_unit_count=72,
        cc_unit_count=0,
        nc_unit_count=133,
        climate_control_pct=0,
        purchase_price=2_500_000.0,
        price_per_unit=12_195.0,
        price_per_sqft=119.0,
        cap_rate_at_cost=0.0811,
        population_3mi=63_110,
        avg_household_income_3mi=49_306.0,
        storage_sqft_per_capita_3mi=6.93,
        nearby_storage_1mi=0,
        nearby_storage_3mi=10,
        nearby_storage_5mi=None,
        return_metrics={"irr": 0.1334, "equity_multiple": 1.74, "dscr_year_one": 1.43},
        criteria={"target_irr": 0.10, "target_equity_multiple": 1.30, "dscr_year_one_floor": 1.25},
        rent_position={
            "current_vs_comp_avg": 1.2249518059571567,
            "exact_size_matched_count": 4,
            "exact_size_total_count": 12,
        },
        stress_tests=[
            {
                "label": "Vacancy +5%",
                "scenario_key": "vacancy_plus_5pct",
                "irr": 0.0842,
                "cash_on_cash": 0.0593,
                "dscr_year_one": 1.33,
                "equity_multiple": 1.44,
            },
            {
                "label": "Rent Growth = 0%",
                "scenario_key": "rent_growth_zero",
                "irr": 0.0353,
                "cash_on_cash": 0.0763,
                "dscr_year_one": 1.43,
                "equity_multiple": 1.16,
            },
        ],
        capital_structure={"capex_reserve_initial": 0.0},
        capex_reserve_per_unit=0.0,
        financing={"loan_term_years": 10, "interest_rate_pct": 0.065},
        warnings=[],
        classification="Pursue",
    )
    base.update(overrides)
    return MemoContext(**base)


class TestRiskPolicy:
    def test_builds_tulsa_structured_risks_without_mismatched_mitigants(self):
        risks = build_structured_risks(_ctx())

        assert risks is not None
        assert 3 <= len(risks.risks) <= 6
        text = "\n".join(f"{risk.title}\n{risk.mitigant or ''}" for risk in risks.risks).lower()

        assert "72 of 205" in text
        assert "non-storage" in text
        assert "in-place rents are 122.5%" in text
        assert "rent sustainability" in text
        assert "downside cushion" not in text
        assert "downside protection" not in text
        assert "zero rent growth" in text
        assert "1.16x" in text
        assert "vacancy +5%" in text
        assert "refinance risk" not in text
        assert "fixed-rate" not in text
        assert "capex reserve is zero" in text

    def test_returns_none_when_policy_has_too_few_supported_risks(self):
        risks = build_structured_risks(_ctx(
            non_storage_unit_count=None,
            total_unit_count=133,
            storage_unit_count=133,
            rent_position={},
            stress_tests=[],
            capital_structure={"capex_reserve_initial": 40_000.0},
            capex_reserve_per_unit=100.0,
        ))

        assert risks is None