"""
Verdict engine for self-storage underwriting.

Evaluates underwriting results against investment criteria and returns
a pass/fail verdict with per-criterion rationale.
"""

from __future__ import annotations

from app.schemas.user_thresholds import UserUnderwritingThresholds

from ..underwriting.schemas.self_storage import (
    InvestmentCriteria,
    SelfStorageResult,
    StressScenario,
    VerdictFailure,
    VerdictResult,
    VerdictWarning,
)
from .thresholds import (
    DSCR_YEAR_ONE_FLOOR,
    EXPENSE_RATIO_HIGH_PCT,
    EXPENSE_RATIO_LOW_PCT,
    INCOME_PERIOD_FULL_YEAR_MONTHS,
    INCOME_PERIOD_VERY_SHORT_THRESHOLD,
    MARKET_SUPPLY_COMPETITOR_COUNT_WATCH,
    MARKET_SUPPLY_SQFT_PER_CAPITA_HIGH,
    MARKET_SUPPLY_SQFT_PER_CAPITA_WATCH,
    MIXED_REVENUE_RENT_SHARE_PCT,
    MIXED_REVENUE_UNIT_SHARE_PCT,
    NOI_RECONCILIATION_GAP_PCT,
    ROLLOVER_CONCENTRATION_PCT,
    STRESS_DSCR_FLOOR,
    UNIT_MIX_GPR_MISMATCH_PCT,
)


_DEFAULTS = {
    "dscr_year_one_floor": DSCR_YEAR_ONE_FLOOR,
    "stress_dscr_floor": STRESS_DSCR_FLOOR,
    "rollover_risk_pct": ROLLOVER_CONCENTRATION_PCT,
}

_CONDITION_WARNING_KEYS = {
    "annualized_short_period_income",
    "expense_ratio_benchmark",
    "expenses_incomplete",
    "expenses_missing",
    "market_supply_watch",
    "mixed_revenue_material",
    "noi_reconciliation_gap",
    "om_noi_quick_screen",
    "very_short_period_income",
}


def _resolve(criteria: InvestmentCriteria, key: str) -> float:
    """Return the per-deal threshold from criteria, falling back to the hardcoded industry minimum."""
    value = getattr(criteria, key, None)
    if value is not None:
        return value
    if key not in _DEFAULTS:
        raise ValueError(f"No default configured for threshold key '{key}'")
    return _DEFAULTS[key]


