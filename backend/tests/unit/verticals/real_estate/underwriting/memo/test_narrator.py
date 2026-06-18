"""Unit tests for the memo narrator."""
from __future__ import annotations

import asyncio
import dataclasses
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.verticals.real_estate.underwriting.memo.narrator import narrate_all_sections
from app.verticals.real_estate.underwriting.memo.schemas import (
    MemoContext,
    PROSE_SECTIONS,
    ProseSection,
    Citation,
    Recommendation,
    Risk,
    RisksSection,
    RetrievedChunk,
    SECTION_EXECUTIVE_SUMMARY,
    SECTION_RECOMMENDATION,
    SECTION_RISKS,
    SECTION_PROPERTY_DESCRIPTION,
    SECTION_MARKET_OVERVIEW,
)


def _ctx(**overrides):
    base = dict(
        deal_name="X", address="A", asset_type="self_storage",
        year_built=2010, num_units=400, rentable_sqft=50_000,
        cc_unit_count=100, nc_unit_count=300, climate_control_pct=0.25,
        purchase_price=5_000_000.0, price_per_unit=12_500.0, price_per_sqft=100.0,
        cap_rate_at_cost=0.07,
        population_3mi=60_000, avg_household_income_3mi=75_000.0,
        storage_sqft_per_capita_3mi=7.5,
        nearby_storage_1mi=2, nearby_storage_3mi=6, nearby_storage_5mi=11,
        max_loan={"max_loan": 3_250_000.0, "binding_constraint": "ltv", "delta_vs_current": 0.0},
        financing={"loan_term_years": 10, "amortization_years": 25},
        criteria={"dscr_year_one_floor": 1.25, "max_ltv": 0.65},
        capex_reserve_per_unit=100.0,
        classification="Pursue",
        warnings=["DSCR slack thin"],
        rationale="Metrics clear thresholds.",
        document_ids=["doc-om-1"],
    )
    base.update(overrides)
    return MemoContext(**base)


class FakeLLM:
    """Stub LLM that returns canned typed objects per section."""

    def __init__(self):
        self.calls: list[dict[str, Any]] = []
        self.responses: dict[str, Any] = {}

    async def parse(self, system, messages, output_format, max_tokens):
        user_blocks = messages[0]["content"]
        section_text = user_blocks[1]["text"]
        # Match against the closing "Now write the X section" sentinel only.
        # The closing line is appended by prompts.build_user_blocks and uses
        # section_key with underscores replaced by spaces.
        marker = "now write the "
        idx = section_text.lower().rfind(marker)
        if idx < 0:
            raise AssertionError(f"Closing 'Now write the ...' marker not found in user block: {section_text[:200]}")
        tail = section_text.lower()[idx + len(marker):]
        matched_section = None
        for section in self.responses:
            if tail.startswith(section.replace("_", " ") + " section"):
                matched_section = section
                break
        if matched_section is None:
            raise AssertionError(f"No canned response matched closing marker. Tail: {tail[:200]}")
        self.calls.append({"section": matched_section, "schema": output_format.__name__})
        resp = self.responses[matched_section]
        if isinstance(resp, Exception):
            raise resp
        return resp


class FakeRetriever:
    """Stub RAG retriever returning predetermined chunks per section."""

    def __init__(self):
        self.chunks_by_section: dict[str, list[RetrievedChunk]] = {}

    def retrieve(self, query, document_ids, top_n, section_key):
        return self.chunks_by_section.get(section_key, [])


def _prose(paras=None, citations=None):
    return ProseSection(
        paragraphs=paras or ["A.", "B."],
        citations=citations or [],
    )


def _risks():
    return RisksSection(
        risks=[
            Risk(title="DSCR slack thin in stress.", severity="medium", source="verdict_warning",
                 mitigant="Capex reserve of $40k cushion."),
            Risk(title="Rollover concentration in Q3.", severity="low", source="rollover",
                 mitigant=None),
            Risk(title="Submarket supply growth.", severity="medium", source="analyst_note",
                 mitigant="Sponsor has 10-yr operating experience."),
        ]
    )


