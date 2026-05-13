import pytest
from types import SimpleNamespace

from app.repositories.template_repository import _merge_extracted_data
from app.verticals.real_estate.template_filling.llm_service import TemplateFillLLMService
from app.verticals.real_estate.template_filling.prompts.base import PromptPair
from app.verticals.real_estate.template_filling.prompts.v1 import (
    OMStructureDetectionResult,
    SchemaTableExtractionResult,
    V1PromptSet,
)
from app.verticals.real_estate.template_filling.source_map import (
    STRUCTURE_HIGH_CONFIDENCE,
    STRUCTURE_LOW_CONFIDENCE,
    normalize_om_structure_with_pdf_fields,
)
from app.verticals.real_estate.template_filling.tasks import (
    _build_narrative_pdf_field,
    _build_om_structure_artifact,
    _build_scalar_context_for_batch,
    _build_structure_confidence_summary,
    _consolidate_scalar_batches_by_context,
    _mark_auto_mapping_exception,
    _plan_schema_targets_for_structure,
    _target_status,
)


def test_structure_detection_prompt_requests_column_map_and_section_presence():
    prompt = V1PromptSet().build_detect_om_structure()

    assert prompt.response_model is OMStructureDetectionResult
    assert "column_map" in prompt.user_message
    assert "section_presence" in prompt.user_message
    assert "confidence" in prompt.user_message
    assert "citations" in prompt.user_message
    assert "evidence" in prompt.user_message


def test_structure_detection_prompt_uses_shared_threshold_constants():
    prompt = V1PromptSet().build_detect_om_structure()

    assert f"≥{STRUCTURE_HIGH_CONFIDENCE:.2f}" in prompt.user_message
    assert f"{STRUCTURE_LOW_CONFIDENCE:.2f}–" in prompt.user_message
    assert f"<{STRUCTURE_LOW_CONFIDENCE:.2f}" in prompt.user_message


def test_structure_detection_result_allows_partial_source_map_for_planner_degrade():
    parsed = {
        "column_map": {
            "current": {
                "present": True,
                "label": "CURRENT",
                "confidence": 0.95,
                "citations": ["[S1:p6]"],
            }
        },
        "section_presence": {
            "year1_operating_statement_present": {
                "present": True,
                "label": "YEAR 1",
                "confidence": 0.92,
                "citations": ["[S1:p6]"],
            }
        },
    }

    plan = _plan_schema_targets_for_structure(
        [
            {
                "id": "year1_expense",
                "sheet": "P&L",
                "value_cell": "E31",
                "fill_when": "year1_operating_statement_present",
                "requires_structure": ["column_map.year1"],
            }
        ],
        [],
        parsed,
    )

    assert plan["fields_to_extract"] == []
    assert plan["skipped_targets"][0]["skip_reason"] == "structure_key_missing"


