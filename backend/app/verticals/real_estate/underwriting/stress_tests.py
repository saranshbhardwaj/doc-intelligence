"""
Stress-test scenarios for self-storage underwriting.

Runs the base case and 4 adverse scenarios, returning a StressScenario for each.
"""

from __future__ import annotations

from .calculator import calculate
from .schemas.self_storage import SelfStorageInputs, StressScenario

# Each entry: scenario_key -> (label, modifier function)
SCENARIOS: dict[str, tuple[str, object]] = {
    "base": (
        "Base Case",
        lambda i: i,
    ),
    "vacancy_plus_500bps": (
        "Vacancy +5%",
        lambda i: i.model_copy(
            update={
                "operational": i.operational.model_copy(
                    update={
                        "vacancy_credit_loss_pct": i.operational.vacancy_credit_loss_pct + 0.05
                    }
                )
            }
        ),
    ),
    "rent_growth_zero": (
        "Rent Growth = 0%",
        lambda i: i.model_copy(
            update={
                "operational": i.operational.model_copy(
                    update={"rent_growth_pct": 0.0}
                )
            }
        ),
    ),
    "opex_plus_10pct": (
        "OpEx +10%",
        lambda i: i.model_copy(
            update={
                "operational": i.operational.model_copy(
                    update={
                        "opex_growth_pct": i.operational.opex_growth_pct + 0.10
                    }
                )
            }
        ),
    ),
    "exit_cap_plus_25bps": (
        "Exit Cap +0.25%",
        lambda i: i.model_copy(
            update={
                "exit": i.exit.model_copy(
                    update={
                        "exit_cap_rate": i.exit.exit_cap_rate + 0.0025
                    }
                )
            }
        ),
    ),
}


def run_stress_tests(inputs: SelfStorageInputs) -> list[StressScenario]:
    """Run the 5 scenarios (base + 4 adverse) and return results.

    Exceptions from calculate() are caught gracefully; affected metrics
    are returned as None rather than raising.
    """
    results: list[StressScenario] = []

    for scenario_key, (label, modifier) in SCENARIOS.items():
        irr = None
        cash_on_cash = None
        dscr_year_one = None
        equity_multiple = None
        min_dscr = None

        try:
            modified_inputs: SelfStorageInputs = modifier(inputs)
            result = calculate(modified_inputs)

            irr = result.irr
            cash_on_cash = result.cash_on_cash
            dscr_year_one = result.dscr_year_one
            equity_multiple = result.equity_multiple

            # min DSCR across all projection years
            annual_ds = result.projections[0].debt_service if result.projections else 0.0
            if annual_ds > 0:
                min_dscr = min(
                    p.noi / annual_ds for p in result.projections
                )
        except Exception:
            # Calculation failure (e.g. IRR non-convergence propagating as
            # exception, bad inputs) — leave all metrics as None.
            pass

        results.append(
            StressScenario(
                scenario_key=scenario_key,
                label=label,
                irr=irr,
                cash_on_cash=cash_on_cash,
                dscr_year_one=dscr_year_one,
                equity_multiple=equity_multiple,
                min_dscr=min_dscr,
            )
        )

    return results
