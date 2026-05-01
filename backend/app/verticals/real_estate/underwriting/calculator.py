"""
Commercial real estate NOI buildup and return metrics calculator.
Uses numpy_financial for IRR/PMT calculations.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import NamedTuple

import numpy_financial as npf

from .schemas.self_storage import (
    AnnualProjection,
    CapitalStructure,
    ExpenseBasis,
    RentCompRow,
    RentPositionRow,
    SelfStorageInputs,
    SelfStorageResult,
    SensitivityPoint,
    TotalReturn,
    UnitMixRow,
)
from .thresholds import LINE_ITEMS_VS_RATIO_CUTOFF


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


_DIMENSION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*$", re.IGNORECASE)
_SCALAR_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:sq\.?\s*ft\.?)?$", re.IGNORECASE)


def _parse_standard_sqft(size: str | None) -> float | None:
    if not size:
        return None
    m = _DIMENSION_RE.match(size)
    if m:
        return float(m.group(1)) * float(m.group(2))
    m = _SCALAR_RE.match(size)
    if m:
        return float(m.group(1))
    return None


def _size_bucket(sqft: float) -> str:
    if sqft <= 0:
        raise ValueError(f"sqft must be positive, got {sqft}")
    if sqft < 25:
        return "locker"
    if sqft < 75:
        return "small"
    if sqft < 150:
        return "medium"
    if sqft < 300:
        return "large"
    return "xlarge"


def _build_rent_position_analysis(
    unit_mix: list[UnitMixRow],
    rent_comps: list[RentCompRow],
) -> tuple[list[RentPositionRow], int]:
    if not unit_mix or not rent_comps:
        return [], 0

    class _CompEntry(NamedTuple):
        bucket: str
        climate: str
        rate: float

    comp_data: list[_CompEntry] = []
    unknown_count = 0
    for comp in rent_comps:
        sqft = comp.standard_sqft or _parse_standard_sqft(comp.size)
        if sqft is None or sqft <= 0:
            continue
        # Treat both None (extractor didn't classify) and "UNKNOWN" (explicitly unclear) as
        # unclassifiable — exclude from matching and surface the count to the UI.
        climate = comp.climate_type or "UNKNOWN"
        if climate == "UNKNOWN":
            unknown_count += 1
            continue
        rate = comp.asking_rent
        if rate is None or rate <= 0:
            continue
        comp_data.append(_CompEntry(_size_bucket(sqft), climate, rate))

    def _weighted_avg(rows: list[UnitMixRow], field: str) -> float | None:
        def weight(r: UnitMixRow) -> int:
            return r.num_units if r.num_units and r.num_units > 0 else 1
        valued = [r for r in rows if getattr(r, field) is not None]
        if not valued:
            return None
        total_w = sum(weight(r) for r in valued)
        return sum(getattr(r, field) * weight(r) for r in valued) / total_w

    cell_rows: dict[tuple[str, str], list[UnitMixRow]] = defaultdict(list)
    for row in unit_mix:
        if not _is_storage_row(row):
            continue
        sqft = row.standard_sqft or _parse_standard_sqft(row.size)
        if sqft is None or sqft <= 0:
            continue
        bucket = _size_bucket(sqft)
        climate = row.climate_type if row.climate_type in ("CC", "NC") else (
            "CC" if _is_climate_control_row(row) else "NC"
        )
        cell_rows[(bucket, climate)].append(row)

    analysis: list[RentPositionRow] = []
    for (bucket, climate), rows in cell_rows.items():
        matched_rates = [e.rate for e in comp_data if e.bucket == bucket and e.climate == climate]
        if not matched_rates:
            continue

        comp_average_rent = sum(matched_rates) / len(matched_rates)
        subject_current = _weighted_avg(rows, "current_rent")
        subject_market = _weighted_avg(rows, "market_rent")
        current_ratio = (
            subject_current / comp_average_rent
            if subject_current is not None and comp_average_rent > 0
            else None
        )
        market_ratio = (
            subject_market / comp_average_rent
            if subject_market is not None and comp_average_rent > 0
            else None
        )

        analysis.append(
            RentPositionRow(
                size=rows[0].size or bucket,
                climate_type=climate,
                subject_current_rent=subject_current,
                subject_market_rent=subject_market,
                comp_average_rent=comp_average_rent,
                current_vs_comp_ratio=current_ratio,
                market_vs_comp_ratio=market_ratio,
                comp_count=len(matched_rates),
                bucket=bucket,
            )
        )

    return analysis, unknown_count


def _positive_ratio(value: float | None) -> bool:
    return value is not None and value > 0


def _stated_om_noi(inputs: SelfStorageInputs) -> float | None:
    """Return the best OM-stated NOI basis available for NOI-only quick screens."""
    if inputs.operational.noi_year_one_stated is not None:
        return inputs.operational.noi_year_one_stated
    return inputs.operational.noi_current_stated


def _resolve_expense_basis(
    inputs: SelfStorageInputs,
    year1_egi: float,
    year1_line_item_opex: float,
) -> ExpenseBasis:
    """Choose the safest available OpEx basis and expose it for analyst review."""

    op = inputs.operational
    ratio_source = None
    ratio_label = None
    ratio = None
    if _positive_ratio(op.expense_ratio_current):
        ratio_source = "expense_ratio_current"
        ratio_label = "Current / T-12 expense ratio"
        ratio = op.expense_ratio_current
    elif _positive_ratio(op.expense_ratio_pro_forma):
        ratio_source = "expense_ratio_pro_forma"
        ratio_label = "OM pro forma expense ratio"
        ratio = op.expense_ratio_pro_forma

    ratio_opex = year1_egi * ratio if ratio is not None and year1_egi > 0 else None
    has_line_items = year1_line_item_opex > 0
    noi_stated = _stated_om_noi(inputs)

    def om_noi_basis() -> ExpenseBasis:
        return ExpenseBasis(
            source="om_noi",
            label="OM-stated NOI quick screen",
            ratio=None,
            year1_line_item_opex=year1_line_item_opex,
            year1_ratio_opex=None,
            reason=(
                f"No reliable GPR/expense build-up is available. Projections use OM-stated NOI "
                f"(${noi_stated or 0:,.0f}) grown at the assumed rent growth rate. "
                "Upload a T-12 to verify actual income and expenses."
            ),
        )

    if ratio_source and ratio_opex is not None:
        if not has_line_items:
            return ExpenseBasis(
                source=ratio_source,
                label=ratio_label,
                ratio=ratio,
                year1_line_item_opex=year1_line_item_opex,
                year1_ratio_opex=ratio_opex,
                reason="Detailed expense line items were missing, so the model used the stated expense ratio.",
            )
        if year1_line_item_opex < ratio_opex * LINE_ITEMS_VS_RATIO_CUTOFF:
            return ExpenseBasis(
                source=ratio_source,
                label=ratio_label,
                ratio=ratio,
                year1_line_item_opex=year1_line_item_opex,
                year1_ratio_opex=ratio_opex,
                reason=(
                    "Detailed expense line items were materially below the ratio-implied expense load, "
                    "so the model used the more conservative expense ratio."
                ),
            )

    if noi_stated and year1_egi <= 0 and not ratio_source:
        return om_noi_basis()

    if has_line_items:
        return ExpenseBasis(
            source="line_items",
            label="Detailed expense line items",
            year1_line_item_opex=year1_line_item_opex,
            year1_ratio_opex=ratio_opex,
            ratio=ratio,
            reason="Operating expenses were modeled from extracted or manually entered line items.",
        )

    if noi_stated and not ratio_source:
        return om_noi_basis()

    return ExpenseBasis(
        source="missing",
        label="Missing expense support",
        ratio=ratio,
        year1_line_item_opex=year1_line_item_opex,
        year1_ratio_opex=ratio_opex,
        reason="No detailed expense line items or usable expense ratio were available.",
    )


def calculate(inputs: SelfStorageInputs) -> SelfStorageResult:
    """Run the full underwriting model and return a SelfStorageResult."""

    acq = inputs.acquisition
    op = inputs.operational
    fin = inputs.financing
    ex = inputs.exit
    proj = inputs.project

    purchase_price = acq.purchase_price
    hold_years: int = ex.hold_period_years
    exit_cap: float = ex.exit_cap_rate

    if purchase_price is None or purchase_price <= 0:
        raise ValueError("purchase_price required and must be > 0")

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
    year1_gpr = op.gross_potential_rent_annual
    year1_vacancy_loss = year1_gpr * op.vacancy_credit_loss_pct
    year1_other_income = op.other_income_annual
    year1_egi = year1_gpr - year1_vacancy_loss + year1_other_income
    year1_fixed_opex = op.property_tax_annual + base_non_tax_opex
    year1_line_item_opex = year1_fixed_opex + (year1_egi * op.mgmt_fee_pct)
    expense_basis = _resolve_expense_basis(inputs, year1_egi, year1_line_item_opex)

    projections: list[AnnualProjection] = []
    prev_prop_value = purchase_price if exit_cap > 0 else 0.0

    for yr in range(1, hold_years + 1):
        n = yr  # 1-indexed

        if expense_basis.source == "om_noi":
            noi_stated = _stated_om_noi(inputs) or 0.0
            noi = noi_stated * (1 + op.rent_growth_pct) ** (n - 1)
            gpr = 0.0
            vacancy_loss = 0.0
            other_income = 0.0
            egi = noi
            opex = 0.0
        else:
            gpr = op.gross_potential_rent_annual * (1 + op.rent_growth_pct) ** (n - 1)
            vacancy_loss = gpr * op.vacancy_credit_loss_pct
            other_income = op.other_income_annual * (1 + op.rent_growth_pct) ** (n - 1)
            egi = gpr - vacancy_loss + other_income

            if expense_basis.source in ("expense_ratio_current", "expense_ratio_pro_forma"):
                opex = (expense_basis.year1_ratio_opex or 0.0) * (1 + op.opex_growth_pct) ** (n - 1)
            else:
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
    # Equity extracted from sale = net sale price after paying off remaining loan
    equity_from_sale = max(net_sale_price - loan_balance_at_exit, 0.0)
    total_cash_received = annual_cash_flows_sum + equity_from_sale
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
            + [cash_flows[-1] + equity_from_sale]
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
        equity_multiple = (annual_cash_flows_sum + equity_from_sale) / total_equity

    dscr_year_one: float | None = None
    if annual_debt_service > 0:
        dscr_year_one = projections[0].noi / annual_debt_service

    # Break-even occupancy: minimum occupancy so Year-1 NOI covers debt service.
    break_even_occupancy_pct: float | None = None
    if expense_basis.source == "om_noi":
        break_even_occupancy_pct = None
    elif annual_debt_service > 0 and op.gross_potential_rent_annual > 0:
        if expense_basis.source in ("expense_ratio_current", "expense_ratio_pro_forma") and expense_basis.ratio is not None:
            noi_margin = 1 - expense_basis.ratio
            if noi_margin > 0:
                required_egi = annual_debt_service / noi_margin
                break_even_occupancy_pct = max(
                    0.0,
                    min(1.0, (required_egi - op.other_income_annual) / op.gross_potential_rent_annual),
                )
        else:
            fixed_opex_yr1 = op.property_tax_annual + base_non_tax_opex
            mgmt_factor = 1 - op.mgmt_fee_pct
            adjusted_numerator = (
                annual_debt_service + fixed_opex_yr1
                - op.other_income_annual * mgmt_factor
            )
            denominator = op.gross_potential_rent_annual * mgmt_factor
            if denominator > 0:
                break_even_occupancy_pct = max(0.0, min(1.0, adjusted_numerator / denominator))
            else:
                break_even_occupancy_pct = None
    else:
        break_even_occupancy_pct = None

    cap_rate_year_one = projections[0].noi / purchase_price if purchase_price > 0 else None
    cap_rate_pro_forma = projections[-1].noi / purchase_price if purchase_price > 0 else None
    ltv = loan_amount / purchase_price if purchase_price > 0 else None
    rent_position_analysis, unknown_climate_comp_count = _build_rent_position_analysis(inputs.unit_mix, inputs.rent_comps)

    # Build formula metadata — backend is the authority
    from .schemas.self_storage import FormulaMetadata, FormulaComputedValues

    fixed_opex_yr1 = op.property_tax_annual + base_non_tax_opex
    mgmt_factor_yr1 = 1 - op.mgmt_fee_pct
    if expense_basis.source == "om_noi":
        break_even_description = (
            "Break-even occupancy is not computed in OM-stated NOI quick-screen mode "
            "because GPR, vacancy, and expense components are not available."
        )
    elif expense_basis.source in ("expense_ratio_current", "expense_ratio_pro_forma"):
        break_even_description = (
            "Debt service ÷ (1 − expense ratio), adjusted for other income, then divided by GPR. "
            "Used when operating expenses are modeled from an expense-ratio fallback."
        )
    else:
        break_even_description = "(Debt service + fixed opex − other income × (1 − mgmt fee)) ÷ (GPR × (1 − mgmt fee)). Minimum occupancy so Year-1 cash flow after debt service equals zero."

    formula_metadata = {
        "irr": FormulaMetadata(
            description="Annualized return on equity across the full hold, accounting for timing of every cash flow in and out.",
            computed_values=FormulaComputedValues(
                entry_equity=float(total_equity),
                total_distributions=float(annual_cash_flows_sum),
                exit_proceeds=float(equity_from_sale),
                loan_balance_at_exit=float(loan_balance_at_exit),
                hold_years=float(hold_years),
            ),
        ),
        "cash_on_cash": FormulaMetadata(
            description="Year 1 cash flow after debt service ÷ total equity invested. Income yield only — excludes appreciation and principal paydown.",
            computed_values=FormulaComputedValues(
                year1_cash_flow=float(projections[0].cash_flow) if projections else None,
                total_equity=float(total_equity),
                annual_debt_service=float(annual_debt_service) if annual_debt_service > 0 else None,
            ),
        ),
        "equity_multiple": FormulaMetadata(
            description="Total cash received by equity investor (operating distributions + net sale proceeds after debt repayment) ÷ equity invested.",
            computed_values=FormulaComputedValues(
                total_cash_flows=float(annual_cash_flows_sum),
                equity_from_sale=float(equity_from_sale),
                loan_balance_at_exit=float(loan_balance_at_exit),
                net_sale_price=float(net_sale_price),
                total_equity=float(total_equity),
                hold_years=float(hold_years),
            ),
        ),
        "dscr_year_one": FormulaMetadata(
            description="Year 1 NOI ÷ annual debt service. Below 1.25× lenders typically won't fund; below 1.0× the property can't pay its own mortgage.",
            computed_values=FormulaComputedValues(
                year1_noi=float(projections[0].noi) if projections else None,
                annual_debt_service=float(annual_debt_service) if annual_debt_service > 0 else None,
            ),
        ),
        "break_even_occupancy": FormulaMetadata(
            description=break_even_description,
            computed_values=FormulaComputedValues(
                debt_service=float(annual_debt_service) if annual_debt_service > 0 else None,
                fixed_opex=float(fixed_opex_yr1),
                expense_ratio=float(expense_basis.ratio) if expense_basis.ratio is not None else None,
                other_income_adj=float(op.other_income_annual * mgmt_factor_yr1),
                gpr_adj=float(op.gross_potential_rent_annual * mgmt_factor_yr1),
            ),
        ),
        "expense_basis": FormulaMetadata(
            description=expense_basis.reason,
            computed_values=FormulaComputedValues(
                source=expense_basis.source,
                ratio=float(expense_basis.ratio) if expense_basis.ratio is not None else None,
                year1_line_item_opex=float(expense_basis.year1_line_item_opex) if expense_basis.year1_line_item_opex is not None else None,
                year1_ratio_opex=float(expense_basis.year1_ratio_opex) if expense_basis.year1_ratio_opex is not None else None,
                year1_egi=float(year1_egi),
            ),
        ),
        "avg_current_rent_per_door": FormulaMetadata(
            description="Gross potential rent ÷ total units ÷ 12. Monthly in-place rent per unit.",
            computed_values=FormulaComputedValues(
                gpr=float(op.gross_potential_rent_annual),
                num_units=float(proj.num_units) if proj.num_units is not None else None,
            ),
        ),
        "avg_market_rent_per_door": FormulaMetadata(
            description="Average market-rate asking rent per unit per month, sourced from the OM or rent roll.",
            computed_values=FormulaComputedValues(
                market_rate=float(op.avg_market_rent_per_unit_monthly) if op.avg_market_rent_per_unit_monthly else None,
            ),
        ),
        "pro_forma_expense_ratio": FormulaMetadata(
            description="Total operating expenses as a % of effective gross income, per OM or broker underwriting. Verify against T-12 actuals.",
            computed_values=FormulaComputedValues(
                pro_forma_expense_pct=float(op.expense_ratio_pro_forma) if op.expense_ratio_pro_forma else None,
                gpr=float(op.gross_potential_rent_annual),
            ),
        ),
    }

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
        expense_basis=expense_basis,
        capital_structure=capital_structure,
        total_return=total_return,
        projections=projections,
        rent_position_analysis=rent_position_analysis,
        unknown_climate_comp_count=unknown_climate_comp_count,
        formula_metadata=formula_metadata,
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