def test_source_map_normalization_infers_sections_and_columns_from_detected_pdf_fields():
    structure = {
        "column_map": {
            "current": {"present": False, "confidence": 0.0, "citations": []},
            "year1": {"present": False, "confidence": 0.0, "citations": []},
            "pro_forma": {"present": False, "confidence": 0.0, "citations": []},
        },
        "section_presence": {},
    }
    pdf_fields = [
        {
            "source": "table_block",
            "name": "Operating Summary",
            "table_name": "Operating Summary",
            "table_columns": ["Line Item", "CURRENT", "YEAR-ONE", "PRO FORMA"],
            "table_rows": [
                ["Gross Potential Rent", "$271,200", "$285,740", "$360,741"],
                ["Total Operating Expenses", "$66,299", "$80,699", "$94,946"],
                ["Net Operating Income", "$177,453", "$202,790", "$246,813"],
            ],
            "citations": ["[S1:p6]"],
        },
        {
            "source": "table_block",
            "name": "Target Rent Analysis",
            "table_name": "Target Rent Analysis",
            "table_columns": ["Type", "# Units", "SqFt", "Current Rent"],
            "table_rows": [["5x10", "26", "50", "$75"]],
            "citations": ["[S2:p15]"],
        }
    ]

    augmented = normalize_om_structure_with_pdf_fields(structure, pdf_fields)

    sections = augmented["section_presence"]
    columns = augmented["column_map"]
    assert columns["current"]["present"] is True
    assert columns["year1"]["present"] is True
    assert columns["pro_forma"]["present"] is True
    assert sections["current_operating_statement_present"]["present"] is True
    assert sections["year1_operating_statement_present"]["present"] is True
    assert sections["pro_forma_operating_statement_present"]["present"] is True
    assert sections["unit_mix_present"]["present"] is True
    assert sections["unit_mix_present"]["citations"] == ["[S2:p15]"]

    plan = _plan_schema_targets_for_structure(
        [
            {
                "id": "year1_expense",
                "sheet": "P&L",
                "value_cell": "E31",
                "fill_when": ["year1_operating_statement_present"],
                "requires_structure": ["column_map.year1"],
            }
        ],
        [
            {
                "id": "actuals_unit_mix_storage_unit_mix",
                "sheet": "Actuals&UnitMix",
                "fill_when": ["unit_mix_present"],
                "requires_structure": [],
            }
        ],
        augmented,
    )

    assert [field["id"] for field in plan["fields_to_extract"]] == ["year1_expense"]
    assert [table["id"] for table in plan["tables_to_extract"]] == [
        "actuals_unit_mix_storage_unit_mix"
    ]
    assert plan["skipped_targets"] == []


def test_scalar_context_for_structure_scopes_to_cited_pages_before_budgeting():
    om_structure = {
        "section_presence": {
            "year1_operating_statement_present": {
                "present": True,
                "confidence": 0.95,
                "citations": ["[S1:p6]"],
            }
        },
        "column_map": {},
    }
    fields = [
        {
            "id": "page6-kv",
            "source": "key_value_pairs",
            "name": "Year 1 NOI",
            "extracted_value": "$202,790",
            "bbox": {"page": 6},
        },
        {
            "id": "page8-kv",
            "source": "key_value_pairs",
            "name": "Too far from Year 1",
            "extracted_value": "skip me",
            "bbox": {"page": 8},
        },
        {
            "id": "page30-kv",
            "source": "key_value_pairs",
            "name": "Unrelated Demographic",
            "extracted_value": "42",
            "bbox": {"page": 30},
        },
    ]
    scalar_batch = [
        {
            "id": "pnl_year1_noi",
            "source_basis": "om_operating_statement",
            "fill_when": ["year1_operating_statement_present"],
        }
    ]

    routed_fields, metadata = _build_scalar_context_for_batch(
        fields,
        om_structure,
        scalar_batch,
    )

    assert [field["id"] for field in routed_fields] == ["page6-kv"]
    assert metadata["routing_applied"] is True
    assert metadata["citation_pages"] == [6]


def test_source_map_normalization_does_not_treat_current_rent_unit_mix_as_operating_current_column():
    normalized = normalize_om_structure_with_pdf_fields(
        {"column_map": {}, "section_presence": {}},
        [
            {
                "source": "table_block",
                "table_name": "Unit Mix by Type",
                "table_columns": ["Type", "# Units", "SqFt", "Current Rent"],
                "table_rows": [["5x10", "26", "50", "$75"]],
                "citations": ["[S2:p15]"],
            }
        ],
    )

    assert normalized["section_presence"]["unit_mix_present"]["present"] is True
    assert normalized["column_map"]["current"]["present"] is False


def test_scalar_context_for_always_fields_keeps_full_pool_before_budgeting():
    fields = [
        {"id": "cover", "source": "key_value_pairs", "bbox": {"page": 1}},
        {"id": "market", "source": "key_value_pairs", "bbox": {"page": 18}},
    ]

    routed_fields, metadata = _build_scalar_context_for_batch(
        fields,
        {"section_presence": {}, "column_map": {}},
        [{"id": "property_name", "source_basis": "om_property_summary", "fill_when": ["always"]}],
    )

    assert [field["id"] for field in routed_fields] == ["cover", "market"]
    assert metadata["routing_applied"] is False


