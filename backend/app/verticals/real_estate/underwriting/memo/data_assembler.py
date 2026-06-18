"""Pulls a completed underwriting run and a memo row into a single MemoContext.

Reads only the run + memo ORM objects. The one outbound call is to the pure
``calculate_max_loan`` helper (max-loan is not persisted on the run; the API
recomputes it on demand and so do we, with the same inputs).
"""
from __future__ import annotations

import logging
from typing import Optional
from pathlib import PurePath

from .schemas import MemoContext, RetrievedChunk  # noqa: F401  (re-export friendly)

logger = logging.getLogger(__name__)

_MAX_UNIT_MIX_ROWS = 20
_MAX_RENT_COMPS_ROWS = 20

# Map calculator's verdict status enum to the renderer/LLM classification labels.
_VERDICT_STATUS_TO_CLASSIFICATION = {
    "worth_pursuing": "Pursue",
    "needs_review": "Needs Review",
    "below_standards": "Below Screen",
}

_SOURCE_SUPPORT_FIELDS = (
    ("Transaction", "purchase_price", "Purchase Price", ("acquisition", "purchase_price"), "money"),
    ("Property", "num_units", "Underwriting Unit Count", ("project", "num_units"), "int"),
    ("Property", "rentable_sqft", "Rentable Sq Ft", ("project", "rentable_sqft"), "sqft"),
    ("Property", "year_built", "Year Built", ("project", "year_built"), "int"),
    ("Income", "gross_potential_rent_annual", "Gross Potential Rent", ("operational", "gross_potential_rent_annual"), "money"),
    ("Income", "other_income_annual", "Other Income", ("operational", "other_income_annual"), "money"),
    ("Income", "vacancy_credit_loss_pct", "Vacancy / Credit Loss", ("operational", "vacancy_credit_loss_pct"), "pct"),
    ("Income", "noi_current_stated", "Current NOI", ("operational", "noi_current_stated"), "money"),
    ("Income", "noi_year_one_stated", "Year-1 NOI", ("operational", "noi_year_one_stated"), "money"),
    ("Expenses", "property_tax_annual", "Property Tax", ("operational", "property_tax_annual"), "money"),
    ("Expenses", "insurance_annual", "Insurance", ("operational", "insurance_annual"), "money"),
    ("Expenses", "mgmt_fee_pct", "Management Fee", ("operational", "mgmt_fee_pct"), "pct"),
    ("Expenses", "payroll_annual", "Payroll", ("operational", "payroll_annual"), "money"),
    ("Expenses", "repairs_maintenance_annual", "Repairs & Maintenance", ("operational", "repairs_maintenance_annual"), "money"),
    ("Expenses", "utilities_annual", "Utilities", ("operational", "utilities_annual"), "money"),
    ("Expenses", "marketing_annual", "Marketing", ("operational", "marketing_annual"), "money"),
    ("Expenses", "other_opex_annual", "Other OpEx", ("operational", "other_opex_annual"), "money"),
    ("Debt / Exit", "ltv_pct", "LTV", ("financing", "ltv_pct"), "pct"),
    ("Debt / Exit", "interest_rate_pct", "Interest Rate", ("financing", "interest_rate_pct"), "pct"),
    ("Debt / Exit", "loan_term_years", "Loan Term", ("financing", "loan_term_years"), "years"),
    ("Debt / Exit", "amortization_years", "Amortization", ("financing", "amortization_years"), "years"),
    ("Debt / Exit", "hold_period_years", "Hold Period", ("exit", "hold_period_years"), "years"),
    ("Debt / Exit", "exit_cap_rate", "Exit Cap Rate", ("exit", "exit_cap_rate"), "pct"),
    ("Debt / Exit", "selling_cost_pct", "Selling Cost", ("exit", "selling_cost_pct"), "pct"),
    ("Criteria", "target_irr", "Target IRR", ("criteria", "target_irr"), "pct"),
    ("Criteria", "target_cash_on_cash", "Target Cash-on-Cash", ("criteria", "target_cash_on_cash"), "pct"),
    ("Criteria", "target_equity_multiple", "Target Equity Multiple", ("criteria", "target_equity_multiple"), "multiple"),
    ("Criteria", "max_ltv", "Max LTV", ("criteria", "max_ltv"), "pct"),
    ("Criteria", "dscr_year_one_floor", "Min DSCR - Year 1", ("criteria", "dscr_year_one_floor"), "multiple"),
    ("Criteria", "stress_dscr_floor", "Min DSCR - Stress", ("criteria", "stress_dscr_floor"), "multiple"),
)


