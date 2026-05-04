"""Unit tests for the two-call OM extraction flow."""
import sys
import types

# Stub out heavy dependencies before importing llm_service
llm_client_module = types.ModuleType("app.services.llm_client")
llm_client_module.LLMClient = type("LLMClient", (), {})
sys.modules.setdefault("app.services.llm_client", llm_client_module)

metrics_module = types.ModuleType("app.utils.metrics")
for _metric_name in (
    "LLM_TOKEN_USAGE",
    "LLM_CACHE_HITS",
    "LLM_CACHE_MISSES",
    "LLM_REQUESTS_TOTAL",
    "LLM_COST_USD",
):
    setattr(metrics_module, _metric_name, object())
sys.modules.setdefault("app.utils.metrics", metrics_module)

import pytest
from unittest.mock import MagicMock, patch

from app.verticals.real_estate.underwriting.extraction.llm_service import (
    REExtractionLLMService,
    _OM_DETECTION_FIELD_NAMES,
)


def _make_tool_block(fields: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.input = fields
    return block


def _make_message(fields: dict, input_tokens=100, output_tokens=50):
    msg = MagicMock()
    msg.content = [_make_tool_block(fields)]
    msg.stop_reason = "end_turn"
    msg.usage = MagicMock(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return msg


def _make_service():
    llm_client = MagicMock()
    llm_client.model = "claude-haiku-4-5-20251001"
    llm_client.max_tokens = 8192
    svc = REExtractionLLMService(llm_client)
    svc.client = MagicMock()
    return svc


def test_detect_om_structure_returns_six_fields_on_success():
    svc = _make_service()
    raw = {
        "detected_deal_subtype": "stabilized",
        "detected_current_column_label": "Current",
        "detected_year1_column_label": "Year 1",
        "detected_has_current_column": True,
        "detected_expense_format": "absolute",
        "detected_income_period_label": "T-12",
        "extra_hallucinated": "should_be_stripped",
    }
    svc.client.messages.create.return_value = _make_message(raw)

    result = svc._detect_om_structure("doc text")

    assert result is not None
    assert set(result.keys()) == set(_OM_DETECTION_FIELD_NAMES)
    assert "extra_hallucinated" not in result
    assert result["detected_year1_column_label"] == "Year 1"


def test_detect_om_structure_returns_none_when_no_tool_block():
    svc = _make_service()
    msg = MagicMock()
    msg.content = []
    msg.usage = MagicMock(
        input_tokens=50,
        output_tokens=0,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    svc.client.messages.create.return_value = msg

    assert svc._detect_om_structure("doc text") is None


def test_detect_om_structure_returns_none_on_exception():
    svc = _make_service()
    svc.client.messages.create.side_effect = RuntimeError("timeout")

    assert svc._detect_om_structure("doc text") is None


@patch("app.verticals.real_estate.underwriting.extraction.llm_service.settings")
def test_extract_om_two_calls_detection_then_extraction(mock_settings):
    mock_settings.re_uw_om_two_call_enabled = True
    mock_settings.re_uw_om_initial_output_max_tokens = 16000
    mock_settings.re_uw_om_retry_output_max_tokens = 32000

    svc = _make_service()
    detection_fields = {
        "detected_deal_subtype": "value_add",
        "detected_current_column_label": "Current",
        "detected_year1_column_label": "Year-One",
        "detected_has_current_column": True,
        "detected_expense_format": "absolute",
        "detected_income_period_label": "T-12",
    }
    extraction_fields = {
        **detection_fields,
        "purchase_price": 2500000.0,
        "expense_property_tax_annual_year1": 15346.0,
    }
    svc.client.messages.create.side_effect = [
        _make_message(detection_fields),
        _make_message(extraction_fields),
    ]

    result = svc.extract_om("doc text")

    assert svc.client.messages.create.call_count == 2
    assert result["scalars"]["detected_year1_column_label"] == "Year-One"

    # Call 2 user message must contain DETECTED STRUCTURE
    call2 = svc.client.messages.create.call_args_list[1]
    content = call2[1]["messages"][0]["content"]
    # content is a list of blocks
    all_text = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    assert "DETECTED STRUCTURE" in all_text
    assert "Year-One" in all_text


@patch("app.verticals.real_estate.underwriting.extraction.llm_service.settings")
def test_extract_om_falls_back_when_detection_fails(mock_settings):
    mock_settings.re_uw_om_two_call_enabled = True
    mock_settings.re_uw_om_initial_output_max_tokens = 16000
    mock_settings.re_uw_om_retry_output_max_tokens = 32000

    svc = _make_service()
    svc.client.messages.create.side_effect = [
        RuntimeError("Call 1 failed"),
        _make_message({"purchase_price": 3000000.0}),
    ]

    result = svc.extract_om("doc text")

    assert svc.client.messages.create.call_count == 2
    # Fallback: no DETECTED STRUCTURE in Call 2 user content
    call2 = svc.client.messages.create.call_args_list[1]
    content = call2[1]["messages"][0]["content"]
    all_text = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    assert "DETECTED STRUCTURE" not in all_text


@patch("app.verticals.real_estate.underwriting.extraction.llm_service.settings")
def test_extract_om_early_exit_for_unsupported(mock_settings):
    mock_settings.re_uw_om_two_call_enabled = True

    svc = _make_service()
    svc.client.messages.create.return_value = _make_message({
        "detected_deal_subtype": "unsupported",
        "detected_current_column_label": None,
        "detected_year1_column_label": None,
        "detected_has_current_column": False,
        "detected_expense_format": None,
        "detected_income_period_label": None,
    })

    result = svc.extract_om("doc text")

    assert svc.client.messages.create.call_count == 1
    assert result["scalars"]["detected_deal_subtype"] == "unsupported"
    assert result["field_citations"] == {}


@patch("app.verticals.real_estate.underwriting.extraction.llm_service.settings")
def test_extract_om_single_call_when_flag_disabled(mock_settings):
    mock_settings.re_uw_om_two_call_enabled = False
    mock_settings.re_uw_om_initial_output_max_tokens = 16000
    mock_settings.re_uw_om_retry_output_max_tokens = 32000

    svc = _make_service()
    svc.client.messages.create.return_value = _make_message({"purchase_price": 1000000.0})

    svc.extract_om("doc text")

    assert svc.client.messages.create.call_count == 1
    call1 = svc.client.messages.create.call_args_list[0]
    content = call1[1]["messages"][0]["content"]
    all_text = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    assert "DETECTED STRUCTURE" not in all_text
