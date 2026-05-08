import pytest

from app.repositories.template_repository import _merge_extracted_data
from app.verticals.real_estate.template_filling.prompts.v1 import (
    OMStructureDetectionResult,
    V1PromptSet,
)
from app.verticals.real_estate.template_filling.source_map import (
    STRUCTURE_HIGH_CONFIDENCE,
    STRUCTURE_LOW_CONFIDENCE,
)
from app.verticals.real_estate.template_filling.tasks import (
    _build_om_structure_artifact,
    _build_structure_confidence_summary,
    _plan_schema_targets_for_structure,
    _target_status,
)


def test_structure_detection_prompt_requests_column_map_and_section_presence():
    prompt = V1PromptSet().build_detect_om_structure(
        '[{"id":"table_1","source":"table_block","text":"CURRENT YEAR 1 PRO FORMA"}]'
    )

    assert prompt.response_model is OMStructureDetectionResult
    assert "column_map" in prompt.user_message
    assert "section_presence" in prompt.user_message
    assert "confidence" in prompt.user_message
    assert "citations" in prompt.user_message
    assert "evidence" in prompt.user_message


def test_structure_detection_prompt_uses_shared_threshold_constants():
    prompt = V1PromptSet().build_detect_om_structure("[]")

    assert f">={STRUCTURE_HIGH_CONFIDENCE:.2f}" in prompt.user_message
    assert f"{STRUCTURE_LOW_CONFIDENCE:.2f}-" in prompt.user_message
    assert f"<{STRUCTURE_LOW_CONFIDENCE:.2f}" in prompt.user_message


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

    assert '"label": "YEAR 1"' in prompt.system_prompt
    assert '"confidence": 0.92' in prompt.system_prompt
    assert "citations" not in prompt.system_prompt
    assert "evidence" not in prompt.system_prompt
    assert "[S1:p6]" not in prompt.system_prompt


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
