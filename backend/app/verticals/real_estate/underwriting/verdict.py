"""
Verdict engine for self-storage underwriting.

Evaluates underwriting results against investment criteria and returns
a pass/fail verdict with per-criterion rationale.
"""

from __future__ import annotations

from ..underwriting.schemas.self_storage import (
    InvestmentCriteria,
    SelfStorageResult,
    StressScenario,
    VerdictFailure,
    VerdictResult,
    VerdictWarning,
)


def evaluate(
    result: SelfStorageResult,
    criteria: InvestmentCriteria,
    stress_scenarios: list[StressScenario] | None = None,
    income_statement_period_months: int | None = None,
) -> VerdictResult:
    """
    Evaluate underwriting results against investment criteria.

    Performs hard checks against the following metrics:
    1. IRR >= target_irr
    2. Cash-on-cash >= target_cash_on_cash
    3. Equity multiple >= target_equity_multiple
    4. DSCR year one >= 1.25 (industry minimum, non-negotiable)
    5. LTV <= max_ltv
    6. Stress scenario DSCR floor >= 1.15 (if stress scenarios provided)

    Soft checks (warnings in rationale, not failures):
    - Rollover risk: if > 40% of rent expiring in 12 months

    Args:
        result: The calculated self-storage underwriting result
        criteria: Investment criteria thresholds
        stress_scenarios: Optional list of stress test scenarios

    Returns:
        VerdictResult with status ("worth_pursuing" | "below_standards"),
        list of failures, and human-readable rationale
    """
    failures: list[VerdictFailure] = []

    # Hard check 1: IRR >= target_irr
    if result.irr is not None and result.irr < criteria.target_irr:
        failures.append(
            VerdictFailure(
                metric="irr",
                target=criteria.target_irr,
                actual=result.irr,
                gap=result.irr - criteria.target_irr,
            )
        )

    # Hard check 2: Cash-on-cash >= target_cash_on_cash
    if (
        result.cash_on_cash is not None
        and result.cash_on_cash < criteria.target_cash_on_cash
    ):
        failures.append(
            VerdictFailure(
                metric="cash_on_cash",
                target=criteria.target_cash_on_cash,
                actual=result.cash_on_cash,
                gap=result.cash_on_cash - criteria.target_cash_on_cash,
            )
        )

    # Hard check 3: Equity multiple >= target_equity_multiple
    if (
        result.equity_multiple is not None
        and result.equity_multiple < criteria.target_equity_multiple
    ):
        failures.append(
            VerdictFailure(
                metric="equity_multiple",
                target=criteria.target_equity_multiple,
                actual=result.equity_multiple,
                gap=result.equity_multiple - criteria.target_equity_multiple,
            )
        )

    # Hard check 4: DSCR year one >= 1.25 (industry minimum)
    if result.dscr_year_one is not None and result.dscr_year_one < 1.25:
        failures.append(
            VerdictFailure(
                metric="dscr_year_one",
                target=1.25,
                actual=result.dscr_year_one,
                gap=result.dscr_year_one - 1.25,
            )
        )

    # Hard check 5: LTV <= max_ltv
    # Note: For LTV, gap = actual - target (positive = over limit, since higher is worse)
    if result.ltv is not None and result.ltv > criteria.max_ltv:
        failures.append(
            VerdictFailure(
                metric="ltv",
                target=criteria.max_ltv,
                actual=result.ltv,
                gap=result.ltv - criteria.max_ltv,  # positive because over limit
            )
        )

    # Hard check 6: Stress scenario DSCR floor >= 1.15
    if stress_scenarios:
        min_stress_dscr = None
        for scenario in stress_scenarios:
            if scenario.min_dscr is not None:
                if min_stress_dscr is None or scenario.min_dscr < min_stress_dscr:
                    min_stress_dscr = scenario.min_dscr

        if min_stress_dscr is not None and min_stress_dscr < 1.15:
            failures.append(
                VerdictFailure(
                    metric="stress_dscr_floor",
                    target=1.15,
                    actual=min_stress_dscr,
                    gap=min_stress_dscr - 1.15,
                )
            )

    # Determine status
    status = "worth_pursuing" if not failures else "below_standards"

    warnings = _build_warnings(result, income_statement_period_months)

    # Build rationale
    rationale = _build_rationale(status, failures, warnings)

    return VerdictResult(
        status=status,
        failures=failures,
        warnings=warnings,
        rationale=rationale,
    )