def _get(d, key, default=None):
    if not isinstance(d, dict):
        return default
    return d.get(key, default)


def _safe_div(num: Optional[float], denom: Optional[float]) -> Optional[float]:
    if num is None or denom is None or denom == 0:
        return None
    return num / denom


def _first(*values):
    """Return the first non-None value, else None."""
    for v in values:
        if v is not None:
            return v
    return None


def _source_type_label(doc_type: str | None) -> str | None:
    normalized = (doc_type or "").lower()
    if normalized == "om":
        return "Offering Memorandum"
    if normalized == "rent_roll":
        return "Rent Roll"
    if normalized == "t12":
        return "T-12"
    return None


def _clean_source_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    name = PurePath(str(filename).replace("\\", "/")).name.strip()
    return name or None


def _source_document_labels(raw_document_ids, raw_citation_context) -> dict[str, str]:
    """Build document_id -> friendly label for memo citations.

    Prefer the original filename from citation context. Fall back to the run's
    typed document list, e.g. "Offering Memorandum", so generated memos do not
    expose internal UUIDs when filename metadata is unavailable.
    """
    labels: dict[str, str] = {}

    if isinstance(raw_document_ids, list):
        for item in raw_document_ids:
            if isinstance(item, dict):
                doc_id = item.get("document_id")
                if not doc_id:
                    continue
                filename = _clean_source_filename(
                    item.get("filename") or item.get("file_name") or item.get("name")
                )
                labels[doc_id] = filename or _source_type_label(item.get("doc_type")) or "Source Document"
            elif isinstance(item, str):
                labels.setdefault(item, "Source Document")

    if isinstance(raw_citation_context, dict):
        for meta in raw_citation_context.values():
            if not isinstance(meta, dict):
                continue
            doc_id = meta.get("document_id")
            filename = _clean_source_filename(meta.get("filename") or meta.get("file_name"))
            if doc_id and filename:
                labels[doc_id] = filename

    return labels


def _nested_get(data: dict, path: tuple[str, ...]):
    cur = data
    for part in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _format_support_value(value, kind: str) -> str:
    if value is None:
        return "-"
    try:
        if kind == "money":
            return f"${float(value):,.0f}"
        if kind == "pct":
            return f"{float(value) * 100:.2f}%"
        if kind == "int":
            return f"{int(value):,}"
        if kind == "sqft":
            return f"{float(value):,.0f} sqft"
        if kind == "years":
            return f"{int(value)} years"
        if kind == "multiple":
            return f"{float(value):.2f}x"
    except (TypeError, ValueError):
        return str(value)
    return str(value)


def _source_basis_label(meta: dict | None) -> str:
    if not isinstance(meta, dict):
        return "Unspecified"
    doc_type = str(meta.get("doc_type") or meta.get("source") or "").lower()
    source_method = str(meta.get("source_method") or "").lower()
    provenance = str(meta.get("provenance_kind") or "").lower()
    if meta.get("is_manual") or meta.get("manual_override") or doc_type == "manual":
        return "Manual override"
    if meta.get("is_default") or provenance == "default":
        return "Model default"
    if meta.get("is_computed") or provenance == "computed" or source_method == "computed":
        return "OM computed" if doc_type == "om" else "Computed"
    if meta.get("is_uncited_extraction") or provenance == "uncited_extraction":
        return "Uncited extraction"
    if doc_type == "om":
        return "OM stated"
    if doc_type == "t12":
        return "T-12"
    if doc_type == "rent_roll":
        return "Rent roll"
    if doc_type:
        return doc_type.replace("_", " ").title()
    return "Unspecified"