def test_scalar_batch_consolidation_merges_only_exact_context_matches():
    consolidated = _consolidate_scalar_batches_by_context(
        [
            {
                "batch_key": "operating:current",
                "fields": [{"id": "current_noi"}],
                "context": [{"id": "ctx-1"}, {"id": "ctx-2"}],
                "budget": {"citation_pages": [16]},
            },
            {
                "batch_key": "operating:pro_forma",
                "fields": [{"id": "proforma_noi"}],
                "context": [{"id": "ctx-1"}, {"id": "ctx-2"}],
                "budget": {"citation_pages": [16]},
            },
            {
                "batch_key": "market:summary",
                "fields": [{"id": "population"}],
                "context": [{"id": "ctx-3"}],
                "budget": {"citation_pages": [29]},
            },
        ]
    )

    assert len(consolidated) == 2
    merged = consolidated[0]
    assert merged["batch_keys"] == ["operating:current", "operating:pro_forma"]
    assert [field["id"] for field in merged["fields"]] == ["current_noi", "proforma_noi"]
    assert [field["id"] for field in merged["context"]] == ["ctx-1", "ctx-2"]


def test_scalar_batch_consolidation_does_not_merge_same_pages_with_different_contexts():
    consolidated = _consolidate_scalar_batches_by_context(
        [
            {
                "batch_key": "operating:current",
                "fields": [{"id": "current_noi"}],
                "context": [{"id": "ctx-1"}, {"id": "ctx-2"}],
                "budget": {"citation_pages": [16]},
            },
            {
                "batch_key": "operating:year1",
                "fields": [{"id": "year1_noi"}],
                "context": [{"id": "ctx-1"}],
                "budget": {"citation_pages": [16]},
            },
        ]
    )

    assert len(consolidated) == 2
    assert consolidated[0]["batch_keys"] == ["operating:current"]
    assert consolidated[1]["batch_keys"] == ["operating:year1"]


def test_structure_confidence_summary_collects_low_keys():
    structure = {
        "column_map": {
            "current": {"present": True, "confidence": 0.91},
            "year1": {"present": True, "confidence": 0.55},
        },
        "section_presence": {
            "unit_mix_present": {"present": True, "confidence": 0.8},
        },
    }

    summary = _build_structure_confidence_summary(structure)

    assert summary["min_confidence"] == 0.55
    assert summary["mean_confidence"] == 0.7533
    assert summary["low_confidence_keys"] == ["column_map.year1"]


def test_om_structure_artifact_normalizes_citations_for_clickable_badges():
    artifact = _build_om_structure_artifact(
        {
            "column_map": {
                "current": {
                    "present": True,
                    "label": "CURRENT",
                    "confidence": 0.95,
                    "citations": ["S219:p6"],
                }
            },
            "section_presence": {
                "rent_comps_present": {
                    "present": True,
                    "label": "Rent Comps",
                    "confidence": 0.9,
                    "citations": ["S298:p22", "[S303:p22]"],
                }
            },
        },
        "model-a",
    )

    assert artifact["effective"]["column_map"]["current"]["citations"] == ["[D219:p6]"]
    assert artifact["original"]["section_presence"]["rent_comps_present"]["citations"] == [
        "[D298:p22]",
        "[D303:p22]",
    ]


def test_narrative_pdf_field_preserves_page_number_for_cover_page_routing():
    field = _build_narrative_pdf_field(
        field_id_counter=77,
        narrative_text="Tulsa Self Storage Units and Parking",
        section_heading="Cover",
        narrative_page=1,
    )

    assert field["id"] == "narrative_block_77"
    assert field["page_number"] == 1
    assert field["citations"] == ["[S77:p1]"]


