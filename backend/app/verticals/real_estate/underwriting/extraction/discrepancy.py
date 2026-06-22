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


def detect_discrepancies(om_data: dict, rent_roll_data: dict, t12_data: dict) -> list[dict]:
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
        discrepancies.append({
            "field": "num_units",
            "sources": [
                {"doc_type": "om", "value": om_units},
                {"doc_type": "rent_roll", "value": rr_units},
            ],
            "severity": "error",
            "note": f"Unit count mismatch: OM states {om_units}, rent roll shows {rr_units}",
        })

    # Rule 2: Occupancy mismatch (OM stated vs rent roll computed; threshold: 2pp)
    om_occ = om_data.get("occupancy_pct")
    rr_occ = rent_roll_data.get("summary", {}).get("occupancy_pct")
    if om_occ is not None and rr_occ is not None:
        delta = abs(om_occ - rr_occ)
        if delta > 0.02:  # 2 percentage points
            discrepancies.append({
                "field": "occupancy_pct",
                "sources": [
                    {"doc_type": "om", "value": om_occ},
                    {"doc_type": "rent_roll", "value": rr_occ},
                ],
                "severity": "warning",
                "note": f"Occupancy delta: OM {om_occ:.1%} vs rent roll {rr_occ:.1%} ({delta:.1%}pp)",
            })

    # Rule 3: Total in-place rent (OM vs Rent Roll; threshold: 3% relative)
    om_gpr = om_data.get("gross_potential_rent_annual")
    rr_gpr = rent_roll_data.get("summary", {}).get("annual_gross_potential_rent")
    if om_gpr and rr_gpr:
        relative_delta = abs(om_gpr - rr_gpr) / rr_gpr
        if relative_delta >= 0.03:  # 3%
            discrepancies.append({
                "field": "gross_potential_rent_annual",
                "sources": [
                    {"doc_type": "om", "value": om_gpr},
                    {"doc_type": "rent_roll", "value": rr_gpr},
                ],
                "severity": "warning",
                "note": f"GPR mismatch: OM ${om_gpr:,.0f} vs rent roll ${rr_gpr:,.0f} ({relative_delta:.1%})",
            })

    # Rule 4: OpEx ratio (OM pro forma vs T12 actual; threshold: 200 bps)
    om_opex_pct = om_data.get("opex_pct")
    t12_opex_ratio = t12_data.get("summary", {}).get("opex_ratio")
    if om_opex_pct is not None and t12_opex_ratio is not None:
        delta = abs(om_opex_pct - t12_opex_ratio)
        if delta >= 0.02:  # 200 bps
            discrepancies.append({
                "field": "opex_ratio",
                "sources": [
                    {"doc_type": "om", "value": om_opex_pct},
                    {"doc_type": "t12", "value": t12_opex_ratio},
                ],
                "severity": "warning",
                "note": f"OpEx ratio: OM pro forma {om_opex_pct:.1%} vs T12 actual {t12_opex_ratio:.1%} ({delta:.0%})",
            })

    # Rule 5: Square footage (OM vs Rent Roll sum; threshold: 1% relative)
    om_sqft = om_data.get("rentable_sqft")
    rr_sqft = rent_roll_data.get("summary", {}).get("total_sqft")
    if om_sqft and rr_sqft:
        relative_delta = abs(om_sqft - rr_sqft) / rr_sqft
        if relative_delta >= 0.01:  # 1%
            discrepancies.append({
                "field": "rentable_sqft",
                "sources": [
                    {"doc_type": "om", "value": om_sqft},
                    {"doc_type": "rent_roll", "value": rr_sqft},
                ],
                "severity": "info",
                "note": f"Square footage: OM {om_sqft:,.0f} sqft vs rent roll {rr_sqft:,.0f} sqft ({relative_delta:.1%})",
            })

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
            discrepancies.append({
                "field": "unit_mix",
                "sources": [
                    {"doc_type": "om", "value": om_unit_mix},
                    {"doc_type": "rent_roll", "value": rr_unit_mix},
                ],
                "severity": "warning",
                "note": "Unit mix mismatch: " + "; ".join(note_parts),
            })

    return discrepancies


def detect_discrepancies_from_results(results: list) -> list[dict]:
    """Detect discrepancies from typed ExtractedDocResult list.

    Converts typed models to the flat dict format expected by detect_discrepancies().

    Args:
        results: List of ExtractedDocResult objects from per-document extraction tasks.

    Returns:
        List of discrepancy dicts: {field, sources, severity, note}
    """
    from .schemas import ExtractedDocResult

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
            }
            # Convert vacancy_pct_projected to occupancy_pct
            if "vacancy_pct_projected" in om_dict and om_dict["vacancy_pct_projected"] is not None:
                om_data["occupancy_pct"] = 1.0 - om_dict["vacancy_pct_projected"]
            # opex_pct not available from OM extraction schema

        elif r.doc_type == "t12" and r.t12 and not r.error:
            t12 = r.t12
            # Annualize if period_months < 12
            factor = 12.0 / t12.period_months if (t12.period_months and t12.period_months < 12) else 1.0
            total_revenue = (t12.gpr_annual_actual or 0) * factor

            t12_data = {
                "summary": {
                    "total_revenue": total_revenue if total_revenue > 0 else None,
                }
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
                },
                "unit_mix": [row.model_dump() for row in rr.unit_mix],
            }

    return detect_discrepancies(om_data, rent_roll_data, t12_data)
