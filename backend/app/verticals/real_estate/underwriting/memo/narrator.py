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
from .risk_policy import build_structured_risks
from .schemas import (
    MemoContext,
    PROSE_SECTIONS,
    ProseSection,
    Recommendation,
    Risk,
    RisksSection,
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


def _strategy_descriptor(strategy_type: str | None) -> str | None:
    if not strategy_type:
        return None
    normalized = "-".join(str(strategy_type).strip().lower().split())
    return normalized or None


def _executive_snapshot_paragraph(ctx: MemoContext) -> str | None:
    if not ctx.non_storage_unit_count:
        return None
    subject = ctx.deal_name or "The deal"
    strategy = _strategy_descriptor(ctx.strategy_type)
    asset_phrase = f"{strategy} self-storage investment" if strategy else "self-storage investment"
    pieces: list[str] = [f"{subject} is a {asset_phrase}"]
    if ctx.address:
        pieces.append(f"located at {ctx.address}")
    if ctx.purchase_price is not None:
        pieces.append(f"being acquired for {_fmt_money(ctx.purchase_price)}")
    opening = ", ".join(pieces) + "."
    mix = _unit_mix_phrase(ctx)
    if mix:
        opening += f" The property includes {mix}."
    return opening


def _transaction_paragraph(ctx: MemoContext) -> str | None:
    pieces: list[str] = []
    price = _fmt_money(ctx.purchase_price)
    per_unit = _fmt_money(ctx.price_per_unit)
    per_sqft = _fmt_money(ctx.price_per_sqft)
    cap = _fmt_pct(ctx.cap_rate_at_cost)

    if price:
        sentence = f"The acquisition price is {price}"
        if per_unit:
            unit_label = "total unit-space" if ctx.non_storage_unit_count else "unit"
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
    om_debt = ctx.om_financing_evidence or {}
    proposed_ltv = om_debt.get("proposed_ltv_pct")
    proposed_loan = om_debt.get("proposed_loan_amount")
    model_ltv = om_debt.get("model_ltv_pct")
    model_loan = om_debt.get("model_loan_amount")
    if proposed_ltv is not None and proposed_loan is not None and model_ltv is not None and model_loan is not None:
        materially_different = abs(float(model_ltv) - float(proposed_ltv)) > 0.0001 or abs(float(model_loan) - float(proposed_loan)) >= 1
        if materially_different:
            pieces.append(
                f"OM proposed {_fmt_pct(proposed_ltv)} / {_fmt_money(proposed_loan)}, "
                f"while the model uses {_fmt_pct(model_ltv)} / {_fmt_money(model_loan)}; "
                "modeled returns use the model capital stack."
            )
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
    target_equity_multiple = (ctx.criteria or {}).get("target_equity_multiple")
    if target_equity_multiple is not None:
        def replace_equity_multiple_contradiction(match: re.Match) -> str:
            actual = float(match.group("actual"))
            target = float(match.group("target"))
            if actual < target:
                return match.group(0)
            return (
                f"{match.group('prefix')}{actual:.2f}x, "
                f"above the {target:.2f}x target{match.group('suffix') or ''}"
            )

        text = re.sub(
            r"(?P<prefix>equity\s+multiple\s+(?:\w+\s+){0,3}?to\s+)"
            r"(?P<actual>\d+(?:\.\d+)?)x,?\s+below\s+the\s+"
            r"(?P<target>\d+(?:\.\d+)?)x\s+target(?P<suffix>[^.,;]*)",
            replace_equity_multiple_contradiction,
            text,
            flags=re.IGNORECASE,
        )

        def replace_invented_equity_threshold(match: re.Match) -> str:
            actual = float(match.group("actual"))
            target = float(target_equity_multiple)
            if actual >= target:
                return f"{match.group('prefix')}{actual:.2f}x, above the {target:.2f}x target"
            return f"{match.group('prefix')}{actual:.2f}x, below the {target:.2f}x target"

        text = re.sub(
            r"(?P<prefix>equity\s+multiple\s+to\s+)(?P<actual>\d+(?:\.\d+)?)x,?\s+"
            r"below\s+the\s+1\.50x\s+threshold\s+for\s+strong\s+equity\s+returns",
            replace_invented_equity_threshold,
            text,
            flags=re.IGNORECASE,
        )

    def replace_dscr_cushion_units(match: re.Match) -> str:
        actual = float(match.group("actual"))
        floor = float(match.group("floor"))
        cushion = actual - floor
        if cushion <= 0:
            return match.group(0)
        return f"{match.group('prefix')}{actual:.2f}x, narrowing the {cushion:.2f}x cushion above the {floor:.2f}x floor"

    text = re.sub(
        r"(?P<prefix>DSCR\s+to\s+)(?P<actual>\d+(?:\.\d+)?)x,?\s+"
        r"narrowing\s+the\s+\d+(?:\.\d+)?\s+basis\s+points?\s+cushion\s+above\s+the\s+"
        r"(?P<floor>\d+(?:\.\d+)?)x\s+floor",
        replace_dscr_cushion_units,
        text,
        flags=re.IGNORECASE,
    )

    def replace_dscr_margin_units(match: re.Match) -> str:
        actual = float(match.group("actual"))
        floor = float(match.group("floor"))
        cushion = actual - floor
        if cushion <= 0:
            return match.group(0)
        return (
            f"{match.group('prefix')}{actual:.2f}x{match.group('context')}, "
            f"narrowing the {cushion:.2f}x cushion above the {floor:.2f}x DSCR floor"
        )

    text = re.sub(
        r"(?P<prefix>DSCR\s+to\s+)(?P<actual>\d+(?:\.\d+)?)x(?P<context>.*?),\s+"
        r"narrowing\s+the\s+margin\s+above\s+the\s+"
        r"(?P<floor>\d+(?:\.\d+)?)x\s+(?:DSCR\s+)?floor\s+to\s+"
        r"\d+(?:\.\d+)?\s+basis\s+points?",
        replace_dscr_margin_units,
        text,
        flags=re.IGNORECASE,
    )

    dscr_floor = (ctx.criteria or {}).get("dscr_year_one_floor")
    target_irr = (ctx.criteria or {}).get("target_irr")
    if dscr_floor is not None and target_irr is not None:
        def replace_dscr_irr_mixed_threshold(match: re.Match) -> str:
            dscr = float(match.group("dscr"))
            irr_pct = float(match.group("irr"))
            target_irr_pct = float(target_irr) * 100
            if dscr >= float(dscr_floor) and irr_pct < target_irr_pct:
                return (
                    f"DSCR to {dscr:.2f}x and IRR to {irr_pct:.2f}%; "
                    f"DSCR remains above the {float(dscr_floor):.2f}x floor, while IRR falls below the {target_irr_pct:.2f}% target"
                )
            return match.group(0)

        text = re.sub(
            r"DSCR\s+to\s+(?P<dscr>\d+(?:\.\d+)?)x\s+and\s+IRR\s+to\s+"
            r"(?P<irr>\d+(?:\.\d+)?)%,?\s+falling\s+below\s+the\s+"
            r"\d+(?:\.\d+)?x\s+minimum\s+DSCR\s+floor\s+and\s+the\s+\d+(?:\.\d+)?%\s+IRR\s+target",
            replace_dscr_irr_mixed_threshold,
            text,
            flags=re.IGNORECASE,
        )

    dscr_floor = (ctx.criteria or {}).get("dscr_year_one_floor")
    target_em = (ctx.criteria or {}).get("target_equity_multiple")
    if dscr_floor is not None and target_em is not None:
        def replace_both_below_thresholds(match: re.Match) -> str:
            dscr = float(match.group("dscr"))
            equity_multiple = float(match.group("em"))
            if dscr >= float(dscr_floor) and equity_multiple >= float(target_em):
                return (
                    f"DSCR to {dscr:.2f}x and equity multiple to {equity_multiple:.2f}x, "
                    "both remain above configured thresholds"
                )
            return match.group(0)

        text = re.sub(
            r"DSCR\s+to\s+(?P<dscr>\d+(?:\.\d+)?)x\s+and\s+equity\s+multiple\s+to\s+"
            r"(?P<em>\d+(?:\.\d+)?)x,?\s+both\s+below\s+target\s+thresholds",
            replace_both_below_thresholds,
            text,
            flags=re.IGNORECASE,
        )
    return text


def _clean_above_comp_rent_language(text: str, ctx: MemoContext) -> str:
    current_vs_comp = (ctx.rent_position or {}).get("current_vs_comp_avg")
    if current_vs_comp is None or current_vs_comp <= 1.0:
        return text
    has_bad_upside_framing = re.search(
        r"pricing power|rent upside|additional upside|upside potential|upside\s+through\s+rent[-\s]rate\s+positioning|downside\s+(?:protection|cushion)|below[-\s]market\s+rent\s+normalization",
        text,
        flags=re.IGNORECASE,
    )
    has_explicit_above_comp_language = re.search(r"above[-\s]?(?:market|comp)", text, flags=re.IGNORECASE)
    has_comp_ratio_language = re.search(r"\b(?:1(?:\.\d+)?|\d{3}(?:\.\d+)?)%\s+of\s+the\s+comp\s+average", text, flags=re.IGNORECASE)
    has_above_comparable_language = re.search(r"(?:trade|trading|leasing|lease)\s+\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?%\s+above\s+comparable", text, flags=re.IGNORECASE)
    has_peer_sustainability_language = re.search(r"rent\s+sustainability\s+above\s+peer\s+facilities", text, flags=re.IGNORECASE)
    if not (has_bad_upside_framing or has_explicit_above_comp_language or has_comp_ratio_language or has_above_comparable_language or has_peer_sustainability_language):
        return text
    text = re.sub(r"pricing power", "rent sustainability risk", text, flags=re.IGNORECASE)
    text = re.sub(
        r"identifiable\s+upside\s+through\s+rent[-\s]rate\s+positioning\s+and\s+unit\s+conversion",
        "rent sustainability risk from above-comp rent positioning; unit conversion remains a separate value-add lever",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"identifiable\s+upside\s+through\s+rent[-\s]rate\s+positioning",
        "rent sustainability risk from above-comp rent positioning",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"upside\s+through\s+rent[-\s]rate\s+positioning",
        "rent sustainability risk from above-comp rent positioning",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"rent\s+positioning\s+supports\s+the\s+conversion\s+thesis",
        "rent positioning is a rent sustainability risk, separate from the conversion thesis",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"support(?:s|ed|ing)? additional rent upside",
        "require rent sustainability diligence",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"support(?:s|ed|ing)? rent upside",
        "require rent sustainability diligence",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"rent\s+sustainability\s+above\s+peer\s+facilities",
        "rent sustainability risk relative to peer facilities",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?:the\s+property\s+is\s+currently\s+)?underrented\s+relative\s+to\s+market\s+comps\s*[-–—]+\s*in[-\s]place\s+rents\s+run",
        "Rent sustainability risk: in-place rents run",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(above\s+comparable\s+asking\s+rents),\s+indicating\s+embedded\s+tenant\s+roll[-\s]over\s+upside\s+of\s+approximately\s+(\$[\d,]+)\s+annually",
        r"\1, creating rent sustainability risk; tenant-level roll-over upside of approximately \2 annually is a separate OM-supported lever",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"below[-\s]market\s+rent\s+positioning",
        "tenant-level below-market upside, separate from comp-set rent sustainability risk",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"below[-\s]market\s+rent\s+normalization",
        "tenant-level below-market upside, separate from comp-set rent sustainability risk",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r",?\s+supporting\s+cash[-\s]on[-\s]cash\s+returns\s+of\s+\d+(?:\.\d+)?%\s+and\s+an\s+equity\s+multiple\s+of\s+\d+(?:\.\d+)?x",
        "; treat this as rent sustainability risk",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"providing\s+downside\s+(?:protection|cushion)\s+if\s+(?P<context>[^.]+)",
        r"creating rent sustainability risk and downside exposure if \g<context>",
        text,
        flags=re.IGNORECASE,
    )
    return text