def _confidence_label(meta: dict | None) -> str:
    if not isinstance(meta, dict):
        return "-"
    confidence = meta.get("confidence")
    if confidence is None:
        return "-"
    try:
        return f"{float(confidence) * 100:.0f}%"
    except (TypeError, ValueError):
        return str(confidence)


def _short_text(value, *, limit: int = 140) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _citation_label_for_doc(doc_id: str | None, doc_labels: dict[str, str]) -> str:
    if not doc_id:
        return "Source Document"
    return doc_labels.get(doc_id) or "Source Document"


def _format_citation_tokens(tokens, citation_context, doc_labels: dict[str, str]) -> str:
    if not tokens:
        return "-"
    if not isinstance(tokens, list):
        tokens = [tokens]
    labels: list[str] = []
    for token in tokens:
        token_text = str(token)
        meta = citation_context.get(token_text) if isinstance(citation_context, dict) else None
        if isinstance(meta, dict):
            doc_label = _citation_label_for_doc(meta.get("document_id"), doc_labels)
            page = meta.get("page")
            if page:
                labels.append(f"{doc_label}: p{page}")
                continue
        labels.append(token_text)
    return ", ".join(dict.fromkeys(labels)) if labels else "-"


def _support_notes(meta: dict | None) -> str:
    if not isinstance(meta, dict):
        return ""
    notes: list[str] = []
    if meta.get("is_manual") or meta.get("manual_override"):
        original_value = meta.get("original_value")
        if original_value is not None:
            notes.append(f"Manual override; original value {original_value}.")
        else:
            notes.append("Manual override.")
        original = meta.get("original_citation")
        if isinstance(original, dict):
            text = _short_text(original.get("source_text"))
            if text:
                notes.append(f"Original source text: {text}")
    elif meta.get("is_default") or meta.get("provenance_kind") == "default":
        notes.append(_short_text(meta.get("selection_note")) or "Model default.")
        missing = meta.get("preferred_sources_missing")
        if isinstance(missing, list) and missing:
            notes.append("Missing preferred source: " + ", ".join(str(v) for v in missing[:3]))
    else:
        note = _short_text(meta.get("selection_note"))
        source_text = _short_text(meta.get("source_text"))
        if note:
            notes.append(note)
        if source_text:
            notes.append(f"Source text: {source_text}")
        if meta.get("is_uncited_extraction"):
            notes.append("No exact citation token captured; review manually.")
    return " ".join(notes)


def _build_source_support(inputs: dict, field_citations: dict, citation_context, doc_labels: dict[str, str]) -> list[dict]:
    rows: list[dict] = []
    if not isinstance(field_citations, dict):
        field_citations = {}
    for group, field_key, label, path, value_kind in _SOURCE_SUPPORT_FIELDS:
        value = _nested_get(inputs, path)
        meta = field_citations.get(field_key)
        if value is None and not isinstance(meta, dict):
            continue
        citation_meta = meta if isinstance(meta, dict) else {}
        citation_tokens = citation_meta.get("citations")
        if citation_meta.get("is_manual") or citation_meta.get("manual_override"):
            original = citation_meta.get("original_citation")
            if isinstance(original, dict):
                citation_tokens = original.get("citations") or citation_tokens
        rows.append({
            "group": group,
            "field_key": field_key,
            "label": label,
            "value": _format_support_value(value, value_kind),
            "source_basis": _source_basis_label(citation_meta),
            "citations": _format_citation_tokens(citation_tokens, citation_context, doc_labels),
            "confidence": _confidence_label(citation_meta),
            "notes": _support_notes(citation_meta),
        })
    return rows


def _clarify_unit_count_source_support(
    rows: list[dict],
    *,
    total_unit_count: int | None,
    storage_unit_count: int | None,
    non_storage_unit_count: int | None,
) -> list[dict]:
    if not (total_unit_count and storage_unit_count and non_storage_unit_count):
        return rows
    clarified: list[dict] = []
    for row in rows:
        if isinstance(row, dict) and row.get("field_key") == "num_units":
            row = dict(row)
            row["label"] = "Underwriting Unit Count"
            note = row.get("notes") or ""
            mix_note = (
                f"Unit mix shows {total_unit_count:,} total units/spaces, "
                f"including {storage_unit_count:,} storage and {non_storage_unit_count:,} non-storage."
            )
            row["notes"] = f"{note} {mix_note}".strip()
        clarified.append(row)
    return clarified


