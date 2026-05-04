"""Prompt/schema contract tests for CRE underwriting extraction."""

import sys
import types

from app.verticals.real_estate.underwriting.extraction.discrepancy import detect_discrepancies
from app.verticals.real_estate.underwriting.extraction.prompts import (
    OM_EXTRACTION_SYSTEM_PROMPT,
    RENT_ROLL_EXTRACTION_SYSTEM_PROMPT,
    T12_EXTRACTION_SYSTEM_PROMPT,
    create_phase2_om_prompt,
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


def test_om_schema_exposes_purchase_cap_rate_basis_period():
    """OM schema should let Phase 2 report whether purchase cap rate is Current/Year-1/etc."""
    from app.verticals.real_estate.underwriting.extraction.schemas import OMExtraction

    fields = OMExtraction.model_fields

    assert "market_cap_rate_purchase_basis_period" in fields
    assert fields["market_cap_rate_purchase_basis_period"].json_schema_extra == {"cite": False}


def test_phase1_prompt_names_period_semantics_for_self_storage_oms():
    from app.verticals.real_estate.underwriting.extraction.prompts import (
        PHASE1_CONDENSATION_SYSTEM_PROMPT,
    )

    prompt = PHASE1_CONDENSATION_SYSTEM_PROMPT.lower()

    assert "current | year 1 | pro forma" in prompt
    assert "actual | budget | pro forma" in prompt
    assert "current | estimated | pro forma" in prompt
    assert "separate field entry for each column" in prompt
    assert "never collapse multiple columns" in prompt


def test_phase2_prompt_requires_cap_rate_basis_period():
    from app.verticals.real_estate.underwriting.extraction.prompts import create_phase2_om_prompt

    prompt = create_phase2_om_prompt("[]").lower()

    assert "market_cap_rate_purchase_basis_period" in prompt
    assert "current cap rate" in prompt
    assert "basis period" in prompt
    assert "do not use stabilized" in prompt or "do not map stabilized" in prompt


def test_om_tool_schema_has_detection_fields_before_extraction_fields():
    """Detection fields must exist in tool schema and appear before extraction fields."""
    props = REExtractionLLMService._TOOL_SCHEMAS["om"]["properties"]
    detection_fields = [
        "detected_deal_subtype",
        "detected_current_column_label",
        "detected_year1_column_label",
        "detected_has_current_column",
        "detected_expense_format",
        "detected_income_period_label",
    ]
    for f in detection_fields:
        assert f in props, f"Missing detection field: {f}"

    # Detection fields should appear before acquisition fields in the ordered dict
    keys = list(props.keys())
    assert keys.index("detected_deal_subtype") < keys.index("purchase_price")


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


def test_extraction_prompts_omit_missing_fields_instead_of_emitting_nulls():
    prompts = [
        OM_EXTRACTION_SYSTEM_PROMPT,
        RENT_ROLL_EXTRACTION_SYSTEM_PROMPT,
        T12_EXTRACTION_SYSTEM_PROMPT,
        create_phase2_om_prompt("{}"),
        create_phase2_t12_prompt("{}"),
        create_phase2_rent_roll_prompt("{}"),
    ]

    for prompt in prompts:
        normalized = prompt.lower()
        assert "omit missing" in normalized
        assert "return null for missing" not in normalized
        assert "null for missing" not in normalized


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
    monkeypatch.setattr(settings, "re_uw_om_two_call_enabled", False)
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
    monkeypatch.setattr(settings, "re_uw_om_two_call_enabled", False)
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


def test_om_extraction_caps_verbose_notes_and_source_text(monkeypatch):
    monkeypatch.setattr(settings, "re_uw_om_two_call_enabled", False)
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


def test_om_prompt_requires_year1_fields_from_three_column_statement():
    """Prompt must use detection-first approach for dual _year1/_current fields."""
    prompt = OM_EXTRACTION_SYSTEM_PROMPT

    # Detection-first anchors must be present
    assert "detected_current_column_label" in prompt
    assert "detected_year1_column_label" in prompt
    assert "detected_has_current_column" in prompt
    assert "detected_deal_subtype" in prompt

    # Must explicitly handle no-current-column case
    assert "detected_has_current_column is false" in prompt.lower()

    # Per-sqft handling must be mentioned
    assert "per_sqft" in prompt

    # Must not fall back to hardcoded "three columns" examples
    assert "EXAMPLE A" not in prompt
    assert "EXAMPLE B" not in prompt

    # Must include concrete output shape with DO NOT OMIT annotation
    assert "DO NOT OMIT" in prompt

    # Must include column position rule for header-agnostic Year-1 identification
    assert "COLUMN POSITION RULE" in prompt


def test_om_prompt_instructs_zero_current_not_omitted():
    """Prompt must explicitly state that $0 Current values must be emitted."""
    prompt = OM_EXTRACTION_SYSTEM_PROMPT.lower()
    assert "_current=0.0" in prompt or "emit _current=0" in prompt or \
           "do not omit it" in prompt


def test_om_extraction_populates_year1_expense_fields_from_three_column_statement(monkeypatch):
    """When the LLM returns Year-1 and Current values for all five adjustable
    expense line items, the extraction service must surface them in scalars."""
    monkeypatch.setattr(settings, "re_uw_om_two_call_enabled", False)
    payload = {
        "detected_deal_subtype": "stabilized",
        "detected_current_column_label": "Current",
        "detected_year1_column_label": "Year 1",
        "detected_has_current_column": True,
        "detected_expense_format": "absolute",
        "detected_income_period_label": "T-12",
        "purchase_price": 2_500_000,
        "purchase_price_citations": ["S1:p16"],
        "purchase_price_confidence": 0.95,
        "purchase_price_source": "$2,500,000",
        # Five adjustable line items — both _year1 and _current populated
        "expense_property_tax_annual_year1": 15_346,
        "expense_property_tax_annual_year1_citations": ["S1:p16"],
        "expense_property_tax_annual_year1_confidence": 0.95,
        "expense_property_tax_annual_year1_source": "Property Taxes Year 1: $15,346",
        "expense_property_tax_annual_current": 6_139,
        "expense_property_tax_annual_current_citations": ["S1:p16"],
        "expense_property_tax_annual_current_confidence": 0.95,
        "expense_property_tax_annual_current_source": "Property Taxes Current: $6,139",
        "expense_marketing_annual_year1": 4_203,
        "expense_marketing_annual_year1_citations": ["S1:p16"],
        "expense_marketing_annual_year1_confidence": 0.9,
        "expense_marketing_annual_year1_source": "Marketing Year 1: $4,203",
        "expense_marketing_annual_current": 3_847,
        "expense_marketing_annual_current_citations": ["S1:p16"],
        "expense_marketing_annual_current_confidence": 0.9,
        "expense_marketing_annual_current_source": "Marketing Current: $3,847",
        "expense_insurance_annual_year1": 11_840,
        "expense_insurance_annual_year1_citations": ["S1:p16"],
        "expense_insurance_annual_year1_confidence": 0.9,
        "expense_insurance_annual_year1_source": "Insurance Year 1: $11,840",
        "expense_insurance_annual_current": 9_867,
        "expense_insurance_annual_current_citations": ["S1:p16"],
        "expense_insurance_annual_current_confidence": 0.9,
        "expense_insurance_annual_current_source": "Insurance Current: $9,867",
        "expense_utilities_annual_year1": 6_868,
        "expense_utilities_annual_year1_citations": ["S1:p16"],
        "expense_utilities_annual_year1_confidence": 0.85,
        "expense_utilities_annual_year1_source": "Utilities Year 1: $6,868",
        "expense_utilities_annual_current": 8_080,
        "expense_utilities_annual_current_citations": ["S1:p16"],
        "expense_utilities_annual_current_confidence": 0.85,
        "expense_utilities_annual_current_source": "Utilities Current: $8,080",
        "expense_repairs_maintenance_annual_year1": 2_102,
        "expense_repairs_maintenance_annual_year1_citations": ["S1:p16"],
        "expense_repairs_maintenance_annual_year1_confidence": 0.9,
        "expense_repairs_maintenance_annual_year1_source": "R&M Year 1: $2,102",
        "expense_repairs_maintenance_annual_current": 1_424,
        "expense_repairs_maintenance_annual_current_citations": ["S1:p16"],
        "expense_repairs_maintenance_annual_current_confidence": 0.9,
        "expense_repairs_maintenance_annual_current_source": "R&M Current: $1,424",
    }
    service = REExtractionLLMService(_FakeLLMClient([_FakeMessage(payload)]))
    extracted = service.extract_om("Operating statement with Current/Year-1/Pro Forma columns")
    scalars = extracted["scalars"]

    assert scalars["expense_property_tax_annual_year1"] == 15_346
    assert scalars["expense_property_tax_annual_current"] == 6_139
    assert scalars["expense_marketing_annual_year1"] == 4_203
    assert scalars["expense_marketing_annual_current"] == 3_847
    assert scalars["expense_insurance_annual_year1"] == 11_840
    assert scalars["expense_utilities_annual_year1"] == 6_868
    assert scalars["expense_repairs_maintenance_annual_year1"] == 2_102

    assert scalars["detected_deal_subtype"] == "stabilized"
    assert scalars["detected_current_column_label"] == "Current"
    assert scalars["detected_year1_column_label"] == "Year 1"
    assert scalars["detected_has_current_column"] is True


def test_om_extraction_handles_no_current_column(monkeypatch):
    """When detected_has_current_column=False, _current fields absent, _year1 present."""
    monkeypatch.setattr(settings, "re_uw_om_two_call_enabled", False)
    payload = {
        "detected_deal_subtype": "value_add",
        "detected_current_column_label": None,
        "detected_year1_column_label": "Year 1",
        "detected_has_current_column": False,
        "detected_expense_format": "absolute",
        "detected_income_period_label": None,
        "purchase_price": 1_800_000,
        "purchase_price_citations": ["S1:p1"],
        "purchase_price_confidence": 0.9,
        "purchase_price_source": "$1,800,000",
        "expense_property_tax_annual_year1": 13_106,
        "expense_property_tax_annual_year1_citations": ["S1:p8"],
        "expense_property_tax_annual_year1_confidence": 0.9,
        "expense_property_tax_annual_year1_source": "Property Taxes Year 1: $13,106",
    }
    service = REExtractionLLMService(_FakeLLMClient([_FakeMessage(payload)]))
    extracted = service.extract_om("No current column OM")
    scalars = extracted["scalars"]

    assert scalars["detected_has_current_column"] is False
    assert scalars["expense_property_tax_annual_year1"] == 13_106
    assert scalars.get("expense_property_tax_annual_current") is None


def test_phase1_prompt_extracts_column_structure_and_both_column_values():
    """Phase 1 must emit structure metadata and both _current/_year1 column values."""
    from app.verticals.real_estate.underwriting.extraction.prompts import (
        PHASE1_CONDENSATION_SYSTEM_PROMPT,
    )
    prompt = PHASE1_CONDENSATION_SYSTEM_PROMPT

    # Must extract column structure as a named metadata field
    assert "operating_statement_column_structure" in prompt

    # Must emit separate entries per column using _current / _year1 suffixes
    assert "_current" in prompt
    assert "_year1" in prompt

    # Must not collapse multiple columns
    assert "never collapse" in prompt.lower() or "separate field entry" in prompt.lower()

    # Must emit explicit $0 values
    assert 'value="0"' in prompt or "do not skip" in prompt.lower() or \
           "do not omit" in prompt.lower()

    # Must extract expense_format metadata
    assert "expense_format" in prompt

    # Must extract income_period_label metadata
    assert "income_period_label" in prompt


def test_phase2_om_rules_map_suffixed_fields_and_structure_metadata():
    """Phase 2 rules must map _current/_year1 suffixed fields and structure metadata."""
    from app.verticals.real_estate.underwriting.extraction.prompts import (
        create_phase2_om_prompt,
    )
    prompt = create_phase2_om_prompt("{}").lower()

    # Must reference the suffixed field naming convention from Phase 1
    assert "_current" in prompt
    assert "_year1" in prompt

    # Must reference structure metadata fields from Phase 1
    assert "operating_statement_column_structure" in prompt

    # Must fill detected_* fields
    assert "detected_current_column_label" in prompt
    assert "detected_has_current_column" in prompt

    # Must handle explicit $0
    assert "_current=0.0" in prompt or "map it as 0.0" in prompt or \
           "do not omit" in prompt


def test_om_structure_detection_prompt_exists_and_mentions_all_six_fields():
    from app.verticals.real_estate.underwriting.extraction.prompts import OM_STRUCTURE_DETECTION_PROMPT
    for field in (
        "detected_deal_subtype",
        "detected_current_column_label",
        "detected_year1_column_label",
        "detected_has_current_column",
        "detected_expense_format",
        "detected_income_period_label",
    ):
        assert field in OM_STRUCTURE_DETECTION_PROMPT, f"Missing: {field}"


def test_create_om_user_prompt_returns_list_of_blocks():
    from app.verticals.real_estate.underwriting.extraction.prompts import create_om_user_prompt
    result = create_om_user_prompt("DOC_TEXT")
    assert isinstance(result, list)
    assert any(b.get("text") == "DOC_TEXT" for b in result)
    texts = " ".join(b.get("text", "") for b in result)
    assert "DETECTED STRUCTURE" not in texts


def test_create_om_user_prompt_with_detection_context_injects_block():
    from app.verticals.real_estate.underwriting.extraction.prompts import create_om_user_prompt
    ctx = {
        "detected_deal_subtype": "value_add",
        "detected_current_column_label": "Current",
        "detected_year1_column_label": "Year-One",
        "detected_has_current_column": True,
        "detected_expense_format": "absolute",
        "detected_income_period_label": "T-12",
    }
    result = create_om_user_prompt("DOC_TEXT", detection_context=ctx)
    assert isinstance(result, list)
    texts = " ".join(b.get("text", "") for b in result)
    assert "DETECTED STRUCTURE" in texts
    assert "Year-One" in texts
    # Document block must have cache_control
    doc_block = next(b for b in result if b.get("text") == "DOC_TEXT")
    assert "cache_control" in doc_block


def test_om_extraction_prompt_no_longer_has_step1_detect_block():
    from app.verticals.real_estate.underwriting.extraction.prompts import OM_EXTRACTION_SYSTEM_PROMPT
    assert "STEP 1 — DETECT STRUCTURE" not in OM_EXTRACTION_SYSTEM_PROMPT
    assert "DETECTED STRUCTURE" in OM_EXTRACTION_SYSTEM_PROMPT
