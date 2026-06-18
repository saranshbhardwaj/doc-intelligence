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
    return parsed


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
