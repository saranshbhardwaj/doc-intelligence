"""Unit tests for memo prompt construction and cache structure."""
from __future__ import annotations

import json

import pytest

from app.verticals.real_estate.underwriting.memo.prompts import (
    UNIVERSAL_RULES,
    SECTION_INSTRUCTIONS,
    build_system_blocks,
    build_user_blocks,
)
from app.verticals.real_estate.underwriting.memo.schemas import (
    PROSE_SECTIONS,
    SECTION_RISKS,
    SECTION_RECOMMENDATION,
    SECTION_PROPERTY_DESCRIPTION,
    SECTION_MARKET_OVERVIEW,
    MemoContext,
    RetrievedChunk,
)


@pytest.fixture
def ctx():
    return MemoContext(
        deal_name="X", address=None, asset_type="self_storage",
        year_built=None, num_units=None, rentable_sqft=None,
        total_unit_count=None, storage_unit_count=None, non_storage_unit_count=None,
        cc_unit_count=0, nc_unit_count=0, climate_control_pct=0.0,
        purchase_price=None, price_per_unit=None, price_per_sqft=None, cap_rate_at_cost=None,
        population_3mi=None, avg_household_income_3mi=None, storage_sqft_per_capita_3mi=None,
        nearby_storage_1mi=None, nearby_storage_3mi=None, nearby_storage_5mi=None,
    )


class TestSystemPrompt:
    def test_universal_rules_is_nonempty(self):
        assert len(UNIVERSAL_RULES) > 200
        assert "CRITICAL RULES" in UNIVERSAL_RULES

    def test_system_blocks_byte_identical_across_sections(self, ctx):
        sys_a = build_system_blocks()
        sys_b = build_system_blocks()
        assert sys_a == sys_b
        # Only one block, marked cacheable.
        assert len(sys_a) == 1
        assert sys_a[0]["type"] == "text"
        assert sys_a[0]["cache_control"] == {"type": "ephemeral"}


class TestUserPrompt:
    def test_first_user_block_is_byte_identical_across_sections(self, ctx):
        blocks_a = build_user_blocks(ctx, section_key="executive_summary")
        blocks_b = build_user_blocks(ctx, section_key="risks")
        # First block (memo context) must be identical for cache to hit.
        assert blocks_a[0] == blocks_b[0]
        assert blocks_a[0]["cache_control"] == {"type": "ephemeral"}
        # Subsequent blocks differ.
        assert blocks_a[1]["text"] != blocks_b[1]["text"]

    def test_memo_context_is_valid_json(self, ctx):
        blocks = build_user_blocks(ctx, section_key="executive_summary")
        json.loads(blocks[0]["text"].split(":\n", 1)[1])

    def test_section_specific_block_contains_section_instructions(self, ctx):
        for section in (*PROSE_SECTIONS, SECTION_RISKS, SECTION_RECOMMENDATION):
            blocks = build_user_blocks(ctx, section_key=section)
            assert section in SECTION_INSTRUCTIONS, f"Missing instructions for {section}"
            assert SECTION_INSTRUCTIONS[section] in blocks[1]["text"]

    def test_rag_excerpts_appear_for_property_and_market(self, ctx):
        chunks = [
            RetrievedChunk(doc_id="d1", page=3, text="Property is climate controlled."),
            RetrievedChunk(doc_id="d1", page=7, text="Submarket grew 4% YoY."),
        ]
        ctx.retrieved_chunks = {SECTION_PROPERTY_DESCRIPTION: chunks, SECTION_MARKET_OVERVIEW: chunks}
        prop = build_user_blocks(ctx, section_key=SECTION_PROPERTY_DESCRIPTION)
        assert "[d1:p3]" in prop[1]["text"]
        assert "climate controlled" in prop[1]["text"]

    def test_no_rag_block_when_chunks_missing(self, ctx):
        blocks = build_user_blocks(ctx, section_key="sponsor")
        # Sponsor doesn't get RAG. Block text should not contain a SOURCE EXCERPTS header.
        assert "SOURCE EXCERPTS" not in blocks[1]["text"]


class TestAllSectionsHaveInstructions:
    def test_all_nine_sections_have_instruction_text(self):
        expected = {*PROSE_SECTIONS, SECTION_RISKS, SECTION_RECOMMENDATION}
        assert set(SECTION_INSTRUCTIONS.keys()) == expected
        for k, v in SECTION_INSTRUCTIONS.items():
            assert isinstance(v, str)
            assert len(v) > 100, f"Section {k} instructions too short"


