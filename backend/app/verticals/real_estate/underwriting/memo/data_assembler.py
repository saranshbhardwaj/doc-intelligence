"""Pulls a completed underwriting run and a memo row into a single MemoContext.

Reads only the run + memo ORM objects. The one outbound call is to the pure
``calculate_max_loan`` helper (max-loan is not persisted on the run; the API
recomputes it on demand and so do we, with the same inputs).
"""
from __future__ import annotations

import logging
from typing import Optional

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


def _aggregate_rent_position(rows: list) -> dict:
    """Roll RentPositionRow buckets into a summary the narrator can cite.

    Real result_artifacts have NO top-level ``rent_position`` key — the data lives
    in ``rent_position_analysis`` (per-bucket list). Without this aggregation the
    LLM gets an empty dict and writes "rent position data not provided".
    """
    if not rows:
        return {}
    current_ratios = [r.get("current_vs_comp_ratio") for r in rows if isinstance(r, dict)]
    market_ratios = [r.get("market_vs_comp_ratio") for r in rows if isinstance(r, dict)]
    current_ratios = [v for v in current_ratios if v is not None]
    market_ratios = [v for v in market_ratios if v is not None]
    return {
        "current_vs_comp_avg": sum(current_ratios) / len(current_ratios) if current_ratios else None,
        "market_vs_comp_avg": sum(market_ratios) / len(market_ratios) if market_ratios else None,
        "matched_bucket_count": len(current_ratios),
        "total_bucket_count": len(rows),
    }


def build_memo_context(run, memo) -> MemoContext:
    """Build a MemoContext from a run ORM object and a memo ORM object."""
    inputs = run.inputs or {}
    artifact = run.result_artifact or {}

    project = _get(inputs, "project", {}) or {}
    acquisition = _get(inputs, "acquisition", {}) or {}
    financing = _get(inputs, "financing", {}) or {}
    criteria = _get(inputs, "criteria", {}) or {}
    unit_mix_raw = _get(inputs, "unit_mix", []) or _get(artifact, "unit_mix", []) or []
    rent_comps_raw = _get(inputs, "rent_comps", []) or []

    # ── Climate-control breakdown ──────────────────────────────────────────
    cc_units = 0
    nc_units = 0
    for row in unit_mix_raw:
        num = _get(row, "num_units", 0) or 0
        climate = (_get(row, "climate_type") or "").upper()
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

    return MemoContext(
        deal_name=_get(project, "name") or getattr(run, "name", None) or "Untitled Deal",
        address=_get(project, "address") or getattr(run, "address", None),
        asset_type=_get(project, "asset_type", "self_storage"),
        year_built=_get(project, "year_built"),
        num_units=num_units,
        rentable_sqft=rentable_sqft,
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
        rent_position=(
            _get(artifact, "rent_position", {})
            or _aggregate_rent_position(_get(artifact, "rent_position_analysis", []) or [])
        ),
        sensitivity=_get(artifact, "sensitivity", {}) or {},
        stress_tests=_get(artifact, "stress_tests", []) or [],
        rollover=_get(artifact, "rollover_risk", {}) or _get(artifact, "rollover", {}) or {},
        projections=list(_get(artifact, "projections", []) or []),
        capital_structure=_get(artifact, "capital_structure", {}) or {},
        rent_position_analysis=list(_get(artifact, "rent_position_analysis", []) or []),
        max_loan=max_loan,
        financing=financing,
        unit_mix=list(unit_mix_raw)[:_MAX_UNIT_MIX_ROWS],
        rent_comps=list(rent_comps_raw)[:_MAX_RENT_COMPS_ROWS],
        criteria=criteria,
        capex_reserve_per_unit=_get(acquisition, "capex_reserve_per_unit"),
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
        document_ids=_extract_om_document_ids(getattr(run, "document_ids", None)),
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