def _aggregate_rent_position(rows: list) -> dict:
    """Roll RentPositionRow buckets into a summary the narrator can cite.

    Real result_artifacts have NO top-level ``rent_position`` key — the data lives
    in ``rent_position_analysis`` (per-bucket list). Without this aggregation the
    LLM gets an empty dict and writes "rent position data not provided".
    """
    if not rows:
        return {}
    valid_rows = [r for r in rows if isinstance(r, dict)]
    comp_matched_rows = [
        r for r in valid_rows
        if (r.get("comp_count") or 0) > 0 and r.get("comp_average_rent") is not None
    ]
    current_ratios = [r.get("current_vs_comp_ratio") for r in valid_rows]
    market_ratios = [r.get("market_vs_comp_ratio") for r in valid_rows]
    current_ratios = [v for v in current_ratios if v is not None]
    market_ratios = [v for v in market_ratios if v is not None]
    unmatched_sizes = [
        str(r.get("size"))
        for r in valid_rows
        if r.get("size") and not ((r.get("comp_count") or 0) > 0 and r.get("comp_average_rent") is not None)
    ]
    return {
        "current_vs_comp_avg": sum(current_ratios) / len(current_ratios) if current_ratios else None,
        "market_vs_comp_avg": sum(market_ratios) / len(market_ratios) if market_ratios else None,
        "matched_bucket_count": len(comp_matched_rows),
        "current_ratio_bucket_count": len(current_ratios),
        "market_ratio_bucket_count": len(market_ratios),
        "total_bucket_count": len(rows),
        "unmatched_bucket_count": max(len(rows) - len(comp_matched_rows), 0),
        "unmatched_sizes": sorted(set(unmatched_sizes)),
    }


def _normalize_size_label(value: str | None) -> str | None:
    if not value:
        return None
    return "".join(ch for ch in str(value).lower() if ch.isdigit() or ch in {".", "x"})


def _is_storage_unit_mix_row(row: dict) -> bool:
    category = (row.get("unit_category") or "storage").lower()
    return category == "storage"


def _rent_comp_exact_coverage(unit_mix_raw: list, rent_comps_raw: list) -> dict:
    """Compute exact-size comp support, matching the Result UI's coverage read."""
    subject_sizes = []
    for row in unit_mix_raw or []:
        if not isinstance(row, dict) or not _is_storage_unit_mix_row(row):
            continue
        normalized = _normalize_size_label(row.get("size"))
        if normalized:
            subject_sizes.append((normalized, row.get("size") or normalized))

    if not subject_sizes:
        return {}

    comp_sizes = set()
    broker_benchmark_rows = 0
    facility_comp_rows = 0
    for row in rent_comps_raw or []:
        if not isinstance(row, dict):
            continue
        if row.get("is_broker_market_average"):
            broker_benchmark_rows += 1
            continue
        facility_comp_rows += 1
        if row.get("asking_rent") is None and row.get("rent_per_sqft") is None:
            continue
        normalized = _normalize_size_label(row.get("size"))
        if normalized:
            comp_sizes.add(normalized)

    subject_by_size = {normalized: label for normalized, label in subject_sizes}
    unmatched = [
        label for normalized, label in subject_by_size.items()
        if normalized not in comp_sizes
    ]
    total = len(subject_by_size)
    matched = max(total - len(unmatched), 0)
    return {
        "exact_size_matched_count": matched,
        "exact_size_total_count": total,
        "exact_size_unmatched_count": len(unmatched),
        "exact_size_unmatched_sizes": sorted(set(str(size) for size in unmatched)),
        "facility_comp_row_count": facility_comp_rows,
        "broker_benchmark_row_count": broker_benchmark_rows,
    }


