"""
Commercial real estate NOI buildup and return metrics calculator.
Uses numpy_financial for IRR/PMT calculations.
"""

from __future__ import annotations

import math
import re

import numpy_financial as npf

from .schemas.self_storage import (
    AnnualProjection,
    CapitalStructure,
    RentCompRow,
    RentPositionRow,
    SelfStorageInputs,
    SelfStorageResult,
    SensitivityPoint,
    TotalReturn,
    UnitMixRow,
)


def _normalize_size_label(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.lower().replace("×", "x")
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"[^0-9xa-z]", "", normalized)
    return normalized or None


def _row_label(*parts: str | None) -> str:
    return " ".join((part or "").strip().lower() for part in parts if part).strip()


def _is_storage_row(row: UnitMixRow) -> bool:
    if row.unit_category is not None:
        return row.unit_category == "storage"
    # Fallback for rows extracted before unit_category was introduced
    label = _row_label(row.section, row.unit_type)
    if not label:
        return True
    return not any(keyword in label for keyword in ("parking", "residential", "apartment", "office"))


def _is_climate_control_row(row: UnitMixRow) -> bool:
    if row.climate_type is not None:
        return row.climate_type == "CC"
    # Fallback for rows extracted before climate_type was introduced
    label = _row_label(row.section, row.unit_type)
    if re.search(r"\bnon[- ]?climate\b|\bnon[- ]?temp\b|\bnc\b|\bdrive[- ]?up\b", label):
        return False
    return bool(re.search(r"\bclimate\b|\bcc\b|\btemp[- ]?controlled\b|\bheated\b|\bhumidity\b", label))


def _resolve_comp_monthly_rent(
    comp: RentCompRow,
    row: UnitMixRow,
) -> float | None:
    if comp.asking_rent is not None and comp.asking_rent > 0:
        return comp.asking_rent

    if comp.rent_per_sqft is not None and comp.rent_per_sqft > 0 and row.standard_sqft and row.standard_sqft > 0:
        return comp.rent_per_sqft * row.standard_sqft
    return None


def _build_rent_position_analysis(
    unit_mix: list[UnitMixRow],
    rent_comps: list[RentCompRow],
) -> list[RentPositionRow]:
    analysis: list[RentPositionRow] = []
    if not unit_mix or not rent_comps:
        return analysis

    for row in unit_mix:
        if not _is_storage_row(row):
            continue

        size_key = _normalize_size_label(row.size)
        if not size_key:
            continue

        is_climate = _is_climate_control_row(row)
        matched_rates: list[float] = []
        for comp in rent_comps:
            if _normalize_size_label(comp.size) != size_key:
                continue
            comp_rate = _resolve_comp_monthly_rent(comp, row)
            if comp_rate is not None and comp_rate > 0:
                matched_rates.append(comp_rate)

        if not matched_rates:
            continue

        comp_average_rent = sum(matched_rates) / len(matched_rates)
        current_ratio = (
            row.current_rent / comp_average_rent
            if row.current_rent is not None and comp_average_rent > 0
            else None
        )
        market_ratio = (
            row.market_rent / comp_average_rent
            if row.market_rent is not None and comp_average_rent > 0
            else None
        )

        analysis.append(
            RentPositionRow(
                size=row.size,
                climate_type="CC" if is_climate else "NC",
                subject_current_rent=row.current_rent,
                subject_market_rent=row.market_rent,
                comp_average_rent=comp_average_rent,
                current_vs_comp_ratio=current_ratio,
                market_vs_comp_ratio=market_ratio,
                comp_count=len(matched_rates),
            )
        )

    return analysis