def test_pre_fill_planner_skips_missing_section_and_low_confidence_structure_key():
    fields = [
        {
            "id": "current_expense",
            "sheet": "Actuals&UnitMix",
            "value_cell": "C19",
            "fill_when": "current_operating_statement_present",
            "requires_structure": ["column_map.current"],
        },
        {
            "id": "year1_expense",
            "sheet": "P&L",
            "value_cell": "E31",
            "fill_when": "year1_operating_statement_present",
            "requires_structure": ["column_map.year1"],
        },
        {
            "id": "property_name",
            "sheet": "DASHBOARD",
            "value_cell": "C3",
            "fill_when": "always",
        },
    ]
    structure = {
        "column_map": {
            "current": {"present": True, "confidence": 0.92},
            "year1": {"present": True, "confidence": 0.52},
        },
        "section_presence": {
            "current_operating_statement_present": {"present": False, "confidence": 0.95},
            "year1_operating_statement_present": {"present": True, "confidence": 0.95},
        },
    }

    plan = _plan_schema_targets_for_structure(fields, [], structure)

    assert [f["id"] for f in plan["fields_to_extract"]] == ["property_name"]
    status_by_id = {item["target_id"]: item for item in plan["skipped_targets"]}
    assert status_by_id["current_expense"]["skip_reason"] == "missing_section"
    assert status_by_id["year1_expense"]["skip_reason"] == "low_structure_confidence"


def test_pre_fill_planner_marks_mid_confidence_for_review_without_skipping():
    fields = [
        {
            "id": "year1_expense",
            "sheet": "P&L",
            "value_cell": "E31",
            "fill_when": "year1_operating_statement_present",
            "requires_structure": ["column_map.year1"],
        }
    ]
    structure = {
        "column_map": {
            "year1": {"present": True, "confidence": 0.72},
        },
        "section_presence": {
            "year1_operating_statement_present": {"present": True, "confidence": 0.95},
        },
    }

    plan = _plan_schema_targets_for_structure(fields, [], structure)

    assert [f["id"] for f in plan["fields_to_extract"]] == ["year1_expense"]
    assert plan["review_required_targets"] == [
        {
            "excel_sheet": "P&L",
            "excel_cell": "E31",
            "target_id": "year1_expense",
            "target_type": "field",
            "review_reason": "mid_structure_confidence",
            "structure_key": "column_map.year1",
            "confidence": 0.72,
        }
    ]


def test_pre_fill_planner_treats_multiple_fill_when_values_as_fallbacks():
    fields = [
        {
            "id": "actuals_taxes",
            "sheet": "Actuals&UnitMix",
            "value_cell": "C19",
            "fill_when": ["t12_present", "current_operating_statement_present"],
        }
    ]
    structure = {
        "section_presence": {
            "t12_present": {"present": False, "confidence": 0.95},
            "current_operating_statement_present": {"present": True, "confidence": 0.95},
        }
    }

    plan = _plan_schema_targets_for_structure(fields, [], structure)

    assert [f["id"] for f in plan["fields_to_extract"]] == ["actuals_taxes"]
    assert plan["skipped_targets"] == []


def test_pre_fill_planner_treats_multiple_structure_keys_as_fallbacks():
    fields = [
        {
            "id": "forward_expense",
            "sheet": "P&L",
            "value_cell": "E31",
            "fill_when": ["year1_operating_statement_present", "pro_forma_operating_statement_present"],
            "requires_structure": ["column_map.year1", "column_map.pro_forma"],
        }
    ]
    structure = {
        "column_map": {
            "year1": {"present": False, "confidence": 0.95},
            "pro_forma": {"present": True, "confidence": 0.9},
        },
        "section_presence": {
            "year1_operating_statement_present": {"present": False, "confidence": 0.95},
            "pro_forma_operating_statement_present": {"present": True, "confidence": 0.95},
        },
    }

    plan = _plan_schema_targets_for_structure(fields, [], structure)

    assert [f["id"] for f in plan["fields_to_extract"]] == ["forward_expense"]
    assert plan["skipped_targets"] == []


