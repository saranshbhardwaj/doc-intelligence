"""CRE-standard merge of per-doc extraction results into SelfStorageInputs dict.

Priority rules (industry standard):
- T-12 actuals win for all operating figures (GPR, vacancy, expenses, NOI)
- Rent Roll wins for unit count, occupancy, lease records, and future in-place unit-mix detail
- OM wins for deal terms (purchase price, exit cap, hold period, LTV, rate)
- OM is the fallback source for unit mix when the rent roll does not provide it
- T-6 figures are annualised: value × (12 / period_months)
"""

from __future__ import annotations

from typing import Any, Optional

from app.utils.logging import logger

from .schemas import (
    ExtractedDocResult,
    OMExtraction,
    RentRollExtraction,
    T12Extraction,
)


def _make_plausibility_flag(doc_type: str, field: str, value: Any, reason: str) -> dict[str, Any]:
    return {
        "doc_type": doc_type,
        "field": field,
        "value": value,
        "reason": reason,
    }


def _invalidate_field(model: Any, doc_type: str, field: str, reason: str, flags: list[dict[str, Any]]) -> None:
    value = getattr(model, field, None)
    if value is None:
        return
    flags.append(_make_plausibility_flag(doc_type, field, value, reason))
    setattr(model, field, None)


def _guard_range(
    model: Any,
    doc_type: str,
    field: str,
    lower: float,
    upper: float,
    flags: list[dict[str, Any]],
    label: str,
) -> None:
    value = getattr(model, field, None)
    if value is None:
        return
    if lower <= value <= upper:
        return
    _invalidate_field(
        model,
        doc_type,
        field,
        f"{label} of {value} is outside the plausible range {lower} to {upper}.",
        flags,
    )


def _guard_positive(
    model: Any,
    doc_type: str,
    field: str,
    flags: list[dict[str, Any]],
    label: str,
) -> None:
    value = getattr(model, field, None)
    if value is None:
        return
    if value > 0:
        return
    _invalidate_field(
        model,
        doc_type,
        field,
        f"{label} must be positive.",
        flags,
    )


def _apply_om_plausibility_guards(om: OMExtraction, flags: list[dict[str, Any]]) -> None:
    _guard_positive(om, "om", "num_units", flags, "Unit count")
    _guard_positive(om, "om", "rentable_sqft", flags, "Rentable square feet")
    _guard_positive(om, "om", "gpr_annual_projected", flags, "Projected annual GPR")
    _guard_range(om, "om", "avg_in_place_rent_per_unit_monthly", 5.0, 2500.0, flags, "Average in-place monthly rent per unit")
    _guard_range(om, "om", "avg_market_rent_per_unit_monthly", 5.0, 2500.0, flags, "Average market monthly rent per unit")
    _guard_range(om, "om", "vacancy_pct_projected", 0.0, 1.0, flags, "Projected vacancy")
    _guard_range(om, "om", "expense_ratio_pro_forma", 0.0, 1.2, flags, "Pro forma expense ratio")
    _guard_range(om, "om", "mgmt_fee_pct", 0.0, 0.25, flags, "Management fee")
    _guard_range(om, "om", "rent_growth_pct", -0.2, 0.2, flags, "Rent growth")
    _guard_range(om, "om", "opex_growth_pct", -0.2, 0.2, flags, "OpEx growth")
    _guard_range(om, "om", "property_tax_growth_pct", -0.2, 0.2, flags, "Property tax growth")
    _guard_range(om, "om", "market_cap_rate_purchase", 0.01, 0.2, flags, "Purchase cap rate")
    _guard_range(om, "om", "market_cap_rate_sale", 0.01, 0.2, flags, "Sale cap rate")
    _guard_range(om, "om", "exit_cap_rate", 0.01, 0.2, flags, "Exit cap rate")
    _guard_range(om, "om", "ltv_pct", 0.0, 1.0, flags, "LTV")
    _guard_range(om, "om", "interest_rate_pct", 0.0, 0.25, flags, "Interest rate")
    _guard_range(om, "om", "physical_occupancy_pct", 0.0, 1.0, flags, "Physical occupancy")
    _guard_range(om, "om", "below_market_tenant_pct", 0.0, 1.0, flags, "Below-market tenant share")
    _guard_range(om, "om", "price_per_rentable_sqft", 5.0, 2500.0, flags, "Price per rentable square foot")

    if om.num_units and om.gpr_annual_projected:
        implied_monthly_rent = om.gpr_annual_projected / om.num_units / 12
        if implied_monthly_rent < 5.0 or implied_monthly_rent > 2500.0:
            _invalidate_field(
                om,
                "om",
                "gpr_annual_projected",
                f"Projected annual GPR implies {implied_monthly_rent:.2f} per unit per month, which is implausible.",
                flags,
            )
        else:
            for field in ("avg_in_place_rent_per_unit_monthly", "avg_market_rent_per_unit_monthly"):
                value = getattr(om, field, None)
                if value is None:
                    continue
                if value > implied_monthly_rent * 5 or value < implied_monthly_rent / 5:
                    _invalidate_field(
                        om,
                        "om",
                        field,
                        f"{field.replace('_', ' ')} of {value} is inconsistent with implied monthly rent {implied_monthly_rent:.2f} from GPR and unit count.",
                        flags,
                    )


