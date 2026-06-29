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
    SECTION_SPONSOR,
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

    def test_executive_summary_uses_canonical_mixed_use_snapshot(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_EXECUTIVE_SUMMARY] = _prose([
            "Tulsa Deal 169 is a 205-unit self-storage facility located at 1540 North Yale Avenue, Tulsa, OK 74115, being acquired for $2,500,000.",
            "The investment thesis rests on base-case returns.",
            "The primary risk is mixed-use revenue composition. Recommendation: Pursue.",
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(
            deal_name="Tulsa Deal 169",
            address="1540 North Yale Avenue, Tulsa, OK 74115",
            strategy_type="Portfolio Build",
            purchase_price=2_500_000,
            total_unit_count=205,
            storage_unit_count=133,
            non_storage_unit_count=72,
        )

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        paragraphs = result[SECTION_EXECUTIVE_SUMMARY].paragraphs

        assert "205-unit self-storage facility" not in paragraphs[0]
        assert "portfolio-build self-storage investment" in paragraphs[0]
        assert "205 total units/spaces" in paragraphs[0]
        assert "133 storage units" in paragraphs[0]
        assert "72 non-storage units/spaces" in paragraphs[0]
        assert "$2,500,000" in paragraphs[0]
        assert paragraphs[1] == "The investment thesis rests on base-case returns."

    def test_transaction_overview_preserves_om_vs_model_debt_distinction(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_TRANSACTION_OVERVIEW] = _prose([
            "The OM proposed 65% LTV, while the model uses 70% LTV."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(
            purchase_price=2_500_000,
            price_per_unit=12_195,
            price_per_sqft=119,
            cap_rate_at_cost=0.0811,
            total_unit_count=205,
            storage_unit_count=133,
            non_storage_unit_count=72,
            om_financing_evidence={
                "proposed_loan_amount": 1_625_000.0,
                "proposed_ltv_pct": 0.65,
                "model_loan_amount": 1_750_000.0,
                "model_ltv_pct": 0.70,
            },
        )

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        paragraph = result[SECTION_TRANSACTION_OVERVIEW].paragraphs[0]

        assert "OM proposed 65.00% / $1,625,000" in paragraph
        assert "model uses 70.00% / $1,750,000" in paragraph
        assert "modeled returns use the model capital stack" in paragraph

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

    def test_prose_guards_fix_climate_control_contradictions(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_EXECUTIVE_SUMMARY] = _prose([
            "The property comprises 133 climate-controlled storage units and 72 parking/residential spaces."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(
            total_unit_count=205,
            storage_unit_count=133,
            non_storage_unit_count=72,
            cc_unit_count=0,
            nc_unit_count=133,
            climate_control_pct=0,
        )

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        text = "\n".join(result[SECTION_EXECUTIVE_SUMMARY].paragraphs)

        assert "133 climate-controlled storage units" not in text
        assert "205 total units/spaces" in text
        assert "133 storage units" in text
        assert "72 non-storage units/spaces" in text

    def test_prose_guards_fix_loan_term_mislabeled_as_hold_period(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_EXECUTIVE_SUMMARY] = _prose([
            "Debt service coverage remains above 1.30x across a 10-year hold under base-case assumptions."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(
            financing={"loan_term_years": 10, "amortization_years": 25},
            source_support=[{"field_key": "hold_period_years", "value": "5 years"}],
        )

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        text = "\n".join(result[SECTION_EXECUTIVE_SUMMARY].paragraphs)

        assert "10-year hold" not in text
        assert "5-year hold" in text

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

    def test_sponsor_prose_drops_false_net_worth_liquidity_inconsistency(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_SPONSOR] = _prose([
            "Sponsor reports $100,000,000 in net worth and $10,000,000 in liquidity.",
            "Net-worth and liquidity figures require analyst verification (reported values are inconsistent).",
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(
            _ctx(sponsor_data={"net_worth": 100_000_000.0, "liquidity": 10_000_000.0}),
            llm=llm,
            retriever=FakeRetriever(),
        ))
        text = "\n".join(result[SECTION_SPONSOR].paragraphs).lower()

        assert "reported values are inconsistent" not in text
        assert "$100,000,000" in text
        assert "$10,000,000" in text

    def test_market_overview_drops_rent_position_paragraph(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_MARKET_OVERVIEW] = _prose([
            "The 3-mile radius contains 63,110 people and 6.93 square feet per capita.",
            "The property's rent position analysis indicates current in-place rents exceed comparable market rates by 20.2%.",
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))
        text = "\n".join(result[SECTION_MARKET_OVERVIEW].paragraphs).lower()

        assert "3-mile radius" in text
        assert "rent position" not in text
        assert "in-place rents exceed" not in text

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
        assert "rent sustainability" in paragraph.lower()
        assert "above market" not in paragraph.lower()

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
                title="Zero-percent rent growth assumption reduces equity multiple below target.",
                severity="medium",
                source="stress_test",
                mitigant="Base-case rent growth of 3% annually is conservative relative to historical self-storage inflation.",
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

    def test_structured_risk_policy_replaces_llm_risks_when_supported(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        # Intentionally do not provide SECTION_RISKS. If the narrator calls the
        # LLM for risks despite having enough structured policy risks, FakeLLM
        # will raise and this assertion will fail.
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(
            _ctx(
                total_unit_count=205,
                storage_unit_count=133,
                non_storage_unit_count=72,
                year_built=2001,
                rent_position={
                    "current_vs_comp_avg": 1.225,
                    "exact_size_matched_count": 4,
                    "exact_size_total_count": 12,
                },
                stress_tests=[
                    {
                        "label": "Vacancy +5%",
                        "scenario_key": "vacancy_plus_5pct",
                        "irr": 0.0842,
                        "dscr_year_one": 1.33,
                        "equity_multiple": 1.44,
                    },
                    {
                        "label": "Rent Growth = 0%",
                        "scenario_key": "rent_growth_zero",
                        "irr": 0.0353,
                        "dscr_year_one": 1.43,
                        "equity_multiple": 1.16,
                    },
                ],
                criteria={"target_irr": 0.10, "target_equity_multiple": 1.30, "dscr_year_one_floor": 1.25},
                capital_structure={"capex_reserve_initial": 0.0},
                capex_reserve_per_unit=0.0,
            ),
            llm=llm,
            retriever=FakeRetriever(),
        ))

        assert SECTION_RISKS not in [call["section"] for call in llm.calls]
        risks = result[SECTION_RISKS].risks
        text = "\n".join(risk.title for risk in risks).lower()
        assert "mixed revenue stream" in text
        assert "rent sustainability risk" in text
        assert "zero rent growth" in text
        assert "vacancy +5%" in text
        assert all(risk.mitigant is None for risk in risks)

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

    def test_prose_guards_reframe_above_comp_rents_without_pricing_power(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_INVESTMENT_THESIS] = _prose([
            "Rents at 119% of the comp average demonstrate pricing power and support rent upside."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(rent_position={
            "matched_bucket_count": 3,
            "total_bucket_count": 4,
            "current_ratio_bucket_count": 3,
            "current_vs_comp_avg": 1.19,
        })

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        text = "\n".join(result[SECTION_INVESTMENT_THESIS].paragraphs)

        assert "pricing power" not in text.lower()
        assert "rent sustainability" in text.lower()
        assert "rent upside" not in text.lower()

    def test_prose_guards_reframe_rent_rate_positioning_upside_when_above_comp(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_INVESTMENT_THESIS] = _prose([
            "The asset carries identifiable upside through rent-rate positioning and unit conversion. "
            "Current rents trade 12-24% above comparable facilities."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(rent_position={
            "matched_bucket_count": 3,
            "total_bucket_count": 4,
            "current_ratio_bucket_count": 3,
            "current_vs_comp_avg": 1.20,
        })

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        text = "\n".join(result[SECTION_INVESTMENT_THESIS].paragraphs)

        assert "upside through rent-rate positioning" not in text.lower()
        assert "rent sustainability" in text.lower()
        assert "above comparable facilities" in text.lower()
        assert "unit conversion remains a separate value-add lever" in text.lower()

    def test_prose_guards_separate_rent_positioning_from_conversion_thesis(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_INVESTMENT_THESIS] = _prose([
            "Current rent positioning supports the conversion thesis. The property is leasing 22-29% above comparable market rents."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(rent_position={
            "matched_bucket_count": 3,
            "total_bucket_count": 4,
            "current_ratio_bucket_count": 3,
            "current_vs_comp_avg": 1.225,
        })

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        text = "\n".join(result[SECTION_INVESTMENT_THESIS].paragraphs).lower()

        assert "rent positioning supports the conversion thesis" not in text
        assert "separate from the conversion thesis" in text
        assert "rent sustainability risk" in text

    def test_prose_guards_fix_underrented_contradiction_when_rents_above_comps(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_INVESTMENT_THESIS] = _prose([
            "The property is currently underrented relative to market comps--in-place rents run 22-29% above comparable asking rents across matched unit sizes."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(rent_position={
            "matched_bucket_count": 3,
            "total_bucket_count": 4,
            "current_ratio_bucket_count": 3,
            "current_vs_comp_avg": 1.225,
        })

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        text = "\n".join(result[SECTION_INVESTMENT_THESIS].paragraphs).lower()

        assert "underrented" not in text
        assert "rent sustainability risk" in text
        assert "above comparable asking rents" in text

    def test_prose_guards_reframe_rent_sustainability_above_peers_phrase(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_EXECUTIVE_SUMMARY] = _prose([
            "Current rents average 1.20x comparable market rates, indicating rent sustainability above peer facilities."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(rent_position={
            "matched_bucket_count": 3,
            "total_bucket_count": 4,
            "current_ratio_bucket_count": 3,
            "current_vs_comp_avg": 1.20,
        })

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        text = "\n".join(result[SECTION_EXECUTIVE_SUMMARY].paragraphs).lower()

        assert "rent sustainability above peer facilities" not in text
        assert "rent sustainability risk relative to peer facilities" in text

    def test_prose_guards_reframe_above_comp_rents_supporting_returns_and_hold_period(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_EXECUTIVE_SUMMARY] = _prose([
            "Current rents across matched unit sizes average 22.5% above comparable facilities, "
            "supporting cash-on-cash returns of 7.6% and an equity multiple of 1.74x over the 10-year hold."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(
            financing={"loan_term_years": 10, "amortization_years": 25},
            rent_position={
                "matched_bucket_count": 3,
                "total_bucket_count": 4,
                "current_ratio_bucket_count": 3,
                "current_vs_comp_avg": 1.225,
            },
            source_support=[{"field_key": "hold_period_years", "value": "5 years"}],
        )

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        text = "\n".join(result[SECTION_EXECUTIVE_SUMMARY].paragraphs).lower()

        assert "supporting cash-on-cash" not in text
        assert "supporting" not in text
        assert "rent sustainability risk" in text
        assert "10-year hold" not in text
        assert "5-year hold" in text

    def test_prose_guards_do_not_frame_above_comp_rents_as_downside_protection(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_EXECUTIVE_SUMMARY] = _prose([
            "Current in-place rents average 22.5% above comparable market rates across matched unit sizes, "
            "providing downside protection if market conditions soften."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(rent_position={
            "matched_bucket_count": 3,
            "total_bucket_count": 4,
            "current_ratio_bucket_count": 3,
            "current_vs_comp_avg": 1.225,
        })

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        text = "\n".join(result[SECTION_EXECUTIVE_SUMMARY].paragraphs).lower()

        assert "downside protection" not in text
        assert "rent sustainability risk" in text
        assert "downside exposure" in text

    def test_prose_guards_do_not_frame_average_above_comp_rents_as_downside_protection(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_EXECUTIVE_SUMMARY] = _prose([
            "Current rents across the storage portfolio average 22.5% above comparable asking rents, "
            "providing downside protection if occupancy or rate assumptions do not hold."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(rent_position={
            "matched_bucket_count": 3,
            "total_bucket_count": 4,
            "current_ratio_bucket_count": 3,
            "current_vs_comp_avg": 1.225,
        })

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        text = "\n".join(result[SECTION_EXECUTIVE_SUMMARY].paragraphs).lower()

        assert "downside protection" not in text
        assert "rent sustainability risk" in text
        assert "downside exposure" in text

    def test_prose_guards_do_not_frame_above_comp_rents_as_downside_cushion(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_EXECUTIVE_SUMMARY] = _prose([
            "Current in-place rents average 22.5% above comparable properties across matched unit sizes, "
            "providing downside cushion if market conditions soften."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(rent_position={
            "matched_bucket_count": 3,
            "total_bucket_count": 4,
            "current_ratio_bucket_count": 3,
            "current_vs_comp_avg": 1.225,
        })

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        text = "\n".join(result[SECTION_EXECUTIVE_SUMMARY].paragraphs).lower()

        assert "downside cushion" not in text
        assert "rent sustainability risk" in text
        assert "downside exposure" in text

    def test_prose_guards_separate_below_market_tenant_upside_from_above_comp_positioning(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_INVESTMENT_THESIS] = _prose([
            "The property offers modest upside through below-market rent positioning and a conversion opportunity. "
            "Current rents run 22% above comparable asking rents across matched unit sizes, but 36% of occupied units are below-market tenants."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(rent_position={
            "matched_bucket_count": 3,
            "total_bucket_count": 4,
            "current_ratio_bucket_count": 3,
            "current_vs_comp_avg": 1.22,
        })

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        text = "\n".join(result[SECTION_INVESTMENT_THESIS].paragraphs).lower()

        assert "below-market rent positioning" not in text
        assert "tenant-level below-market upside" in text
        assert "comp-set rent sustainability risk" in text

    def test_prose_guards_do_not_link_above_comp_rents_to_rollover_upside(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_INVESTMENT_THESIS] = _prose([
            "Current rents across three matched unit sizes trade 12-29% above comparable asking rents, "
            "indicating embedded tenant roll-over upside of approximately $10,410 annually."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(rent_position={
            "matched_bucket_count": 3,
            "total_bucket_count": 4,
            "current_ratio_bucket_count": 3,
            "current_vs_comp_avg": 1.225,
        })

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        text = "\n".join(result[SECTION_INVESTMENT_THESIS].paragraphs).lower()

        assert "above comparable asking rents, indicating" not in text
        assert "roll-over upside" in text
        assert "separate" in text
        assert "rent sustainability risk" in text

    def test_prose_guards_separate_below_market_rent_normalization_from_above_comp_positioning(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_INVESTMENT_THESIS] = _prose([
            "The investment thesis is a value-add play centered on rent growth and unit conversion. "
            "The property offers modest upside through below-market rent normalization. "
            "Current rents run 22% above comparable asking rents across matched unit sizes."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(rent_position={
            "matched_bucket_count": 3,
            "total_bucket_count": 4,
            "current_ratio_bucket_count": 3,
            "current_vs_comp_avg": 1.22,
        })

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        text = "\n".join(result[SECTION_INVESTMENT_THESIS].paragraphs).lower()

        assert "below-market rent normalization" not in text
        assert "tenant-level below-market upside" in text
        assert "comp-set rent sustainability risk" in text

    def test_prose_guards_fix_competitor_radius_transposition(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_INVESTMENT_THESIS] = _prose([
            "The market supports non-climate-controlled positioning with 10 competitors within 5 miles."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        ctx = _ctx(nearby_storage_3mi=10, nearby_storage_5mi=None)

        result = asyncio.run(narrate_all_sections(ctx, llm=llm, retriever=FakeRetriever()))
        text = "\n".join(result[SECTION_INVESTMENT_THESIS].paragraphs).lower()

        assert "10 competitors within 5 miles" not in text
        assert "10 competitors within 3 miles" in text

    def test_risk_guards_fix_equity_multiple_target_contradiction(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Occupancy stress reduces DSCR to 1.33x and equity multiple to 1.44x, below the 1.30x target equity multiple threshold.",
                severity="medium",
                source="stress_test",
                mitigant=None,
            ),
            Risk(title="DSCR slack thin in stress.", severity="medium", source="verdict_warning", mitigant=None),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(
            _ctx(criteria={"target_equity_multiple": 1.30}),
            llm=llm,
            retriever=FakeRetriever(),
        ))
        title = result[SECTION_RISKS].risks[0].title.lower()

        assert "below the 1.30x target" not in title
        assert "above the 1.30x target" in title

    def test_risk_guards_fix_both_below_thresholds_contradiction(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Occupancy stress of +5% vacancy reduces year-one DSCR to 1.33x and equity multiple to 1.44x, both below target thresholds.",
                severity="medium",
                source="stress_test",
                mitigant=None,
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(
            _ctx(criteria={"dscr_year_one_floor": 1.25, "target_equity_multiple": 1.30}),
            llm=llm,
            retriever=FakeRetriever(),
        ))
        title = result[SECTION_RISKS].risks[0].title.lower()

        assert "both below target thresholds" not in title
        assert "both remain above configured thresholds" in title

    def test_risk_guards_remove_invented_strong_equity_return_threshold(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Occupancy stress of +5% vacancy reduces DSCR to 1.33x and equity multiple to 1.44x, below the 1.50x threshold for strong equity returns.",
                severity="medium",
                source="stress_test",
                mitigant=None,
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(
            _ctx(criteria={"dscr_year_one_floor": 1.25, "target_equity_multiple": 1.30}),
            llm=llm,
            retriever=FakeRetriever(),
        ))
        title = result[SECTION_RISKS].risks[0].title.lower()

        assert "1.50x threshold" not in title
        assert "strong equity returns" not in title
        assert "above the 1.30x target" in title

    def test_risk_guards_fix_dscr_cushion_basis_point_wording(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Interest rate increase of 100 basis points reduces DSCR to 1.31x, narrowing the 6 basis point cushion above the 1.25x floor.",
                severity="low",
                source="stress_test",
                mitigant=None,
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))
        title = result[SECTION_RISKS].risks[0].title.lower()

        assert "6 basis point cushion" not in title
        assert "0.06x cushion" in title

    def test_risk_guards_fix_dscr_margin_basis_point_wording(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Occupancy stress of +5% vacancy reduces DSCR to 1.33x and IRR to 8.42%, narrowing the margin above the 1.25x DSCR floor to 8 basis points.",
                severity="medium",
                source="stress_test",
                mitigant=None,
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))
        title = result[SECTION_RISKS].risks[0].title.lower()

        assert "8 basis points" not in title
        assert "0.08x cushion" in title

    def test_risk_guards_remove_liquidity_risk_when_liquidity_covers_equity(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Sponsor liquidity of $10,000,000 is modest relative to $800,000 equity commitment and provides limited reserve for operational shortfalls.",
                severity="medium",
                source="analyst_note",
                mitigant="Sponsor's 90 prior self-storage acquisitions reduce execution risk.",
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(
            _ctx(
                capital_structure={"total_equity_invested": 800_000.0},
                sponsor_data={"liquidity": 10_000_000.0},
            ),
            llm=llm,
            retriever=FakeRetriever(),
        ))
        risks_text = "\n".join(risk.title for risk in result[SECTION_RISKS].risks).lower()

        assert "liquidity" not in risks_text
        assert "modest relative" not in risks_text

    def test_risk_guards_remove_liquidity_risk_when_liquidity_covers_purchase_price(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Sponsor liquidity of $10,000,000 is modest relative to a $2,500,000 acquisition and provides limited cushion for unexpected capital calls.",
                severity="low",
                source="analyst_note",
                mitigant="Sponsor net worth of $100,000,000 and 10 years of self-storage experience provide capacity to support the asset.",
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(
            _ctx(purchase_price=2_500_000.0, sponsor_data={"liquidity": 10_000_000.0}),
            llm=llm,
            retriever=FakeRetriever(),
        ))
        risks_text = "\n".join(risk.title for risk in result[SECTION_RISKS].risks).lower()

        assert "liquidity" not in risks_text
        assert "modest relative" not in risks_text

    def test_risk_guards_remove_experience_mitigant_for_liquidity_risk(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Sponsor liquidity of $1,000,000 is modest relative to the $800,000 equity investment, limiting ability to fund unexpected shortfalls or lease-up gaps.",
                severity="low",
                source="analyst_note",
                mitigant="Sponsor has 10 years of experience and 218 prior deals in self-storage, reducing execution risk on a stabilized asset.",
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(
            _ctx(
                capital_structure={"total_equity_invested": 800_000.0},
                sponsor_data={"liquidity": 1_000_000.0},
            ),
            llm=llm,
            retriever=FakeRetriever(),
        ))

        assert result[SECTION_RISKS].risks[0].title.startswith("Sponsor liquidity")
        assert result[SECTION_RISKS].risks[0].mitigant is None

    def test_risk_guards_remove_mixed_use_diversification_mitigant(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Mixed revenue stream: 72 of 205 units (35% of unit count) are parking or residential, not self-storage.",
                severity="high",
                source="verdict_warning",
                mitigant="Parking and residential units generated $34,278 in other income, providing diversified revenue that reduces single-asset-class dependency.",
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Property tax reassessment risk remains open.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))

        assert result[SECTION_RISKS].risks[0].mitigant is None

    def test_risk_guards_remove_mixed_use_diversified_cash_flow_mitigant(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Mixed revenue stream: 72 of 205 units are parking or residential, not self-storage, creating concentration risk and model mismatch.",
                severity="high",
                source="verdict_warning",
                mitigant="Parking and residential units generated $34,278 in other income during the trailing period, providing diversified cash flow that reduces reliance on storage-unit performance alone.",
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Property tax reassessment risk remains open.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))

        assert result[SECTION_RISKS].risks[0].mitigant is None

    def test_risk_guards_remove_base_case_return_mitigant_for_rent_growth_stress(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Stress scenario with zero rent growth produces equity multiple of 1.16x, falling below the 1.30x target.",
                severity="medium",
                source="stress_test",
                mitigant="Base-case IRR of 13.34% exceeds the 10% target by 334 basis points, providing cushion against modest rent-growth shortfalls.",
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))

        assert result[SECTION_RISKS].risks[0].mitigant is None

    def test_risk_guards_remove_small_unit_only_mitigant_for_above_market_rents(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="In-place rents on small units are 29% above comparable market rents, creating downside risk if tenant turnover forces re-leasing at market rates.",
                severity="medium",
                source="rent_position",
                mitigant="Only 26 small units are exposed to this premium; the remaining 107 storage units are priced at or below market comparables, limiting portfolio-wide rent compression risk.",
            ),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
            Risk(title="Property tax reassessment risk remains open.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))

        assert result[SECTION_RISKS].risks[0].mitigant is None

    def test_risk_guards_remove_below_market_upside_mitigant_for_above_market_rents(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="In-place rents exceed market comparables by 22-29% across matched unit sizes, creating downside risk.",
                severity="high",
                source="rent_position",
                mitigant="36% of storage units are below-market, representing $10,410 in annual upside if rents are normalized, which offsets the overlevered positions on larger units.",
            ),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
            Risk(title="Property tax reassessment risk remains open.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))

        assert result[SECTION_RISKS].risks[0].mitigant is None

    def test_risk_guards_remove_sponsor_experience_mitigant_for_above_market_rents(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="In-place rents exceed market comparables by 22-29% across matched unit sizes, creating downside risk if occupancy declines or tenants roll.",
                severity="high",
                source="rent_position",
                mitigant="Current occupancy across storage units averages 82%, providing buffer before rent realization pressure forces concessions; additionally, sponsor has completed 185 prior self-storage acquisitions, reducing execution risk on lease management.",
            ),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
            Risk(title="Property tax reassessment risk remains open.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))

        assert result[SECTION_RISKS].risks[0].mitigant is None

    def test_risk_guards_remove_conversion_upside_as_capex_reserve_mitigant(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Capex reserve is zero, leaving no dedicated funding for unit conversions or unexpected capital repairs.",
                severity="low",
                source="verdict_warning",
                mitigant="The offering memorandum identifies $122,400 in annual revenue upside from converting 56 uncovered parking spaces, providing a self-funded value-creation path.",
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))

        assert result[SECTION_RISKS].risks[0].mitigant is None

    def test_risk_guards_remove_fixed_rate_debt_as_exit_cap_mitigant(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Exit cap rate assumption of 8.61% is model-default and unsupported by market evidence; cap expansion would reduce equity multiple.",
                severity="medium",
                source="verdict_warning",
                mitigant="10-year fixed-rate debt at 6.5% with 25-year amortization locks debt service through the hold period, insulating equity returns from refinance risk.",
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))

        assert result[SECTION_RISKS].risks[0].mitigant is None

    def test_risk_guards_remove_fixed_rate_debt_as_vacancy_stress_mitigant(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Occupancy stress of +5% vacancy reduces DSCR to 1.33x and IRR to 8.42%, narrowing the margin above the 1.25x DSCR floor to 8 basis points.",
                severity="medium",
                source="stress_test",
                mitigant="Fixed 10-year debt term at 6.50% interest locks debt service through the hold period, preventing refinance risk during a downturn.",
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))

        assert result[SECTION_RISKS].risks[0].mitigant is None

    def test_risk_guards_remove_fixed_rate_debt_as_vacancy_stress_mitigant_when_title_mentions_equity_multiple(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Occupancy stress of +5% vacancy reduces Year-1 DSCR to 1.33x and equity multiple to 1.44x, narrowing return cushion and increasing refinance risk in a downturn.",
                severity="medium",
                source="stress_test",
                mitigant="10-year fixed-rate debt at 6.50% locks debt service through the hold period, insulating cash flow from refinance risk if rates rise.",
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))

        assert result[SECTION_RISKS].risks[0].mitigant is None

    def test_risk_guards_remove_sponsor_experience_as_capex_reserve_mitigant(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Capex reserve is zero, leaving no funding cushion for unexpected repairs, maintenance spikes, or parking-to-storage conversion capital.",
                severity="low",
                source="verdict_warning",
                mitigant="Year-1 repairs and maintenance expense of $2,102 is minimal, and sponsor's 10 years of experience reduces execution risk on capital planning.",
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))

        assert result[SECTION_RISKS].risks[0].mitigant is None

    def test_risk_guards_fix_vacancy_stress_mixed_threshold_wording(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Vacancy stress (+5%) reduces DSCR to 1.33x and IRR to 8.42%, falling below the 1.25x minimum DSCR floor and the 10% IRR target.",
                severity="medium",
                source="stress_test",
                mitigant=None,
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(
            _ctx(criteria={"dscr_year_one_floor": 1.25, "target_irr": 0.10}),
            llm=llm,
            retriever=FakeRetriever(),
        ))
        title = result[SECTION_RISKS].risks[0].title.lower()

        assert "below the 1.25x minimum dscr floor" not in title
        assert "dscr remains above the 1.25x floor" in title
        assert "irr falls below the 10.00% target" in title

    def test_risk_guards_remove_adequate_liquidity_non_risk(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Sponsor liquidity of $10,000,000 and net worth of $200,000,000 are adequate for a $800,000 equity check, but experience reduces execution risk.",
                severity="low",
                source="analyst_note",
                mitigant=None,
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(
            _ctx(capital_structure={"total_equity_invested": 800_000.0}, sponsor_data={"liquidity": 10_000_000.0}),
            llm=llm,
            retriever=FakeRetriever(),
        ))
        risks_text = "\n".join(risk.title for risk in result[SECTION_RISKS].risks).lower()

        assert "liquidity" not in risks_text
        assert "adequate" not in risks_text

    def test_sponsor_prose_does_not_treat_target_matching_track_record_as_positive(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_SPONSOR] = _prose([
            "Track record IRR is reported at 10.00%, which aligns with the fund's target IRR for this investment."
        ])
        llm.responses[SECTION_RISKS] = _risks()
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(
            _ctx(criteria={"target_irr": 0.10}, sponsor_data={"track_record_irr": 0.10}),
            llm=llm,
            retriever=FakeRetriever(),
        ))
        text = "\n".join(result[SECTION_SPONSOR].paragraphs).lower()

        assert "aligns with the fund's target" not in text
        assert "not a mitigant" in text

    def test_risk_guards_remove_balance_sheet_mitigant_for_negative_track_record(self):
        llm = FakeLLM()
        for s in PROSE_SECTIONS:
            llm.responses[s] = _prose()
        llm.responses[SECTION_RISKS] = RisksSection(risks=[
            Risk(
                title="Sponsor track record shows negative IRR of -2% on prior deals, raising execution and value-creation risk.",
                severity="medium",
                source="analyst_note",
                mitigant="Sponsor has completed 220 deals in self-storage and maintains $1,000,000,000 net worth and $10,000,000 liquidity, supporting operational continuity and capital availability.",
            ),
            Risk(title="Rent sustainability risk remains open.", severity="medium", source="rent_position", mitigant=None),
            Risk(title="Mixed-use revenue concentration.", severity="medium", source="verdict_warning", mitigant=None),
        ])
        llm.responses[SECTION_RECOMMENDATION] = _rec()

        result = asyncio.run(narrate_all_sections(_ctx(), llm=llm, retriever=FakeRetriever()))

        assert result[SECTION_RISKS].risks[0].mitigant is None

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