def _clean_competitor_radius_language(text: str, ctx: MemoContext) -> str:
    count_3mi = ctx.nearby_storage_3mi
    count_5mi = ctx.nearby_storage_5mi
    if count_3mi is None or count_5mi is not None:
        return text
    return re.sub(
        rf"\b{int(count_3mi)}\s+(competitors|competing\s+facilities|facilities)\s+within\s+5\s+miles\b",
        f"{int(count_3mi)} competitors within 3 miles",
        text,
        flags=re.IGNORECASE,
    )


def _clean_climate_control_language(text: str, ctx: MemoContext) -> str:
    storage_units = ctx.storage_unit_count or ((ctx.cc_unit_count or 0) + (ctx.nc_unit_count or 0))
    if not storage_units:
        return text
    if (ctx.cc_unit_count or 0) == 0 and (ctx.nc_unit_count or 0) >= storage_units:
        text = re.sub(
            rf"\b{storage_units:,}?\s+climate[-\s]controlled\s+storage\s+units\b",
            f"{storage_units:,} non-climate-controlled storage units",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            rf"\b{storage_units}\s+climate[-\s]controlled\s+storage\s+units\b",
            f"{storage_units} non-climate-controlled storage units",
            text,
            flags=re.IGNORECASE,
        )
    return text


