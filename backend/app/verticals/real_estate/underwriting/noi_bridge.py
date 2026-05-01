"""NOI bridge artifact builder.

This module intentionally sits outside the calculator: the calculator produces
math outputs, while this helper packages source-vs-model context for the UI.
"""

from __future__ import annotations

from typing import Any

from .extraction.schemas import OMExtraction, T12Extraction
from .schemas.self_storage import SelfStorageInputs, SelfStorageResult


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _artifact_value(source_artifact: dict | None, *path: str) -> Any:
    current: Any = source_artifact
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _row(
    *,
    label: str,
    value: float,
    source_type: str,
    source_field: str,
    prior_value: float | None,
) -> dict[str, Any]:
    """Create one bridge row.

    `delta_to_prior` follows standard analyst convention: positive means the
    current row is HIGHER than the prior row (i.e. value increased).
    """
    payload: dict[str, Any] = {
        "label": label,
        "value": value,
        "source_type": source_type,
        "source_field": source_field,
    }
    if prior_value is not None:
        delta = value - prior_value
        payload["delta_to_prior"] = {
            "amount": delta,
            "pct": delta / prior_value if prior_value else None,
        }
    return payload


def build_noi_bridge(
    merged: SelfStorageInputs,
    om: OMExtraction | None,
    t12: T12Extraction | None,
    result: SelfStorageResult,
    source_artifact: dict | None = None,
) -> dict[str, Any]:
    """Build an analyst-facing NOI source bridge.

    `source_artifact` is used only on manual recalculation, where the original
    typed extraction models are no longer available but preserved source blocks
    still contain enough evidence to keep the bridge fresh.
    """
    rows: list[dict[str, Any]] = []

    def append_row(label: str, value: float | None, source_type: str, source_field: str) -> None:
        if value is None:
            return
        prior = rows[-1]["value"] if rows else None
        rows.append(
            _row(
                label=label,
                value=value,
                source_type=source_type,
                source_field=source_field,
                prior_value=prior,
            )
        )

    om_year_one_noi = _number(merged.operational.noi_year_one_stated)
    if om_year_one_noi is None and om is not None:
        om_year_one_noi = _number(om.noi_year_one_stated)
        if om_year_one_noi is None:
            om_year_one_noi = _number(om.noi_projected)
    if om_year_one_noi is None:
        om_year_one_noi = _number(_artifact_value(source_artifact, "om_data", "noi_year_one_stated"))
        if om_year_one_noi is None:
            om_year_one_noi = _number(_artifact_value(source_artifact, "om_data", "noi_projected"))
    append_row("OM Year-1 NOI", om_year_one_noi, "om", "noi_year_one_stated")

    om_current_noi = _number(merged.operational.noi_current_stated)
    if om_current_noi is None and om is not None:
        om_current_noi = _number(om.noi_current_stated)
    if om_current_noi is None:
        om_current_noi = _number(_artifact_value(source_artifact, "om_data", "noi_current_stated"))
    append_row("OM Current NOI", om_current_noi, "om", "noi_current_stated")

    t12_noi = None
    period_months = None
    if t12 is not None:
        period_months = t12.period_months
        factor = 12.0 / period_months if period_months and 0 < period_months < 12 else 1.0
        t12_noi = _number(t12.noi_actual * factor if t12.noi_actual is not None else None)
    if t12_noi is None:
        t12_noi = _number(_artifact_value(source_artifact, "t12_data", "summary", "noi_actual"))
        period_months = _artifact_value(source_artifact, "t12_data", "summary", "period_months")
    if period_months and period_months < 12:
        t12_label = f"T-{period_months} actual NOI annualized"
    elif period_months == 12:
        t12_label = "T-12 actual NOI"
    else:
        t12_label = "Operating statement NOI"
    append_row(t12_label, t12_noi, "t12", "noi_actual")

    model_noi = None
    if result.projections:
        model_noi = _number(result.projections[0].noi)
    if model_noi is None:
        model_noi = _number(result.noi_year_one)
    append_row("Model Year-1 NOI", model_noi, "model", "noi_year_one")

    return {
        "rows": rows,
        "has_t12": any(row["source_type"] == "t12" for row in rows),
        "model_source": result.expense_basis.source if result.expense_basis else None,
    }
