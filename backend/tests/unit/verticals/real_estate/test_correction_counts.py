"""Unit tests for _compute_correction_counts."""
import pytest
from app.verticals.real_estate.api.templates import _compute_correction_counts


def test_llm_success_no_edits():
    data = {"f1": {"value": "8.11%", "confidence": 0.9, "user_edited": False}}
    counts = _compute_correction_counts(data)
    assert counts["user_corrected_count"] == 0
    assert counts["user_filled_blank_count"] == 0
    assert counts["user_edited_count"] == 0


def test_user_corrected_llm_value():
    data = {"f1": {"value": "8.11%", "confidence": 1.0, "user_edited": True, "original_value": "7.75%", "source": "manual_input"}}
    counts = _compute_correction_counts(data)
    assert counts["user_corrected_count"] == 1
    assert counts["user_filled_blank_count"] == 0
    assert counts["user_edited_count"] == 1


def test_user_filled_blank_from_pdf():
    data = {"f1": {"value": "2500000", "confidence": 1.0, "user_edited": True, "original_value": None, "source": "pdf_paste"}}
    counts = _compute_correction_counts(data)
    assert counts["user_corrected_count"] == 0
    assert counts["user_filled_blank_count"] == 1
    assert counts["user_edited_count"] == 1


def test_user_filled_blank_manually():
    data = {"f1": {"value": "custom", "confidence": 1.0, "user_edited": True, "original_value": None, "source": "manual_input"}}
    counts = _compute_correction_counts(data)
    assert counts["user_corrected_count"] == 0
    assert counts["user_filled_blank_count"] == 1
    assert counts["user_edited_count"] == 1


def test_mixed_fields():
    data = {
        "f1": {"value": "8.11%", "user_edited": False},
        "f2": {"value": "8.11%", "user_edited": True, "original_value": "7.75%", "source": "manual_input"},
        "f3": {"value": "2.5M", "user_edited": True, "original_value": None, "source": "pdf_paste"},
        "f4": {"value": "note", "user_edited": True, "original_value": None, "source": "manual_input"},
    }
    counts = _compute_correction_counts(data)
    assert counts["user_corrected_count"] == 1
    assert counts["user_filled_blank_count"] == 2
    assert counts["user_edited_count"] == 3


def test_legacy_edit_no_original_value_key():
    data = {"f1": {"value": "x", "user_edited": True}}
    counts = _compute_correction_counts(data)
    assert counts["user_corrected_count"] == 0
    assert counts["user_filled_blank_count"] == 0
    assert counts["user_edited_count"] == 1


def test_manual_edits_key_excluded():
    data = {
        "f1": {"value": "8%", "user_edited": False},
        "manual_edits": {"Sheet1": {"A1": {"value": "x", "user_edited": True}}},
    }
    counts = _compute_correction_counts(data)
    assert counts["user_edited_count"] == 0  # manual_edits excluded
    assert counts["user_corrected_count"] == 0
    assert counts["user_filled_blank_count"] == 0
