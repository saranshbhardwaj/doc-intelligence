"""Shared Source Map contract helpers for template filling."""

from __future__ import annotations

import copy
import logging
import re
from typing import Any, Dict, List

from app.verticals.real_estate.template_filling.citations import (
    parse_citation_pages,
    resolve_pdf_field_page_info,
)


logger = logging.getLogger(__name__)

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

COLUMN_MAP_KEYS = ("current", "t12", "year1", "pro_forma", "stabilized")
SECTION_PRESENCE_KEYS = (
    "current_operating_statement_present",
    "year1_operating_statement_present",
    "pro_forma_operating_statement_present",
    "t12_present",
    "unit_mix_present",
    "rent_roll_present",
    "rent_comps_present",
    "market_summary_present",
)

COLUMN_TO_SECTION = {
    "current": "current_operating_statement_present",
    "t12": "t12_present",
    "year1": "year1_operating_statement_present",
    "pro_forma": "pro_forma_operating_statement_present",
    "stabilized": "pro_forma_operating_statement_present",
}

MARKET_MAX_CLUSTER_PAGES = 8
MARKET_CONTENT_PAGE = "content"
MARKET_TOC_PAGE = "toc_or_navigation"
MARKET_WEAK_PAGE = "weak_heading_only"
MARKET_UNKNOWN_PAGE = "unknown"


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


def _default_missing_entry() -> Dict[str, Any]:
    return {
        "present": False,
        "label": None,
        "confidence": 0.0,
        "citations": [],
        "evidence": None,
    }


def _ensure_known_structure_keys(structure: Dict[str, Any]) -> None:
    column_map = structure.setdefault("column_map", {})
    section_presence = structure.setdefault("section_presence", {})
    for key in COLUMN_MAP_KEYS:
        column_map.setdefault(key, _default_missing_entry())
    for key in SECTION_PRESENCE_KEYS:
        section_presence.setdefault(key, _default_missing_entry())


def _field_search_text(field: Dict[str, Any]) -> str:
    parts: List[str] = [
        str(field.get("name") or ""),
        str(field.get("table_name") or ""),
        str(field.get("section") or ""),
        str(field.get("full_text") or ""),
    ]
    columns = field.get("table_columns") or []
    parts.extend(str(column) for column in columns)
    rows = field.get("table_rows") or []
    for row in rows[:8]:
        values = row.values() if isinstance(row, dict) else row
        parts.extend(str(value) for value in values)
    return " ".join(parts).lower()


def _set_inferred_entry(
    structure: Dict[str, Any],
    bucket: str,
    key: str,
    *,
    label: str,
    confidence: float,
    citations: List[str] | None,
    evidence: str,
) -> None:
    entries = structure.setdefault(bucket, {})
    existing = entries.get(key)
    if isinstance(existing, dict) and existing.get("present"):
        return
    entries[key] = {
        "present": True,
        "label": label,
        "confidence": confidence,
        "citations": citations or [],
        "evidence": evidence,
        "source": "inferred",
    }


def _has_market_signal(text: str) -> bool:
    return (
        "market overview" in text
        or "population profile" in text
        or "population" in text
        or "household" in text
        or "household income" in text
        or "demographic" in text
        or "major employers" in text
        or "storage sqft per capita" in text
        or "employment" in text
        or "median income" in text
        or "per capita income" in text
        or "housing units" in text
        or "metro highlights" in text
        or "economy" in text
    )


def _build_market_page_text_index(pdf_fields: List[Dict[str, Any]] | None) -> Dict[int, str]:
    page_parts: Dict[int, List[str]] = {}
    for field in pdf_fields or []:
        text = _field_search_text(field)
        if not text:
            continue
        _, pages = resolve_pdf_field_page_info(field)
        for page in pages:
            if page is not None and page > 0:
                page_parts.setdefault(page, []).append(text)
    return {page: " ".join(parts) for page, parts in page_parts.items()}


def _market_content_score(text: str) -> int:
    signals = (
        "market overview",
        "metro highlights",
        "demographic",
        "population",
        "population profile",
        "household",
        "household income",
        "median household income",
        "per capita income",
        "employment",
        "major employers",
        "employees",
        "housing units",
        "education",
        "median age",
        "economy",
        "storage sqft per capita",
        "msa",
        "submarket",
    )
    return sum(1 for signal in signals if signal in text)


