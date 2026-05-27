"""IC memo narrator: 1 priming call (Executive Summary) + 8 parallel calls.

The narrator depends on two collaborators passed in by the Celery task:

  - `llm`: anything with `async def parse(system, messages, output_format, max_tokens)`
           returning a parsed Pydantic instance. In production this is a thin wrapper
           around `AsyncAnthropic.messages.parse(...)`. In tests it's a FakeLLM.

  - `retriever`: anything with `def retrieve(query, document_ids, top_n, section_key)`
           returning a list of `RetrievedChunk`. In production this wraps the existing
           RAG service + reranker.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional

from .prompts import build_system_blocks, build_user_blocks
from .schemas import (
    Citation,
    MemoContext,
    PROSE_SECTIONS,
    ProseSection,
    Recommendation,
    Risk,
    RisksSection,
    RetrievedChunk,
    SECTION_EXECUTIVE_SUMMARY,
    SECTION_FINANCIAL_ANALYSIS,
    SECTION_INVESTMENT_THESIS,
    SECTION_MARKET_OVERVIEW,
    SECTION_PROPERTY_DESCRIPTION,
    SECTION_RECOMMENDATION,
    SECTION_RENT_POSITION,
    SECTION_RISKS,
    SECTION_TRANSACTION_OVERVIEW,
)

logger = logging.getLogger(__name__)


_RAG_SECTIONS: dict[str, dict[str, Any]] = {
    SECTION_PROPERTY_DESCRIPTION: {
        "query": "property description construction year built climate control unit configuration",
        "top_n": 3,
    },
    SECTION_MARKET_OVERVIEW: {
        "query": "submarket demographics supply demand population growth competing facilities",
        "top_n": 5,
    },
}


SECTION_SCHEMAS = {
    **{s: ProseSection for s in PROSE_SECTIONS},
    SECTION_RISKS: RisksSection,
    SECTION_RECOMMENDATION: Recommendation,
}


async def _call_one_section(ctx: MemoContext, section: str, llm) -> Any:
    """Single LLM call for one section. Returns the parsed Pydantic object."""
    schema = SECTION_SCHEMAS[section]
    system = build_system_blocks()
    user = build_user_blocks(ctx, section_key=section)
    return await llm.parse(
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=schema,
        max_tokens=1000,
    )


def _retrieve_for_rag_sections(ctx: MemoContext, retriever) -> None:
    """Populate ctx.retrieved_chunks for RAG-using sections, in place."""
    for section, params in _RAG_SECTIONS.items():
        chunks = retriever.retrieve(
            query=params["query"],
            document_ids=ctx.document_ids,
            top_n=params["top_n"],
            section_key=section,
        )
        ctx.retrieved_chunks[section] = list(chunks or [])


def _validate_citations(parsed: Any, ctx: MemoContext, section: str) -> Any:
    """Drop any citation referencing a (doc_id, page) not in the retrieved set for this section."""
    if parsed is None:
        return None
    retrieved = {(c.doc_id, c.page) for c in ctx.retrieved_chunks.get(section, [])}

    if isinstance(parsed, ProseSection):
        kept = [c for c in parsed.citations if (c.doc_id, c.page) in retrieved]
        dropped = len(parsed.citations) - len(kept)
        if dropped:
            logger.warning("Dropped %d fabricated citations in section %s", dropped, section)
        parsed.citations = kept

    elif isinstance(parsed, RisksSection):
        for risk in parsed.risks:
            if risk.citation and (risk.citation.doc_id, risk.citation.page) not in retrieved:
                logger.warning("Dropped fabricated citation on risk: %s", risk.title)
                risk.citation = None

    return parsed


def _fmt_money(value: float | int | None) -> str | None:
    if value is None:
        return None
    return f"${float(value):,.0f}"


def _fmt_pct(value: float | int | None) -> str | None:
    if value is None:
        return None
    return f"{float(value) * 100:.2f}%"


def _fmt_int(value: float | int | None) -> str | None:
    if value is None:
        return None
    return f"{int(value):,}"


def _unit_mix_phrase(ctx: MemoContext) -> str | None:
    total = ctx.total_unit_count
    storage = ctx.storage_unit_count
    non_storage = ctx.non_storage_unit_count
    if total and storage and non_storage:
        return (
            f"{_fmt_int(total)} total units/spaces, including "
            f"{_fmt_int(storage)} storage units and {_fmt_int(non_storage)} "
            "non-storage units/spaces"
        )
    if storage:
        return f"{_fmt_int(storage)} storage units"
    if total:
        return f"{_fmt_int(total)} total units/spaces"
    return None


def _transaction_paragraph(ctx: MemoContext) -> str | None:
    pieces: list[str] = []
    price = _fmt_money(ctx.purchase_price)
    per_unit = _fmt_money(ctx.price_per_unit)
    per_sqft = _fmt_money(ctx.price_per_sqft)
    cap = _fmt_pct(ctx.cap_rate_at_cost)

    if price:
        sentence = f"The acquisition price is {price}"
        if per_unit:
            unit_label = "storage unit" if ctx.non_storage_unit_count else "unit"
            sentence += f", or {per_unit} per {unit_label}"
        if per_sqft:
            sentence += f" and {per_sqft} per rentable square foot"
        sentence += "."
        pieces.append(sentence)
    if cap:
        pieces.append(f"The going-in cap rate is {cap}.")
    mix = _unit_mix_phrase(ctx)
    if mix and ctx.non_storage_unit_count:
        pieces.append(f"The unit basis should be read against {mix}.")
    return " ".join(pieces) if pieces else None


def _property_opening_paragraph(ctx: MemoContext) -> str | None:
    subject_bits: list[str] = []
    mix = _unit_mix_phrase(ctx)
    if mix:
        subject_bits.append(mix)
    if ctx.rentable_sqft is not None:
        subject_bits.append(f"{_fmt_int(ctx.rentable_sqft)} rentable square feet")
    if not subject_bits and ctx.year_built is None:
        return None

    opening_parts: list[str] = []
    if subject_bits:
        opening_parts.append(f"The property includes {' and '.join(subject_bits)}")
    if ctx.year_built is not None:
        opening_parts.append(f"it was built in {ctx.year_built}")

    opening = "; ".join(opening_parts) + "."
    storage_units = (ctx.cc_unit_count or 0) + (ctx.nc_unit_count or 0)
    if storage_units:
        opening += (
            f" Storage mix is {_fmt_int(ctx.cc_unit_count)} climate-controlled units "
            f"and {_fmt_int(ctx.nc_unit_count)} non-climate-controlled units "
            f"({ctx.climate_control_pct * 100:.1f}% climate-controlled)."
        )
    return opening


def _clean_mixed_unit_language(text: str) -> str:
    text = re.sub(
        r"(\d+\s+of\s+\d+\s+units(?:/spaces)?\s*)\((\d+(?:\.\d+)?)%\s+of\s+unit-mix\s+scheduled\s+rent\)",
        r"\1(\2% of unit count)",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\((\d+(?:\.\d+)?)%\s+of\s+unit-mix\s+scheduled\s+rent\)",
        r"(\1% of scheduled rent)",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(\d+\s+of\s+\d+\s+units(?:/spaces)?\s*)\((\d+(?:\.\d+)?)%\)",
        r"\1(\2% of unit count)",
        text,
        flags=re.IGNORECASE,
    )
    return text


def _clean_metric_threshold_language(text: str, ctx: MemoContext) -> str:
    target_irr = (ctx.criteria or {}).get("target_irr")
    irr = (ctx.return_metrics or {}).get("irr")
    if irr is not None and target_irr is not None and irr >= target_irr:
        text = re.sub(
            r"(IRR\s+of\s+[\d.]+%\s+)falls\s+short\s+of\s+the\s+([\d.]+%\s+hurdle)(?:\s+only\s+marginally)?",
            r"\1exceeds the \2",
            text,
            flags=re.IGNORECASE,
        )
    return text


def _clean_prose_paragraph(paragraph: str, ctx: MemoContext) -> str:
    text = _clean_mixed_unit_language(paragraph)
    text = _clean_metric_threshold_language(text, ctx)
    replacements = {
        "supply-constrained market": "supply-pressured market",
        "supply-constrained environment": "supply-pressured market",
        "warrant rejection absent": "warrant repricing or stronger diligence support absent",
        "warrants rejection absent": "warrants repricing or stronger diligence support absent",
        "material enough to warrant rejection": "material enough to require repricing or stronger diligence support",
        "driven by below-benchmark expense ratios and mixed-use revenue concentration": (
            "with below-benchmark expense ratios and mixed-use revenue concentration requiring diligence"
        ),
    }
    for old, new in replacements.items():
        text = re.sub(old, new, text, flags=re.IGNORECASE)
    return text


def _fmt_signed_money_delta(value: float | int | None) -> str | None:
    if value is None:
        return None
    amount = abs(float(value))
    sign = "+" if value > 0 else "-" if value < 0 else ""
    return f"{sign}${amount:,.0f}"


def _financial_analysis_paragraph(ctx: MemoContext) -> str | None:
    modeled_noi = (ctx.noi_buildup or {}).get("noi")
    bridge = ctx.noi_bridge or {}
    operational = ctx.operational or {}
    om_y1 = (
        bridge.get("om_year_one_noi")
        or bridge.get("om_stated")
        or bridge.get("om_year_1")
        or operational.get("noi_year_one_stated")
    )
    om_current = (
        bridge.get("om_current_noi")
        or bridge.get("om_current")
        or operational.get("noi_current_stated")
    )
    parts: list[str] = []

    if modeled_noi is not None and om_y1 is not None:
        delta = modeled_noi - om_y1
        parts.append(
            f"Modeled Year-1 NOI is {_fmt_money(modeled_noi)} versus OM Year-1 NOI of "
            f"{_fmt_money(om_y1)}, a {_fmt_signed_money_delta(delta)} variance."
        )
    elif modeled_noi is not None:
        parts.append(f"Modeled Year-1 NOI is {_fmt_money(modeled_noi)}.")

    if modeled_noi and om_current is not None:
        pct_below = (modeled_noi - om_current) / modeled_noi
        relationship = "below" if pct_below >= 0 else "above"
        parts.append(
            f"OM current NOI is {_fmt_money(om_current)}, "
            f"{abs(pct_below):.1%} {relationship} modeled Year-1 NOI."
        )

    returns = ctx.return_metrics or {}
    criteria = ctx.criteria or {}
    threshold_lines: list[str] = []
    metric_specs = [
        ("IRR", returns.get("irr"), criteria.get("target_irr"), _fmt_pct, "target"),
        ("cash-on-cash", returns.get("cash_on_cash"), criteria.get("target_cash_on_cash"), _fmt_pct, "target"),
        ("equity multiple", returns.get("equity_multiple"), criteria.get("target_equity_multiple"), lambda v: f"{v:.2f}x" if v is not None else None, "target"),
        ("Year-1 DSCR", returns.get("dscr_year_one"), criteria.get("dscr_year_one_floor"), lambda v: f"{v:.2f}x" if v is not None else None, "floor"),
    ]
    for label, value, threshold, formatter, threshold_label in metric_specs:
        if value is None or threshold is None:
            continue
        verb = "clears" if value >= threshold else "falls short of"
        threshold_lines.append(
            f"{label} {formatter(value)} {verb} the {formatter(threshold)} {threshold_label}"
        )
    if threshold_lines:
        parts.append("; ".join(threshold_lines) + ".")

    if not parts:
        return None
    return " ".join(parts)


def _rent_position_paragraph(ctx: MemoContext) -> str | None:
    rp = ctx.rent_position or {}
    total = rp.get("total_bucket_count")
    matched = rp.get("matched_bucket_count")
    current_ratio_count = rp.get("current_ratio_bucket_count")
    current_avg = rp.get("current_vs_comp_avg")
    market_avg = rp.get("market_vs_comp_avg")
    unmatched = rp.get("unmatched_sizes") or []
    exact_total = rp.get("exact_size_total_count")
    exact_matched = rp.get("exact_size_matched_count")
    exact_unmatched = rp.get("exact_size_unmatched_sizes") or []

    if not total:
        return "Rent position cannot be assessed because no subject-to-comp matching data is available."

    if not matched:
        return (
            "Rent position cannot be assessed because no subject size buckets matched "
            "the available comp set cleanly enough for a rent-position read."
        )

    coverage = f"{matched} of {total} rent-position buckets have comp coverage"
    if exact_total:
        coverage = (
            f"{exact_matched} of {exact_total} exact subject sizes have comp support; "
            f"{coverage}"
        )
    if current_avg is None:
        sentence = (
            f"{coverage}, but rent position cannot be quantified because subject rent "
            "data or clean current-rent ratios are incomplete."
        )
    else:
        relationship = "below"
        if current_avg > 1.05:
            relationship = "above"
        elif 0.95 <= current_avg <= 1.05:
            relationship = "broadly in line with"
        sentence = (
            f"Rent-position support is partial: {coverage}. In-place rents are "
            f"{current_avg:.1%} of the matched comp average, or {relationship} market."
        )
        if market_avg is not None and current_ratio_count:
            sentence += f" Stated market rents are {market_avg:.1%} of the matched comp average."

    if matched < total:
        listed = ", ".join(str(size) for size in (exact_unmatched or unmatched)[:6])
        if listed:
            sentence += f" Unmatched subject sizes include {listed}."
        else:
            sentence += " Remaining subject sizes should be reviewed manually."
    return sentence


def _contains_derived_bad_unit_count(paragraph: str, ctx: MemoContext) -> bool:
    if not (ctx.storage_unit_count and ctx.non_storage_unit_count):
        return False
    derived = ctx.storage_unit_count - ctx.non_storage_unit_count
    if derived <= 0:
        return False
    haystack = paragraph.lower()
    return str(derived) in haystack and ("unit" in haystack or "space" in haystack)


def _apply_deterministic_prose_guards(parsed: Any, ctx: MemoContext, section: str) -> Any:
    """Replace fragile LLM count prose with canonical structured-data prose."""
    if not isinstance(parsed, ProseSection):
        return parsed
    parsed = parsed.model_copy(update={
        "paragraphs": [_clean_prose_paragraph(p, ctx) for p in parsed.paragraphs]
    })

    if section == SECTION_TRANSACTION_OVERVIEW:
        paragraph = _transaction_paragraph(ctx)
        if paragraph:
            return parsed.model_copy(update={"paragraphs": [paragraph]})

    if section == SECTION_PROPERTY_DESCRIPTION:
        opening = _property_opening_paragraph(ctx)
        if opening:
            remaining = [
                p for p in parsed.paragraphs[1:]
                if not _contains_derived_bad_unit_count(p, ctx)
            ]
            return parsed.model_copy(update={"paragraphs": [opening, *remaining]})

    if section == SECTION_RENT_POSITION:
        paragraph = _rent_position_paragraph(ctx)
        if paragraph:
            return parsed.model_copy(update={"paragraphs": [paragraph]})

    if section == SECTION_FINANCIAL_ANALYSIS:
        paragraph = _financial_analysis_paragraph(ctx)
        if paragraph:
            return parsed.model_copy(update={"paragraphs": [paragraph]})

    return parsed


def _is_bad_mitigant(risk: Risk) -> bool:
    title = risk.title.lower()
    mitigant = (risk.mitigant or "").lower()
    if not mitigant:
        return False
    if "cash-on-cash" in title or "cash on cash" in title:
        return any(token in mitigant for token in ("leverage", "ltv", "additional debt", "dscr"))
    if "equity multiple" in title:
        return (
            "irr" in mitigant
            or "dscr" in mitigant
            or "internal rate of return" in mitigant
            or "still below target" in mitigant
            or "cap compression" in mitigant
            or "declines to" in mitigant
        )
    if "rent growth" in title:
        return "material sensitivity" in mitigant or "dscr" in mitigant
    if "stress scenario" in title or "vacancy" in title:
        return (
            "dscr" in mitigant
            or "break-even" in mitigant
            or "breakeven" in mitigant
            or "occupancy" in mitigant
        )
    if "expense ratio" in title or "operating cost" in title or "operating costs" in title:
        return "sponsor" in mitigant or "prior deals" in mitigant
    if "non-storage" in title or "parking" in title or "residential" in title:
        return (
            "dscr" in mitigant
            or "occupancy" in mitigant
            or "occupied" in mitigant
            or "sponsor" in mitigant
        )
    return False


def _clean_risk_title(title: str) -> str:
    return _clean_mixed_unit_language(title)


def _apply_risk_guards(parsed: RisksSection) -> RisksSection:
    cleaned: list[Risk] = []
    for risk in parsed.risks:
        updates: dict[str, Any] = {}
        title = _clean_risk_title(risk.title)
        if title != risk.title:
            updates["title"] = title
        if _is_bad_mitigant(risk):
            updates["mitigant"] = None
        cleaned.append(risk.model_copy(update=updates) if updates else risk)
    return parsed.model_copy(update={"risks": cleaned})


def _soften_below_screen_recommendation(parsed: Recommendation) -> Recommendation:
    if parsed.classification != "Below Screen":
        return parsed
    replacements = {
        "warrant rejection": "warrant repricing or additional diligence support",
        "warrants rejection": "warrants repricing or additional diligence support",
        "preclude advancement": "do not support advancement under current assumptions",
        "precludes advancement": "does not support advancement under current assumptions",
        "unattractive risk-adjusted opportunity": "below-screen opportunity under current assumptions",
    }
    rationale = parsed.rationale
    for old, new in replacements.items():
        rationale = re.sub(old, new, rationale, flags=re.IGNORECASE)
    return parsed.model_copy(update={"rationale": rationale})


def _apply_recommendation_override(parsed: Recommendation, ctx: MemoContext) -> Recommendation:
    """If the LLM's classification disagrees with the calculator's verdict, override."""
    canonical = ctx.classification
    if canonical and parsed.classification != canonical:
        logger.warning(
            "LLM classification '%s' overridden by verdict '%s'",
            parsed.classification,
            canonical,
        )
        parsed = parsed.model_copy(update={"classification": canonical})
    driving_metrics = [
        metric for metric in parsed.driving_metrics
        if " vs " in metric and "non-storage" not in metric.lower()
    ]
    if len(driving_metrics) != len(parsed.driving_metrics):
        parsed = parsed.model_copy(update={"driving_metrics": driving_metrics})
    return _soften_below_screen_recommendation(parsed)


async def narrate_all_sections(
    ctx: MemoContext,
    *,
    llm,
    retriever,
) -> dict[str, Optional[Any]]:
    """Run 1 priming + 8 parallel calls. Return a {section_key: parsed_object_or_None} dict.

    A `None` value means that section's LLM call failed; the caller should render a placeholder
    and surface the failure via `repo.append_warning`. Failures of the priming call propagate.
    """
    _retrieve_for_rag_sections(ctx, retriever)

    # PHASE 1 — priming call (raises on failure).
    primed = await _call_one_section(ctx, SECTION_EXECUTIVE_SUMMARY, llm)
    primed = _validate_citations(primed, ctx, SECTION_EXECUTIVE_SUMMARY)
    primed = _apply_deterministic_prose_guards(primed, ctx, SECTION_EXECUTIVE_SUMMARY)

    # PHASE 2 — parallel fan-out of the other 9 sections.
    fan_out_sections = [
        s for s in (
            SECTION_INVESTMENT_THESIS,
            SECTION_TRANSACTION_OVERVIEW,
            SECTION_PROPERTY_DESCRIPTION,
            SECTION_MARKET_OVERVIEW,
            "sponsor",
            "financial_analysis",
            SECTION_RENT_POSITION,
            SECTION_RISKS,
            SECTION_RECOMMENDATION,
        )
    ]
    coros = [_call_one_section(ctx, s, llm) for s in fan_out_sections]
    raw_results = await asyncio.gather(*coros, return_exceptions=True)

    sections: dict[str, Optional[Any]] = {SECTION_EXECUTIVE_SUMMARY: primed}
    for section, value in zip(fan_out_sections, raw_results):
        if isinstance(value, Exception):
            logger.warning("Section %s failed: %s", section, value)
            sections[section] = None
            continue
        validated = _validate_citations(value, ctx, section)
        validated = _apply_deterministic_prose_guards(validated, ctx, section)
        if isinstance(validated, RisksSection):
            validated = _apply_risk_guards(validated)
        if isinstance(validated, Recommendation):
            validated = _apply_recommendation_override(validated, ctx)
        sections[section] = validated

    return sections


def collect_section_warnings(sections: dict[str, Optional[Any]]) -> list[str]:
    """Build human-readable warnings for any sections that returned None."""
    return [
        f"Section '{name}' fell back to placeholder (LLM call failed)"
        for name, val in sections.items()
        if val is None
    ]
