"""Shared Source Map contract helpers for template filling."""

from __future__ import annotations

from typing import Any, Dict, List


STRUCTURE_HIGH_CONFIDENCE = 0.85
STRUCTURE_LOW_CONFIDENCE = 0.60

SOURCE_PERIOD_VALUES = {"current", "t12", "year1", "pro_forma", "stabilized", "static"}
SOURCE_BASIS_VALUES = {
    "om_operating_statement",
    "om_unit_mix",
    "om_property_summary",
    "om_market_summary",
    "om_rent_roll",
    "om_rent_comps",
    "om_capex_schedule",
}
FILL_WHEN_VALUES = {
    "always",
    "current_operating_statement_present",
    "year1_operating_statement_present",
    "pro_forma_operating_statement_present",
    "t12_present",
    "unit_mix_present",
    "rent_roll_present",
    "rent_comps_present",
    "market_summary_present",
}

SKIP_REASON_VALUES = {
    "missing_section",
    "low_structure_confidence",
    "structure_key_missing",
    "data_type_mismatch",
    "extraction_returned_null",
}


def as_list(value: Any) -> List[Any]:
    """Return value as a list while preserving existing list values."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def trim_om_structure_for_prompt(structure: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """
    Return Source Map context safe for repeated extraction prompts.

    The full artifact keeps citations/evidence for audit. Extraction calls only
    need routing state and confidence, so keep those prompts lean.
    """
    if not isinstance(structure, dict):
        return None

    trimmed: Dict[str, Any] = {}
    for section_name in ("column_map", "section_presence"):
        section = structure.get(section_name)
        if not isinstance(section, dict):
            continue
        trimmed_section: Dict[str, Any] = {}
        for key, entry in section.items():
            if not isinstance(entry, dict):
                continue
            trimmed_section[key] = {
                "present": entry.get("present"),
                "label": entry.get("label"),
                "confidence": entry.get("confidence"),
            }
        trimmed[section_name] = trimmed_section
    return trimmed
