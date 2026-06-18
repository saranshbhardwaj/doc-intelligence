"""CRE-standard merge of per-doc extraction results into SelfStorageInputs dict.

Priority rules (industry standard):
- T-12 actuals win for all operating figures (GPR, vacancy, expenses, NOI)
- Rent Roll wins for unit count, occupancy, lease records, and future in-place unit-mix detail
- OM wins for deal terms (purchase price, exit cap, hold period, LTV, rate)
- OM is the fallback source for unit mix when the rent roll does not provide it
- T-6 figures are annualised: value × (12 / period_months)
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
import re
from typing import Any, Optional

from .schemas import (
    ExtractedDocResult,
    OMExtraction,
    RentRollExtraction,
    T12Extraction,
)
from ..benchmarks import get_expense_floors


DEFAULT_HOLD_PERIOD_YEARS = 5
DEFAULT_EXIT_CAP_RATE = 0.08
DEFAULT_EXIT_CAP_SPREAD = 0.005
PRO_FORMA_CAP_RATE_RE = re.compile(r"\b(pro\s*forma|stabili[sz]ed)\b.{0,40}\bcap\s*rate\b", re.IGNORECASE)
SALE_CAP_RATE_RE = re.compile(r"\b(exit|terminal|going[-\s]*out|sale|disposition)\b.{0,40}\bcap\s*rate\b", re.IGNORECASE)


@dataclass(slots=True)
class MergeCandidate:
    value: Any
    doc_type: str
    source_field: str
    formula: str | None = None
    is_default_candidate: bool = False
    is_computed: bool = False
    metadata: dict[str, Any] = dc_field(default_factory=dict)


def _candidate(
    value: Any,
    doc_type: str,
    source_field: str,
    formula: str | None = None,
    is_default_candidate: bool = False,
    is_computed: bool = False,
    metadata: dict[str, Any] | None = None,
) -> MergeCandidate:
    return MergeCandidate(
        value=value,
        doc_type=doc_type,
        source_field=source_field,
        formula=formula,
        is_default_candidate=is_default_candidate,
        is_computed=is_computed,
        metadata=dict(metadata) if metadata else {},
    )


def _infer_source_period(doc_type: str | None, field: str | None) -> str:
    if doc_type == "t12":
        return "t12"
    if not field:
        return "unknown"
    if field.endswith("_year1") or "_year1_" in field:
        return "year1"
    if field.endswith("_current") or "_current_" in field:
        return "current"
    if field.endswith("_pro_forma") or "_pro_forma_" in field:
        return "pro_forma"
    if field.endswith("_actual") or "_actual_" in field:
        return "t12"
    return "unknown"


def _infer_source_method(doc_type: str | None, field: str | None, is_computed: bool = False) -> str:
    if doc_type == "benchmark":
        return "benchmark"
    if is_computed or doc_type == "derived":
        return "computed"
    if not field:
        return "unknown"
    if field.startswith("expense_ratio"):
        return "expense_ratio"
    if field.startswith("expense_") and "_annual" in field:
        return "line_item"
    if field.startswith("noi_"):
        return "noi"
    return "extracted"


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
    _guard_positive(om, "om", "property_tax_value_basis_amount", flags, "Property tax value basis")
    _guard_positive(om, "om", "property_tax_assessed_value", flags, "Property tax assessed value")
    _guard_range(om, "om", "property_tax_assessment_ratio", 0.0, 1.0, flags, "Property tax assessment ratio")
    _guard_positive(om, "om", "property_tax_millage_rate", flags, "Property tax millage rate")
    _guard_positive(om, "om", "property_tax_rate_per_assessed_dollar", flags, "Property tax rate per assessed dollar")
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


def _is_pro_forma_cap_rate_source(source_text: str | None) -> bool:
    if not source_text:
        return False
    return bool(PRO_FORMA_CAP_RATE_RE.search(source_text) and not SALE_CAP_RATE_RE.search(source_text))


def _apply_om_cap_rate_label_guards(
    om: OMExtraction,
    field_citations: dict,
    flags: list[dict[str, Any]],
) -> None:
    """Reject broker pro forma/stabilized cap rates when misclassified as sale cap assumptions."""

    for field in ("exit_cap_rate", "market_cap_rate_sale"):
        if getattr(om, field, None) is None:
            continue
        source_text = (field_citations.get(field) or {}).get("source_text")
        if not _is_pro_forma_cap_rate_source(source_text):
            continue
        _invalidate_field(
            om,
            "om",
            field,
            (
                f"{field.replace('_', ' ')} was sourced from a broker pro forma/stabilized cap-rate label, "
                "not an explicit exit, terminal, going-out, sale, or disposition cap rate."
            ),
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
            _apply_om_cap_rate_label_guards(sanitized.om, sanitized.field_citations or {}, flags)
        if sanitized.rent_roll and not sanitized.error:
            _apply_rent_roll_plausibility_guards(sanitized.rent_roll, flags)
        if sanitized.t12 and not sanitized.error:
            _apply_t12_plausibility_guards(sanitized.t12, flags)
        sanitized_results.append(sanitized)

    return sanitized_results, flags


def _derived_t12_expense_ratio_details(
    t12: Optional[T12Extraction],
    factor: float,
) -> tuple[Optional[float], Optional[str], bool]:
    if not t12:
        return None, None, False
    if t12.expense_ratio_actual is not None:
        return t12.expense_ratio_actual, None, False

    total_revenue = ((t12.gpr_annual_actual or 0) + (t12.other_income_annual or 0)) * factor
    if total_revenue <= 0:
        return None, None, False

    line_items = [
        ("property tax", t12.property_tax_annual),
        ("insurance", t12.insurance_annual),
        ("payroll", t12.payroll_annual),
        ("repairs & maintenance", t12.repairs_maintenance_annual),
        ("utilities", t12.utilities_annual),
        ("marketing", t12.marketing_annual),
        ("other OpEx", t12.other_opex_annual),
    ]
    annualized_items = [
        (label, value * factor)
        for label, value in line_items
        if value is not None
    ]
    total_opex = sum(value for _, value in annualized_items)
    formula_parts = [f"${value:,.0f} {label}" for label, value in annualized_items if value]
    if t12.mgmt_fee_pct_actual is not None:
        mgmt_fee = total_revenue * t12.mgmt_fee_pct_actual
        total_opex += mgmt_fee
        if mgmt_fee:
            formula_parts.append(f"${mgmt_fee:,.0f} management fee")
    if total_opex <= 0:
        return None, None, False
    formula = f"({' + '.join(formula_parts)}) ÷ ${total_revenue:,.0f} total revenue"
    return total_opex / total_revenue, formula, True


def _derived_t12_expense_ratio(t12: Optional[T12Extraction], factor: float) -> Optional[float]:
    ratio, _, _ = _derived_t12_expense_ratio_details(t12, factor)
    return ratio


def _om_other_income_total(om: Optional[OMExtraction]) -> Optional[float]:
    if not om:
        return None
    if om.other_income_annual is not None:
        return om.other_income_annual
    # Fallback: sum individual components if any were extracted
    components = [
        om.other_income_admin_fees_annual,
        om.other_income_late_fees_annual,
        om.other_income_insurance_annual,
        om.other_income_misc_annual,
    ]
    present = [v for v in components if v is not None]
    return sum(present) if present else None


def _om_other_opex_total(om: Optional[OMExtraction]) -> Optional[float]:
    if not om:
        return None

    present = [value for _, value in _om_other_opex_components(om)]
    if not present:
        return None
    return sum(present)


def _om_other_opex_components(om: Optional[OMExtraction]) -> list[tuple[str, float]]:
    if not om:
        return []
    components = [
        ("expense_office_admin_annual", om.expense_office_admin_annual),
        ("expense_bank_fees_annual", om.expense_bank_fees_annual),
        ("expense_contract_services_annual", om.expense_contract_services_annual),
        ("expense_miscellaneous_annual", om.expense_miscellaneous_annual),
        ("expense_telephone_annual", om.expense_telephone_annual),
    ]
    return [(field, value) for field, value in components if value is not None]


def _humanize_field_name(field: str | None) -> str | None:
    if not field:
        return None
    return field.replace("expense_", "").replace("_", " ")


def _describe_source(doc_type: str | None, field: str | None) -> str:
    doc_label = {
        "om": "OM",
        "t12": "T-12",
        "rent_roll": "rent roll",
        "derived": "derived",
        "benchmark": "benchmark",
    }.get(doc_type or "", doc_type or "source")
    field_label = _humanize_field_name(field)
    return f"{doc_label} {field_label}" if field_label else doc_label


def _default_exit_cap_candidate(om: Optional[OMExtraction]) -> MergeCandidate:
    purchase_cap = om.market_cap_rate_purchase if om else None
    if purchase_cap:
        exit_cap = min(max(purchase_cap + DEFAULT_EXIT_CAP_SPREAD, 0.01), 0.20)
        formula = (
            f"{purchase_cap * 100:.2f}% purchase cap rate + "
            f"{DEFAULT_EXIT_CAP_SPREAD * 100:.2f}% spread"
        )
        return _candidate(
            exit_cap,
            "om",
            "exit_cap_rate",
            formula,
            True,
            False,
            {
                "selection_note": (
                    "Used default terminal cap assumption equal to purchase cap rate plus 50 bps "
                    "because OM exit cap rate was unavailable."
                ),
                "derived_from_field": "market_cap_rate_purchase",
                "default_basis": "purchase_cap_plus_50bps",
            },
        )
    return _candidate(
        DEFAULT_EXIT_CAP_RATE,
        "om",
        "exit_cap_rate",
        None,
        True,
        False,
        {"default_basis": "fallback_8pct"},
    )


def _benchmark_citation(
    floor_value: float,
    original_value: float | None,
    formula: str,
    overridden_citation: dict | None = None,
) -> dict:
    overridden_doc_type = overridden_citation.get("doc_type") if overridden_citation else None
    overridden_source_field = overridden_citation.get("source_field") if overridden_citation else None
    overridden_source_period = overridden_citation.get("source_period") if overridden_citation else None
    overridden_source_method = overridden_citation.get("source_method") if overridden_citation else None
    overridden_source = _describe_source(overridden_doc_type, overridden_source_field)
    overridden_citations = list((overridden_citation or {}).get("citations", []) or [])
    return {
        "doc_type": "benchmark",
        "citations": overridden_citations,
        "is_default": False,
        "is_computed": True,
        "provenance_kind": "benchmark_override",
        "override_reason": "Raised to benchmark floor",
        "source_field": overridden_source_field,
        "source_period": overridden_source_period or _infer_source_period(overridden_doc_type, overridden_source_field),
        "source_method": overridden_source_method or _infer_source_method(overridden_doc_type, overridden_source_field),
        "overridden_doc_type": overridden_doc_type,
        "overridden_source_field": overridden_source_field,
        "overridden_source_period": overridden_source_period,
        "overridden_source_method": overridden_source_method,
        "selection_note": f"Raised {overridden_source} to benchmark floor." if overridden_source_field else "Raised source value to benchmark floor.",
        "formula": formula,
        "original_value": original_value,
        "benchmark_floor_value": floor_value,
    }


def _apply_benchmark_floors(merged: dict, citations: dict) -> None:
    """Apply benchmark floors to OM-sourced expense lines after merge selection."""
    rentable_sqft = merged.get("project", {}).get("rentable_sqft")
    gpr = merged.get("operational", {}).get("gross_potential_rent_annual")
    floors = get_expense_floors("self_storage", rentable_sqft=rentable_sqft, egi=gpr)

    floored_fields = ["repairs_maintenance_annual", "insurance_annual", "utilities_annual", "marketing_annual"]
    complete_om_year1_package = all(
        citations.get(field, {}).get("doc_type") == "om"
        and citations.get(field, {}).get("source_period") == "year1"
        for field in floored_fields
    )

    for field in floored_fields:
        floor_val = floors.get(field)
        if floor_val is None:
            continue
        current_citation = citations.get(field, {})
        if current_citation.get("doc_type") == "t12":
            continue
        if complete_om_year1_package:
            continue
        current_val = merged["operational"].get(field)
        if current_val is None or current_val >= floor_val:
            continue
        sqft_based = field in ("repairs_maintenance_annual", "insurance_annual", "utilities_annual")
        if sqft_based and rentable_sqft:
            rate = floor_val / rentable_sqft
            formula = f"${rate:.2f}/sqft × {rentable_sqft:,.0f} sqft"
        elif gpr:
            pct = floor_val / gpr
            formula = f"{pct:.1%} of GPR × ${gpr:,.0f}"
        else:
            formula = f"${floor_val:,.0f} (marketing floor)"
        merged["operational"][field] = floor_val
        citations[field] = _benchmark_citation(
            floor_value=floor_val,
            original_value=current_val,
            formula=formula,
            overridden_citation=current_citation,
        )



def _combined_om_other_opex_citation(
    per_doc_citations: dict,
    components: list[tuple[str, float]],
) -> dict:
    citations: list[str] = []
    source_parts: list[str] = []
    formula_parts: list[str] = []

    for field, value in components:
        cdata = per_doc_citations.get("om", {}).get(field, {})
        for token in cdata.get("citations", []) or []:
            if token not in citations:
                citations.append(token)
        if cdata.get("source_text"):
            source_parts.append(str(cdata["source_text"]))
        label = field.replace("expense_", "").replace("_annual", "").replace("_", " ")
        formula_parts.append(f"${value:,.0f} {label}")

    return {
        "doc_type": "om",
        "confidence": 1.0 if citations else 0.0,
        "citations": citations,
        "source_text": "; ".join(source_parts)[:240] if source_parts else None,
        "is_default": False,
        "is_computed": True,
        "formula": " + ".join(formula_parts) if formula_parts else None,
        **({"is_uncited_extraction": True} if not citations else {}),
    }


def _om_total_revenue(om: Optional[OMExtraction]) -> Optional[float]:
    if not om:
        return None
    total_revenue = (om.gpr_annual_projected or 0) + (om.other_income_annual or 0)
    return total_revenue if total_revenue > 0 else None


def _om_year1_line_item_total(om: Optional[OMExtraction]) -> Optional[float]:
    if not om:
        return None
    line_items = [
        om.expense_property_tax_annual_year1,
        om.expense_insurance_annual_year1,
        om.expense_payroll_annual,
        om.expense_repairs_maintenance_annual_year1,
        om.expense_utilities_annual_year1,
        om.expense_marketing_annual_year1,
        _om_other_opex_total(om),
        om.expense_mgmt_fee_annual,
    ]
    present = [value for value in line_items if value is not None]
    if not present:
        return None
    total_opex = sum(present)
    return total_opex if total_opex > 0 else None


def _om_year1_egi(om: Optional[OMExtraction], total_opex: Optional[float] = None) -> Optional[float]:
    if not om:
        return None
    if om.noi_year_one_stated is not None and total_opex is not None:
        egi = om.noi_year_one_stated + total_opex
        return egi if egi > 0 else None
    if om.gpr_annual_projected is None:
        return None
    vacancy_loss = om.gpr_annual_projected * (om.vacancy_pct_projected or 0)
    egi = om.gpr_annual_projected - vacancy_loss + (om.other_income_annual or 0)
    return egi if egi > 0 else None


def _derived_om_mgmt_fee_pct(om: Optional[OMExtraction]) -> Optional[float]:
    if not om or om.expense_mgmt_fee_annual is None:
        return None
    egi = _om_year1_egi(om, _om_year1_line_item_total(om))
    if egi is None:
        egi = _om_total_revenue(om)
    if egi is None:
        return None
    return om.expense_mgmt_fee_annual / egi


def _derived_om_expense_ratio_details(om: Optional[OMExtraction]) -> tuple[Optional[float], Optional[str], Optional[float], Optional[float]]:
    if not om:
        return None, None, None, None
    total_opex = _om_year1_line_item_total(om)
    egi = _om_year1_egi(om, total_opex)
    if total_opex is None or egi is None:
        return None, None, egi, total_opex
    ratio = total_opex / egi
    formula = f"${total_opex:,.0f} total expenses ÷ ${egi:,.0f} EGI"
    return ratio, formula, egi, total_opex


def _derived_om_expense_ratio(om: Optional[OMExtraction]) -> Optional[float]:
    ratio, _, _, _ = _derived_om_expense_ratio_details(om)
    return ratio


def _property_tax_rate_components(om: Optional[OMExtraction]) -> tuple[Optional[float], Optional[str]]:
    if not om:
        return None, None
    if om.property_tax_rate_per_assessed_dollar is not None:
        rate = om.property_tax_rate_per_assessed_dollar
        return rate, f"${rate:.5f} per assessed dollar"
    if om.property_tax_millage_rate is not None:
        rate = om.property_tax_millage_rate / 1000.0
        return rate, f"{om.property_tax_millage_rate:.2f} mills / 1,000"
    return None, None


def _derived_om_property_tax_details(om: Optional[OMExtraction]) -> tuple[Optional[float], Optional[str]]:
    if not om:
        return None, None

    rate, rate_label = _property_tax_rate_components(om)
    if rate is None or rate_label is None:
        return None, None

    if om.property_tax_assessed_value is not None:
        assessed_value = om.property_tax_assessed_value
        value = assessed_value * rate
        formula = f"${assessed_value:,.0f} assessed value × {rate_label}"
        return value, formula

    if om.property_tax_value_basis_amount is None or om.property_tax_assessment_ratio is None:
        return None, None

    assessed_value = om.property_tax_value_basis_amount * om.property_tax_assessment_ratio
    value = assessed_value * rate
    formula = (
        f"${om.property_tax_value_basis_amount:,.0f} value basis × "
        f"{om.property_tax_assessment_ratio:.2%} assessment ratio × {rate_label}"
    )
    return value, formula


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
    formula: str | None = None,
    is_default_candidate: bool = False,
    is_computed: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict:
    """Build a citation entry for the winning field from the given doc_type.

    When doc_type == "derived", the value was computed from other extracted fields.
    formula (optional) carries the human-readable computation e.g. "$14,174 ÷ $320,018 EGI".
    """
    source_period = (metadata or {}).get("source_period") or _infer_source_period(doc_type, field)
    source_method = (metadata or {}).get("source_method") or _infer_source_method(doc_type, field, is_computed)
    if doc_type == "derived":
        citation = {
            "doc_type": "derived",
            "confidence": 1.0,
            "citations": [],
            "source_text": None,
            "is_default": False,
            "is_derived": True,
            "provenance_kind": "derived",
            "source_field": field,
            "source_period": source_period,
            "source_method": source_method,
            "formula": formula,
        }
        if metadata:
            citation.update(metadata)
        return citation
    cdata = per_doc_citations.get(doc_type, {}).get(field, {})
    citation = {
        "doc_type": doc_type,
        "confidence": cdata.get("confidence", 0.0),
        "citations":  cdata.get("citations", []),
        "source_text": cdata.get("source_text"),
        "is_default": is_default_candidate,
        "source_field": field,
        "source_period": source_period,
        "source_method": source_method,
    }
    if cdata.get("is_computed") or is_computed:
        citation["is_computed"] = True
    if formula:
        citation["formula"] = formula
    if not cdata and not is_default_candidate:
        citation["is_uncited_extraction"] = True
    if metadata:
        citation.update(metadata)
    if "provenance_kind" not in citation:
        if is_default_candidate:
            citation["provenance_kind"] = "default"
        elif citation.get("is_computed"):
            citation["provenance_kind"] = "computed"
        elif citation.get("is_uncited_extraction"):
            citation["provenance_kind"] = "uncited_extraction"
        else:
            citation["provenance_kind"] = "extracted"
    return citation


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

    def annualized_candidate(raw_value: Optional[float], src_field: str) -> MergeCandidate:
        annualized_value = ann(raw_value)
        formula: str | None = None
        metadata: dict[str, Any] = {}
        if raw_value is not None and t12 and t12_factor != 1.0:
            formula = f"${raw_value:,.0f} × (12 ÷ {t12.period_months} months)"
            metadata = {
                "annualized_from_value": raw_value,
                "annualized_from_months": t12.period_months,
                "annualization_factor": t12_factor,
                "selection_note": f"Annualized from {t12.period_months}-month T-12 value.",
            }
        return _candidate(annualized_value, "t12", src_field, formula, False, False, metadata)

    def pick(output_field: str, *candidates: MergeCandidate) -> Any:
        """Pick first non-None candidate.
        Each candidate is a MergeCandidate describing a possible source value.
        Records citation for the winning candidate."""
        for index, candidate in enumerate(candidates):
            val = candidate.value
            doc_type = candidate.doc_type
            src_field = candidate.source_field
            formula = candidate.formula
            is_default_candidate = candidate.is_default_candidate
            is_computed = candidate.is_computed
            metadata = dict(candidate.metadata)
            if val is not None:
                if index > 0:
                    skipped_sources = [
                        _describe_source(previous.doc_type, previous.source_field)
                        for previous in candidates[:index]
                        if previous.value is None
                    ]
                    if skipped_sources:
                        metadata.setdefault("used_fallback_source", True)
                        metadata.setdefault("preferred_sources_missing", skipped_sources)
                        if is_default_candidate:
                            selection_note = (
                                f"Used default {_humanize_field_name(output_field)} assumption because "
                                f"{', '.join(skipped_sources)} was unavailable."
                            )
                        else:
                            selection_note = (
                                f"Used {_describe_source(doc_type, src_field)} because "
                                f"{', '.join(skipped_sources)} was unavailable."
                            )
                        metadata.setdefault(
                            "selection_note",
                            selection_note,
                        )
                citations[output_field] = _cited(
                    per_doc_citations,
                    doc_type,
                    src_field,
                    formula,
                    is_default_candidate,
                    is_computed,
                    metadata,
                )
                return val
        return None

    # Pre-compute derived values and their formula strings before the merged dict
    _om_year1_total_opex = _om_year1_line_item_total(om)
    _om_year1_egi_value = _om_year1_egi(om, _om_year1_total_opex)
    _mgmt_derived = _derived_om_mgmt_fee_pct(om)
    _mgmt_total_rev = _om_year1_egi_value or _om_total_revenue(om)
    _mgmt_formula = (
        f"${om.expense_mgmt_fee_annual:,.0f} ÷ ${_mgmt_total_rev:,.0f} EGI"
    ) if _mgmt_derived is not None and om and om.expense_mgmt_fee_annual and _mgmt_total_rev else None

    _property_tax_derived, _property_tax_formula = _derived_om_property_tax_details(om)

    _opex_derived, _opex_formula, _opex_egi, _opex_line_total = _derived_om_expense_ratio_details(om)

    _t12_opex_derived, _t12_opex_formula, _t12_opex_is_computed = _derived_t12_expense_ratio_details(t12, t12_factor)
    _om_other_opex_parts = _om_other_opex_components(om)

    _other_inc = _om_other_income_total(om)
    _other_formula: str | None = None
    if om and om.other_income_annual is None and _other_inc is not None:
        parts = []
        if om.other_income_admin_fees_annual:
            parts.append(f"${om.other_income_admin_fees_annual:,.0f} admin")
        if om.other_income_late_fees_annual:
            parts.append(f"${om.other_income_late_fees_annual:,.0f} late fees")
        if om.other_income_insurance_annual:
            parts.append(f"${om.other_income_insurance_annual:,.0f} insurance")
        if om.other_income_misc_annual:
            parts.append(f"${om.other_income_misc_annual:,.0f} misc")
        _other_formula = " + ".join(parts) if parts else None

    def build_project_section() -> dict[str, Any]:
        return {
            "name": pick("name",
                _candidate(om.name if om else None, "om", "name"),
            ) or "Untitled Deal",
            "asset_type": "self_storage",
            "address": pick("address",
                _candidate(om.address if om else None, "om", "address"),
            ),
            "num_units": pick("num_units",
                _candidate(rr.num_units_actual if rr else None, "rent_roll", "num_units_actual"),
                _candidate(om.num_units if om else None, "om", "num_units"),
            ),
            "rentable_sqft": pick("rentable_sqft",
                _candidate(om.rentable_sqft if om else None, "om", "rentable_sqft"),
            ),
            "year_built": pick("year_built",
                _candidate(om.year_built if om else None, "om", "year_built"),
            ),
            "nearby_storage_count_1mi": pick("nearby_storage_count_1mi",
                _candidate(om.nearby_storage_count_1mi if om else None, "om", "nearby_storage_count_1mi"),
            ),
            "nearby_storage_count_3mi": pick("nearby_storage_count_3mi",
                _candidate(om.nearby_storage_count_3mi if om else None, "om", "nearby_storage_count_3mi"),
            ),
            "nearby_storage_count_5mi": pick("nearby_storage_count_5mi",
                _candidate(om.nearby_storage_count_5mi if om else None, "om", "nearby_storage_count_5mi"),
            ),
            "population_3mi": pick("population_3mi",
                _candidate(om.population_3mi if om else None, "om", "population_3mi"),
            ),
            "avg_household_income_3mi": pick("avg_household_income_3mi",
                _candidate(om.avg_household_income_3mi if om else None, "om", "avg_household_income_3mi"),
            ),
            "storage_sqft_per_capita_3mi": pick("storage_sqft_per_capita_3mi",
                _candidate(om.storage_sqft_per_capita_3mi if om else None, "om", "storage_sqft_per_capita_3mi"),
            ),
        }

    def build_acquisition_section() -> dict[str, Any]:
        return {
            "purchase_price": pick("purchase_price",
                _candidate(om.purchase_price if om else None, "om", "purchase_price"),
            ),
            "closing_cost_pct": pick("closing_cost_pct",
                _candidate(om.closing_cost_pct if om else None, "om", "closing_cost_pct"),
                _candidate(0.02, "om", "closing_cost_pct", None, True),
            ),
            "market_cap_rate_purchase": pick("market_cap_rate_purchase",
                _candidate(om.market_cap_rate_purchase if om else None, "om", "market_cap_rate_purchase"),
            ),
            "capex_reserve_per_unit": pick("capex_reserve_per_unit",
                _candidate(om.capex_reserve_per_unit if om else None, "om", "capex_reserve_per_unit"),
                _candidate(0.0, "om", "capex_reserve_per_unit", None, True),
            ),
        }

    def build_operational_section() -> dict[str, Any]:
        return {
            "gross_potential_rent_annual": pick("gross_potential_rent_annual",
                annualized_candidate(t12.gpr_annual_actual if t12 else None, "gpr_annual_actual"),
                _candidate(om.gpr_annual_projected if om else None, "om", "gpr_annual_projected"),
                _candidate(0.0, "om", "gpr_annual_projected", None, True),
            ),
            "avg_in_place_rent_per_unit_monthly": pick("avg_in_place_rent_per_unit_monthly",
                _candidate(rr.avg_in_place_rent_per_unit_monthly if rr else None, "rent_roll", "avg_in_place_rent_per_unit_monthly"),
                _candidate(om.avg_in_place_rent_per_unit_monthly if om else None, "om", "avg_in_place_rent_per_unit_monthly"),
            ),
            "avg_market_rent_per_unit_monthly": pick("avg_market_rent_per_unit_monthly",
                _candidate(rr.avg_market_rent_per_unit_monthly if rr else None, "rent_roll", "avg_market_rent_per_unit_monthly"),
                _candidate(om.avg_market_rent_per_unit_monthly if om else None, "om", "avg_market_rent_per_unit_monthly"),
            ),
            "vacancy_credit_loss_pct": pick("vacancy_credit_loss_pct",
                _candidate(t12.vacancy_credit_loss_pct_actual if t12 else None, "t12", "vacancy_credit_loss_pct_actual"),
                _candidate(om.vacancy_pct_projected if om else None, "om", "vacancy_pct_projected"),
                _candidate(0.10, "om", "vacancy_pct_projected", None, True),
            ),
            "expense_ratio_t12": pick("expense_ratio_t12",
                _candidate(_t12_opex_derived, "t12", "expense_ratio_actual", _t12_opex_formula, False, _t12_opex_is_computed),
            ),
            "expense_ratio_current": pick("expense_ratio_current",
                _candidate(om.expense_ratio_current if om else None, "om", "expense_ratio_current"),
            ),
            "expense_ratio_year1": pick("expense_ratio_year1",
                _candidate(_opex_derived, "om", "expense_ratio_year1", _opex_formula, False, _opex_derived is not None),
                _candidate(om.expense_ratio_year1 if om else None, "om", "expense_ratio_year1"),
            ),
            "expense_ratio_pro_forma": pick("expense_ratio_pro_forma",
                _candidate(om.expense_ratio_pro_forma if om else None, "om", "expense_ratio_pro_forma"),
            ),
            "noi_year_one_stated": pick("noi_year_one_stated",
                _candidate(om.noi_year_one_stated if om else None, "om", "noi_year_one_stated"),
                _candidate(om.noi_projected if om else None, "om", "noi_projected"),
            ),
            "noi_current_stated": pick("noi_current_stated",
                _candidate(om.noi_current_stated if om else None, "om", "noi_current_stated"),
            ),
            "income_basis_months": pick("income_basis_months",
                _candidate(t12.period_months if t12 else None, "t12", "period_months"),
                _candidate(om.income_basis_months if om else None, "om", "income_basis_months"),
            ),
            "income_basis_note": pick("income_basis_note",
                _candidate(om.income_basis_note if om else None, "om", "income_basis_note"),
            ),
            "operating_statement_period": "t12" if t12 else ("year1" if om else "unknown"),
            "operating_statement_warnings": [],
            "other_income_annual": pick("other_income_annual",
                annualized_candidate(t12.other_income_annual if t12 else None, "other_income_annual"),
                _candidate(om.other_income_annual if om else None, "om", "other_income_annual"),
                _candidate(_other_inc, "derived", "other_income_annual", _other_formula),
                _candidate(0.0, "t12", "other_income_annual", None, True),
            ),
            "bad_debt_annual": pick("bad_debt_annual",
                annualized_candidate(t12.bad_debt_annual if t12 else None, "bad_debt_annual"),
            ),
            "corrections_collections_annual": pick("corrections_collections_annual",
                annualized_candidate(t12.corrections_collections_annual if t12 else None, "corrections_collections_annual"),
            ),
            "rent_growth_pct": pick("rent_growth_pct",
                _candidate(rr.rent_growth_pct if rr else None, "rent_roll", "rent_growth_pct"),
                _candidate(om.rent_growth_pct if om else None, "om", "rent_growth_pct"),
                _candidate(0.03, "rent_roll", "rent_growth_pct", None, True),
            ),
            "property_tax_annual": pick("property_tax_annual",
                annualized_candidate(t12.property_tax_annual if t12 else None, "property_tax_annual"),
                _candidate(om.expense_property_tax_annual_year1 if om else None, "om", "expense_property_tax_annual_year1"),
                _candidate(_property_tax_derived, "derived", "property_tax_annual", _property_tax_formula),
                _candidate(om.expense_property_tax_annual_current if om else None, "om", "expense_property_tax_annual_current"),
                _candidate(None, "om", "property_tax_annual", None, True),
            ),
            "insurance_annual": pick("insurance_annual",
                annualized_candidate(t12.insurance_annual if t12 else None, "insurance_annual"),
                _candidate(om.expense_insurance_annual_year1 if om else None, "om", "expense_insurance_annual_year1"),
                _candidate(om.expense_insurance_annual_current if om else None, "om", "expense_insurance_annual_current"),
                _candidate(0.0, "t12", "insurance_annual", None, True),
            ),
            "mgmt_fee_pct": pick("mgmt_fee_pct",
                _candidate(t12.mgmt_fee_pct_actual if t12 else None, "t12", "mgmt_fee_pct_actual"),
                _candidate(om.mgmt_fee_pct if om else None, "om", "mgmt_fee_pct"),
                _candidate(_mgmt_derived, "derived", "expense_mgmt_fee_annual", _mgmt_formula),
                _candidate(0.08, "om", "mgmt_fee_pct", None, True),
            ),
            "payroll_annual": pick("payroll_annual",
                annualized_candidate(t12.payroll_annual if t12 else None, "payroll_annual"),
                _candidate(om.expense_payroll_annual if om else None, "om", "expense_payroll_annual"),
                _candidate(0.0, "t12", "payroll_annual", None, True),
            ),
            "repairs_maintenance_annual": pick("repairs_maintenance_annual",
                annualized_candidate(t12.repairs_maintenance_annual if t12 else None, "repairs_maintenance_annual"),
                _candidate(om.expense_repairs_maintenance_annual_year1 if om else None, "om", "expense_repairs_maintenance_annual_year1"),
                _candidate(om.expense_repairs_maintenance_annual_current if om else None, "om", "expense_repairs_maintenance_annual_current"),
                _candidate(0.0, "t12", "repairs_maintenance_annual", None, True),
            ),
            "utilities_annual": pick("utilities_annual",
                annualized_candidate(t12.utilities_annual if t12 else None, "utilities_annual"),
                _candidate(om.expense_utilities_annual_year1 if om else None, "om", "expense_utilities_annual_year1"),
                _candidate(om.expense_utilities_annual_current if om else None, "om", "expense_utilities_annual_current"),
                _candidate(0.0, "t12", "utilities_annual", None, True),
            ),
            "marketing_annual": pick("marketing_annual",
                annualized_candidate(t12.marketing_annual if t12 else None, "marketing_annual"),
                _candidate(om.expense_marketing_annual_year1 if om else None, "om", "expense_marketing_annual_year1"),
                _candidate(om.expense_marketing_annual_current if om else None, "om", "expense_marketing_annual_current"),
                _candidate(0.0, "t12", "marketing_annual", None, True),
            ),
            "other_opex_annual": pick("other_opex_annual",
                annualized_candidate(t12.other_opex_annual if t12 else None, "other_opex_annual"),
                _candidate(_om_other_opex_total(om), "om", "expense_miscellaneous_annual"),
                _candidate(0.0, "t12", "other_opex_annual", None, True),
            ),
            "property_tax_growth_pct": pick("property_tax_growth_pct",
                _candidate(om.property_tax_growth_pct if om else None, "om", "property_tax_growth_pct"),
            ),
            "property_tax_value_basis_amount": pick("property_tax_value_basis_amount",
                _candidate(om.property_tax_value_basis_amount if om else None, "om", "property_tax_value_basis_amount"),
            ),
            "property_tax_assessed_value": pick("property_tax_assessed_value",
                _candidate(om.property_tax_assessed_value if om else None, "om", "property_tax_assessed_value"),
            ),
            "property_tax_assessment_ratio": pick("property_tax_assessment_ratio",
                _candidate(om.property_tax_assessment_ratio if om else None, "om", "property_tax_assessment_ratio"),
            ),
            "property_tax_millage_rate": pick("property_tax_millage_rate",
                _candidate(om.property_tax_millage_rate if om else None, "om", "property_tax_millage_rate"),
            ),
            "property_tax_rate_per_assessed_dollar": pick("property_tax_rate_per_assessed_dollar",
                _candidate(om.property_tax_rate_per_assessed_dollar if om else None, "om", "property_tax_rate_per_assessed_dollar"),
            ),
            "opex_growth_pct": pick("opex_growth_pct",
                _candidate(om.opex_growth_pct if om else None, "om", "opex_growth_pct"),
                _candidate(0.02, "om", "opex_growth_pct", None, True),
            ),
        }

    def build_financing_section() -> dict[str, Any]:
        return {
            "ltv_pct": pick("ltv_pct",
                _candidate(om.ltv_pct if om else None, "om", "ltv_pct"),
                _candidate(0.70, "om", "ltv_pct", None, True),
            ),
            "interest_rate_pct": pick("interest_rate_pct",
                _candidate(om.interest_rate_pct if om else None, "om", "interest_rate_pct"),
                _candidate(0.065, "om", "interest_rate_pct", None, True),
            ),
            "amortization_years": pick("amortization_years",
                _candidate(om.amortization_years if om else None, "om", "amortization_years"),
                _candidate(25, "om", "amortization_years", None, True),
            ),
            "loan_term_years": pick("loan_term_years",
                _candidate(om.loan_term_years if om else None, "om", "loan_term_years"),
                _candidate(10, "om", "loan_term_years", None, True),
            ),
        }

    def build_exit_section() -> dict[str, Any]:
        return {
            "hold_period_years": pick("hold_period_years",
                _candidate(om.hold_period_years if om else None, "om", "hold_period_years"),
                _candidate(DEFAULT_HOLD_PERIOD_YEARS, "om", "hold_period_years", None, True),
            ),
            "market_cap_rate_sale": pick("market_cap_rate_sale",
                _candidate(om.market_cap_rate_sale if om else None, "om", "market_cap_rate_sale"),
            ),
            "exit_cap_rate": pick("exit_cap_rate",
                _candidate(om.exit_cap_rate if om else None, "om", "exit_cap_rate"),
                _default_exit_cap_candidate(om),
            ),
            "selling_cost_pct": pick("selling_cost_pct",
                _candidate(om.selling_cost_pct if om else None, "om", "selling_cost_pct"),
                _candidate(0.03, "om", "selling_cost_pct", None, True),
            ),
        }

    def build_criteria_section() -> dict[str, Any]:
        return {
            "target_irr": pick("target_irr",
                _candidate(om.target_irr if om else None, "om", "target_irr"),
                _candidate(0.15, "om", "target_irr", None, True),
            ),
            "target_cash_on_cash": pick("target_cash_on_cash",
                _candidate(om.target_cash_on_cash if om else None, "om", "target_cash_on_cash"),
                _candidate(0.08, "om", "target_cash_on_cash", None, True),
            ),
            "target_equity_multiple": pick("target_equity_multiple",
                _candidate(om.target_equity_multiple if om else None, "om", "target_equity_multiple"),
                _candidate(2.0, "om", "target_equity_multiple", None, True),
            ),
            "max_ltv": pick("max_ltv",
                _candidate(getattr(om, "max_ltv", None) if om else None, "om", "max_ltv"),
                _candidate(0.80, "om", "max_ltv", None, True),
            ),
        }

    merged = {
        "project": build_project_section(),
        "acquisition": build_acquisition_section(),
        "operational": build_operational_section(),
        "financing": build_financing_section(),
        "exit": build_exit_section(),
        "criteria": build_criteria_section(),
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

    # Apply benchmark floors to OM-sourced expenses (T-12 actuals bypass floors)
    _apply_benchmark_floors(merged, citations)

    if merged["operational"].get("operating_statement_period") == "year1":
        fallback_fields = []
        for field in (
            "property_tax_annual",
            "insurance_annual",
            "repairs_maintenance_annual",
            "utilities_annual",
            "marketing_annual",
        ):
            if citations.get(field, {}).get("source_period") == "current":
                fallback_fields.append(field)
        if fallback_fields:
            merged["operational"]["operating_statement_period"] = "mixed"
            merged["operational"]["operating_statement_warnings"] = [
                "Year 1 operating basis uses Current fallback for: "
                + ", ".join(field.replace("_annual", "").replace("_", " ") for field in fallback_fields)
                + "."
            ]

    if t12 and t12.noi_actual is not None and "noi_actual" not in citations:
        citations["noi_actual"] = _cited(per_doc_citations, "t12", "noi_actual")

    if (not t12 or t12.other_opex_annual is None) and _om_other_opex_parts:
        citations["other_opex_annual"] = _combined_om_other_opex_citation(
            per_doc_citations,
            _om_other_opex_parts,
        )

    return merged, citations