def _build_warnings(
    result: SelfStorageResult,
    income_statement_period_months: int | None = None,
) -> list[VerdictWarning]:
    warnings: list[VerdictWarning] = []

    if income_statement_period_months and 0 < income_statement_period_months < 12:
        warnings.append(
            VerdictWarning(
                key="annualized_short_period_income",
                message=(
                    f"Income data is based on a trailing {income_statement_period_months}-month period, annualized. "
                    "A full T-12 is recommended before closing."
                ),
            )
        )

    mixed_revenue_warning = _build_mixed_revenue_warning(result)
    if mixed_revenue_warning:
        warnings.append(mixed_revenue_warning)

    if (
        result.rollover_risk
        and result.rollover_risk.pct_rent_expiring_12mo > 0.40
    ):
        warnings.append(
            VerdictWarning(
                key="rollover_concentration",
                message=(
                    f"{result.rollover_risk.pct_rent_expiring_12mo:.1%} of rent expires within 12 months, "
                    "which raises rollover concentration risk."
                ),
            )
        )

    return warnings


def _build_mixed_revenue_warning(result: SelfStorageResult) -> VerdictWarning | None:
    if not result.unit_mix:
        return None

    def _is_non_storage_row(row) -> bool:
        if isinstance(row, dict):
            section = row.get("section") or ""
            unit_type = row.get("unit_type") or ""
        else:
            section = row.section or ""
            unit_type = row.unit_type or ""
        label = " ".join(
            part.strip().lower()
            for part in [section, unit_type]
            if part
        )
        if not label:
            return False
        return any(keyword in label for keyword in ("parking", "residential", "apartment", "office"))

    non_storage_rows = [row for row in result.unit_mix if _is_non_storage_row(row)]
    if not non_storage_rows:
        return None

    def _row_units(row) -> int:
        if isinstance(row, dict):
            return row.get("num_units") or 0
        return row.num_units or 0

    non_storage_units = sum(_row_units(row) for row in non_storage_rows)
    total_units = sum(_row_units(row) for row in result.unit_mix)

    if non_storage_units > 0 and total_units > 0:
        detail = f"{non_storage_units} of {total_units} units/spaces appear to be parking or residential"
    else:
        detail = "parking or residential rows appear in the extracted unit mix"

    return VerdictWarning(
        key="mixed_revenue_unit_mix",
        message=(
            f"Mixed revenue detected: {detail}. The current underwriting model still applies blended self-storage assumptions, "
            "so per-door metrics and growth interpretations should be reviewed manually."
        ),
    )


def _build_rationale(
    status: str,
    failures: list[VerdictFailure],
    warnings: list[VerdictWarning],
) -> str:
    """
    Build human-readable rationale for the verdict.

    Args:
        status: "worth_pursuing" or "below_standards"
        failures: List of failed criteria
        warnings: Non-fatal warnings affecting confidence or interpretation

    Returns:
        Human-readable rationale string
    """
    if status == "worth_pursuing":
        rationale = "All investment criteria met."
    else:
        # List failed metrics
        failed_metrics = []
        for failure in failures:
            if failure.metric == "irr":
                failed_metrics.append(
                    f"IRR {failure.actual:.1%} below target {failure.target:.1%}"
                )
            elif failure.metric == "cash_on_cash":
                failed_metrics.append(
                    f"Cash-on-cash {failure.actual:.1%} below target {failure.target:.1%}"
                )
            elif failure.metric == "equity_multiple":
                failed_metrics.append(
                    f"Equity multiple {failure.actual:.2f}x below target {failure.target:.2f}x"
                )
            elif failure.metric == "dscr_year_one":
                failed_metrics.append(
                    f"DSCR year one {failure.actual:.2f}x below minimum 1.25x"
                )
            elif failure.metric == "ltv":
                failed_metrics.append(
                    f"LTV {failure.actual:.1%} exceeds maximum {failure.target:.1%}"
                )
            elif failure.metric == "stress_dscr_floor":
                failed_metrics.append(
                    f"Stress scenario DSCR floor {failure.actual:.2f}x below 1.15x minimum"
                )

        rationale = "Deal fails on: " + "; ".join(failed_metrics) + "."

    for warning in warnings:
        rationale += f" Warning: {warning.message}"

    return rationale