def _apply_rent_roll_plausibility_guards(rent_roll: RentRollExtraction, flags: list[dict[str, Any]]) -> None:
    _guard_positive(rent_roll, "rent_roll", "num_units_actual", flags, "Rent roll unit count")
    _guard_range(rent_roll, "rent_roll", "physical_occupancy_pct", 0.0, 1.0, flags, "Rent roll physical occupancy")
    _guard_range(rent_roll, "rent_roll", "avg_in_place_rent_per_unit_monthly", 5.0, 2500.0, flags, "Rent roll average in-place rent")
    _guard_range(rent_roll, "rent_roll", "avg_market_rent_per_unit_monthly", 5.0, 2500.0, flags, "Rent roll average market rent")
    _guard_range(rent_roll, "rent_roll", "rent_growth_pct", -0.2, 0.2, flags, "Rent roll rent growth")


def _apply_t12_plausibility_guards(t12: T12Extraction, flags: list[dict[str, Any]]) -> None:
    _guard_positive(t12, "t12", "gpr_annual_actual", flags, "Actual annual GPR")
    _guard_range(t12, "t12", "vacancy_credit_loss_pct_actual", 0.0, 1.0, flags, "Actual vacancy and credit loss")
    _guard_range(t12, "t12", "expense_ratio_actual", 0.0, 1.2, flags, "Actual expense ratio")
    _guard_range(t12, "t12", "mgmt_fee_pct_actual", 0.0, 0.25, flags, "Actual management fee")
    _guard_range(t12, "t12", "period_months", 1, 12, flags, "Income statement period months")


def apply_plausibility_guards(results: list[ExtractedDocResult]) -> tuple[list[ExtractedDocResult], list[dict[str, Any]]]:
    sanitized_results: list[ExtractedDocResult] = []
    flags: list[dict[str, Any]] = []

    for result in results:
        sanitized = result.model_copy(deep=True)
        if sanitized.om and not sanitized.error:
            _apply_om_plausibility_guards(sanitized.om, flags)
        if sanitized.rent_roll and not sanitized.error:
            _apply_rent_roll_plausibility_guards(sanitized.rent_roll, flags)
        if sanitized.t12 and not sanitized.error:
            _apply_t12_plausibility_guards(sanitized.t12, flags)
        sanitized_results.append(sanitized)

    return sanitized_results, flags


def _derived_t12_expense_ratio(t12: Optional[T12Extraction], factor: float) -> Optional[float]:
    if not t12:
        return None
    if t12.expense_ratio_actual is not None:
        return t12.expense_ratio_actual

    total_revenue = ((t12.gpr_annual_actual or 0) + (t12.other_income_annual or 0)) * factor
    if total_revenue <= 0:
        return None

    total_opex = sum(
        (value or 0) * factor
        for value in [
            t12.property_tax_annual,
            t12.insurance_annual,
            t12.payroll_annual,
            t12.repairs_maintenance_annual,
            t12.utilities_annual,
            t12.marketing_annual,
            t12.other_opex_annual,
        ]
    )
    if t12.mgmt_fee_pct_actual is not None:
        total_opex += total_revenue * t12.mgmt_fee_pct_actual
    return total_opex / total_revenue if total_opex > 0 else None