def evaluate(
    result: SelfStorageResult,
    criteria: InvestmentCriteria,
    stress_scenarios: list[StressScenario] | None = None,
    income_statement_period_months: int | None = None,
    inputs=None,
    thresholds: UserUnderwritingThresholds | None = None,  # noqa: ARG001 — kept for call-site backward compat
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
        VerdictResult with status ("worth_pursuing" | "needs_review" | "below_standards"),
        list of failures, and human-readable rationale
    """
    failures: list[VerdictFailure] = []

    # Hard check 0: IRR non-convergence — treat as hard failure when equity is invested
    if result.irr is None and result.capital_structure.total_equity_invested > 0:
        failures.append(
            VerdictFailure(
                metric="irr",
                target=criteria.target_irr,
                actual=None,
                gap=None,
            )
        )

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

    # Hard check 4: DSCR year one floor (default 1.25; snapshotted from user defaults at run creation)
    dscr_floor = _resolve(criteria, "dscr_year_one_floor")
    if result.dscr_year_one is not None and result.dscr_year_one < dscr_floor:
        failures.append(
            VerdictFailure(
                metric="dscr_year_one",
                target=dscr_floor,
                actual=result.dscr_year_one,
                gap=result.dscr_year_one - dscr_floor,
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

        stress_floor = _resolve(criteria, "stress_dscr_floor")
        if min_stress_dscr is not None and min_stress_dscr < stress_floor:
            failures.append(
                VerdictFailure(
                    metric="stress_dscr_floor",
                    target=stress_floor,
                    actual=min_stress_dscr,
                    gap=min_stress_dscr - stress_floor,
                )
            )

    warnings = _build_warnings(result, income_statement_period_months, inputs=inputs, criteria=criteria)

    # Determine status
    if failures:
        status = "below_standards"
    elif any(
        warning.severity == "critical" or warning.key in _CONDITION_WARNING_KEYS
        for warning in warnings
    ):
        status = "needs_review"
    else:
        status = "worth_pursuing"

    # Build rationale
    rationale = _build_rationale(status, failures, warnings)

    return VerdictResult(
        status=status,
        failures=failures,
        warnings=warnings,
        rationale=rationale,
    )


def _build_unit_mix_gpr_warning(inputs) -> VerdictWarning | None:
    if not inputs or not inputs.unit_mix:
        return None
    model_gpr = inputs.operational.gross_potential_rent_annual
    if not model_gpr or model_gpr <= 0:
        return None
    implied_gpr = sum(
        (row.current_rent or 0) * (row.num_units or 0) * 12
        for row in inputs.unit_mix
        if row.current_rent and row.num_units
    )
    if implied_gpr <= 0:
        return None
    delta_pct = abs(implied_gpr - model_gpr) / model_gpr
    if delta_pct < UNIT_MIX_GPR_MISMATCH_PCT:
        return None
    return VerdictWarning(
        key="unit_mix_gpr_mismatch",
        message=(
            f"Unit-mix implied GPR ${implied_gpr:,.0f} differs from model GPR ${model_gpr:,.0f} "
            f"by {delta_pct:.1%}. Review unit mix or income inputs."
        ),
        severity="warning",
    )


def _row_label(row) -> str:
    if isinstance(row, dict):
        part = row.get("unit_category")
    else:
        part = getattr(row, "unit_category", None)
    return str(part).strip().lower() if part else ""


def _is_non_storage_row(row) -> bool:
    label = _row_label(row)
    if not label:
        return False
    return any(keyword in label for keyword in ("parking", "residential", "apartment", "office"))


def _row_units(row) -> int:
    value = row.get("num_units") if isinstance(row, dict) else getattr(row, "num_units", None)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _row_rent(row) -> float | None:
    if isinstance(row, dict):
        value = row.get("current_rent")
        if value is None:
            value = row.get("market_rent")
    else:
        value = getattr(row, "current_rent", None)
        if value is None:
            value = getattr(row, "market_rent", None)
    try:
        rent = float(value)
    except (TypeError, ValueError):
        return None
    return rent if rent > 0 else None


def _scheduled_rent(rows) -> float:
    total = 0.0
    for row in rows:
        rent = _row_rent(row)
        units = _row_units(row)
        if rent is not None and units > 0:
            total += rent * units * 12
    return total


def _build_expense_ratio_benchmark_warning(result: SelfStorageResult, inputs) -> VerdictWarning | None:
    if inputs is None:
        return None
    op = inputs.operational
    expense_basis = getattr(result, "expense_basis", None)
    ratio = None
    if expense_basis is not None and expense_basis.ratio is not None:
        ratio = expense_basis.ratio
    elif getattr(op, "expense_ratio_t12", None) is not None:
        ratio = op.expense_ratio_t12
    elif op.expense_ratio_current is not None:
        ratio = op.expense_ratio_current
    elif getattr(op, "expense_ratio_year1", None) is not None:
        ratio = op.expense_ratio_year1
    elif op.expense_ratio_pro_forma is not None:
        ratio = op.expense_ratio_pro_forma
    if ratio is None or ratio <= 0:
        return None
    if ratio < EXPENSE_RATIO_LOW_PCT:
        message = (
            f"Expense ratio of {ratio:.1%} is below the {EXPENSE_RATIO_LOW_PCT:.0%} screening benchmark. "
            "Verify missing operating expenses, management load, insurance, and post-acquisition property tax reassessment."
        )
    elif ratio > EXPENSE_RATIO_HIGH_PCT:
        message = (
            f"Expense ratio of {ratio:.1%} is above the {EXPENSE_RATIO_HIGH_PCT:.0%} screening benchmark. "
            "Review expense load, staffing, repairs, utilities, and whether the deal requires an expense-normalization case."
        )
    else:
        return None
    return VerdictWarning(
        key="expense_ratio_benchmark",
        message=message,
        severity="warning",
    )


def _build_market_supply_warning(inputs) -> VerdictWarning | None:
    if inputs is None:
        return None
    project = inputs.project
    sqft_per_capita = project.storage_sqft_per_capita_3mi
    competitor_count = project.nearby_storage_count_3mi
    if sqft_per_capita is None:
        return None
    high_supply = sqft_per_capita >= MARKET_SUPPLY_SQFT_PER_CAPITA_HIGH
    watch_supply = (
        sqft_per_capita >= MARKET_SUPPLY_SQFT_PER_CAPITA_WATCH
        and competitor_count is not None
        and competitor_count >= MARKET_SUPPLY_COMPETITOR_COUNT_WATCH
    )
    if not (high_supply or watch_supply):
        return None
    competitor_text = (
        f" with {competitor_count} competitors in 3 miles"
        if competitor_count is not None
        else ""
    )
    return VerdictWarning(
        key="market_supply_watch",
        message=(
            f"Storage supply is {sqft_per_capita:.1f} sqft/capita{competitor_text}. "
            "This is a supply-pressure signal; review pipeline, rent pressure, and lease-up assumptions."
        ),
        severity="warning",
    )


def _build_warnings(
    result: SelfStorageResult,
    income_statement_period_months: int | None = None,
    inputs=None,
    criteria: InvestmentCriteria | None = None,
) -> list[VerdictWarning]:
    warnings: list[VerdictWarning] = []
    expense_basis = getattr(result, "expense_basis", None)
    om_noi_mode = expense_basis is not None and expense_basis.source == "om_noi"

    if om_noi_mode:
        warnings.append(
            VerdictWarning(
                key="om_noi_quick_screen",
                message=(
                    "Returns are based on OM-stated NOI. Revenue and expense breakdown "
                    "are not available. Upload a T-12 to verify actual income and expenses."
                ),
                severity="warning",
            )
        )
    elif income_statement_period_months is None:
        warnings.append(
            VerdictWarning(
                key="income_period_unknown",
                message=(
                    "Income statement period is not provided. Results may not reflect "
                    "full-year performance. Upload a T-12 for higher confidence."
                ),
                severity="warning",
            )
        )
    elif 0 < income_statement_period_months <= INCOME_PERIOD_VERY_SHORT_THRESHOLD:
        warnings.append(
            VerdictWarning(
                key="very_short_period_income",
                message=(
                    f"Income data is based on only {income_statement_period_months} month(s), annualized. "
                    "This is highly sensitive to timing and should not be relied on without a fuller T-12. "
                    "Stress test a -10% reduction to GPR before relying on the screen."
                ),
                severity="critical",
            )
        )
    elif 0 < income_statement_period_months < INCOME_PERIOD_FULL_YEAR_MONTHS:
        warnings.append(
            VerdictWarning(
                key="annualized_short_period_income",
                message=(
                    f"Income data is based on a trailing {income_statement_period_months}-month period, annualized. "
                    "If the period includes peak leasing season, annualized GPR may overstate full-year revenue. "
                    "Stress test a -10% reduction to GPR and request a full T-12 before closing."
                ),
                severity="warning",
            )
        )

    # Negative Year 1 NOI
    if result.projections and result.projections[0].noi < 0:
        warnings.append(
            VerdictWarning(
                key="negative_noi_year_one",
                message=(
                    "Year 1 NOI is negative — the property is cash-flow negative before debt service. "
                    "Review expense inputs and revenue assumptions."
                ),
                severity="warning",
            )
        )

    # Expense completeness and basis transparency.
    if inputs is not None and expense_basis is not None:
        if expense_basis.source == "missing":
            warnings.append(
                VerdictWarning(
                    key="expenses_missing",
                    message=(
                        "Operating expense support is missing. The model cannot reliably assess NOI "
                        "until expense line items or a credible expense ratio are provided."
                    ),
                    severity="critical",
                )
            )
        elif expense_basis.source == "om_noi":
            pass
        elif expense_basis.method == "expense_ratio" and expense_basis.period == "pro_forma":
            warnings.append(
                VerdictWarning(
                    key="expenses_ratio_fallback",
                    message=(
                        "Operating expenses are modeled from the OM pro forma expense ratio because "
                        "detailed expense line items were missing or incomplete. Verify against a T-12."
                    ),
                    severity="warning",
                )
            )
        elif expense_basis.method == "expense_ratio":
            warnings.append(
                VerdictWarning(
                    key="expenses_ratio_fallback",
                    message=(
                        f"Operating expenses are modeled from the {expense_basis.label.lower()} because "
                        "detailed expense line items were missing or incomplete."
                    ),
                    severity="info",
                )
            )
    elif inputs is not None:
        op = inputs.operational
        individual_expense_sum = (
            op.property_tax_annual
            + op.insurance_annual
            + op.payroll_annual
            + op.repairs_maintenance_annual
            + op.utilities_annual
        )
        if individual_expense_sum == 0 and op.gross_potential_rent_annual > 0:
            warnings.append(
                VerdictWarning(
                    key="expenses_incomplete",
                    message=(
                        "Individual expense line items appear to be zero or missing. "
                        "Verify all operating expenses are captured."
                    ),
                    severity="critical",
                )
            )

    expense_ratio_warning = _build_expense_ratio_benchmark_warning(result, inputs)
    if expense_ratio_warning:
        warnings.append(expense_ratio_warning)

    # NOI reconciliation: compare computed Year 1 NOI against OM-stated NOI
    if inputs is not None and result.projections and not om_noi_mode:
        noi_computed = result.projections[0].noi
        noi_stated = inputs.operational.noi_year_one_stated
        if (
            noi_computed is not None
            and noi_stated is not None
            and noi_stated > 0
        ):
            deviation = abs(noi_computed - noi_stated) / noi_stated
            if deviation > NOI_RECONCILIATION_GAP_PCT:
                warnings.append(
                    VerdictWarning(
                        key="noi_reconciliation_gap",
                        severity="critical",
                        message=(
                            f"Computed Year 1 NOI (${noi_computed:,.0f}) deviates "
                            f"{deviation:.0%} from OM-stated NOI (${noi_stated:,.0f}). "
                            "Key income fields (other income, vacancy) may not have been fully "
                            "extracted. Review the NOI bridge and re-run if results seem off."
                        ),
                    )
                )

    mixed_revenue_warning = _build_mixed_revenue_warning(result)
    if mixed_revenue_warning:
        warnings.append(mixed_revenue_warning)

    unit_mix_gpr_warning = _build_unit_mix_gpr_warning(inputs)
    if unit_mix_gpr_warning:
        warnings.append(unit_mix_gpr_warning)

    market_supply_warning = _build_market_supply_warning(inputs)
    if market_supply_warning:
        warnings.append(market_supply_warning)

    rollover_floor = _resolve(criteria or InvestmentCriteria(), "rollover_risk_pct")
    if (
        result.rollover_risk
        and result.rollover_risk.pct_rent_expiring_12mo > rollover_floor
    ):
        warnings.append(
            VerdictWarning(
                key="rollover_concentration",
                message=(
                    f"{result.rollover_risk.pct_rent_expiring_12mo:.1%} of rent expires within 12 months, "
                    "which raises rollover concentration risk."
                ),
                severity="warning",
            )
        )

    return warnings


def _build_mixed_revenue_warning(result: SelfStorageResult) -> VerdictWarning | None:
    if not result.unit_mix:
        return None

    non_storage_rows = [row for row in result.unit_mix if _is_non_storage_row(row)]
    if not non_storage_rows:
        return None

    non_storage_units = sum(_row_units(row) for row in non_storage_rows)
    total_units = sum(_row_units(row) for row in result.unit_mix)
    unit_share = non_storage_units / total_units if total_units > 0 else None
    non_storage_rent = _scheduled_rent(non_storage_rows)
    total_rent = _scheduled_rent(result.unit_mix)
    rent_share = non_storage_rent / total_rent if total_rent > 0 else None

    is_material = (
        (unit_share is not None and unit_share >= MIXED_REVENUE_UNIT_SHARE_PCT)
        or (rent_share is not None and rent_share >= MIXED_REVENUE_RENT_SHARE_PCT)
    )

    if non_storage_units > 0 and total_units > 0:
        detail = (
            f"{non_storage_units} of {total_units} units/spaces ({unit_share:.0%}) "
            "appear to be parking or residential"
        )
    else:
        detail = "parking or residential rows appear in the extracted unit mix"
    if rent_share is not None:
        detail += f", representing approximately {rent_share:.0%} of unit-mix scheduled rent"

    material_note = (
        " This is a material non-storage exposure."
        if is_material
        else ""
    )

    return VerdictWarning(
        key="mixed_revenue_material" if is_material else "mixed_revenue_unit_mix",
        message=(
            f"Mixed revenue detected: {detail}.{material_note} The current underwriting model still applies blended self-storage assumptions, "
            "so per-door metrics and growth interpretations should be reviewed manually."
        ),
        severity="warning",
    )


def _build_rationale(
    status: str,
    failures: list[VerdictFailure],
    warnings: list[VerdictWarning],
) -> str:
    """
    Build human-readable rationale for the verdict.

    Args:
        status: "worth_pursuing", "needs_review", or "below_standards"
        failures: List of failed criteria
        warnings: Non-fatal warnings affecting confidence or interpretation

    Returns:
        Human-readable rationale string
    """
    if status == "worth_pursuing":
        rationale = "Passes the initial screen based on current assumptions."
    elif status == "needs_review":
        rationale = (
            "Returns clear the initial screen, but analyst review is required before relying on this result."
        )
    else:
        # List failed metrics
        failed_metrics = []
        for failure in failures:
            if failure.metric == "irr":
                if failure.actual is None:
                    failed_metrics.append(
                        f"IRR did not converge to a usable value against target {failure.target:.1%}"
                    )
                else:
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
                    f"DSCR year one {failure.actual:.2f}x below minimum {failure.target:.2f}x"
                )
            elif failure.metric == "ltv":
                failed_metrics.append(
                    f"LTV {failure.actual:.1%} exceeds maximum {failure.target:.1%}"
                )
            elif failure.metric == "stress_dscr_floor":
                failed_metrics.append(
                    f"Stress scenario DSCR floor {failure.actual:.2f}x below {failure.target:.2f}x minimum"
                )

        rationale = "Deal fails on: " + "; ".join(failed_metrics) + "."

    for warning in warnings:
        rationale += f" Warning: {warning.message}"

    return rationale
