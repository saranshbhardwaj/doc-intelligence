"""Prompt contract tests for underwriting extraction guidance."""

from app.verticals.real_estate.underwriting.extraction.prompts import OM_EXTRACTION_SYSTEM_PROMPT


def test_om_prompt_distinguishes_current_vs_exit_cap_rate_terms():
    prompt = OM_EXTRACTION_SYSTEM_PROMPT.lower()

    assert "current cap rate" in prompt
    assert "market_cap_rate_purchase" in prompt
    assert "pro forma cap rate" in prompt
    assert "exit_cap_rate" in prompt
    assert 'never map "current cap rate" into exit_cap_rate'.lower() in prompt


def test_om_prompt_maps_common_tax_rate_labels_to_mil_rate():
    prompt = OM_EXTRACTION_SYSTEM_PROMPT.lower()

    assert "mil_rate" in prompt
    assert "mill rate" in prompt
    assert "current tax rate" in prompt
    assert "mill levy" in prompt
    assert "tax assumptions and footnotes are valid sources" in prompt
    assert "current tax rate ($0.11161)" in prompt
    assert "mil_rate = 0.11161" in prompt
    assert "do not substitute them for mil_rate" in prompt
    assert "do not confuse it with annual property tax expense or property tax growth" in prompt


def test_om_prompt_uses_three_mile_column_for_demographics():
    prompt = OM_EXTRACTION_SYSTEM_PROMPT.lower()

    # Bad example removed
    assert "population in your selected geography is 153,689" not in prompt
    # Core 1/3/5 layout rule
    assert "1 mile | 3 miles | 5 miles" in prompt
    assert "2023 estimate 10,509 63,110 153,689" in prompt
    assert "population_3mi = 63,110" in prompt
    # Header-matching rule, not value-picking
    assert "match by" in prompt or "match the column" in prompt
    assert "do not" in prompt and ("largest" in prompt or "middle value" in prompt)
    # Exclude non-population rows
    assert "do not use population age 25+" in prompt or "do not use age-25+" in prompt
    # Variant layouts
    assert "1 mile | 2 miles | 3 miles" in prompt
    assert "3 miles | 5 miles" in prompt
    assert "1 mile | 5 miles" in prompt
    assert "leave population_3mi null" in prompt or "leave null" in prompt
    # Income and sqft fields follow the same rule
    assert "avg_household_income_3mi" in prompt
    assert "storage_sqft_per_capita_3mi" in prompt
    assert "same radius-column matching rules" in prompt or "same" in prompt and "radius" in prompt
