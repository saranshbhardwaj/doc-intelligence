"""Deterministic risk policy for IC memo risks.

This module builds risk candidates directly from ``MemoContext`` so known
credit-risk dimensions do not depend on LLM-generated wording or mitigants.
"""
from __future__ import annotations

from typing import Any

from .schemas import MemoContext, Risk, RisksSection


def _fmt_pct(value: float | int | None, digits: int = 1) -> str | None:
    if value is None:
        return None
    return f"{float(value) * 100:.{digits}f}%"


def _fmt_multiple(value: float | int | None) -> str | None:
    if value is None:
        return None
    return f"{float(value):.2f}x"


def _metric_from_stress(stress: dict[str, Any], key: str) -> float | None:
    value = stress.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stress_identity(stress: dict[str, Any]) -> str:
    return f"{stress.get('scenario_key') or ''} {stress.get('label') or ''}".lower()


def _is_zero_rent_growth(stress: dict[str, Any]) -> bool:
    identity = _stress_identity(stress)
    return "rent_growth_zero" in identity or "rent growth = 0" in identity or "zero rent" in identity


def _is_vacancy_stress(stress: dict[str, Any]) -> bool:
    identity = _stress_identity(stress)
    return "vacancy" in identity or "occupancy" in identity


def _mixed_revenue_risk(ctx: MemoContext) -> Risk | None:
    total = ctx.total_unit_count
    non_storage = ctx.non_storage_unit_count
    if not total or not non_storage:
        return None
    share = non_storage / total
    return Risk(
        title=(
            f"Mixed revenue stream: {non_storage} of {total} units/spaces "
            f"({_fmt_pct(share, 0)} of unit count) are non-storage, creating model risk because blended self-storage assumptions may not reflect parking/residential economics."
        ),
        severity="high" if share >= 0.20 else "medium",
        source="verdict_warning",
        mitigant=None,
    )


def _above_comp_rent_risk(ctx: MemoContext) -> Risk | None:
    rent_position = ctx.rent_position or {}
    current_vs_comp = rent_position.get("current_vs_comp_avg")
    if current_vs_comp is None:
        return None
    try:
        current_vs_comp = float(current_vs_comp)
    except (TypeError, ValueError):
        return None
    if current_vs_comp <= 1.10:
        return None

    coverage = ""
    matched = rent_position.get("exact_size_matched_count")
    total = rent_position.get("exact_size_total_count")
    if matched is not None and total:
        coverage = f" Rent-position support covers {matched} of {total} exact subject sizes."
    return Risk(
        title=(
            f"In-place rents are {_fmt_pct(current_vs_comp)} of the matched comp average, creating rent sustainability risk if occupancy declines or tenants roll."
            f"{coverage}"
        ),
        severity="high" if current_vs_comp >= 1.20 else "medium",
        source="rent_position",
        mitigant=None,
    )


def _zero_rent_growth_risk(ctx: MemoContext) -> Risk | None:
    criteria = ctx.criteria or {}
    target_irr = criteria.get("target_irr")
    target_em = criteria.get("target_equity_multiple")
    for stress in ctx.stress_tests or []:
        if not isinstance(stress, dict) or not _is_zero_rent_growth(stress):
            continue
        irr = _metric_from_stress(stress, "irr")
        equity_multiple = _metric_from_stress(stress, "equity_multiple")
        misses_irr = target_irr is not None and irr is not None and irr < float(target_irr)
        misses_em = target_em is not None and equity_multiple is not None and equity_multiple < float(target_em)
        if not (misses_irr or misses_em):
            return None
        pieces = []
        if equity_multiple is not None:
            pieces.append(f"equity multiple to {_fmt_multiple(equity_multiple)}")
        if irr is not None:
            pieces.append(f"IRR to {_fmt_pct(irr, 2)}")
        metrics = " and ".join(pieces) if pieces else "returns below target"
        return Risk(
            title=(
                f"Zero rent growth stress reduces {metrics}, indicating material sensitivity to the modeled rent-growth assumption."
            ),
            severity="medium",
            source="stress_test",
            mitigant=None,
        )
    return None


def _vacancy_stress_risk(ctx: MemoContext) -> Risk | None:
    criteria = ctx.criteria or {}
    target_irr = criteria.get("target_irr")
    dscr_floor = criteria.get("dscr_year_one_floor")
    for stress in ctx.stress_tests or []:
        if not isinstance(stress, dict) or not _is_vacancy_stress(stress):
            continue
        irr = _metric_from_stress(stress, "irr")
        dscr = _metric_from_stress(stress, "dscr_year_one")
        equity_multiple = _metric_from_stress(stress, "equity_multiple")
        misses_irr = target_irr is not None and irr is not None and irr < float(target_irr)
        tight_dscr = dscr_floor is not None and dscr is not None and dscr - float(dscr_floor) <= 0.10
        if not (misses_irr or tight_dscr):
            return None
        pieces = []
        if dscr is not None:
            pieces.append(f"DSCR to {_fmt_multiple(dscr)}")
        if irr is not None:
            pieces.append(f"IRR to {_fmt_pct(irr, 2)}")
        if equity_multiple is not None:
            pieces.append(f"equity multiple to {_fmt_multiple(equity_multiple)}")
        metrics = ", ".join(pieces) if pieces else "returns"
        return Risk(
            title=f"Vacancy +5% stress reduces {metrics}, narrowing operating cushion under lower occupancy.",
            severity="medium",
            source="stress_test",
            mitigant=None,
        )
    return None


def _capex_reserve_risk(ctx: MemoContext) -> Risk | None:
    reserve_per_unit = ctx.capex_reserve_per_unit
    reserve_initial = (ctx.capital_structure or {}).get("capex_reserve_initial")
    has_zero_reserve = reserve_per_unit == 0 or reserve_initial == 0
    if not has_zero_reserve:
        return None
    age_phrase = ""
    if ctx.year_built:
        age_phrase = f" on a {ctx.year_built}-vintage asset"
    return Risk(
        title=f"Capex reserve is zero, leaving no dedicated cushion for unexpected repairs or capital improvements{age_phrase}.",
        severity="medium",
        source="verdict_warning",
        mitigant=None,
    )


def build_structured_risks(ctx: MemoContext) -> RisksSection | None:
    """Return deterministic risks when policy has enough supported candidates.

    The renderer requires 3-6 risks. If fewer than 3 supported policy risks are
    present, the caller should fall back to the guarded LLM risk section.
    """
    candidates = [
        _mixed_revenue_risk(ctx),
        _above_comp_rent_risk(ctx),
        _zero_rent_growth_risk(ctx),
        _vacancy_stress_risk(ctx),
        _capex_reserve_risk(ctx),
    ]
    risks = [risk for risk in candidates if risk is not None]
    if len(risks) < 3:
        return None
    return RisksSection(risks=risks[:6])