def _clean_false_sponsor_inconsistency(text: str, ctx: MemoContext) -> str:
    sponsor = ctx.sponsor_data or {}
    net_worth = sponsor.get("net_worth")
    liquidity = sponsor.get("liquidity")
    if net_worth is None or liquidity is None:
        return text
    try:
        if float(liquidity) > float(net_worth):
            return text
    except (TypeError, ValueError):
        return text
    return re.sub(
        r"\s*Net[-\s]worth\s+and\s+liquidity\s+figures\s+require\s+analyst\s+verification\s*\([^)]*reported\s+values\s+are\s+inconsistent[^)]*\)\.?",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()


def _clean_track_record_target_language(text: str, ctx: MemoContext) -> str:
    sponsor = ctx.sponsor_data or {}
    track_record = sponsor.get("track_record_irr")
    target_irr = (ctx.criteria or {}).get("target_irr")
    if track_record is None or target_irr is None:
        return text
    try:
        if abs(float(track_record) - float(target_irr)) > 0.0001:
            return text
    except (TypeError, ValueError):
        return text
    return re.sub(
        r"Track\s+record\s+IRR\s+is\s+reported\s+at\s+\d+(?:\.\d+)?%,\s+which\s+aligns\s+with\s+the\s+fund's\s+target\s+IRR\s+for\s+this\s+investment\.?",
        "Track record IRR matches the configured target; treat it as neutral background, not a mitigant.",
        text,
        flags=re.IGNORECASE,
    )


def _source_support_int(ctx: MemoContext, field_key: str) -> int | None:
    for row in ctx.source_support or []:
        if not isinstance(row, dict) or row.get("field_key") != field_key:
            continue
        value = row.get("value")
        if value is None:
            return None
        match = re.search(r"\d+", str(value))
        if not match:
            return None
        try:
            return int(match.group(0))
        except ValueError:
            return None
    return None


def _clean_hold_period_language(text: str, ctx: MemoContext) -> str:
    hold_period = ctx.hold_period_years_override or _source_support_int(ctx, "hold_period_years")
    loan_term = (ctx.financing or {}).get("loan_term_years")
    if hold_period is None or loan_term is None or int(hold_period) == int(loan_term):
        return text
    return re.sub(
        rf"\b{int(loan_term)}[-\s]year\s+hold\b",
        f"{int(hold_period)}-year hold",
        text,
        flags=re.IGNORECASE,
    )


def _clean_prose_paragraph(paragraph: str, ctx: MemoContext) -> str:
    text = _clean_mixed_unit_language(paragraph)
    text = _clean_metric_threshold_language(text, ctx)
    text = _clean_above_comp_rent_language(text, ctx)
    text = _clean_competitor_radius_language(text, ctx)
    text = _clean_climate_control_language(text, ctx)
    text = _clean_false_sponsor_inconsistency(text, ctx)
    text = _clean_track_record_target_language(text, ctx)
    text = _clean_hold_period_language(text, ctx)
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
        if current_avg > 1.05:
            sentence = (
                f"Rent-position support is partial: {coverage}. In-place rents are "
                f"{current_avg:.1%} of the matched comp average; treat this as rent "
                "sustainability / downside risk, not rent upside."
            )
        elif 0.95 <= current_avg <= 1.05:
            sentence = (
                f"Rent-position support is partial: {coverage}. In-place rents are "
                f"{current_avg:.1%} of the matched comp average, broadly in line with market."
            )
        else:
            sentence = (
                f"Rent-position support is partial: {coverage}. In-place rents are "
                f"{current_avg:.1%} of the matched comp average, below market."
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


def _is_rent_position_market_overview_leak(paragraph: str) -> bool:
    text = paragraph.lower()
    return (
        "rent position" in text
        or "in-place rents exceed" in text
        or "current in-place rents" in text and "comparable market" in text
        or "premium to the average" in text and "comparable" in text
    )


def _apply_deterministic_prose_guards(parsed: Any, ctx: MemoContext, section: str) -> Any:
    """Replace fragile LLM count prose with canonical structured-data prose."""
    if not isinstance(parsed, ProseSection):
        return parsed
    cleaned_paragraphs = [
        paragraph for paragraph in (_clean_prose_paragraph(p, ctx) for p in parsed.paragraphs)
        if paragraph.strip()
    ]
    parsed = parsed.model_copy(update={"paragraphs": cleaned_paragraphs})

    if section == SECTION_EXECUTIVE_SUMMARY:
        paragraph = _executive_snapshot_paragraph(ctx)
        if paragraph:
            return parsed.model_copy(update={"paragraphs": [paragraph, *parsed.paragraphs[1:]]})

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

    if section == SECTION_MARKET_OVERVIEW:
        remaining = [p for p in parsed.paragraphs if not _is_rent_position_market_overview_leak(p)]
        return parsed.model_copy(update={"paragraphs": remaining})

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
    if "rent growth" in title:
        return any(token in mitigant for token in (
            "material sensitivity",
            "dscr",
            "historical self-storage inflation",
            "not the underwriting assumption",
            "tail scenario",
            "base-case rent growth",
            "base case rent growth",
            "base-case irr",
            "base case irr",
            "providing cushion",
            "cushion above",
            "rent-growth shortfalls",
        ))
    if "rent" in title and ("above" in title or "premium" in title or "market" in title):
        return any(token in mitigant for token in (
            "only ",
            "remaining",
            "at or below market",
            "limiting portfolio-wide",
            "limiting portfolio wide",
            "small units",
            "below-market",
            "annual upside",
            "normalized",
            "offsets",
            "overlevered",
            "occupancy",
            "buffer",
            "sponsor",
            "prior self-storage acquisitions",
            "execution risk",
            "lease management",
        ))
    if "capex" in title or "capital repairs" in title or "capital improvements" in title:
        return any(token in mitigant for token in (
            "repairs and maintenance expense",
            "minimal relative",
            "sponsor",
            "experience",
            "capital planning",
            "revenue upside",
            "converting",
            "conversion",
            "self-funded",
            "value-creation path",
        ))
    if "exit cap" in title or "cap expansion" in title:
        return any(token in mitigant for token in (
            "fixed-rate debt",
            "fixed rate debt",
            "refinance risk",
            "debt service",
            "amortization",
            "interest rate",
        ))
    if "negative irr" in title or "track record" in title:
        return any(token in mitigant for token in (
            "completed",
            "prior deals",
            "net worth",
            "liquidity",
            "capital availability",
            "operational continuity",
            "years of experience",
        ))
    if "liquidity" in title or "capital call" in title or "shortfalls" in title:
        return any(token in mitigant for token in (
            "experience",
            "prior deals",
            "execution risk",
            "stabilized asset",
            "years",
        ))
    if "stress scenario" in title or "vacancy" in title or "occupancy stress" in title:
        return (
            "dscr" in mitigant
            or "break-even" in mitigant
            or "breakeven" in mitigant
            or "occupancy" in mitigant
            or "fixed-rate debt" in mitigant
            or "fixed rate debt" in mitigant
            or "debt term" in mitigant
            or "debt service" in mitigant
            or "refinance risk" in mitigant
            or "interest" in mitigant
        )
    if "equity multiple" in title:
        return (
            "irr" in mitigant
            or "dscr" in mitigant
            or "internal rate of return" in mitigant
            or "still below target" in mitigant
            or "cap compression" in mitigant
            or "declines to" in mitigant
        )
    if "expense ratio" in title or "operating cost" in title or "operating costs" in title:
        return "sponsor" in mitigant or "prior deals" in mitigant
    if "non-storage" in title or "parking" in title or "residential" in title:
        return (
            "dscr" in mitigant
            or "occupancy" in mitigant
            or "occupied" in mitigant
            or "sponsor" in mitigant
            or "diversified revenue" in mitigant
            or "diversified cash flow" in mitigant
            or "single-asset-class dependency" in mitigant
            or "reduces reliance on storage" in mitigant
        )
    return False


def _clean_risk_title(title: str, ctx: MemoContext) -> str:
    return _clean_metric_threshold_language(_clean_mixed_unit_language(title), ctx)


def _is_unsupported_liquidity_risk(risk: Risk, ctx: MemoContext) -> bool:
    title = risk.title.lower()
    if "liquidity" not in title or not ("equity commitment" in title or "equity check" in title or "acquisition" in title):
        return False
    liquidity = (ctx.sponsor_data or {}).get("liquidity")
    equity = (ctx.capital_structure or {}).get("total_equity_invested")
    purchase_price = ctx.purchase_price
    basis = equity if ("equity commitment" in title or "equity check" in title) else purchase_price
    if liquidity is None or basis is None:
        return False
    try:
        return float(liquidity) >= float(basis) * 2
    except (TypeError, ValueError):
        return False


def _apply_risk_guards(parsed: RisksSection, ctx: MemoContext) -> RisksSection:
    cleaned: list[Risk] = []
    for risk in parsed.risks:
        if _is_unsupported_liquidity_risk(risk, ctx):
            continue
        updates: dict[str, Any] = {}
        title = _clean_risk_title(risk.title, ctx)
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
    structured_risks = build_structured_risks(ctx)

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
            SECTION_RECOMMENDATION,
        )
    ]
    if structured_risks is None:
        fan_out_sections.insert(-1, SECTION_RISKS)
    coros = [_call_one_section(ctx, s, llm) for s in fan_out_sections]
    raw_results = await asyncio.gather(*coros, return_exceptions=True)

    sections: dict[str, Optional[Any]] = {SECTION_EXECUTIVE_SUMMARY: primed}
    if structured_risks is not None:
        sections[SECTION_RISKS] = structured_risks
    for section, value in zip(fan_out_sections, raw_results):
        if isinstance(value, Exception):
            logger.warning("Section %s failed: %s", section, value)
            sections[section] = None
            continue
        validated = _validate_citations(value, ctx, section)
        validated = _apply_deterministic_prose_guards(validated, ctx, section)
        if isinstance(validated, RisksSection):
            validated = _apply_risk_guards(validated, ctx)
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
