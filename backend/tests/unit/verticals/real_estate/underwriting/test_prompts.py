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
    assert "do not confuse it with annual property tax expense or property tax growth" in prompt