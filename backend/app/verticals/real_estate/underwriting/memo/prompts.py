"""System prompt + per-section instruction blocks for the IC memo narrator.

Design goals:
- System prompt is byte-identical across all 9 narrator calls so the Anthropic
  prompt cache treats it as a single cacheable prefix.
- User content's first block is the full MemoContext as JSON, also byte-identical
  per memo, marked cacheable. Section-specific instructions and RAG excerpts go
  in a second block AFTER the cache breakpoint.
- Prompt discipline mirrors `verticals/real_estate/underwriting/extraction/prompts.py`:
  explicit allowed sources of truth, explicit do-nots, fallback behavior for
  missing data.
"""
from __future__ import annotations

import dataclasses
import json
from typing import Any

from .schemas import (
    MemoContext,
    PROSE_SECTIONS,
    SECTION_EXECUTIVE_SUMMARY,
    SECTION_FINANCIAL_ANALYSIS,
    SECTION_MARKET_OVERVIEW,
    SECTION_PROPERTY_DESCRIPTION,
    SECTION_RECOMMENDATION,
    SECTION_RENT_POSITION,
    SECTION_INVESTMENT_THESIS,
    SECTION_RISKS,
    SECTION_SPONSOR,
    SECTION_TRANSACTION_OVERVIEW,
)


# ── Universal system prompt (byte-identical across all 9 calls) ──────────────

UNIVERSAL_RULES = """You are writing a section of a Commercial Real Estate Investment Committee Memo for a self-storage acquisition. Tone: senior CRE credit analyst — concise, factual, decision-oriented. No marketing language ("strong fundamentals", "exciting opportunity", "well-positioned"). No hedging filler ("it should be noted that"). Lead with the conclusion.

CRITICAL RULES (apply to every sentence you write):
1. Use ONLY values that appear in the STRUCTURED DATA block or the SOURCE EXCERPTS block. Never invent numbers, dates, sponsor history, market figures, or risks.
2. If a section requires data that is not present, write ONE short sentence acknowledging the gap (e.g. "Sponsor liquidity not provided in this submission."). Do not fill the gap with plausible-sounding prose.
3. If your confidence in any specific claim is below ~70%, omit the claim entirely. The committee prefers a shorter memo to an unsupported one.
4. Numbers in prose must match the STRUCTURED DATA verbatim. Do not round, restate ranges loosely, or convert units. If structured data says NOI = $412,300, do not write "approximately $400K".
5. Cite source excerpts inline as [doc_id:page] whenever a sentence draws on SOURCE EXCERPTS. Add the same citation to the `citations` field of your output. Never fabricate a citation. Never cite a doc:page that is not in SOURCE EXCERPTS.
6. Format: 2-4 short paragraphs unless the section instructions say otherwise. No bullet lists unless requested.
7. Do NOT echo the structured data back as a table — the document already contains the tables. Your job is interpretation."""


# ── Per-section instruction blocks ──────────────────────────────────────────