def _rec():
    return Recommendation(
        classification="Pursue",
        rationale="DSCR 1.45x clears 1.25x floor; debt yield 9.2% clears 8% floor.",
        driving_metrics=["DSCR 1.45x vs 1.25x floor", "Debt Yield 9.2% vs 8.0% floor"],
        conditions=["DSCR slack monitored quarterly"],
    )


class TestNarrator:
    def test_fires_priming_call_first_then_parallel(self):
        llm = FakeLLM()
        # Canned responses for all 9 sections.
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        retriever = FakeRetriever()
        ctx = _ctx()

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=retriever))

        # Priming call must be Executive Summary and must be the FIRST call.
        assert llm.calls[0]["section"] == SECTION_EXECUTIVE_SUMMARY
        # All sections present in result (8 prose + risks + recommendation = 10).
        assert set(result.keys()) == {
            *PROSE_SECTIONS, SECTION_RISKS, SECTION_RECOMMENDATION
        }
        # Total calls = 10 (1 priming + 9 parallel).
        assert len(llm.calls) == 10

    def test_uses_correct_schema_per_section(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))

        schemas = {c["section"]: c["schema"] for c in llm.calls}
        for s in PROSE_SECTIONS:
            assert schemas[s] == "ProseSection"
        assert schemas[SECTION_RISKS] == "RisksSection"
        assert schemas[SECTION_RECOMMENDATION] == "Recommendation"

    def test_one_section_failure_does_not_block_others(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RuntimeError("LLM blew up")
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))

        # Failed section gets a placeholder; other 8 succeed.
        assert "executive_summary" in result
        assert result[SECTION_RISKS] is None
        assert isinstance(result[SECTION_RECOMMENDATION], Recommendation)

    def test_priming_failure_propagates(self):
        llm = FakeLLM()
        llm.responses[SECTION_EXECUTIVE_SUMMARY] = RuntimeError("priming exploded")
        for s in PROSE_SECTIONS:
            if s != SECTION_EXECUTIVE_SUMMARY:
                llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        with pytest.raises(RuntimeError, match="priming"):
            asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))

    def test_citation_validator_drops_fabricated_citations(self):
        llm = FakeLLM()
        ctx = _ctx()
        retriever = FakeRetriever()
        # Property section gets one real chunk on (doc-om-1, p5).
        retriever.chunks_by_section[SECTION_PROPERTY_DESCRIPTION] = [
            RetrievedChunk(doc_id="doc-om-1", page=5, text="Real chunk.")
        ]

        # LLM returns one real citation and one fabricated.
        property_response = ProseSection(
            paragraphs=["Property is climate controlled per [doc-om-1:p5].",
                        "Year-built per [doc-fake:p99]."],
            citations=[
                Citation(doc_id="doc-om-1", page=5),
                Citation(doc_id="doc-fake", page=99),
            ],
        )
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_PROPERTY_DESCRIPTION] = property_response
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=retriever))
        kept = result[SECTION_PROPERTY_DESCRIPTION].citations
        assert len(kept) == 1
        assert kept[0].doc_id == "doc-om-1"

    def test_recommendation_classification_override_when_disagrees(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = _risks()
        # LLM claims "Below Screen" but verdict says "Pursue".
        llm.responses[SECTION_RECOMMENDATION] = Recommendation(
            classification="Below Screen",
            rationale="LLM disagrees",
            driving_metrics=["foo vs bar"],
            conditions=[],
        )

        result = asyncio.run(narrate_all_sections(_ctx(classification="Pursue"),
                                                  llm=llm, retriever=FakeRetriever()))
        # Override applied.
        assert result[SECTION_RECOMMENDATION].classification == "Pursue"