def calculate(inputs: SelfStorageInputs) -> SelfStorageResult:
    """Run the full underwriting model and return a SelfStorageResult."""

    acq = inputs.acquisition
    op = inputs.operational
    fin = inputs.financing
    ex = inputs.exit
    proj = inputs.project

    purchase_price: float = acq.purchase_price
    hold_years: int = ex.hold_period_years
    exit_cap: float = ex.exit_cap_rate

    if exit_cap <= 0:
        raise ValueError(
            f"exit_cap_rate must be > 0 to compute a sale price (got {exit_cap}). "
            "Set a realistic exit cap rate in the Debt & Exit tab."
        )

    # ── Capital structure ────────────────────────────────────────────────────
    loan_amount = purchase_price * fin.ltv_pct
    down_payment = purchase_price * (1.0 - fin.ltv_pct)
    closing_cost = purchase_price * acq.closing_cost_pct
    capex_reserve = (
        (proj.num_units or 0) * acq.capex_reserve_per_unit
    )
    total_equity = down_payment + closing_cost + capex_reserve

    capital_structure = CapitalStructure(
        purchase_price=purchase_price,
        down_payment=down_payment,
        loan_amount=loan_amount,
        closing_cost=closing_cost,
        capex_reserve_initial=capex_reserve,
        total_equity_invested=total_equity,
    )

    # ── Debt service ─────────────────────────────────────────────────────────
    has_debt = loan_amount > 0 and fin.interest_rate_pct > 0 and fin.amortization_years > 0

    if has_debt:
        monthly_payment = float(
            npf.pmt(
                rate=fin.interest_rate_pct / 12,
                nper=fin.amortization_years * 12,
                pv=-loan_amount,
            )
        )
        annual_debt_service = monthly_payment * 12
    else:
        monthly_payment = 0.0
        annual_debt_service = 0.0

    # Build amortization schedule month-by-month so we can extract
    # per-year principal paydown and ending loan balance.
    outstanding = loan_amount
    # Pre-compute all monthly splits up to hold_period end (or full amort)
    total_months = hold_years * 12
    monthly_interest: list[float] = []
    monthly_principal: list[float] = []

    for _ in range(total_months):
        if outstanding <= 0:
            monthly_interest.append(0.0)
            monthly_principal.append(0.0)
        else:
            interest_p = outstanding * (fin.interest_rate_pct / 12)
            principal_p = monthly_payment - interest_p
            # Clamp principal in final payment if balance is tiny
            principal_p = min(principal_p, outstanding)
            outstanding -= principal_p
            monthly_interest.append(interest_p)
            monthly_principal.append(principal_p)

    # ── NOI buildup year-by-year ─────────────────────────────────────────────
    # Fixed opex components (before growth) at year 0:
    base_non_tax_opex = (
        op.insurance_annual
        + op.payroll_annual
        + op.repairs_maintenance_annual
        + op.utilities_annual
        + op.marketing_annual
        + op.other_opex_annual
    )
    property_tax_growth = (
        op.property_tax_growth_pct
        if op.property_tax_growth_pct is not None
        else op.opex_growth_pct
    )

    projections: list[AnnualProjection] = []
    prev_prop_value = purchase_price if exit_cap > 0 else 0.0

    for yr in range(1, hold_years + 1):
        n = yr  # 1-indexed

        gpr = op.gross_potential_rent_annual * (1 + op.rent_growth_pct) ** (n - 1)
        vacancy_loss = gpr * op.vacancy_credit_loss_pct
        other_income = op.other_income_annual * (1 + op.rent_growth_pct) ** (n - 1)
        egi = gpr - vacancy_loss + other_income

        property_tax = op.property_tax_annual * (1 + property_tax_growth) ** (n - 1)
        other_fixed_opex = base_non_tax_opex * (1 + op.opex_growth_pct) ** (n - 1)
        fixed_opex = property_tax + other_fixed_opex
        mgmt_fee = egi * op.mgmt_fee_pct
        opex = fixed_opex + mgmt_fee

        noi = egi - opex

        # Property value — guard against zero exit cap
        if exit_cap > 0:
            prop_value = noi / exit_cap
        else:
            prop_value = 0.0

        # Per-year debt data from amortization schedule
        year_months = slice((yr - 1) * 12, yr * 12)
        principal_paydown = sum(monthly_principal[year_months])
        loan_balance = outstanding if yr == hold_years else (
            loan_amount - sum(monthly_principal[: yr * 12])
        )

        cash_flow = noi - annual_debt_service
        appreciation = prop_value - prev_prop_value
        net_worth_increase = cash_flow + principal_paydown + appreciation

        projections.append(
            AnnualProjection(
                year=yr,
                gpr=gpr,
                vacancy_loss=vacancy_loss,
                other_income=other_income,
                egi=egi,
                opex=opex,
                noi=noi,
                debt_service=annual_debt_service,
                cash_flow=cash_flow,
                principal_paydown=principal_paydown,
                property_value=prop_value,
                net_worth_increase=net_worth_increase,
            )
        )
        prev_prop_value = prop_value

    # ── Exit metrics ─────────────────────────────────────────────────────────
    final_noi = projections[-1].noi
    if exit_cap > 0:
        gross_sale_price = final_noi / exit_cap
    else:
        gross_sale_price = 0.0

    net_sale_price = gross_sale_price * (1.0 - ex.selling_cost_pct)

    # Loan balance at end of hold period
    loan_balance_at_exit = loan_amount - sum(monthly_principal[:total_months])
    loan_balance_at_exit = max(loan_balance_at_exit, 0.0)

    cash_flows = [p.cash_flow for p in projections]
    annual_cash_flows_sum = sum(cash_flows)
    total_cash_received = annual_cash_flows_sum + net_sale_price
    total_cash_invested = -total_equity
    total_profit = total_cash_received + total_cash_invested

    total_return = TotalReturn(
        annual_cash_flows_sum=annual_cash_flows_sum,
        net_sale_price=net_sale_price,
        loan_balance_at_exit=loan_balance_at_exit,
        total_cash_received=total_cash_received,
        total_cash_invested=total_cash_invested,
        total_profit=total_profit,
    )

    # ── IRR ──────────────────────────────────────────────────────────────────
    irr: float | None = None
    if total_equity > 0:
        cf_for_irr = (
            [-total_equity]
            + cash_flows[:-1]
            + [cash_flows[-1] + net_sale_price]
        )
        raw_irr = npf.irr(cf_for_irr)
        # npf.irr returns nan when it fails to converge
        if raw_irr is not None and not math.isnan(raw_irr) and not math.isinf(raw_irr):
            irr = float(raw_irr)

    # ── Summary metrics ──────────────────────────────────────────────────────
    cash_on_cash: float | None = None
    equity_multiple: float | None = None
    if total_equity > 0:
        cash_on_cash = projections[0].cash_flow / total_equity
        equity_multiple = (annual_cash_flows_sum + net_sale_price) / total_equity

    dscr_year_one: float | None = None
    if annual_debt_service > 0:
        dscr_year_one = projections[0].noi / annual_debt_service

    # Break-even occupancy: what vacancy rate makes NOI = debt service
    # Rearranging: GPR_yr1 * (1 - vacancy) + other_income - opex = debt_service
    # Solve for vacancy at year-1 rent and expense levels
    # Break-even occupancy: occupancy needed so NOI = debt service at Year 1 levels.
    # NOI = EGI - opex, EGI = GPR*(1-v) + other_income
    # opex = fixed_opex + mgmt_fee*EGI
    # Solve for v: GPR*(1-v)*(1-mgmt_fee) + other_income*(1-mgmt_fee) - fixed_opex = debt_service
    # other_income is revenue, NOT part of fixed_opex — kept only in the denominator.
    break_even_occupancy_pct: float | None = None
    if annual_debt_service > 0 and op.gross_potential_rent_annual > 0:
        fixed_opex_yr1 = op.property_tax_annual + base_non_tax_opex
        numerator = annual_debt_service + fixed_opex_yr1
        denominator = (
            op.gross_potential_rent_annual * (1 - op.mgmt_fee_pct)
            + op.other_income_annual * (1 - op.mgmt_fee_pct)
        )
        if denominator > 0:
            break_even_vacancy = 1 - (numerator / denominator)
            break_even_occupancy_pct = max(0.0, min(1.0, 1 - break_even_vacancy))
        else:
            break_even_occupancy_pct = None
    else:
        break_even_occupancy_pct = None

    cap_rate_year_one = projections[0].noi / purchase_price if purchase_price > 0 else None
    cap_rate_pro_forma = projections[-1].noi / purchase_price if purchase_price > 0 else None
    ltv = loan_amount / purchase_price if purchase_price > 0 else None
    rent_position_analysis = _build_rent_position_analysis(inputs.unit_mix, inputs.rent_comps)

    return SelfStorageResult(
        irr=irr,
        cash_on_cash=cash_on_cash,
        equity_multiple=equity_multiple,
        total_profit=total_profit,
        cap_rate_year_one=cap_rate_year_one,
        cap_rate_pro_forma=cap_rate_pro_forma,
        dscr_year_one=dscr_year_one,
        break_even_occupancy_pct=break_even_occupancy_pct,
        ltv=ltv,
        noi_year_one=projections[0].noi,
        monthly_cashflow=projections[0].cash_flow / 12,
        capital_structure=capital_structure,
        total_return=total_return,
        projections=projections,
        rent_position_analysis=rent_position_analysis,
    )


def calculate_sensitivity(
    inputs: SelfStorageInputs, prices: list[float]
) -> list[SensitivityPoint]:
    """Run calculate() for each purchase price and return sensitivity points."""

    results: list[SensitivityPoint] = []
    for price in prices:
        modified = inputs.model_copy(
            update={
                "acquisition": inputs.acquisition.model_copy(
                    update={"purchase_price": price}
                )
            }
        )
        try:
            result = calculate(modified)
            results.append(
                SensitivityPoint(
                    purchase_price=price,
                    irr=result.irr if result.irr is not None else float("nan"),
                    cash_on_cash=result.cash_on_cash if result.cash_on_cash is not None else float("nan"),
                    dscr_year_one=result.dscr_year_one if result.dscr_year_one is not None else float("nan"),
                    equity_multiple=result.equity_multiple if result.equity_multiple is not None else float("nan"),
                )
            )
        except Exception:
            # Skip prices that cause calculation errors
            continue

    return results
