"""Unit tests for template fill analytics aggregation logic."""
from app.services.template_fill_analytics_service import aggregate_field_stats as _aggregate_field_stats


def test_llm_success():
    rows = [{"f1": {"value": "8%", "user_edited": False}}]
    result = _aggregate_field_stats(rows)
    assert result["f1"]["llm_success"] == 1
    assert result["f1"]["total_runs"] == 1
    assert result["f1"]["llm_corrected"] == 0


def test_llm_corrected():
    rows = [{"f1": {"value": "8%", "user_edited": True, "original_value": "7%", "source": "manual_input"}}]
    result = _aggregate_field_stats(rows)
    assert result["f1"]["llm_corrected"] == 1
    assert result["f1"]["blank_filled_from_pdf"] == 0


def test_blank_filled_from_pdf():
    rows = [{"f1": {"value": "2.5M", "user_edited": True, "original_value": None, "source": "pdf_paste"}}]
    result = _aggregate_field_stats(rows)
    assert result["f1"]["blank_filled_from_pdf"] == 1
    assert result["f1"]["blank_filled_manually"] == 0


def test_blank_filled_manually():
    rows = [{"f1": {"value": "note", "user_edited": True, "original_value": None, "source": "manual_input"}}]
    result = _aggregate_field_stats(rows)
    assert result["f1"]["blank_filled_manually"] == 1
    assert result["f1"]["blank_filled_from_pdf"] == 0


def test_multiple_runs_aggregate():
    rows = [
        {"f1": {"user_edited": False, "value": "8%"}},
        {"f1": {"user_edited": True, "original_value": "7%", "source": "manual_input", "value": "8%"}},
        {"f1": {"user_edited": True, "original_value": None, "source": "pdf_paste", "value": "2.5M"}},
    ]
    result = _aggregate_field_stats(rows)
    assert result["f1"]["total_runs"] == 3
    assert result["f1"]["llm_success"] == 1
    assert result["f1"]["llm_corrected"] == 1
    assert result["f1"]["blank_filled_from_pdf"] == 1


def test_nested_format_llm_extracted():
    rows = [{"llm_extracted": {"f1": {"user_edited": False, "value": "8%"}}}]
    result = _aggregate_field_stats(rows)
    assert result["f1"]["llm_success"] == 1


def test_missing_field_in_some_runs():
    rows = [
        {"f1": {"user_edited": False, "value": "8%"}},
        {"f2": {"user_edited": False, "value": "10%"}},
    ]
    result = _aggregate_field_stats(rows)
    assert result["f1"]["total_runs"] == 1
    assert result["f2"]["total_runs"] == 1


def test_manual_edits_key_excluded():
    rows = [{"f1": {"user_edited": False, "value": "8%"}, "manual_edits": {"Sheet1": {"A1": {"value": "x"}}}}]
    result = _aggregate_field_stats(rows)
    assert "manual_edits" not in result
    assert result["f1"]["llm_success"] == 1


def test_legacy_edit_no_original_value_key():
    # user_edited=True but original_value key absent — legacy data, counted in total_runs only
    rows = [{"f1": {"value": "x", "user_edited": True}}]
    result = _aggregate_field_stats(rows)
    assert result["f1"]["total_runs"] == 1
    assert result["f1"]["llm_success"] == 0
    assert result["f1"]["llm_corrected"] == 0
    assert result["f1"]["blank_filled_from_pdf"] == 0
    assert result["f1"]["blank_filled_manually"] == 0