def _fallback_rent_position_analysis(unit_mix_raw: list, rent_comps_raw: list) -> list[dict]:
    """Recompute rent-position rows for legacy runs that predate persistence.

    The result page can still show rent-comp coverage from raw unit_mix/rent_comps.
    Memo generation should have the same visibility, even when older
    result_artifacts do not include ``rent_position_analysis``.
    """
    if not unit_mix_raw or not rent_comps_raw:
        return []
    try:
        from app.verticals.real_estate.underwriting.calculator import _build_rent_position_analysis
        from app.verticals.real_estate.underwriting.schemas.self_storage import RentCompRow, UnitMixRow
    except Exception:
        logger.exception("Could not import rent-position fallback helpers")
        return []

    try:
        unit_mix = [
            row if isinstance(row, UnitMixRow) else UnitMixRow.model_validate(row)
            for row in unit_mix_raw
            if isinstance(row, (dict, UnitMixRow))
        ]
        rent_comps = [
            row if isinstance(row, RentCompRow) else RentCompRow.model_validate(row)
            for row in rent_comps_raw
            if isinstance(row, (dict, RentCompRow))
        ]
        analysis, _unknown_count = _build_rent_position_analysis(unit_mix, rent_comps)
    except Exception:
        logger.exception("Could not compute fallback rent-position analysis")
        return []

    return [row.model_dump() for row in analysis]