SECTION_INSTRUCTIONS: dict[str, str] = {
    SECTION_EXECUTIVE_SUMMARY: """SECTION: Executive Summary
Output: 3 short paragraphs.
Paragraph 1 — deal snapshot in 2 sentences: property name, asset type, units, purchase price, location. If STRUCTURED DATA.strategy_type is set, mention it in one phrase (e.g., "value-add acquisition", "stable-income hold").
Paragraph 2 — investment thesis in 1-2 sentences. If STRUCTURED DATA.thesis_text is set, paraphrase it (do not copy verbatim). Otherwise cite the single most favorable metric from STRUCTURED DATA.return_metrics or rent_position as the primary strength.
Paragraph 3 — primary risk in 1 sentence (the most material item from STRUCTURED DATA.warnings, stress_tests, or rollover), followed by the recommendation matching STRUCTURED DATA.classification verbatim. If STRUCTURED DATA.verdict_override is set AND differs from STRUCTURED DATA.classification_calculator, append: "Note: analyst override of calculator's [calculator value] — rationale in Recommendation section."
Do not introduce facts that are not also developed in later sections.""",

    SECTION_INVESTMENT_THESIS: """SECTION: Investment Thesis
Output: 1-2 short paragraphs (~5 sentences total).
This section answers "why this deal" and frames the entire memo. Build it from these sources in order of precedence:

1. STRUCTURED DATA.thesis_text (analyst-entered seed). Treat as analyst INTENT, not finished prose.
   - PARAPHRASE the seed into a polished thesis statement. NEVER copy the seed verbatim. NEVER prepend, quote, or bracket it.
   - If the seed is shorter than 20 characters OR matches an obvious placeholder pattern ("my", "my thesis", "test", "tbd", "n/a", "todo", "placeholder", "lorem"), TREAT IT AS ABSENT and fall through to rule 2 (use strategy_type framing only).
   - When you DO use the seed, also add 1-2 sentences of supporting evidence drawn from STRUCTURED DATA.return_metrics, rent_position, value_add_opportunities, or stress_tests.
2. STRUCTURED DATA.strategy_type. Frame the thesis around this strategy:
   - "Stable Income" → emphasize current yield, debt service coverage, downside protection
   - "Value-Add" → emphasize the operational lever (rent push, conversion, occupancy fill, capex-driven repositioning)
   - "Distressed" → emphasize discount to replacement cost, motivated seller, capital-structure stress at seller
   - "Conversion" → emphasize the conversion plan, capex required, NOI uplift potential
   - "Portfolio Build" → emphasize fit with existing portfolio, scale benefits, operator leverage
   - "Opportunistic" → emphasize unique angle that doesn't fit other categories
3. STRUCTURED DATA.sourcing_type / sourcing_detail. If present, work into one sentence ("Sourced off-market via repeat seller relationship.")

If NEITHER thesis_text NOR strategy_type is present, the entire section reads:
"Investment thesis has not been articulated for this deal. The underwriting metrics are documented in Section 6 and the verdict in Section 10; analyst should populate the thesis before committee submission."

Do NOT invent a thesis if neither input is given — placeholder is better than fabrication.
Do NOT repeat the deal snapshot from the Executive Summary.
Do NOT include numbers that contradict STRUCTURED DATA.""",

    SECTION_TRANSACTION_OVERVIEW: """SECTION: Transaction Overview
Output: 1 short paragraph (~3 sentences).
Use ONLY values from STRUCTURED DATA.purchase_price, price_per_unit, price_per_sqft, cap_rate_at_cost. State the price, $/unit, and the going-in cap rate. Do NOT comment on whether the price is fair — that is the Recommendation section's job. No citations needed.""",

    SECTION_PROPERTY_DESCRIPTION: """SECTION: Property Description
Output: 2-3 short paragraphs. Strictly about the PHYSICAL property.
Paragraph 1 (structured): year built, total units, total rentable sqft, CC unit count vs NC unit count, climate-control percentage. All numbers come from STRUCTURED DATA verbatim.
Paragraph 2 (narrative): construction type, on-site management, security, recent capex, drive-up vs interior access. THIS MUST come from SOURCE EXCERPTS with inline [doc:page] citations. If SOURCE EXCERPTS contains no relevant material, write ONE sentence: "No additional property description available from the offering memorandum." Do not invent.
Paragraph 3 (optional): explicitly stated value-add or expansion opportunities — only if SOURCE EXCERPTS supports them.

DO NOT include in this section (each belongs in a different section):
- Purchase price, $/unit, $/sqft, cap rate ← Transaction Overview §3
- IRR, cash-on-cash, DSCR, equity multiple, return targets ← Financial Analysis §7
- Recommendation, classification, "fails to meet thresholds" language ← Recommendation §11
Restating transaction terms or returns here is a CRITICAL error.""",

    SECTION_MARKET_OVERVIEW: """SECTION: Market Overview
Output: 2-3 short paragraphs.
Paragraph 1 (structured demographics): population_3mi, avg_household_income_3mi, storage_sqft_per_capita_3mi, and competing facility counts (1mi / 3mi / 5mi). All come from STRUCTURED DATA verbatim. If a field is null, omit it; do not infer.
Paragraph 2 (narrative): submarket dynamics, supply pipeline, recent comparable transactions. THIS MUST come from SOURCE EXCERPTS with inline [doc:page] citations. If SOURCE EXCERPTS is empty, write ONE sentence: "No market commentary available in the offering memorandum."
Paragraph 3 (optional): analyst notes — STRUCTURED DATA.market_notes verbatim or paraphrased, attributed as "Per analyst notes:". Skip if market_notes is null.""",

    SECTION_SPONSOR: """SECTION: Sponsor / Borrower
Output: 1-2 short paragraphs.
Use ONLY fields from STRUCTURED DATA.sponsor_data. For each provided field, include it in the prose verbatim or lightly paraphrased. For each missing field, do NOT speculate.

PLACEHOLDER FILTER: skip any free-text field (experience, notes, entity, sponsor_name) that:
- is shorter than 20 characters AND looks like a placeholder ("good summary", "test", "tbd", "n/a", "todo", "lorem", "my", "—"), OR
- contains only generic phrases with no specifics (numbers, names, or concrete facts)
When a free-text field is filtered out, do NOT mention that field at all — do not write "experience is characterized as good summary" or any similar phrasing that surfaces placeholder text. Just omit.

CONSISTENCY CHECK: if sponsor_data.liquidity > sponsor_data.net_worth, do NOT report both numbers — they are inconsistent (liquidity is a subset of net worth). Report the lower of the two as liquidity and flag in ONE phrase: "Net-worth and liquidity figures require analyst verification (reported values are inconsistent)."

If sponsor_data is empty OR has no meaningful fields populated after the placeholder filter, the entire section must read: "Sponsor information not provided. To be completed prior to committee submission."
Do not infer sponsor experience from the deal type. Do not invent a track record. No citations.""",

    SECTION_FINANCIAL_ANALYSIS: """SECTION: Financial Analysis
Output: 1 short paragraph (~4 sentences).
The Word document already contains the NOI buildup, return metrics, and sensitivity tables — do NOT re-state numbers that appear in tables.
Acceptable claims (each must be supported by STRUCTURED DATA):
- Which expense basis was selected and why (from STRUCTURED DATA.noi_buildup if it includes a basis label; otherwise omit).
- How modeled Year-1 NOI compares to OM-stated NOI — cite STRUCTURED DATA.noi_bridge delta numerically.
- Whether key return metrics clear STRUCTURED DATA.criteria thresholds — state cleared / not cleared, no commentary on adequacy.
Do NOT opine on whether the cap rate is appropriate (Recommendation section's job).""",

    SECTION_RENT_POSITION: """SECTION: Rent Position
Output: 1 short paragraph (~3 sentences).
The Word document already contains a rent-position table. Do NOT re-state per-bucket numbers.

Read STRUCTURED DATA.rent_position which has these fields:
- current_vs_comp_avg: in-place rent / comp average across matched buckets. <1.0 means below market, >1.0 means above market.
- market_vs_comp_avg: subject's stated market rent / comp average.
- matched_bucket_count, total_bucket_count: how many size buckets had comp coverage.

Acceptable claims:
- Whether overall in-place rents are above or below market (use current_vs_comp_avg).
- Whether the operator's stated market rent diverges from comp average (compare current_vs_comp_avg to market_vs_comp_avg).
- One sentence on the implication for upside / downside, only when current_vs_comp_avg is materially below 1.0 (e.g. <0.95).
- If matched_bucket_count < total_bucket_count, note coverage limitation in one phrase.

If rent_position is empty or matched_bucket_count is 0, write ONE sentence: "Rent position cannot be assessed — no matched comp buckets in this submission." Do not speculate.""",

    SECTION_RISKS: """SECTION: Risks & Mitigants
Return 3-6 risks. For each risk, the `source` field MUST be one of these enum values and the risk's content MUST be supportable by that source:
- "verdict_warning"  — drawn from STRUCTURED DATA.warnings (use warning text as title)
- "stress_test"      — drawn from STRUCTURED DATA.stress_tests showing DSCR < 1.0 OR breakeven occupancy > 90% OR equity_multiple < 1.5 under any scenario
- "rollover"         — drawn from STRUCTURED DATA.rollover showing >25% rollover in any 12-month window
- "rent_position"    — drawn from STRUCTURED DATA.rent_position showing in-place rents above market by >10% (current_vs_comp_avg > 1.10)
- "overlevered"     — drawn from STRUCTURED DATA.max_loan showing delta_vs_current < 0
- "analyst_note"     — drawn from STRUCTURED DATA.sponsor_data.notes or STRUCTURED DATA.market_notes only

Do NOT invent risks not supported by the above. Do NOT include generic risks ("interest rate risk", "market conditions") unless a specific stress test or warning in STRUCTURED DATA points to them.

MITIGANTS — required discipline:
For every risk, evaluate ALL FIVE mitigant sources below in order and use the first that applies. Only set `mitigant` to null when NONE of the five yield a defensible mitigant.

1. METRIC CUSHION vs CRITERIA. If the risk is a return-threshold miss (IRR, CoC, DSCR), check the OTHER computed metrics in return_metrics against the same criteria. Example: an IRR miss can be partially mitigated by DSCR 1.43x vs the 1.25x floor (18bp cushion) or LTV 70% vs the 80% max (1000bp equity cushion).
2. FIXED-RATE DEBT STRUCTURE. If the risk is rate/refinance/market-volatility-related, cite STRUCTURED DATA.financing.loan_term_years and amortization_years as the mitigant ("X-year fixed term locks debt service through hold").
3. CAPEX RESERVE. If the risk is physical/operational/condition-related, and STRUCTURED DATA.capex_reserve_per_unit > 0, cite the reserve.
4. SPONSOR. If the risk is operational/lease-up/execution-related, and sponsor_data has any of (years_experience, deals_in_asset_class, track_record_irr, net_worth, liquidity) populated, cite the most relevant strength. Prefer the structured numeric fields over free-text notes. Example: "Sponsor's 12 prior self-storage acquisitions reduce execution risk." If only the unstructured `experience` summary is present, paraphrase it concisely.
5. SOURCE EXCERPT. If SOURCE EXCERPTS explicitly describes a mitigant for this risk, cite it with `citation`.

Format each mitigant as ONE concrete sentence with a number from STRUCTURED DATA when available. NEVER use vague phrases like "may be mitigated by sound underwriting" — quote the actual cushion figure or contract term.

If a risk has no supportable mitigant after evaluating all 5 sources, set `mitigant` to null (not a placeholder string).

DIMENSION-MATCH RULE: a mitigant MUST address the same risk dimension as the risk itself.
- IRR miss → mitigant must address upside (DSCR cushion, LTV slack, conversion thesis), NOT equity multiple. EM and IRR measure different things (terminal vs annual); citing EM as offsetting IRR is incorrect.
- Cash-on-cash miss → mitigant must address near-term cash flow (LTV cushion enabling more leverage, lower expense load), NOT 10-year equity multiple.
- Lease-up / non-storage concentration risk → mitigant must address the diversification or stability of that revenue stream, NOT pure occupancy snapshot (occupancy today doesn't mitigate concentration tomorrow).
- Rent above market → mitigant must address sustainability (tenure data, defensible advantage), NOT generic sponsor experience.

When NO defensible same-dimension mitigant exists, set `mitigant` to null. Better to flag for committee than to write a mismatched mitigant.""",

    SECTION_RECOMMENDATION: """SECTION: Recommendation
- `classification` MUST equal STRUCTURED DATA.classification verbatim (one of: "Pursue", "Needs Review", "Below Screen", "Pass"). If the value would differ, return the STRUCTURED DATA value — the renderer will override anyway.
- `rationale`: 2-3 sentences.
   • If STRUCTURED DATA.verdict_override IS NOT NULL AND differs from STRUCTURED DATA.classification_calculator: open with "Analyst override of calculator's [classification_calculator] classification." Then quote STRUCTURED DATA.verdict_override_reason verbatim or paraphrase tightly. Conclude with 1 sentence acknowledging which calculator metrics support OR contradict the override.
   • Otherwise: 2-3 sentences citing the 1-2 driving metrics from STRUCTURED DATA. Compare to STRUCTURED DATA.criteria (e.g. "DSCR 1.45x clears the 1.25x floor").
- `driving_metrics`: max 3 entries. STRICT FORMAT — each entry MUST be a single metric value vs a single threshold value, like "DSCR 1.45x vs 1.25x floor" or "IRR 14.1% vs 15.0% target". Each entry MUST contain the substring " vs " (with spaces). Each entry MUST end with a number followed by an optional unit/qualifier. Do NOT include thesis statements (no "Non-storage units 35% of mix" — that is a thesis, not a metric).
- `conditions`: 1-5 conditions for proceeding.
   • If STRUCTURED DATA.custom_conditions has entries, those MUST appear as the FIRST entries verbatim — they are analyst-supplied and authoritative.
   • Then append auto-derived conditions when classification is "Pursue" or "Needs Review" AND STRUCTURED DATA.warnings is non-empty. Each auto-derived condition should be one short sentence describing a specific verifiable action drawn from STRUCTURED DATA.warnings. Examples: "Obtain T-12 income statement to confirm full-year NOI before commitment." / "Reconcile unit-mix implied GPR with model GPR (X.X% variance noted)." / "Validate post-acquisition property tax reassessment given expense ratio below benchmark."
   • Total list capped at 5 entries — if more, drop the lowest-priority auto-derived ones first, never drop a custom_condition.
   • If classification == "Below Screen" AND custom_conditions is empty AND warnings is empty, leave conditions empty.""",
}