def _om_other_opex_total(om: Optional[OMExtraction]) -> Optional[float]:
    if not om:
        return None

    components = [
        om.expense_office_admin_annual,
        om.expense_bank_fees_annual,
        om.expense_contract_services_annual,
        om.expense_miscellaneous_annual,
        om.expense_telephone_annual,
    ]
    present = [value for value in components if value is not None]
    if not present:
        return None
    return sum(present)


def _om_total_revenue(om: Optional[OMExtraction]) -> Optional[float]:
    if not om:
        return None
    total_revenue = (om.gpr_annual_projected or 0) + (om.other_income_annual or 0)
    return total_revenue if total_revenue > 0 else None


def _derived_om_mgmt_fee_pct(om: Optional[OMExtraction]) -> Optional[float]:
    if not om or om.expense_mgmt_fee_annual is None:
        return None
    total_revenue = _om_total_revenue(om)
    if total_revenue is None:
        return None
    return om.expense_mgmt_fee_annual / total_revenue


def _derived_om_expense_ratio(om: Optional[OMExtraction]) -> Optional[float]:
    if not om:
        return None
    if om.expense_ratio_pro_forma is not None:
        return om.expense_ratio_pro_forma

    total_revenue = _om_total_revenue(om)
    if total_revenue is None:
        return None

    line_items = [
        om.expense_property_tax_annual,
        om.expense_insurance_annual,
        om.expense_payroll_annual,
        om.expense_repairs_maintenance_annual,
        om.expense_utilities_annual,
        om.expense_marketing_annual,
        _om_other_opex_total(om),
        om.expense_mgmt_fee_annual,
    ]
    present = [value for value in line_items if value is not None]
    if not present:
        return None

    total_opex = sum(present)
    return total_opex / total_revenue if total_opex > 0 else None


def merge_extractions(
    results: list[ExtractedDocResult],
) -> tuple[dict, dict]:
    """Merge per-doc extraction results into a SelfStorageInputs-compatible dict.

    Returns:
        (merged_inputs_dict, field_citations_dict)
        field_citations_dict keys are output field names; values have doc_type, confidence, citations, source_text.
    """
    sanitized_results, _ = apply_plausibility_guards(results)

    om: Optional[OMExtraction] = None
    t12: Optional[T12Extraction] = None
    rr: Optional[RentRollExtraction] = None
    per_doc_citations: dict[str, dict] = {}  # doc_type → {field: citation_data}

    for r in sanitized_results:
        if r.field_citations:
            per_doc_citations[r.doc_type] = r.field_citations
        if r.doc_type == "om" and r.om and not r.error:
            om = r.om
        elif r.doc_type == "t12" and r.t12 and not r.error:
            t12 = r.t12
        elif r.doc_type == "rent_roll" and r.rent_roll and not r.error:
            rr = r.rent_roll

    merged, field_citations = _build_merged_inputs(om, t12, rr, per_doc_citations)
    return merged, field_citations


def _cited(
    per_doc_citations: dict,
    doc_type: str,
    field: str,
    output_field: str | None = None,
) -> dict:
    """Build a citation entry for the winning field from the given doc_type."""
    cdata = per_doc_citations.get(doc_type, {}).get(field, {})
    return {
        "doc_type": doc_type,
        "confidence": cdata.get("confidence", 0.0),
        "citations":  cdata.get("citations", []),
        "source_text": cdata.get("source_text"),
        "is_default": not bool(cdata),  # True when AI found nothing; value is a hardcoded fallback
    }


