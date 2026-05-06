"""Cross-document discrepancy detection for Self Storage underwriting.

Compares extracted data from OM, Rent Roll, and T12 to flag inconsistencies
that may indicate data quality issues or broker/actuals misalignment.
"""

from __future__ import annotations


def _normalize_bucket_part(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def _unit_mix_bucket_key(row: dict) -> tuple[str, str, str]:
    return (
        _normalize_bucket_part(row.get("section")),
        _normalize_bucket_part(row.get("unit_type")),
        _normalize_bucket_part(row.get("size")),
    )


def _unit_mix_label(row: dict) -> str:
    return row.get("size") or row.get("unit_type") or row.get("section") or "unlabeled bucket"


def _unit_mix_index(unit_mix: list[dict]) -> dict[tuple[str, str, str], dict]:
    buckets: dict[tuple[str, str, str], dict] = {}
    for row in unit_mix or []:
        key = _unit_mix_bucket_key(row)
        if not any(key):
            continue
        buckets[key] = row
    return buckets


def _get_path(data: dict | None, *path: str):
    current = data or {}
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _model_value(field: str, model_inputs: dict | None):
    mapping = {
        "num_units": ("project", "num_units"),
        "rentable_sqft": ("project", "rentable_sqft"),
        "gross_potential_rent_annual": ("operational", "gross_potential_rent_annual"),
        "other_income_annual": ("operational", "other_income_annual"),
        "expense_ratio": ("operational", "expense_ratio_year1"),
        "opex_ratio": ("operational", "expense_ratio_year1"),
        "avg_in_place_rent_per_unit_monthly": ("operational", "avg_in_place_rent_per_unit_monthly"),
        "avg_market_rent_per_unit_monthly": ("operational", "avg_market_rent_per_unit_monthly"),
        "property_tax_annual": ("operational", "property_tax_annual"),
        "insurance_annual": ("operational", "insurance_annual"),
        "payroll_annual": ("operational", "payroll_annual"),
        "repairs_maintenance_annual": ("operational", "repairs_maintenance_annual"),
        "utilities_annual": ("operational", "utilities_annual"),
        "marketing_annual": ("operational", "marketing_annual"),
    }
    if field == "occupancy_pct":
        vacancy = _get_path(model_inputs, "operational", "vacancy_credit_loss_pct")
        return 1.0 - vacancy if vacancy is not None else None
    path = mapping.get(field)
    return _get_path(model_inputs, *path) if path else None


def _preferred_source(field: str) -> tuple[str | None, str | None]:
    if field in {"num_units", "rentable_sqft", "occupancy_pct", "avg_in_place_rent_per_unit_monthly", "avg_market_rent_per_unit_monthly", "unit_mix"}:
        return "rent_roll", "Rent roll unit-level rows are preferred for inventory, occupancy, and in-place rent."
    if field in {
        "gross_potential_rent_annual",
        "other_income_annual",
        "expense_ratio",
        "opex_ratio",
        "noi",
        "property_tax_annual",
        "insurance_annual",
        "payroll_annual",
        "repairs_maintenance_annual",
        "utilities_annual",
        "marketing_annual",
    }:
        return "t12", "T-12 actual operating data is preferred over OM pro forma for current performance."
    return None, None


def _relative_delta(a: float | int | None, b: float | int | None) -> float | None:
    if a is None or b is None:
        return None
    denominator = abs(float(b))
    if denominator <= 0:
        return None
    return abs(float(a) - float(b)) / denominator


def _add_discrepancy(
    discrepancies: list[dict],
    *,
    field: str,
    sources: list[dict],
    severity: str,
    note: str,
    model_inputs: dict | None,
    variance: float | None = None,
) -> None:
    preferred_source, reason = _preferred_source(field)
    discrepancies.append({
        "field": field,
        "sources": sources,
        "severity": severity,
        "note": note,
        "model_used": _model_value(field, model_inputs),
        "preferred_source": preferred_source,
        "variance": variance,
        "reason": reason,
    })


def _gpr_note(a_val, b_val, rel, abs_d):
    return f"GPR mismatch: OM ${a_val:,.0f} vs rent roll ${b_val:,.0f} ({rel:.1%} / ${abs_d:,.0f})"


def _opex_ratio_note(a_val, b_val, _, abs_d):
    return f"OpEx ratio: OM pro forma {a_val:.1%} vs T12 actual {b_val:.1%} ({abs_d * 10_000:.0f} bps)"


def _sqft_note(a_val, b_val, rel, _):
    return f"Square footage: OM {a_val:,.0f} sqft vs rent roll {b_val:,.0f} sqft ({rel:.1%})"


def _compare_numeric_sources(
    discrepancies: list[dict],
    *,
    field: str,
    om_value,
    t12_value=None,
    rent_roll_value=None,
    label: str,
    threshold_pct: float = 0.05,
    threshold_abs: float | None = None,
    model_inputs: dict | None = None,
    severity: str = "warning",
    note_fn=None,
) -> None:
    candidates = [
        ("om", om_value),
        ("t12", t12_value),
        ("rent_roll", rent_roll_value),
    ]
    present = [(doc_type, value) for doc_type, value in candidates if value is not None]
    if len(present) < 2:
        return

    first_doc, first_value = present[0]
    for other_doc, other_value in present[1:]:
        rel = _relative_delta(first_value, other_value)
        abs_delta = abs(float(first_value) - float(other_value))
        if (rel is not None and rel >= threshold_pct) or (threshold_abs is not None and abs_delta >= threshold_abs):
            note = (
                note_fn(first_value, other_value, rel, abs_delta)
                if note_fn is not None
                else f"{label}: {first_doc.upper()} {first_value:,.2f} vs {other_doc.upper()} {other_value:,.2f}"
            )
            _add_discrepancy(
                discrepancies,
                field=field,
                sources=[
                    {"doc_type": first_doc, "value": first_value},
                    {"doc_type": other_doc, "value": other_value},
                ],
                severity=severity,
                note=note,
                model_inputs=model_inputs,
                variance=rel,
            )
            return


def detect_discrepancies(
    om_data: dict,
    rent_roll_data: dict,
    t12_data: dict,
    model_inputs: dict | None = None,
) -> list[dict]:
    """
    Detect cross-document discrepancies using deterministic rules.

    Args:
        om_data: Offering Memorandum extracted data
        rent_roll_data: Rent Roll extracted data
        t12_data: T12 operating statement extracted data

    Returns:
        List of discrepancy dicts: {field, sources, severity, note}
    """
    discrepancies = []

    if not om_data:
        om_data = {}
    if not rent_roll_data:
        rent_roll_data = {}
    if not t12_data:
        t12_data = {}

    # Rule 1: Unit count mismatch (OM vs Rent Roll)
    om_units = om_data.get("num_units")
    rr_units = rent_roll_data.get("summary", {}).get("total_units")
    if om_units and rr_units and om_units != rr_units:
            _add_discrepancy(
                discrepancies,
                field="num_units",
                sources=[
                    {"doc_type": "om", "value": om_units},
                    {"doc_type": "rent_roll", "value": rr_units},
                ],
                severity="error",
                note=f"Unit count mismatch: OM states {om_units}, rent roll shows {rr_units}",
                model_inputs=model_inputs,
                variance=_relative_delta(om_units, rr_units),
            )

    # Rule 2: Occupancy mismatch (OM stated vs rent roll computed)
    # Tiered: < 3pp = no flag, 3–8pp = warning, > 8pp = error
    om_occ = om_data.get("occupancy_pct")
    rr_occ = rent_roll_data.get("summary", {}).get("occupancy_pct")
    if om_occ is not None and rr_occ is not None:
        delta = abs(om_occ - rr_occ)
        if delta > 0.08:
            _add_discrepancy(
                discrepancies,
                field="occupancy_pct",
                sources=[
                    {"doc_type": "om", "value": om_occ},
                    {"doc_type": "rent_roll", "value": rr_occ},
                ],
                severity="error",
                note=f"Major occupancy discrepancy: OM {om_occ:.1%} vs rent roll {rr_occ:.1%} ({delta:.1%} gap)",
                model_inputs=model_inputs,
                variance=delta,
            )
        elif delta > 0.03:
            _add_discrepancy(
                discrepancies,
                field="occupancy_pct",
                sources=[
                    {"doc_type": "om", "value": om_occ},
                    {"doc_type": "rent_roll", "value": rr_occ},
                ],
                severity="warning",
                note=f"Occupancy delta: OM {om_occ:.1%} vs rent roll {rr_occ:.1%} ({delta:.1%})",
                model_inputs=model_inputs,
                variance=delta,
            )

    # Rule 3: Total in-place rent (OM vs Rent Roll; threshold: 3% relative OR $50k absolute)
    _compare_numeric_sources(
        discrepancies,
        field="gross_potential_rent_annual",
        om_value=om_data.get("gross_potential_rent_annual"),
        rent_roll_value=rent_roll_data.get("summary", {}).get("annual_gross_potential_rent"),
        label="GPR mismatch",
        threshold_pct=0.03,
        threshold_abs=50_000,
        model_inputs=model_inputs,
        note_fn=_gpr_note,
    )

    # Rule 4: OpEx ratio (OM pro forma vs T12 actual; threshold: 200 bps)
    _compare_numeric_sources(
        discrepancies,
        field="opex_ratio",
        om_value=om_data.get("expense_ratio_pro_forma", om_data.get("opex_pct")),
        t12_value=t12_data.get("summary", {}).get("opex_ratio"),
        label="OpEx ratio mismatch",
        threshold_pct=1.0,
        threshold_abs=0.02,
        model_inputs=model_inputs,
        note_fn=_opex_ratio_note,
    )

    # Rule 5: Square footage (OM vs Rent Roll sum; threshold: 1% relative)
    _compare_numeric_sources(
        discrepancies,
        field="rentable_sqft",
        om_value=om_data.get("rentable_sqft"),
        rent_roll_value=rent_roll_data.get("summary", {}).get("total_sqft"),
        label="Square footage mismatch",
        threshold_pct=0.01,
        model_inputs=model_inputs,
        severity="info",
        note_fn=_sqft_note,
    )

    _compare_numeric_sources(
        discrepancies,
        field="other_income_annual",
        om_value=om_data.get("other_income_annual"),
        t12_value=t12_data.get("summary", {}).get("other_income_annual"),
        label="Other income mismatch",
        threshold_pct=0.05,
        threshold_abs=10_000,
        model_inputs=model_inputs,
    )

    _compare_numeric_sources(
        discrepancies,
        field="noi",
        om_value=om_data.get("noi_year_one_stated") or om_data.get("noi_projected"),
        t12_value=t12_data.get("summary", {}).get("noi_actual"),
        label="NOI mismatch",
        threshold_pct=0.05,
        threshold_abs=25_000,
        model_inputs=model_inputs,
    )

    _compare_numeric_sources(
        discrepancies,
        field="avg_in_place_rent_per_unit_monthly",
        om_value=om_data.get("avg_in_place_rent_per_unit_monthly"),
        rent_roll_value=rent_roll_data.get("summary", {}).get("avg_in_place_rent_per_unit_monthly"),
        label="Average in-place rent mismatch",
        threshold_pct=0.05,
        model_inputs=model_inputs,
    )

    _compare_numeric_sources(
        discrepancies,
        field="avg_market_rent_per_unit_monthly",
        om_value=om_data.get("avg_market_rent_per_unit_monthly"),
        rent_roll_value=rent_roll_data.get("summary", {}).get("avg_market_rent_per_unit_monthly"),
        label="Average market rent mismatch",
        threshold_pct=0.05,
        model_inputs=model_inputs,
    )

    for field, om_field, label in [
        ("property_tax_annual", "expense_property_tax_annual_year1", "Property tax mismatch"),
        ("insurance_annual", "expense_insurance_annual_year1", "Insurance mismatch"),
        ("payroll_annual", "expense_payroll_annual", "Payroll mismatch"),
        ("repairs_maintenance_annual", "expense_repairs_maintenance_annual_year1", "Repairs and maintenance mismatch"),
        ("utilities_annual", "expense_utilities_annual_year1", "Utilities mismatch"),
        ("marketing_annual", "expense_marketing_annual_year1", "Marketing mismatch"),
    ]:
        _compare_numeric_sources(
            discrepancies,
            field=field,
            om_value=om_data.get(om_field),
            t12_value=t12_data.get("expenses", {}).get(field),
            label=label,
            threshold_pct=0.10,
            threshold_abs=10_000,
            model_inputs=model_inputs,
        )

    # Rule 6: Unit mix mismatch (rent roll should be source of truth when present)
    om_unit_mix = om_data.get("unit_mix") or []
    rr_unit_mix = rent_roll_data.get("unit_mix") or []
    if om_unit_mix and rr_unit_mix:
        om_buckets = _unit_mix_index(om_unit_mix)
        rr_buckets = _unit_mix_index(rr_unit_mix)

        bucket_deltas: list[str] = []
        missing_in_rr: list[str] = []
        missing_in_om: list[str] = []

        for key, om_row in om_buckets.items():
            rr_row = rr_buckets.get(key)
            if rr_row is None:
                missing_in_rr.append(_unit_mix_label(om_row))
                continue

            om_units = om_row.get("num_units")
            rr_units = rr_row.get("num_units")
            if om_units is not None and rr_units is not None and om_units != rr_units:
                bucket_deltas.append(
                    f"{_unit_mix_label(rr_row)} (OM {om_units}, rent roll {rr_units})"
                )

        for key, rr_row in rr_buckets.items():
            if key not in om_buckets:
                missing_in_om.append(_unit_mix_label(rr_row))

        if bucket_deltas or missing_in_rr or missing_in_om:
            note_parts: list[str] = []
            if bucket_deltas:
                note_parts.append("bucket counts differ for " + ", ".join(bucket_deltas[:3]))
            if missing_in_rr:
                note_parts.append("OM-only buckets: " + ", ".join(missing_in_rr[:3]))
            if missing_in_om:
                note_parts.append("rent-roll-only buckets: " + ", ".join(missing_in_om[:3]))
            _add_discrepancy(
                discrepancies,
                field="unit_mix",
                sources=[
                    {"doc_type": "om", "value": om_unit_mix},
                    {"doc_type": "rent_roll", "value": rr_unit_mix},
                ],
                severity="warning",
                note="Unit mix mismatch: " + "; ".join(note_parts),
                model_inputs=model_inputs,
            )

    return discrepancies


def detect_discrepancies_from_results(results: list, model_inputs: dict | None = None) -> list[dict]:
    """Detect discrepancies from typed ExtractedDocResult list.

    Converts typed models to the flat dict format expected by detect_discrepancies().

    Args:
        results: List of ExtractedDocResult objects from per-document extraction tasks.

    Returns:
        List of discrepancy dicts: {field, sources, severity, note}
    """
    om_data: dict = {}
    rent_roll_data: dict = {}
    t12_data: dict = {}

    for r in results:
        if r.doc_type == "om" and r.om and not r.error:
            om_dict = r.om.model_dump(exclude_none=True)
            om_data = {
                "num_units": om_dict.get("num_units"),
                "rentable_sqft": om_dict.get("rentable_sqft"),
                "gross_potential_rent_annual": om_dict.get("gpr_annual_projected"),
                "unit_mix": om_dict.get("unit_mix") or [],
                "other_income_annual": om_dict.get("other_income_annual"),
                "noi_projected": om_dict.get("noi_projected"),
                "noi_year_one_stated": om_dict.get("noi_year_one_stated"),
                "avg_in_place_rent_per_unit_monthly": om_dict.get("avg_in_place_rent_per_unit_monthly"),
                "avg_market_rent_per_unit_monthly": om_dict.get("avg_market_rent_per_unit_monthly"),
                "expense_property_tax_annual": om_dict.get("expense_property_tax_annual_year1"),
                "expense_insurance_annual": om_dict.get("expense_insurance_annual_year1"),
                "expense_payroll_annual": om_dict.get("expense_payroll_annual"),
                "expense_repairs_maintenance_annual": om_dict.get("expense_repairs_maintenance_annual_year1"),
                "expense_utilities_annual": om_dict.get("expense_utilities_annual_year1"),
                "expense_marketing_annual": om_dict.get("expense_marketing_annual_year1"),
                "property_tax_value_basis_amount": om_dict.get("property_tax_value_basis_amount"),
                "property_tax_assessed_value": om_dict.get("property_tax_assessed_value"),
                "property_tax_assessment_ratio": om_dict.get("property_tax_assessment_ratio"),
                "property_tax_millage_rate": om_dict.get("property_tax_millage_rate"),
                "property_tax_rate_per_assessed_dollar": om_dict.get("property_tax_rate_per_assessed_dollar"),
            }
            # Convert vacancy_pct_projected to occupancy_pct
            if "vacancy_pct_projected" in om_dict and om_dict["vacancy_pct_projected"] is not None:
                om_data["occupancy_pct"] = 1.0 - om_dict["vacancy_pct_projected"]
            if om_dict.get("expense_ratio_pro_forma") is not None:
                om_data["expense_ratio_pro_forma"] = om_dict.get("expense_ratio_pro_forma")

        elif r.doc_type == "t12" and r.t12 and not r.error:
            t12 = r.t12
            # Annualize if period_months < 12
            factor = 12.0 / t12.period_months if (t12.period_months and t12.period_months < 12) else 1.0
            total_revenue = ((t12.gpr_annual_actual or 0) + (t12.other_income_annual or 0)) * factor

            t12_data = {
                "summary": {
                    "total_revenue": total_revenue if total_revenue > 0 else None,
                    "other_income_annual": t12.other_income_annual * factor if t12.other_income_annual is not None else None,
                    "noi_actual": t12.noi_actual * factor if t12.noi_actual is not None else None,
                },
                "expenses": {
                    "property_tax_annual": t12.property_tax_annual * factor if t12.property_tax_annual is not None else None,
                    "insurance_annual": t12.insurance_annual * factor if t12.insurance_annual is not None else None,
                    "payroll_annual": t12.payroll_annual * factor if t12.payroll_annual is not None else None,
                    "repairs_maintenance_annual": t12.repairs_maintenance_annual * factor if t12.repairs_maintenance_annual is not None else None,
                    "utilities_annual": t12.utilities_annual * factor if t12.utilities_annual is not None else None,
                    "marketing_annual": t12.marketing_annual * factor if t12.marketing_annual is not None else None,
                },
            }
            total_opex = sum(
                value or 0
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
            if t12.mgmt_fee_pct_actual is not None and total_revenue > 0:
                total_opex += total_revenue * t12.mgmt_fee_pct_actual
            if total_revenue > 0 and total_opex > 0:
                t12_data["summary"]["opex_ratio"] = total_opex / total_revenue

        elif r.doc_type == "rent_roll" and r.rent_roll and not r.error:
            rr = r.rent_roll
            total_sqft = sum(row.total_sqft or 0 for row in rr.unit_mix)
            rent_roll_data = {
                "summary": {
                    "total_units": rr.num_units_actual,
                    "occupancy_pct": rr.physical_occupancy_pct,
                    "annual_gross_potential_rent": None,  # Not available from rent roll extraction
                    "total_sqft": total_sqft or None,
                    "avg_in_place_rent_per_unit_monthly": rr.avg_in_place_rent_per_unit_monthly,
                    "avg_market_rent_per_unit_monthly": rr.avg_market_rent_per_unit_monthly,
                },
                "unit_mix": [row.model_dump() for row in rr.unit_mix],
            }
            annual_gpr = sum(
                (row.num_units or 0) * (row.market_rent if row.market_rent is not None else (row.current_rent or 0)) * 12
                for row in rr.unit_mix
                if row.num_units is not None and (row.market_rent is not None or row.current_rent is not None)
            )
            if annual_gpr > 0:
                rent_roll_data["summary"]["annual_gross_potential_rent"] = annual_gpr

    return detect_discrepancies(om_data, rent_roll_data, t12_data, model_inputs=model_inputs)