# ── Block builders ───────────────────────────────────────────────────────────

def build_system_blocks() -> list[dict[str, Any]]:
    """Return system content blocks. Byte-identical across all narrator calls."""
    return [
        {
            "type": "text",
            "text": UNIVERSAL_RULES,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def _serialize_context(ctx: MemoContext) -> str:
    """Serialize MemoContext to compact, deterministic JSON for the cacheable user block."""
    d = dataclasses.asdict(ctx)
    # Exclude `retrieved_chunks` — those are per-section, sent in the second block.
    d.pop("retrieved_chunks", None)
    return json.dumps(d, sort_keys=True, default=str, separators=(",", ":"))


def _format_rag_excerpts(chunks: list) -> str:
    if not chunks:
        return ""
    lines = ["SOURCE EXCERPTS (cite as [doc_id:page] when used):"]
    for c in chunks:
        lines.append(f"[{c.doc_id}:p{c.page}]\n{c.text}\n")
    return "\n".join(lines)


def build_user_blocks(ctx: MemoContext, section_key: str) -> list[dict[str, Any]]:
    """Return user content blocks for one narrator call.

    Block 0: full MemoContext as JSON, byte-identical across all sections (cache breakpoint).
    Block 1: section-specific instructions + RAG excerpts + closing prompt.
    """
    instructions = SECTION_INSTRUCTIONS[section_key]
    chunks = ctx.retrieved_chunks.get(section_key, []) if ctx.retrieved_chunks else []
    rag_block = _format_rag_excerpts(chunks)

    second_text_parts = [instructions]
    if rag_block:
        second_text_parts.append("\n\n" + rag_block)
    second_text_parts.append(
        f"\n\nNow write the {section_key.replace('_', ' ')} section per the rules above. "
        "Return the structured output the schema requires."
    )

    return [
        {
            "type": "text",
            "text": "STRUCTURED DATA (canonical source of truth — verbatim numbers only):\n"
                    + _serialize_context(ctx),
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": "".join(second_text_parts),
        },
    ]
