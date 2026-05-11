"""Tests for Source Map detection hardening."""

import asyncio
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.verticals.real_estate.template_filling.prompts.v1 import (
    OMColumnMap,
    OMSectionPresence,
    OMStructureDetectionResult,
    OMStructureKey,
)
from app.verticals.real_estate.template_filling.tasks import (
    _plan_schema_targets_for_structure,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _key(present: bool, confidence: float = 0.95) -> Dict[str, Any]:
    return {"present": present, "label": None, "confidence": confidence, "citations": [], "evidence": None}


def _full_structure(
    *,
    section_overrides: Dict[str, bool] | None = None,
    column_overrides: Dict[str, bool] | None = None,
) -> Dict[str, Any]:
    """Build a complete 13-key structure dict for planner tests."""
    section_defaults = {
        "current_operating_statement_present": True,
        "year1_operating_statement_present": True,
        "pro_forma_operating_statement_present": True,
        "t12_present": False,
        "unit_mix_present": True,
        "rent_roll_present": False,
        "rent_comps_present": True,
        "market_summary_present": True,
    }
    column_defaults = {
        "current": True,
        "t12": False,
        "year1": True,
        "pro_forma": True,
        "stabilized": False,
    }
    if section_overrides:
        section_defaults.update(section_overrides)
    if column_overrides:
        column_defaults.update(column_overrides)
    return {
        "section_presence": {k: _key(v) for k, v in section_defaults.items()},
        "column_map": {k: _key(v) for k, v in column_defaults.items()},
    }


# ---------------------------------------------------------------------------
# Pydantic schema strictness
# ---------------------------------------------------------------------------

class TestOMStructureKeyRequired:
    def test_rejects_missing_present(self):
        with pytest.raises(ValidationError):
            OMStructureKey(confidence=0.9, citations=[])

    def test_rejects_missing_confidence(self):
        with pytest.raises(ValidationError):
            OMStructureKey(present=True, citations=[])

    def test_accepts_valid(self):
        key = OMStructureKey(present=True, confidence=0.9)
        assert key.present is True


class TestOMColumnMapRequired:
    def test_rejects_partial_output(self):
        """column_map must have all five keys — omitting any raises ValidationError."""
        with pytest.raises(ValidationError):
            OMColumnMap(
                current=OMStructureKey(present=True, confidence=0.9),
                # missing t12, year1, pro_forma, stabilized
            )

    def test_accepts_complete(self):
        key = OMStructureKey(present=True, confidence=0.9)
        cm = OMColumnMap(current=key, t12=key, year1=key, pro_forma=key, stabilized=key)
        assert cm.current.present is True


class TestOMSectionPresenceRequired:
    def test_rejects_partial_output(self):
        """section_presence must have all eight keys — omitting any raises ValidationError."""
        with pytest.raises(ValidationError):
            OMSectionPresence(
                current_operating_statement_present=OMStructureKey(present=True, confidence=0.9),
                # missing 7 keys
            )

    def test_accepts_complete(self):
        false_key = OMStructureKey(present=False, confidence=0.0)
        true_key = OMStructureKey(present=True, confidence=0.9)
        sp = OMSectionPresence(
            current_operating_statement_present=true_key,
            year1_operating_statement_present=true_key,
            pro_forma_operating_statement_present=true_key,
            t12_present=false_key,
            unit_mix_present=true_key,
            rent_roll_present=false_key,
            rent_comps_present=true_key,
            market_summary_present=true_key,
        )
        assert sp.unit_mix_present.present is True
        assert sp.t12_present.present is False


class TestOMStructureDetectionResultRequired:
    def test_rejects_missing_unit_mix_present(self):
        """Tool response missing unit_mix_present must fail Pydantic validation."""
        raw = {
            "column_map": {k: {"present": True, "confidence": 0.9} for k in ("current", "t12", "year1", "pro_forma", "stabilized")},
            "section_presence": {
                "current_operating_statement_present": {"present": True, "confidence": 0.9},
                "year1_operating_statement_present": {"present": True, "confidence": 0.9},
                "pro_forma_operating_statement_present": {"present": True, "confidence": 0.9},
                "t12_present": {"present": False, "confidence": 0.0},
                # unit_mix_present deliberately missing
                "rent_roll_present": {"present": False, "confidence": 0.0},
                "rent_comps_present": {"present": True, "confidence": 0.9},
                "market_summary_present": {"present": True, "confidence": 0.9},
            },
        }
        with pytest.raises(ValidationError):
            OMStructureDetectionResult.model_validate(raw)


# ---------------------------------------------------------------------------
# Prompt content
# ---------------------------------------------------------------------------

class TestPromptContent:
    def _get_user_message(self) -> str:
        from app.verticals.real_estate.template_filling.prompts import get_prompt_set
        prompts = get_prompt_set()
        pair = prompts.build_detect_om_structure()
        return pair.user_message

    def test_lists_all_five_column_keys(self):
        msg = self._get_user_message()
        for key in ("current", "t12", "year1", "pro_forma", "stabilized"):
            assert key in msg, f"column key '{key}' missing from prompt"

    def test_lists_all_eight_section_keys(self):
        msg = self._get_user_message()
        for key in (
            "current_operating_statement_present",
            "year1_operating_statement_present",
            "pro_forma_operating_statement_present",
            "t12_present",
            "unit_mix_present",
            "rent_roll_present",
            "rent_comps_present",
            "market_summary_present",
        ):
            assert key in msg, f"section key '{key}' missing from prompt"

    def test_toc_rule_present(self):
        msg = self._get_user_message()
        assert "table of contents" in msg.lower() or "TOC" in msg


# ---------------------------------------------------------------------------
# Structural inventory builder
# ---------------------------------------------------------------------------

class TestStructuralInventory:
    def _make_service(self):
        from unittest.mock import patch
        with patch("app.verticals.real_estate.template_filling.llm_service.Anthropic"):
            from app.verticals.real_estate.template_filling.llm_service import TemplateFillLLMService
            svc = TemplateFillLLMService.__new__(TemplateFillLLMService)
            svc.prompts = MagicMock()
            return svc

    def test_includes_all_table_blocks(self):
        from app.verticals.real_estate.template_filling.llm_service import TemplateFillLLMService
        svc = self._make_service()

        pdf_fields = [
            {
                "source": "table_block",
                "page_number": 15,
                "table_name": "UNIT MIX OVERVIEW",
                "table_columns": ["# Units", "SqFt", "Rent"],
                "table_rows": [{"a": "26", "b": "50", "c": "$75"}],
                "citations": ["[S3:p15]"],
            },
            {
                "source": "table_block",
                "page_number": 6,
                "table_name": None,
                "table_columns": ["blank", "CURRENT", "YEAR-ONE", "PRO FORMA"],
                "table_rows": [{"a": "Cap Rate", "b": "7.10%", "c": "8.11%", "d": "9.87%"}],
                "citations": ["[S2:p6]"],
            },
        ]
        inventory = svc._build_structural_inventory(pdf_fields)
        assert "T1" in inventory
        assert "T2" in inventory
        assert "UNIT MIX OVERVIEW" in inventory
        assert "# Units" in inventory
        assert "[S3:p15]" in inventory
        assert "CURRENT" in inventory

    def test_includes_kv_pairs(self):
        svc = self._make_service()
        pdf_fields = [
            {
                "source": "key_value_pairs",
                "name": "Total Units",
                "extracted_value": "205",
                "bbox": {"page": 10},
                "citations": [],
            }
        ]
        inventory = svc._build_structural_inventory(pdf_fields)
        assert "Total Units" in inventory
        assert "205" in inventory

    def test_includes_narrative_headings(self):
        svc = self._make_service()
        pdf_fields = [
            {
                "source": "narrative_block",
                "page_number": 9,
                "section": "PROPERTY DETAILS",
                "full_text": "",
                "citations": [],
            }
        ]
        inventory = svc._build_structural_inventory(pdf_fields)
        assert "PROPERTY DETAILS" in inventory


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

class TestRetryLogic:
    def _make_service(self):
        with patch("app.verticals.real_estate.template_filling.llm_service.Anthropic"):
            from app.verticals.real_estate.template_filling.llm_service import TemplateFillLLMService
            svc = TemplateFillLLMService.__new__(TemplateFillLLMService)
            svc.model = "test-model"
            svc.max_tokens = 4096
            svc.capture_io_log = False
            svc._io_log_repo = None
            svc.fill_run_id = "test-run"
            from app.verticals.real_estate.template_filling.prompts import get_prompt_set
            svc.prompts = get_prompt_set()
            return svc

    def _complete_raw(self) -> Dict[str, Any]:
        key = {"present": True, "confidence": 0.9}
        false_key = {"present": False, "confidence": 0.0}
        return {
            "column_map": {k: key for k in ("current", "t12", "year1", "pro_forma", "stabilized")},
            "section_presence": {
                "current_operating_statement_present": key,
                "year1_operating_statement_present": key,
                "pro_forma_operating_statement_present": key,
                "t12_present": false_key,
                "unit_mix_present": key,
                "rent_roll_present": false_key,
                "rent_comps_present": key,
                "market_summary_present": key,
            },
        }

    def _partial_raw(self) -> Dict[str, Any]:
        raw = self._complete_raw()
        del raw["section_presence"]["unit_mix_present"]
        return raw

    def _make_message(self, raw: Dict[str, Any]):
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.input = raw
        msg = MagicMock()
        msg.content = [tool_block]
        msg.usage = MagicMock(
            input_tokens=100, output_tokens=50,
            cache_creation_input_tokens=0, cache_read_input_tokens=0,
        )
        return msg

    def test_retry_on_pydantic_failure(self):
        svc = self._make_service()
        partial_msg = self._make_message(self._partial_raw())
        complete_msg = self._make_message(self._complete_raw())
        call_count = 0

        async def fake_create(**kwargs):
            nonlocal call_count
            call_count += 1
            return partial_msg if call_count == 1 else complete_msg

        pdf_fields = [{"source": "table_block", "page_number": 1, "table_name": "T", "table_columns": [], "table_rows": [], "citations": []}]
        with patch.object(svc, "_record_llm_metrics"):
            with patch("asyncio.to_thread", side_effect=lambda fn, **kw: asyncio.coroutine(lambda: fn(**kw))()):
                pass

        # Use direct asyncio patching
        import asyncio as _asyncio

        async def run():
            with patch("app.verticals.real_estate.template_filling.llm_service.asyncio.to_thread", new=AsyncMock(side_effect=[partial_msg, complete_msg])):
                with patch.object(svc, "_record_llm_metrics"):
                    result = await svc.detect_om_structure(pdf_fields)
            return result

        result = _asyncio.get_event_loop().run_until_complete(run())
        assert "column_map" in result
        assert "section_presence" in result
        assert result["section_presence"]["unit_mix_present"]["present"] is True

    def test_retry_exhausted_returns_empty_dict(self):
        svc = self._make_service()
        partial_msg = self._make_message(self._partial_raw())

        import asyncio as _asyncio

        async def run():
            with patch("app.verticals.real_estate.template_filling.llm_service.asyncio.to_thread", new=AsyncMock(return_value=partial_msg)):
                with patch.object(svc, "_record_llm_metrics"):
                    result = await svc.detect_om_structure([
                        {"source": "table_block", "page_number": 1, "table_name": "T", "table_columns": [], "table_rows": [], "citations": []}
                    ])
            return result

        result = _asyncio.get_event_loop().run_until_complete(run())
        assert result == {}


# ---------------------------------------------------------------------------
# Planner graceful-absence
# ---------------------------------------------------------------------------

class TestPlannerGracefulAbsence:
    def test_skips_rent_comps_when_section_absent(self):
        structure = _full_structure(section_overrides={"rent_comps_present": False})
        fields = [
            {"id": "f1", "sheet": "S1", "value_cell": "A1", "fill_when": ["rent_comps_present"], "requires_structure": []},
            {"id": "f2", "sheet": "S1", "value_cell": "A2", "fill_when": [], "requires_structure": []},
        ]
        plan = _plan_schema_targets_for_structure(fields, [], structure)
        field_ids_to_extract = {f["id"] for f in plan["fields_to_extract"]}
        skipped_ids = {s["target_id"] for s in plan["skipped_targets"]}

        assert "f1" in skipped_ids
        assert "f2" in field_ids_to_extract

    def test_skip_reason_is_missing_section(self):
        structure = _full_structure(section_overrides={"rent_comps_present": False})
        fields = [
            {"id": "f1", "sheet": "S1", "value_cell": "A1", "fill_when": ["rent_comps_present"], "requires_structure": []},
        ]
        plan = _plan_schema_targets_for_structure(fields, [], structure)
        skipped = plan["skipped_targets"]
        assert len(skipped) == 1
        assert skipped[0]["skip_reason"] == "missing_section"

    def test_non_gated_fields_always_extract(self):
        structure = _full_structure(section_overrides={k: False for k in (
            "current_operating_statement_present", "year1_operating_statement_present",
            "pro_forma_operating_statement_present", "t12_present", "unit_mix_present",
            "rent_roll_present", "rent_comps_present", "market_summary_present",
        )})
        fields = [
            {"id": "f1", "sheet": "S1", "value_cell": "A1", "fill_when": [], "requires_structure": []},
        ]
        plan = _plan_schema_targets_for_structure(fields, [], structure)
        assert "f1" in {f["id"] for f in plan["fields_to_extract"]}
        assert not plan["skipped_targets"]