def _build_merged_inputs(
    om: Optional[OMExtraction],
    t12: Optional[T12Extraction],
    rr: Optional[RentRollExtraction],
    per_doc_citations: dict,
) -> tuple[dict, dict]:
    """Apply CRE priority rules and produce a SelfStorageInputs-compatible dict.

    Returns (merged_inputs, field_citations).
    """
    citations: dict = {}

    # T-6 annualisation factor
    t12_factor = 1.0
    if t12 and t12.period_months and t12.period_months > 0 and t12.period_months < 12:
        t12_factor = 12.0 / t12.period_months
        if t12.period_months < 3:
            import logging
            logging.getLogger(__name__).warning(
                "Income statement is only %d month(s) — annualized figures may be "
                "highly unrepresentative. A T-12 or T-6 is strongly recommended.",
                t12.period_months,
            )

    def ann(val: Optional[float]) -> Optional[float]:
        return val * t12_factor if val is not None else None

    def pick(output_field: str, *candidates: tuple) -> Any:
        """Pick first non-None candidate. Each candidate is (value, doc_type, src_field).
        Records citation for the winning candidate."""
        for val, doc_type, src_field in candidates:
            if val is not None:
                citations[output_field] = _cited(per_doc_citations, doc_type, src_field)
                return val
        return None

    merged = {
        "project": {
            "name": pick("name",
                (om.name if om else None, "om", "name"),
            ) or "Untitled Deal",
            "asset_type": "self_storage",
            "address": pick("address",
                (om.address if om else None, "om", "address"),
            ),
            "num_units": pick("num_units",
                (rr.num_units_actual if rr else None, "rent_roll", "num_units_actual"),
                (om.num_units if om else None, "om", "num_units"),
            ),
            "rentable_sqft": pick("rentable_sqft",
                (om.rentable_sqft if om else None, "om", "rentable_sqft"),
            ),
            "year_built": pick("year_built",
                (om.year_built if om else None, "om", "year_built"),
            ),
            "nearby_storage_count_1mi": pick("nearby_storage_count_1mi",
                (om.nearby_storage_count_1mi if om else None, "om", "nearby_storage_count_1mi"),
            ),
            "nearby_storage_count_3mi": pick("nearby_storage_count_3mi",
                (om.nearby_storage_count_3mi if om else None, "om", "nearby_storage_count_3mi"),
            ),
            "nearby_storage_count_5mi": pick("nearby_storage_count_5mi",
                (om.nearby_storage_count_5mi if om else None, "om", "nearby_storage_count_5mi"),
            ),
            "population_3mi": pick("population_3mi",
                (om.population_3mi if om else None, "om", "population_3mi"),
            ),
            "avg_household_income_3mi": pick("avg_household_income_3mi",
                (om.avg_household_income_3mi if om else None, "om", "avg_household_income_3mi"),
            ),
            "storage_sqft_per_capita_3mi": pick("storage_sqft_per_capita_3mi",
                (om.storage_sqft_per_capita_3mi if om else None, "om", "storage_sqft_per_capita_3mi"),
            ),
        },
        "acquisition": {
            "purchase_price": pick("purchase_price",
                (om.purchase_price if om else None, "om", "purchase_price"),
                (0.0, "om", "purchase_price"),
            ),
            "closing_cost_pct": pick("closing_cost_pct",
                (om.closing_cost_pct if om else None, "om", "closing_cost_pct"),
                (0.02, "om", "closing_cost_pct"),
            ),
            "market_cap_rate_purchase": pick("market_cap_rate_purchase",
                (om.market_cap_rate_purchase if om else None, "om", "market_cap_rate_purchase"),
            ),
            "capex_reserve_per_unit": pick("capex_reserve_per_unit",
                (om.capex_reserve_per_unit if om else None, "om", "capex_reserve_per_unit"),
                (0.0, "om", "capex_reserve_per_unit"),
            ),
        },
        "operational": {
            "gross_potential_rent_annual": pick("gross_potential_rent_annual",
                (ann(t12.gpr_annual_actual) if t12 else None, "t12", "gpr_annual_actual"),
                (om.gpr_annual_projected if om else None, "om", "gpr_annual_projected"),
                (0.0, "om", "gpr_annual_projected"),
            ),
            "avg_in_place_rent_per_unit_monthly": pick("avg_in_place_rent_per_unit_monthly",
                (rr.avg_in_place_rent_per_unit_monthly if rr else None, "rent_roll", "avg_in_place_rent_per_unit_monthly"),
                (om.avg_in_place_rent_per_unit_monthly if om else None, "om", "avg_in_place_rent_per_unit_monthly"),
            ),
            "avg_market_rent_per_unit_monthly": pick("avg_market_rent_per_unit_monthly",
                (rr.avg_market_rent_per_unit_monthly if rr else None, "rent_roll", "avg_market_rent_per_unit_monthly"),
                (om.avg_market_rent_per_unit_monthly if om else None, "om", "avg_market_rent_per_unit_monthly"),
            ),
            "vacancy_credit_loss_pct": pick("vacancy_credit_loss_pct",
                (t12.vacancy_credit_loss_pct_actual if t12 else None, "t12", "vacancy_credit_loss_pct_actual"),
                (om.vacancy_pct_projected if om else None, "om", "vacancy_pct_projected"),
                (0.10, "om", "vacancy_pct_projected"),
            ),
            "expense_ratio_current": pick("expense_ratio_current",
                (_derived_t12_expense_ratio(t12, t12_factor), "t12", "expense_ratio_actual"),
                (_derived_om_expense_ratio(om), "om", "expense_ratio_pro_forma"),
            ),
            "expense_ratio_pro_forma": pick("expense_ratio_pro_forma",
                (om.expense_ratio_pro_forma if om else None, "om", "expense_ratio_pro_forma"),
            ),
            "other_income_annual": pick("other_income_annual",
                (ann(t12.other_income_annual) if t12 else None, "t12", "other_income_annual"),
                (om.other_income_annual if om else None, "om", "other_income_annual"),
                (0.0, "t12", "other_income_annual"),
            ),
            "bad_debt_annual": pick("bad_debt_annual",
                (ann(t12.bad_debt_annual) if t12 else None, "t12", "bad_debt_annual"),
            ),
            "corrections_collections_annual": pick("corrections_collections_annual",
                (ann(t12.corrections_collections_annual) if t12 else None, "t12", "corrections_collections_annual"),
            ),
            "rent_growth_pct": pick("rent_growth_pct",
                (rr.rent_growth_pct if rr else None, "rent_roll", "rent_growth_pct"),
                (om.rent_growth_pct if om else None, "om", "rent_growth_pct"),
                (0.03, "rent_roll", "rent_growth_pct"),
            ),
            "property_tax_annual": pick("property_tax_annual",
                (ann(t12.property_tax_annual) if t12 else None, "t12", "property_tax_annual"),
                (om.expense_property_tax_annual if om else None, "om", "expense_property_tax_annual"),
                (0.0, "t12", "property_tax_annual"),
            ),
            "insurance_annual": pick("insurance_annual",
                (ann(t12.insurance_annual) if t12 else None, "t12", "insurance_annual"),
                (om.expense_insurance_annual if om else None, "om", "expense_insurance_annual"),
                (0.0, "t12", "insurance_annual"),
            ),
            "mgmt_fee_pct": pick("mgmt_fee_pct",
                (t12.mgmt_fee_pct_actual if t12 else None, "t12", "mgmt_fee_pct_actual"),
                (om.mgmt_fee_pct if om else None, "om", "mgmt_fee_pct"),
                (_derived_om_mgmt_fee_pct(om), "om", "expense_mgmt_fee_annual"),
                (0.08, "om", "mgmt_fee_pct"),
            ),
            "payroll_annual": pick("payroll_annual",
                (ann(t12.payroll_annual) if t12 else None, "t12", "payroll_annual"),
                (om.expense_payroll_annual if om else None, "om", "expense_payroll_annual"),
                (0.0, "t12", "payroll_annual"),
            ),
            "repairs_maintenance_annual": pick("repairs_maintenance_annual",
                (ann(t12.repairs_maintenance_annual) if t12 else None, "t12", "repairs_maintenance_annual"),
                (om.expense_repairs_maintenance_annual if om else None, "om", "expense_repairs_maintenance_annual"),
                (0.0, "t12", "repairs_maintenance_annual"),
            ),
            "utilities_annual": pick("utilities_annual",
                (ann(t12.utilities_annual) if t12 else None, "t12", "utilities_annual"),
                (om.expense_utilities_annual if om else None, "om", "expense_utilities_annual"),
                (0.0, "t12", "utilities_annual"),
            ),
            "marketing_annual": pick("marketing_annual",
                (ann(t12.marketing_annual) if t12 else None, "t12", "marketing_annual"),
                (om.expense_marketing_annual if om else None, "om", "expense_marketing_annual"),
                (0.0, "t12", "marketing_annual"),
            ),
            "other_opex_annual": pick("other_opex_annual",
                (ann(t12.other_opex_annual) if t12 else None, "t12", "other_opex_annual"),
                (_om_other_opex_total(om), "om", "expense_miscellaneous_annual"),
                (0.0, "t12", "other_opex_annual"),
            ),
            "property_tax_growth_pct": pick("property_tax_growth_pct",
                (om.property_tax_growth_pct if om else None, "om", "property_tax_growth_pct"),
            ),
            "mil_rate": pick("mil_rate",
                (om.mil_rate if om else None, "om", "mil_rate"),
            ),
            "opex_growth_pct": pick("opex_growth_pct",
                (om.opex_growth_pct if om else None, "om", "opex_growth_pct"),
                (0.02, "om", "opex_growth_pct"),
            ),
        },
        "financing": {
            "ltv_pct": pick("ltv_pct",
                (om.ltv_pct if om else None, "om", "ltv_pct"),
                (0.70, "om", "ltv_pct"),
            ),
            "interest_rate_pct": pick("interest_rate_pct",
                (om.interest_rate_pct if om else None, "om", "interest_rate_pct"),
                (0.065, "om", "interest_rate_pct"),
            ),
            "amortization_years": pick("amortization_years",
                (om.amortization_years if om else None, "om", "amortization_years"),
                (25, "om", "amortization_years"),
            ),
            "loan_term_years": pick("loan_term_years",
                (om.loan_term_years if om else None, "om", "loan_term_years"),
                (10, "om", "loan_term_years"),
            ),
        },
        "exit": {
            "hold_period_years": pick("hold_period_years",
                (om.hold_period_years if om else None, "om", "hold_period_years"),
                (10, "om", "hold_period_years"),
            ),
            "market_cap_rate_sale": pick("market_cap_rate_sale",
                (om.market_cap_rate_sale if om else None, "om", "market_cap_rate_sale"),
            ),
            "exit_cap_rate": pick("exit_cap_rate",
                (om.exit_cap_rate if om else None, "om", "exit_cap_rate"),
                (0.065, "om", "exit_cap_rate"),
            ),
            "selling_cost_pct": pick("selling_cost_pct",
                (om.selling_cost_pct if om else None, "om", "selling_cost_pct"),
                (0.03, "om", "selling_cost_pct"),
            ),
        },
        "criteria": {
            "target_irr": pick("target_irr",
                (om.target_irr if om else None, "om", "target_irr"),
                (0.15, "om", "target_irr"),
            ),
            "target_cash_on_cash": pick("target_cash_on_cash",
                (om.target_cash_on_cash if om else None, "om", "target_cash_on_cash"),
                (0.08, "om", "target_cash_on_cash"),
            ),
            "target_equity_multiple": pick("target_equity_multiple",
                (om.target_equity_multiple if om else None, "om", "target_equity_multiple"),
                (2.0, "om", "target_equity_multiple"),
            ),
            "max_ltv": 0.80,
        },
        "lease_records": [
            lr.model_dump() for lr in (rr.lease_records if rr else [])
        ],
        "unit_mix": [
            row.model_dump() for row in ((rr.unit_mix if rr and rr.unit_mix else (om.unit_mix if om else [])))
        ],
        "rent_comps": [
            row.model_dump() for row in (om.rent_comps if om else [])
        ],
    }

    return merged, citations
