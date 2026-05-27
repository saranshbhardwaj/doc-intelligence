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
    SECTION_FINANCIAL_ANALYSIS,
    SECTION_INVESTMENT_THESIS,
    SECTION_TRANSACTION_OVERVIEW,
    SECTION_RECOMMENDATION,
    SECTION_RISKS,
    SECTION_RENT_POSITION,
    SECTION_PROPERTY_DESCRIPTION,
    SECTION_MARKET_OVERVIEW,
)


def _ctx(**overrides):
    base = dict(
        deal_name="X", address="A", asset_type="self_storage",
        year_built=2010, num_units=400, rentable_sqft=50_000,
        total_unit_count=400, storage_unit_count=400, non_storage_unit_count=None,
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

    def test_transaction_overview_uses_canonical_unit_mix_counts(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_TRANSACTION_OVERVIEW] = _prose([
            "The 133-unit portfolio comprises 61 storage units and 72 non-storage units."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(
            purchase_price=2_500_000,
            price_per_unit=18_797,
            price_per_sqft=119,
            cap_rate_at_cost=0.0811,
            total_unit_count=205,
            storage_unit_count=133,
            non_storage_unit_count=72,
        )
        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        paragraph = result[SECTION_TRANSACTION_OVERVIEW].paragraphs[0]
        assert "205 total units/spaces" in paragraph
        assert "133 storage units" in paragraph
        assert "72 non-storage" in paragraph
        assert "61 storage" not in paragraph

    def test_property_description_drops_bad_derived_unit_count(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_PROPERTY_DESCRIPTION] = _prose([
            "The property includes 61 storage units.",
            "The 133-unit portfolio comprises 61 storage units and 72 non-storage units.",
            "Security includes keypad gate access.",
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(
            total_unit_count=205,
            storage_unit_count=133,
            non_storage_unit_count=72,
            rentable_sqft=21_017,
            year_built=2001,
            cc_unit_count=0,
            nc_unit_count=133,
            climate_control_pct=0,
        )
        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        paragraphs = result[SECTION_PROPERTY_DESCRIPTION].paragraphs
        text = "\n".join(paragraphs)
        assert "205 total units/spaces" in paragraphs[0]
        assert "133 storage units" in paragraphs[0]
        assert "21,017 rentable square feet; it was built in 2001" in paragraphs[0]
        assert "61 storage" not in text
        assert "Security includes keypad gate access." in text

    def test_recommendation_drops_non_metric_driving_items(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = Recommendation(
            classification="Pursue",
            rationale="Rationale.",
            driving_metrics=[
                "DSCR 1.45x vs 1.25x floor",
                "Non-storage units 35% of mix vs pure-storage underwriting",
            ],
            conditions=[],
        )

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))
        assert result[SECTION_RECOMMENDATION].driving_metrics == [
            "DSCR 1.45x vs 1.25x floor"
        ]

    def test_rent_position_uses_comp_coverage_when_ratio_missing(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()
        ctx = _ctx(rent_position={
            "matched_bucket_count": 4,
            "total_bucket_count": 12,
            "current_ratio_bucket_count": 0,
            "current_vs_comp_avg": None,
            "unmatched_sizes": ["7 x 12.5", "8 x 15"],
        })

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        paragraph = result[SECTION_RENT_POSITION].paragraphs[0]

        assert "4 of 12 rent-position buckets have comp coverage" in paragraph
        assert "cannot be quantified" in paragraph
        assert "no matched comp buckets" not in paragraph

    def test_rent_position_mentions_exact_size_coverage_when_available(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()
        ctx = _ctx(rent_position={
            "matched_bucket_count": 3,
            "total_bucket_count": 4,
            "current_ratio_bucket_count": 3,
            "current_vs_comp_avg": 1.19,
            "exact_size_matched_count": 4,
            "exact_size_total_count": 12,
            "exact_size_unmatched_sizes": ["7 x 12.5", "8 x 15"],
        })

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        paragraph = result[SECTION_RENT_POSITION].paragraphs[0]

        assert "Rent-position support is partial" in paragraph
        assert "4 of 12 exact subject sizes have comp support" in paragraph
        assert "3 of 4 rent-position buckets have comp coverage" in paragraph
        assert "7 x 12.5" in paragraph

    def test_risk_guards_remove_mismatched_mitigants_and_clean_unit_share_language(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Cash-on-cash return of 7.7% falls short.",
                severity="medium",
                source="verdict_warning",
                mitigant="Year-1 DSCR of 1.54x provides cushion above the 1.25x floor.",
            ),
            Risk(
                title="Equity multiple of 1.90x trails target.",
                severity="medium",
                source="verdict_warning",
                mitigant="Year-1 DSCR of 1.54x provides cushion above the 1.25x floor.",
            ),
            Risk(
                title="72 of 205 units (35% of unit-mix scheduled rent) are non-storage units.",
                severity="high",
                source="verdict_warning",
                mitigant="Sponsor has 20 years of experience in self-storage.",
            ),
            Risk(
                title="Expense ratio of 28.5% is below the benchmark.",
                severity="medium",
                source="verdict_warning",
                mitigant="Sponsor has 141 prior deals in the self-storage asset class.",
            ),
            Risk(
                title="Stress scenario with 5% vacancy increase reduces IRR below target.",
                severity="high",
                source="stress_test",
                mitigant="DSCR remains 1.44x under the +5% vacancy stress.",
            ),
            Risk(
                title="Mixed-use portfolio includes 72 non-storage units.",
                severity="high",
                source="verdict_warning",
                mitigant="Parking and residential units are fully occupied.",
            ),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))
        risks = result[SECTION_RISKS].risks

        assert risks[0].mitigant is None
        assert risks[1].mitigant is None
        assert "35% of unit count" in risks[2].title
        assert risks[2].mitigant is None
        assert risks[3].mitigant is None
        assert risks[4].mitigant is None
        assert risks[5].mitigant is None

    def test_prose_guards_fix_metric_contradictions_and_mixed_unit_language(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_INVESTMENT_THESIS] = _prose([
            "The IRR of 15.4% falls short of the 15% hurdle only marginally.",
            "72 of 205 units (35% of unit-mix scheduled rent) are parking or residential.",
            "The asset operates in a supply-constrained market.",
            "The shortfall is material enough to warrant rejection absent repricing.",
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(
            return_metrics={"irr": 0.154},
            criteria={"target_irr": 0.15},
        )

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        text = "\n".join(result[SECTION_INVESTMENT_THESIS].paragraphs)

        assert "exceeds the 15% hurdle" in text
        assert "falls short" not in text
        assert "35% of unit count" in text
        assert "supply-pressured market" in text
        assert "warrant rejection" not in text
        assert "warrant repricing" in text

    def test_financial_analysis_uses_deterministic_noi_bridge_and_thresholds(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_FINANCIAL_ANALYSIS] = _prose([
            "Year-1 NOI is modeled at $202,802, a $12,012 increase from OM-stated Year-1 figure."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(
            noi_buildup={"noi": 202_802.0},
            noi_bridge={"om_year_one_noi": 202_790.0, "om_current_noi": 177_453.0},
            return_metrics={
                "irr": 0.1543,
                "cash_on_cash": 0.0769,
                "equity_multiple": 1.90,
                "dscr_year_one": 1.54,
            },
            criteria={
                "target_irr": 0.15,
                "target_cash_on_cash": 0.08,
                "target_equity_multiple": 2.0,
                "dscr_year_one_floor": 1.25,
            },
        )

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        text = result[SECTION_FINANCIAL_ANALYSIS].paragraphs[0]

        assert "$12 variance" in text
        assert "$12,012" not in text
        assert "cash-on-cash 7.69% falls short" in text
        assert "Year-1 DSCR 1.54x clears" in text

    def test_below_screen_recommendation_language_is_softened(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = Recommendation(
            classification="Below Screen",
            rationale="The shortfall warrants rejection and precludes advancement.",
            driving_metrics=["Cash-on-cash 7.7% vs 8.0% target"],
            conditions=[],
        )

        result = asyncio.run(narrate_all_sections(
            _ctx(classification="Below Screen"),
            llm=llm,
            retriever=FakeRetriever(),
        ))
        rationale = result[SECTION_RECOMMENDATION].rationale.lower()

        assert "rejection" not in rationale
        assert "preclude" not in rationale
        assert "current assumptions" in rationale