def _market_value_score(text: str) -> int:
    patterns = (
        r"\$[\d,]+",
        r"\b\d{1,3}(?:,\d{3})+\b",
        r"\b\d+(?:\.\d+)?%",
        r"\b20\d{2}\b",
        r"\b[135]\s*miles?\b",
        r"\b\d+(?:\.\d+)?\s*[mk]\b",
    )
    return sum(1 for pattern in patterns if re.search(pattern, text))


def _toc_navigation_score(text: str) -> int:
    signals = (
        "table of contents",
        "section 1",
        "section 2",
        "section 3",
        "section 4",
        "section 5",
        "executive summary",
        "property information",
        "financial analysis",
        "rent comparables",
    )
    return sum(1 for signal in signals if signal in text)


def _classify_market_page_text(text: str) -> str:
    if not text:
        return MARKET_UNKNOWN_PAGE

    toc_score = _toc_navigation_score(text)
    content_score = _market_content_score(text)
    value_score = _market_value_score(text)

    if toc_score >= 2 and content_score < 3:
        return MARKET_TOC_PAGE
    if content_score >= 2 and value_score >= 1:
        return MARKET_CONTENT_PAGE
    if content_score >= 3 and len(text.split()) >= 25:
        return MARKET_CONTENT_PAGE
    if content_score >= 1:
        return MARKET_WEAK_PAGE
    return MARKET_UNKNOWN_PAGE


def _classify_market_pages(page_text: Dict[int, str]) -> Dict[int, str]:
    classifications: Dict[int, str] = {}
    for page, text in page_text.items():
        classification = _classify_market_page_text(text)
        if classification != MARKET_UNKNOWN_PAGE:
            classifications[page] = classification
    return classifications


def _cluster_from_anchor(page_classes: Dict[int, str], anchor: int) -> List[int]:
    allowed = {MARKET_CONTENT_PAGE, MARKET_WEAK_PAGE}
    if page_classes.get(anchor) not in allowed:
        return []

    pages = {anchor}
    for direction in (-1, 1):
        page = anchor + direction
        while page_classes.get(page) in allowed:
            candidate_pages = pages | {page}
            if max(candidate_pages) - min(candidate_pages) + 1 > MARKET_MAX_CLUSTER_PAGES:
                break
            pages.add(page)
            page += direction
    return sorted(pages)


def _nearest_content_page(anchor_pages: List[int], content_pages: List[int]) -> int | None:
    if not content_pages:
        return None
    if not anchor_pages:
        return content_pages[0]
    return min(
        content_pages,
        key=lambda page: (min(abs(page - anchor) for anchor in anchor_pages), page),
    )


def _apply_market_routing_metadata(structure: Dict[str, Any], page_classes: Dict[int, str]) -> None:
    entry = (structure.get("section_presence") or {}).get("market_summary_present")
    if not isinstance(entry, dict) or not entry.get("present"):
        return

    anchor_pages = sorted(set(parse_citation_pages(entry.get("citations") or [])))
    content_pages = sorted(
        page for page, classification in page_classes.items()
        if classification == MARKET_CONTENT_PAGE
    )
    excluded_toc_pages = sorted(
        page for page, classification in page_classes.items()
        if classification == MARKET_TOC_PAGE
    )

    accepted_anchor = next(
        (page for page in anchor_pages if page_classes.get(page) == MARKET_CONTENT_PAGE),
        None,
    )
    routing_source = "market_section_cluster"
    if accepted_anchor is None:
        accepted_anchor = _nearest_content_page(anchor_pages, content_pages)
        routing_source = "market_section_cluster_repaired_anchor"
    if accepted_anchor is None:
        logger.info(
            "Market routing skipped: anchor_pages=%s content_pages=%s excluded_toc_pages=%s",
            anchor_pages,
            content_pages,
            excluded_toc_pages,
        )
        return

    routing_pages = _cluster_from_anchor(page_classes, accepted_anchor)
    if not routing_pages:
        return

    start, end = routing_pages[0], routing_pages[-1]

    entry["page_range"] = [start, end]
    entry["routing_pages"] = routing_pages
    entry["routing_source"] = routing_source
    logger.info(
        "Market routing selected: anchor_pages=%s accepted_anchor=%s content_pages=%s excluded_toc_pages=%s routing_pages=%s routing_source=%s",
        anchor_pages,
        accepted_anchor,
        content_pages,
        excluded_toc_pages,
        routing_pages,
        routing_source,
    )


def _table_has_operating_rows(text: str) -> bool:
    return (
        "gross potential rent" in text
        and ("net operating income" in text or re.search(r"\bnoi\b", text) is not None)
        and ("expense" in text or "operating expenses" in text)
    )