class TestSharpenedRiskAndRecommendationInstructions:
    """Regression tests so future edits can't quietly soften the mitigant /
    conditions discipline that prior memos missed."""

    def test_risks_instructions_enumerate_all_five_mitigant_sources(self):
        text = SECTION_INSTRUCTIONS[SECTION_RISKS]
        # The prompt should explicitly call out each mitigant source so the LLM
        # has nowhere to default to "None identified".
        assert "METRIC CUSHION" in text
        assert "FIXED-RATE DEBT" in text
        assert "CAPEX RESERVE" in text
        assert "SPONSOR" in text
        assert "SOURCE EXCERPT" in text
        # And it should ban vague mitigant phrasing.
        assert "vague phrases" in text.lower() or "never use vague" in text.lower()

    def test_recommendation_instructions_require_conditions_when_warnings_present(self):
        text = SECTION_INSTRUCTIONS[SECTION_RECOMMENDATION]
        # Conditions list must be auto-derived from warnings when classification
        # is Pursue/Needs Review. The instruction enforces this with explicit logic.
        assert "warnings" in text.lower()
        assert "custom_conditions" in text  # analyst-supplied entries take priority
        # And it should provide concrete examples so the LLM has a template.
        assert "T-12" in text or "Obtain" in text

    def test_recommendation_instructions_enforce_driving_metric_format(self):
        text = SECTION_INSTRUCTIONS[SECTION_RECOMMENDATION]
        # The "VALUE vs THRESHOLD" pattern must be explicit so the LLM stops
        # producing thesis bullets like "Non-storage units 35% of mix".
        assert " vs " in text
        assert "thesis" in text.lower()  # explicit ban on thesis-style entries

    def test_rent_position_instructions_reference_new_summary_fields(self):
        from app.verticals.real_estate.underwriting.memo.schemas import SECTION_RENT_POSITION
        text = SECTION_INSTRUCTIONS[SECTION_RENT_POSITION]
        # New aggregated summary fields produced by _aggregate_rent_position
        # should be referenced so the LLM stops saying "data not provided".
        assert "current_vs_comp_avg" in text
        assert "matched_bucket_count" in text
        assert "current_ratio_bucket_count" in text
        assert "cannot be quantified" in text


class TestQualityFixesRoundTwo:
    """Regression tests for the second round of prompt tightening: thesis seed
    handling, property restate ban, sponsor placeholder filter, dimension-match
    mitigant rule."""

    def test_thesis_instructions_ban_verbatim_seed_echo(self):
        from app.verticals.real_estate.underwriting.memo.schemas import SECTION_INVESTMENT_THESIS
        text = SECTION_INSTRUCTIONS[SECTION_INVESTMENT_THESIS]
        # Must paraphrase, never copy.
        assert "PARAPHRASE" in text
        assert "verbatim" in text.lower()  # appears as "NEVER copy the seed verbatim"
        # Placeholder detection by length and pattern.
        assert "20 characters" in text or "shorter than 20" in text
        # Common placeholders enumerated.
        for placeholder in ["test", "tbd", "n/a"]:
            assert placeholder in text.lower()

    def test_property_description_bans_transaction_and_returns_restating(self):
        from app.verticals.real_estate.underwriting.memo.schemas import SECTION_PROPERTY_DESCRIPTION
        text = SECTION_INSTRUCTIONS[SECTION_PROPERTY_DESCRIPTION]
        # Explicit "do not include" list with the cross-section pointers.
        assert "DO NOT include" in text
        assert "Transaction Overview" in text
        assert "Financial Analysis" in text
        assert "Recommendation" in text
        # Tagged as critical so the LLM doesn't drift.
        assert "CRITICAL" in text

    def test_sponsor_instructions_have_placeholder_filter(self):
        from app.verticals.real_estate.underwriting.memo.schemas import SECTION_SPONSOR
        text = SECTION_INSTRUCTIONS[SECTION_SPONSOR]
        assert "PLACEHOLDER FILTER" in text
        # Specific placeholder strings enumerated.
        assert "good summary" in text or "tbd" in text.lower()
        # Concrete instruction: omit the field, don't quote the placeholder.
        assert "do NOT mention" in text or "Just omit" in text
        # Liquidity > net_worth sanity check.
        assert "liquidity" in text.lower() and "net_worth" in text

    def test_risks_instructions_enforce_dimension_match_for_mitigants(self):
        text = SECTION_INSTRUCTIONS[SECTION_RISKS]
        assert "DIMENSION-MATCH" in text
        # Specific anti-patterns called out by name.
        assert "EM" in text and "IRR" in text  # EM-as-IRR-mitigant ban
        assert "equity multiple" in text.lower()
        assert "Cash-on-cash" in text or "cash-on-cash" in text
        assert "Additional leverage is a financing option" in text
        assert "Do NOT cite IRR" in text
        # Fall-through to null when no same-dimension mitigant exists.
        assert "null" in text.lower()

    def test_recommendation_instructions_soften_below_screen_language(self):
        text = SECTION_INSTRUCTIONS[SECTION_RECOMMENDATION]
        assert "does not clear the configured screen" in text
        assert "warrant rejection" in text
        assert "OM-only underwriting" in text