def test_pre_fill_planner_skips_missing_structure_key():
    fields = [
        {
            "id": "year1_expense",
            "sheet": "P&L",
            "value_cell": "E31",
            "fill_when": "year1_operating_statement_present",
            "requires_structure": ["column_map.year1"],
        }
    ]
    structure = {
        "column_map": {},
        "section_presence": {
            "year1_operating_statement_present": {"present": True, "confidence": 0.95},
        },
    }

    plan = _plan_schema_targets_for_structure(fields, [], structure)

    assert plan["fields_to_extract"] == []
    assert plan["skipped_targets"][0]["skip_reason"] == "structure_key_missing"


def test_target_status_rejects_unknown_skip_reason_and_prevents_shadowing():
    target = {"id": "field_a", "sheet": "Sheet1", "value_cell": "A1"}

    status = _target_status(
        target,
        "field",
        "missing_section",
        target_id="shadow",
        excel_cell="Z9",
        structure_key="section_presence.t12_present",
    )

    assert status["target_id"] == "field_a"
    assert status["excel_cell"] == "A1"
    assert status["structure_key"] == "section_presence.t12_present"

    with pytest.raises(ValueError, match="Unknown skip reason"):
        _target_status(target, "field", "bad_reason")


def test_extract_schema_field_prompt_uses_trimmed_source_map_context():
    full_structure = {
        "column_map": {
            "year1": {
                "present": True,
                "label": "YEAR 1",
                "confidence": 0.92,
                "citations": ["[S1:p6]"],
                "evidence": "YEAR 1 appears in the operating table",
            }
        },
        "section_presence": {
            "year1_operating_statement_present": {
                "present": True,
                "label": "Financial Summary",
                "confidence": 0.9,
                "citations": ["[S2:p7]"],
                "evidence": "Financial Summary table",
            }
        },
    }
    prompt = V1PromptSet().build_extract_schema_fields(
        "[]",
        [{"id": "pnl_year1_personnel_expense", "sheet": "P&L", "value_cell": "E32"}],
        om_structure=full_structure,
    )

    # Source Map goes in user_message so system_prompt stays static (cacheable).
    assert '"label": "YEAR 1"' in prompt.user_message
    assert '"confidence": 0.92' in prompt.user_message
    # trim_om_structure_for_prompt strips citations/evidence — only labels/confidence included.
    assert "[S1:p6]" not in prompt.user_message
    assert '"evidence"' not in prompt.user_message
    assert "YEAR 1" not in prompt.system_prompt


def test_extract_table_prompt_uses_trimmed_source_map_context():
    full_structure = {
        "column_map": {
            "current": {
                "present": True,
                "label": "CURRENT",
                "confidence": 0.93,
                "citations": ["[S1:p16]"],
                "evidence": "CURRENT operating column",
            }
        },
        "section_presence": {
            "unit_mix_present": {
                "present": True,
                "label": "Unit Mix",
                "confidence": 0.96,
                "citations": ["[S2:p15]"],
                "evidence": "Unit mix table",
            }
        },
    }

    prompt = V1PromptSet().build_extract_table_values_rag(
        "[]",
        [{"table_id": "actuals_unit_mix_storage_unit_mix"}],
        "headers",
        om_structure=full_structure,
    )

    # Source Map goes in user_message so system_prompt stays static (cacheable).
    assert '"label": "CURRENT"' in prompt.user_message
    assert '"confidence": 0.93' in prompt.user_message
    assert "[S1:p16]" not in prompt.user_message
    assert '"evidence"' not in prompt.user_message
    assert "CURRENT" not in prompt.system_prompt


def test_shared_azure_context_block_is_stable_across_source_map_and_scalar_calls():
    prompt_set = V1PromptSet()
    context_json = '[{"id":"table_1","source":"table_block"}]'

    source_map_context = prompt_set.build_azure_di_context_block(context_json)
    scalar_context = prompt_set.build_azure_di_context_block(context_json)

    assert source_map_context == scalar_context
    assert context_json in source_map_context