def normalize_om_structure_with_pdf_fields(
    structure: Dict[str, Any] | None,
    pdf_fields: List[Dict[str, Any]] | None,
) -> Dict[str, Any]:
    """
    Normalize Source Map output and conservatively repair obvious false negatives.

    The LLM remains the primary detector. This layer only fills known missing keys
    and upgrades entries when Azure DI table evidence makes the structure mechanical.
    """
    normalized = copy.deepcopy(structure or {})
    _ensure_known_structure_keys(normalized)
    market_page_classes = _classify_market_pages(_build_market_page_text_index(pdf_fields))

    for field in pdf_fields or []:
        text = _field_search_text(field)
        citations = field.get("citations") or []
        label = field.get("table_name") or field.get("name") or field.get("section") or "Detected section"
        operating_rows_present = _table_has_operating_rows(text)

        if operating_rows_present and ("current" in text or "in-place" in text or "actual" in text):
            _set_inferred_entry(
                normalized,
                "column_map",
                "current",
                label="CURRENT",
                confidence=0.9,
                citations=citations,
                evidence="Inferred from Azure DI table headers or row labels containing a current/in-place operating period.",
            )
        if operating_rows_present and ("year 1" in text or "year-one" in text or "year one" in text or "underwriting" in text):
            _set_inferred_entry(
                normalized,
                "column_map",
                "year1",
                label="YEAR 1",
                confidence=0.9,
                citations=citations,
                evidence="Inferred from Azure DI table headers or row labels containing a Year 1 operating period.",
            )
        if operating_rows_present and ("pro forma" in text or "pro-forma" in text):
            _set_inferred_entry(
                normalized,
                "column_map",
                "pro_forma",
                label="PRO FORMA",
                confidence=0.9,
                citations=citations,
                evidence="Inferred from Azure DI table headers or row labels containing a pro forma operating period.",
            )
        if operating_rows_present and ("t-12" in text or "t12" in text or "trailing 12" in text):
            _set_inferred_entry(
                normalized,
                "column_map",
                "t12",
                label="T12",
                confidence=0.9,
                citations=citations,
                evidence="Inferred from Azure DI table headers or row labels containing a trailing twelve month period.",
            )

        if operating_rows_present:
            for column_key, section_key in COLUMN_TO_SECTION.items():
                column_entry = normalized["column_map"].get(column_key) or {}
                if column_entry.get("present"):
                    _set_inferred_entry(
                        normalized,
                        "section_presence",
                        section_key,
                        label=column_entry.get("label") or label,
                        confidence=float(column_entry.get("confidence") or 0.9),
                        citations=column_entry.get("citations") or citations,
                        evidence=f"Inferred from an operating statement table supporting `{column_key}`.",
                    )

        has_unit_shape = (
            ("# units" in text or "unit count" in text or " units " in f" {text} ")
            and ("sqft" in text or "sq ft" in text or " square feet" in text)
            and ("rent" in text or "occupancy" in text or "rate" in text)
        )
        if "unit mix" in text or "target rent analysis" in text or has_unit_shape:
            _set_inferred_entry(
                normalized,
                "section_presence",
                "unit_mix_present",
                label=label,
                confidence=0.9,
                citations=citations,
                evidence="Inferred from Azure DI table evidence with unit counts, sizes, and rent/occupancy columns.",
            )

        if "rent roll" in text and ("tenant" in text or "unit" in text or "lease" in text):
            _set_inferred_entry(
                normalized,
                "section_presence",
                "rent_roll_present",
                label=label,
                confidence=0.9,
                citations=citations,
                evidence="Inferred from Azure DI rent-roll heading or detailed tenant/unit table evidence.",
            )

        looks_like_rent_comps = (
            ("rent compar" in text or "rental rate comparison" in text)
            and ("distance" in text or "address" in text or "facility" in text or "property" in text)
        )
        if looks_like_rent_comps:
            _set_inferred_entry(
                normalized,
                "section_presence",
                "rent_comps_present",
                label=label,
                confidence=0.88,
                citations=citations,
                evidence="Inferred from Azure DI comparable-property table evidence.",
            )

        if _has_market_signal(text):
            _set_inferred_entry(
                normalized,
                "section_presence",
                "market_summary_present",
                label=label,
                confidence=0.86,
                citations=citations,
                evidence="Inferred from Azure DI market or demographic table/narrative evidence.",
            )

    _apply_market_routing_metadata(normalized, market_page_classes)
    return normalized