def build_memo_context(run, memo) -> MemoContext:
    """Build a MemoContext from a run ORM object and a memo ORM object."""
    inputs = run.inputs or {}
    artifact = run.result_artifact or {}

    project = _get(inputs, "project", {}) or {}
    acquisition = _get(inputs, "acquisition", {}) or {}
    financing = _get(inputs, "financing", {}) or {}
    criteria = _get(inputs, "criteria", {}) or {}
    unit_mix_raw = _get(inputs, "unit_mix", []) or _get(artifact, "unit_mix", []) or []
    rent_comps_raw = _get(inputs, "rent_comps", []) or _get(artifact, "rent_comps", []) or []
    rent_position_analysis = list(_get(artifact, "rent_position_analysis", []) or [])
    if not rent_position_analysis:
        rent_position_analysis = _fallback_rent_position_analysis(unit_mix_raw, rent_comps_raw)

    # ── Climate-control breakdown ──────────────────────────────────────────
    cc_units = 0
    nc_units = 0
    total_unit_count = 0
    storage_unit_count = 0
    non_storage_unit_count = 0
    for row in unit_mix_raw:
        num = _get(row, "num_units", 0) or 0
        category = (_get(row, "unit_category") or "").lower()
        total_unit_count += int(num)
        if category == "storage":
            storage_unit_count += int(num)
        elif category:
            non_storage_unit_count += int(num)
        climate = (_get(row, "climate_type") or "").upper()
        if category and category != "storage":
            continue
        if climate == "CC":
            cc_units += int(num)
        elif climate == "NC":
            nc_units += int(num)
    total_units = cc_units + nc_units
    cc_pct = (cc_units / total_units) if total_units > 0 else 0.0

    # ── Acquisition derived metrics ────────────────────────────────────────
    purchase_price = _get(acquisition, "purchase_price")
    num_units = _get(project, "num_units")
    rentable_sqft = _get(project, "rentable_sqft")

    price_per_unit = _safe_div(purchase_price, num_units)
    price_per_sqft = _safe_div(purchase_price, rentable_sqft)

    # Cap rate at cost — prefer the modeled year-one cap, fall back to the
    # broker-stated market cap rate from the acquisition inputs.
    cap_rate_at_cost = _first(
        getattr(run, "cap_rate_year_one", None),
        _get(artifact, "cap_rate_year_one"),
        _get(acquisition, "market_cap_rate_purchase"),
    )

    # ── NOI buildup (Year 1) ───────────────────────────────────────────────
    # Pass-through of the calculator's AnnualProjection[0] shape. No key
    # renaming — the renderer reads the same names.
    projections = _get(artifact, "projections", []) or []
    noi_buildup = dict(projections[0]) if projections else {}
    # Ensure noi is present even if projections list is empty.
    if "noi" not in noi_buildup or noi_buildup["noi"] is None:
        noi_buildup["noi"] = _first(
            getattr(run, "noi_year_one", None),
            _get(artifact, "noi_year_one"),
        )

    # ── Return metrics ─────────────────────────────────────────────────────
    # Pass-through of the calculator's SelfStorageResult top-level metric
    # fields. No key renaming — the renderer reads the same names.
    return_metrics = {
        "irr": _first(getattr(run, "irr", None), _get(artifact, "irr")),
        "cash_on_cash": _first(getattr(run, "cash_on_cash", None), _get(artifact, "cash_on_cash")),
        "equity_multiple": _first(getattr(run, "equity_multiple", None), _get(artifact, "equity_multiple")),
        "dscr_year_one": _first(getattr(run, "dscr_year_one", None), _get(artifact, "dscr_year_one")),
        "debt_yield": _get(artifact, "debt_yield"),
        "break_even_occupancy_pct": _get(artifact, "break_even_occupancy_pct"),
    }

    # ── Max loan (computed inline — not persisted) ─────────────────────────
    max_loan = _compute_max_loan(run)

    # ── Verdict / classification ───────────────────────────────────────────
    verdict_status = getattr(run, "verdict_status", None)
    classification_calculator = _VERDICT_STATUS_TO_CLASSIFICATION.get(verdict_status)
    verdict_failures = list(getattr(run, "verdict_failures", []) or [])
    # Compose human-readable warnings from verdict_failures rows.
    warnings_list = []
    for f in verdict_failures:
        if isinstance(f, dict):
            metric = f.get("metric") or "metric"
            actual = f.get("actual")
            target = f.get("target")
            if actual is not None and target is not None:
                warnings_list.append(f"{metric}: {actual} vs target {target}")
            else:
                warnings_list.append(str(f))
        else:
            warnings_list.append(str(f))

    # ── Analyst thesis & strategy inputs ────────────────────────────────────
    thesis_data = dict(getattr(memo, "thesis_data", {}) or {})
    verdict_override = thesis_data.get("verdict_override") or None
    # Only treat override as active if it's one of the expected classification labels.
    if verdict_override not in {"Pursue", "Needs Review", "Below Screen"}:
        verdict_override = None
    # Effective classification: analyst override wins; otherwise calculator verdict.
    classification = verdict_override or classification_calculator
    citation_context = getattr(run, "citation_context", None)
    document_ids = _extract_om_document_ids(getattr(run, "document_ids", None))
    citation_doc_labels = _source_document_labels(getattr(run, "document_ids", None), citation_context)
    source_support = _build_source_support(
        inputs,
        getattr(run, "field_citations", None) or {},
        citation_context,
        citation_doc_labels,
    )
    source_support = _clarify_unit_count_source_support(
        source_support,
        total_unit_count=total_unit_count or num_units,
        storage_unit_count=storage_unit_count or num_units,
        non_storage_unit_count=non_storage_unit_count or None,
    )

    return MemoContext(
        deal_name=_get(project, "name") or getattr(run, "name", None) or "Untitled Deal",
        address=_get(project, "address") or getattr(run, "address", None),
        asset_type=_get(project, "asset_type", "self_storage"),
        year_built=_get(project, "year_built"),
        num_units=num_units,
        rentable_sqft=rentable_sqft,
        total_unit_count=total_unit_count or num_units,
        storage_unit_count=storage_unit_count or num_units,
        non_storage_unit_count=non_storage_unit_count or None,
        cc_unit_count=cc_units,
        nc_unit_count=nc_units,
        climate_control_pct=cc_pct,
        purchase_price=purchase_price,
        price_per_unit=price_per_unit,
        price_per_sqft=price_per_sqft,
        cap_rate_at_cost=cap_rate_at_cost,
        population_3mi=_get(project, "population_3mi"),
        avg_household_income_3mi=_get(project, "avg_household_income_3mi"),
        storage_sqft_per_capita_3mi=_get(project, "storage_sqft_per_capita_3mi"),
        nearby_storage_1mi=_get(project, "nearby_storage_count_1mi"),
        nearby_storage_3mi=_get(project, "nearby_storage_count_3mi"),
        nearby_storage_5mi=_get(project, "nearby_storage_count_5mi"),
        noi_buildup=noi_buildup,
        return_metrics=return_metrics,
        noi_bridge=_get(artifact, "noi_bridge", {}) or {},
        # Aggregate per-bucket rent_position_analysis into a summary the narrator
        # can cite — real artifacts have no top-level rent_position key.
        rent_position={
            **(_get(artifact, "rent_position", {}) or _aggregate_rent_position(rent_position_analysis)),
            **_rent_comp_exact_coverage(unit_mix_raw, rent_comps_raw),
        },
        sensitivity=_get(artifact, "sensitivity", {}) or {},
        stress_tests=_get(artifact, "stress_tests", []) or [],
        rollover=_get(artifact, "rollover_risk", {}) or _get(artifact, "rollover", {}) or {},
        projections=list(_get(artifact, "projections", []) or []),
        capital_structure=_get(artifact, "capital_structure", {}) or {},
        rent_position_analysis=rent_position_analysis,
        max_loan=max_loan,
        financing=financing,
        operational=_get(inputs, "operational", {}) or {},
        unit_mix=list(unit_mix_raw)[:_MAX_UNIT_MIX_ROWS],
        rent_comps=list(rent_comps_raw)[:_MAX_RENT_COMPS_ROWS],
        criteria=criteria,
        capex_reserve_per_unit=_get(acquisition, "capex_reserve_per_unit"),
        source_support=source_support,
        classification=classification,
        classification_calculator=classification_calculator,
        warnings=warnings_list,
        rationale=(_get(artifact, "verdict", {}) or {}).get("rationale"),
        cover_data=dict(getattr(memo, "cover_data", {}) or {}),
        sponsor_data=dict(getattr(memo, "sponsor_data", {}) or {}),
        market_notes=getattr(memo, "market_notes", None),
        # Analyst inputs — straight from thesis_data JSON
        thesis_text=(thesis_data.get("thesis_text") or None),
        strategy_type=(thesis_data.get("strategy_type") or None),
        hold_period_years_override=thesis_data.get("hold_period_years") or None,
        verdict_override=verdict_override,
        verdict_override_reason=(thesis_data.get("verdict_override_reason") or None),
        custom_conditions=[
            c for c in (thesis_data.get("custom_conditions") or []) if isinstance(c, str) and c.strip()
        ],
        sourcing_type=(thesis_data.get("sourcing_type") or None),
        sourcing_detail=(thesis_data.get("sourcing_detail") or None),
        retrieved_chunks={},
        document_ids=document_ids,
        citation_doc_labels=citation_doc_labels,
    )


def _compute_max_loan(run) -> dict:
    """Compute MaxLoanResult inline using the shared helper from max_loan.py.

    Returns ``{}`` (empty table) if computation cannot proceed — the renderer
    handles missing fields gracefully.
    """
    try:
        from app.verticals.real_estate.underwriting.max_loan import compute_max_loan_for_run
    except Exception:
        logger.exception("Could not import compute_max_loan_for_run; max-loan table will be blank")
        return {}

    try:
        result = compute_max_loan_for_run(run)
    except Exception:
        logger.exception("compute_max_loan_for_run failed; max-loan table will be blank")
        return {}

    if result is None:
        return {}
    return result.model_dump()


def _extract_om_document_ids(raw) -> list[str]:
    """Extract OM document IDs from run.document_ids.

    Production schema (per db_models_re.py): list of {document_id, doc_type} dicts.
    Filter to doc_type == "om" to scope RAG retrieval to the offering memorandum.
    Accept bare strings too so legacy/test fixtures keep working.
    """
    if not raw:
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            doc_type = (item.get("doc_type") or "").lower()
            doc_id = item.get("document_id")
            if doc_id and (not doc_type or doc_type == "om"):
                out.append(doc_id)
    return out