@pytest.mark.asyncio
async def test_table_extraction_service_passes_om_structure_to_prompt_builder():
    captured = {}

    class PromptSpy:
        version = "v1"

        def build_extract_table_values_rag(
            self,
            context_json,
            table_requests,
            header_equivalents,
            om_structure=None,
        ):
            captured["om_structure"] = om_structure
            return PromptPair(
                system_prompt="system",
                user_message="user",
                response_model=SchemaTableExtractionResult,
            )

        def build_azure_di_context_block(self, context_json):
            return f"context: {context_json}"

    class MessageSpy:
        def create(self, **_kwargs):
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        text='{"results":[],"total_tables":0,"total_rows":0}'
                    )
                ],
                usage=SimpleNamespace(
                    input_tokens=0,
                    output_tokens=0,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=0,
                ),
            )

    service = TemplateFillLLMService.__new__(TemplateFillLLMService)
    service.prompts = PromptSpy()
    service.client = SimpleNamespace(messages=MessageSpy())
    service.model = "test-model"
    service.max_tokens = 1024
    service.capture_io_log = False
    service._io_log_repo = None
    service._record_llm_metrics = lambda *_args, **_kwargs: None

    structure = {"column_map": {"current": {"present": True, "confidence": 0.9}}}
    await service.extract_schema_table_values_rag_batch(
        [
            {
                "id": "table_a",
                "sheet": "Actuals&UnitMix",
                "data_start_row": 5,
                "data_end_row": 5,
                "columns": [{"excel_column": "G", "header": "Type"}],
            }
        ],
        [{"source": "table_block", "type": "table", "table_rows": []}],
        om_structure=structure,
    )

    assert captured["om_structure"] is structure


def test_table_context_excludes_targeted_schema_virtual_fields():
    service = TemplateFillLLMService.__new__(TemplateFillLLMService)

    context = service._build_table_context_from_pdf_fields(
        [
            {"source": "table_block", "name": "Unit Mix", "table_rows": [["5x10"]]},
            {
                "source": "targeted_schema",
                "name": "pnl_year1_personnel_expense",
                "extracted_value": "$17,250",
            },
        ]
    )

    assert len(context) == 1
    assert "Unit Mix" in context[0]["text"]


def test_auto_mapping_exception_uses_mark_error_for_sse_termination():
    class RepoSpy:
        def __init__(self):
            self.updated = None

        def update_fill_run(self, fill_run_id, **kwargs):
            self.updated = {"fill_run_id": fill_run_id, **kwargs}

    class TrackerSpy:
        def __init__(self):
            self.error = None

        def mark_error(self, **kwargs):
            self.error = kwargs

    repo = RepoSpy()
    tracker = TrackerSpy()

    _mark_auto_mapping_exception(repo, tracker, "run-1", RuntimeError("source map failed"))

    assert repo.updated["status"] == "failed"
    assert repo.updated["error_stage"] == "auto_mapping"
    assert tracker.error["error_stage"] == "auto_mapping"
    assert tracker.error["error_message"] == "source map failed"


def test_om_structure_artifact_keeps_original_and_effective_independent():
    detected = {
        "column_map": {
            "year1": {"present": True, "label": "YEAR 1", "confidence": 0.91}
        },
        "section_presence": {},
    }

    artifact = _build_om_structure_artifact(detected, "model-a")
    artifact["effective"]["column_map"]["year1"]["label"] = "Edited"

    assert artifact["original"]["column_map"]["year1"]["label"] == "YEAR 1"
    assert artifact["effective"]["column_map"]["year1"]["label"] == "Edited"


def test_merge_extracted_data_preserves_existing_values_and_adds_source_map():
    merged = _merge_extracted_data(
        {
            "llm_extracted": {"field_a": {"value": "A"}},
            "manual_edits": {"Sheet1": {"A1": {"value": "manual"}}},
        },
        {"om_structure": {"effective": {"column_map": {}}}},
    )

    assert merged["llm_extracted"]["field_a"]["value"] == "A"
    assert merged["manual_edits"]["Sheet1"]["A1"]["value"] == "manual"
    assert merged["om_structure"]["effective"] == {"column_map": {}}
