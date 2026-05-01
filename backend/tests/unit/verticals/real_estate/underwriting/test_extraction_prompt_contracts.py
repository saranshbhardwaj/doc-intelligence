"""Prompt/schema contract tests for CRE underwriting extraction."""

import sys
import types

from app.verticals.real_estate.underwriting.extraction.discrepancy import detect_discrepancies
from app.verticals.real_estate.underwriting.extraction.prompts import (
    RENT_ROLL_EXTRACTION_SYSTEM_PROMPT,
    T12_EXTRACTION_SYSTEM_PROMPT,
    create_phase2_rent_roll_prompt,
    create_phase2_t12_prompt,
)

llm_client_module = types.ModuleType("app.services.llm_client")
llm_client_module.LLMClient = type("LLMClient", (), {})
sys.modules.setdefault("app.services.llm_client", llm_client_module)

metrics_module = types.ModuleType("app.utils.metrics")
for metric_name in (
    "LLM_TOKEN_USAGE",
    "LLM_CACHE_HITS",
    "LLM_CACHE_MISSES",
    "LLM_REQUESTS_TOTAL",
    "LLM_COST_USD",
):
    setattr(metrics_module, metric_name, object())
sys.modules.setdefault("app.utils.metrics", metrics_module)

from app.verticals.real_estate.underwriting.extraction.llm_service import REExtractionLLMService  # noqa: E402
from app.config import settings  # noqa: E402


class _FakeUsage:
    input_tokens = 10
    output_tokens = 5
    cache_creation_input_tokens = 0
    cache_read_input_tokens = 0


class _FakeToolBlock:
    type = "tool_use"

    def __init__(self, payload):
        self.input = payload


class _FakeMessage:
    def __init__(self, payload, stop_reason="end_turn"):
        self.content = [_FakeToolBlock(payload)]
        self.stop_reason = stop_reason
        self.usage = _FakeUsage()


class _FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.max_tokens_seen = []

    def create(self, **kwargs):
        self.max_tokens_seen.append(kwargs["max_tokens"])
        return self.responses.pop(0)


class _FakeLLMClient:
    def __init__(self, responses):
        self.client = type("Client", (), {"messages": _FakeMessages(responses)})()
        self.model = "fake-model"
        self.max_tokens = 50_000


def test_rent_roll_prompt_uses_schema_lease_expiration_field():
    prompt = RENT_ROLL_EXTRACTION_SYSTEM_PROMPT

    assert "lease_expiration" in prompt
    assert "lease_end" not in prompt


def test_rent_roll_tool_schema_accepts_unit_mix_classification():
    unit_mix_props = (
        REExtractionLLMService._TOOL_SCHEMAS["rent_roll"]["properties"]["unit_mix"]["items"]["properties"]
    )

    assert unit_mix_props["climate_type"]["description"] == '"CC" | "NC" | "UNKNOWN"'
    assert unit_mix_props["unit_category"]["description"] == (
        '"storage" | "parking" | "residential" | "office" | "other"'
    )


def test_t12_prompt_keeps_t6_values_on_source_period_basis():
    prompt = T12_EXTRACTION_SYSTEM_PROMPT.lower()

    assert "return totals for the source statement period" in prompt
    assert "do not annualize t-6" in prompt
    assert "the merger annualizes" in prompt


def test_phase2_prompts_include_doc_specific_rules():
    t12_prompt = create_phase2_t12_prompt("{}").lower()
    rent_roll_prompt = create_phase2_rent_roll_prompt("{}").lower()

    assert "t-12 / t-6 mapping rules" in t12_prompt
    assert "source-period totals" in t12_prompt
    assert "rent roll mapping rules" in rent_roll_prompt
    assert "lease_expiration" in rent_roll_prompt
    assert "unit category" in rent_roll_prompt


def test_discrepancy_includes_model_used_and_preferred_source_reason():
    discrepancies = detect_discrepancies(
        {"occupancy_pct": 0.95},
        {"summary": {"occupancy_pct": 0.86}},
        {},
        model_inputs={"operational": {"vacancy_credit_loss_pct": 0.14}},
    )

    assert len(discrepancies) == 1
    assert discrepancies[0]["model_used"] == 0.86
    assert discrepancies[0]["preferred_source"] == "rent_roll"
    assert "preferred" in discrepancies[0]["reason"]


def test_om_extraction_uses_initial_output_token_cap(monkeypatch):
    monkeypatch.setattr(settings, "re_uw_om_initial_output_max_tokens", 16_000)
    payload = {
        "purchase_price": 2_500_000,
        "purchase_price_citations": ["S1:p1"],
        "purchase_price_confidence": 0.9,
        "purchase_price_source": "$2,500,000 asking price",
    }
    fake_client = _FakeLLMClient([_FakeMessage(payload)])
    service = REExtractionLLMService(fake_client)

    service.extract_om("Purchase price: $2,500,000")

    assert fake_client.client.messages.max_tokens_seen == [16_000]


def test_om_extraction_retries_with_larger_cap_when_truncated(monkeypatch):
    monkeypatch.setattr(settings, "re_uw_om_initial_output_max_tokens", 16_000)
    monkeypatch.setattr(settings, "re_uw_om_retry_output_max_tokens", 32_000)
    payload = {
        "purchase_price": 2_500_000,
        "purchase_price_citations": ["S1:p1"],
        "purchase_price_confidence": 0.9,
        "purchase_price_source": "$2,500,000 asking price",
    }
    fake_client = _FakeLLMClient([
        _FakeMessage(payload, stop_reason="max_tokens"),
        _FakeMessage(payload),
    ])
    service = REExtractionLLMService(fake_client)

    service.extract_om("Purchase price: $2,500,000")

    assert fake_client.client.messages.max_tokens_seen == [16_000, 32_000]


def test_om_extraction_caps_verbose_notes_and_source_text():
    long_note = "A" * 200
    long_source = "Purchase price source text that is much longer than forty characters"
    payload = {
        "purchase_price": 2_500_000,
        "purchase_price_citations": ["S1:p1"],
        "purchase_price_confidence": 0.9,
        "purchase_price_source": long_source,
        "value_add_notes": "B" * 250,
        "rent_comps": [
            {
                "facility": "Comp A",
                "size": "10 x 10",
                "asking_rent": 99,
                "rent_per_sqft": 0.99,
                "distance_mi": 1.2,
                "notes": long_note,
            }
        ],
    }
    service = REExtractionLLMService(_FakeLLMClient([_FakeMessage(payload)]))

    extracted = service.extract_om("Purchase price: $2,500,000")

    assert len(extracted["field_citations"]["purchase_price"]["source_text"]) <= 100
    assert len(extracted["scalars"]["value_add_notes"]) <= 200
    assert len(extracted["scalars"]["rent_comps"][0]["notes"]) <= 120
