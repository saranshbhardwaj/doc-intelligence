"""Pure max-loan calculator.

Given Year-1 NOI and lender constraints, returns the maximum supportable loan
amount and which constraint binds. Stateless, side-effect free, no DB access.
"""

from __future__ import annotations

import math

import numpy_financial as npf

from .schemas.self_storage import MaxLoanResult


def _pv_of_annual_debt_service(
    annual_debt_service: float,
    interest_rate_pct: float,
    amortization_years: int,
) -> float:
    """Return the present value of a level monthly P+I that totals `annual_debt_service`/year."""
    monthly_payment = annual_debt_service / 12.0
    pv = float(
        npf.pv(
            rate=interest_rate_pct / 12.0,
            nper=amortization_years * 12,
            pmt=-monthly_payment,
        )
    )
    if not math.isfinite(pv) or pv < 0:
        return 0.0
    return pv


def calculate_max_loan(
    noi_year_one: float | None,
    purchase_price: float | None,
    interest_rate_pct: float | None,
    amortization_years: int | None,
    dscr_floor: float,
    max_ltv: float,
    debt_yield_floor: float,
    current_loan: float,
) -> MaxLoanResult:
    """Compute the maximum supportable loan from three lender constraints.

    Any constraint with insufficient inputs is reported as ``None`` and excluded
    from the minimum. If no constraint can be computed, ``max_loan`` falls back
    to ``current_loan``.
    """
    notes: list[str] = []

    noi_available = noi_year_one is not None and noi_year_one > 0
    if not noi_available:
        notes.append("NOI is required to size DSCR and debt yield constraints.")

    max_loan_by_dscr: float | None = None
    implied_monthly_payment: float | None = None
    implied_annual_debt_service: float | None = None

    rate_amort_available = (
        interest_rate_pct is not None
        and interest_rate_pct > 0
        and amortization_years is not None
        and amortization_years > 0
    )

    if noi_available and dscr_floor > 0 and rate_amort_available:
        annual_ds = noi_year_one / dscr_floor
        max_loan_by_dscr = _pv_of_annual_debt_service(
            annual_ds, interest_rate_pct, amortization_years
        )
    elif noi_available and dscr_floor > 0 and not rate_amort_available:
        notes.append(
            "DSCR sizing requires interest rate and amortization on the Financing tab."
        )

    max_loan_by_ltv: float | None = None
    if purchase_price is not None and purchase_price > 0 and max_ltv > 0:
        max_loan_by_ltv = purchase_price * max_ltv
    elif max_ltv > 0:
        notes.append("LTV sizing requires a purchase price.")

    max_loan_by_debt_yield: float | None = None
    if noi_available and debt_yield_floor and debt_yield_floor > 0:
        max_loan_by_debt_yield = noi_year_one / debt_yield_floor

    candidates: list[tuple[str, float]] = []
    if max_loan_by_dscr is not None:
        candidates.append(("dscr", max_loan_by_dscr))
    if max_loan_by_ltv is not None:
        candidates.append(("ltv", max_loan_by_ltv))
    if max_loan_by_debt_yield is not None:
        candidates.append(("debt_yield", max_loan_by_debt_yield))

    if not noi_available and max_loan_by_ltv is None:
        binding = "noi_unavailable"
        max_loan = 0.0
    elif not candidates:
        # Distinguish "rate/amort missing was the reason" from a generic empty case.
        if noi_available and dscr_floor > 0 and not rate_amort_available:
            binding = "rate_or_amort_missing"
        else:
            binding = "none"
        max_loan = current_loan
        notes.append("No active lender constraints - defaulting to current loan.")
    else:
        binding, max_loan = min(candidates, key=lambda pair: pair[1])

    if binding == "dscr" and rate_amort_available:
        implied_annual_debt_service = noi_year_one / dscr_floor
        implied_monthly_payment = implied_annual_debt_service / 12.0

    if purchase_price is not None and purchase_price > 0:
        equity_required = max(0.0, purchase_price - max_loan)
    else:
        equity_required = 0.0

    return MaxLoanResult(
        max_loan=float(max_loan),
        max_loan_by_dscr=max_loan_by_dscr,
        max_loan_by_ltv=max_loan_by_ltv,
        max_loan_by_debt_yield=max_loan_by_debt_yield,
        binding_constraint=binding,
        implied_monthly_payment=implied_monthly_payment,
        implied_annual_debt_service=implied_annual_debt_service,
        equity_required=float(equity_required),
        current_loan=float(current_loan),
        delta_vs_current=float(max_loan - current_loan),
        notes=notes,
    )
