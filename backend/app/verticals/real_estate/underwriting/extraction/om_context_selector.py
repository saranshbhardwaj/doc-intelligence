"""Deterministic high-signal context selection for large OM extraction."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OMContextSelection:
    """Selected OM chunks and lightweight metadata for observability."""

    selected_chunks: list[Any]
    metadata: dict[str, Any]


_HIGH_SIGNAL_KEYWORDS = (
    "asking price",
    "purchase price",
    "listing price",
    "sources and uses",
    "cap rate",
    "current cap",
    "pro forma cap",
    "stabilized cap",
    "exit cap",
    "terminal cap",
    "gross potential rent",
    "scheduled rent",
    "rental income",
    "effective gross",
    "other income",
    "operating statement",
    "income statement",
    "financial",
    "revenue",
    "expense",
    "noi",
    "net operating income",
    "year 1",
    "year-one",
    "current",
    "t-6",
    "t-12",
    "occupancy",
    "vacancy",
    "unit mix",
    "rent roll",
    "rent comp",
    "rent comparable",
    "competitive",
    "competition",
    "competitor",
    "nearby",
    "facility",
    "demographic",
    "population",
    "household income",
    "storage sqft",
    "square feet per capita",
    "financing",
    "loan",
    "interest rate",
    "amortization",
    "ltv",
    "tax rate",
    "mill rate",
    "property tax",
    "insurance",
    "payroll",
    "utilities",
    "marketing",
    "repairs",
    "maintenance",
    "management fee",
    "value-add",
    "value add",
    "upside",
    "below market",
)

_TABLE_KEYWORDS = (
    "unit",
    "rent",
    "income",
    "expense",
    "noi",
    "financial",
    "operating",
    "competition",
    "comp",
    "demographic",
    "population",
    "financing",
    "loan",
)

_LOW_SIGNAL_KEYWORDS = (
    "confidential",
    "confidentiality",
    "disclaimer",
    "disclosure",
    "broker",
    "advisor",
    "advisory",
    "team",
    "biography",
    "bio",
    "contact",
    "legal",
    "non-binding",
    "non binding",
    "copyright",
    "photo",
    "image",
    "aerial",
    "map",
    "table of contents",
)


def _metadata(chunk: Any) -> dict[str, Any]:
    value = getattr(chunk, "chunk_metadata", None)
    return value if isinstance(value, dict) else {}


def _text(chunk: Any) -> str:
    return str(getattr(chunk, "text", "") or "")


def _chunk_id(chunk: Any) -> str | None:
    return getattr(chunk, "chunk_id", None) or getattr(chunk, "id", None)


def _section_type(chunk: Any) -> str:
    metadata = _metadata(chunk)
    return str(getattr(chunk, "section_type", None) or metadata.get("section_type") or metadata.get("chunk_type") or "").lower()


def _page(chunk: Any) -> int | None:
    metadata = _metadata(chunk)
    bbox = metadata.get("bbox")
    if isinstance(bbox, dict) and bbox.get("page") is not None:
        try:
            return int(bbox["page"])
        except (TypeError, ValueError):
            pass
    for value in (getattr(chunk, "page_number", None), metadata.get("page_number")):
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    page_range = metadata.get("page_range")
    if isinstance(page_range, list) and page_range:
        try:
            return int(page_range[0])
        except (TypeError, ValueError):
            return None
    return None


def _source_token(chunk: Any, source_index: int) -> str:
    metadata = _metadata(chunk)
    if metadata.get("source_kind") == "spreadsheet":
        sheet_name = metadata.get("sheet_name") or "Sheet"
        row_start = metadata.get("row_start")
        row_end = metadata.get("row_end")
        if row_start and row_end:
            return f"S{source_index}:{sheet_name}!R{row_start}-R{row_end}"
        return f"S{source_index}:{sheet_name}"
    return f"S{source_index}:p{_page(chunk) or '?'}"


def _haystack(chunk: Any) -> str:
    metadata = _metadata(chunk)
    pieces = [
        _text(chunk),
        str(getattr(chunk, "section_heading", "") or ""),
        str(metadata.get("section_heading") or ""),
        " ".join(str(item) for item in (metadata.get("column_headers") or [])),
        str(metadata.get("table_name") or ""),
    ]
    return "\n".join(piece for piece in pieces if piece).lower()


def _has_keyword(haystack: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in haystack for keyword in keywords)


def _classification(chunk: Any) -> tuple[int, str]:
    """Return (priority, reason). Lower priority numbers are selected first."""
    section_type = _section_type(chunk)
    page = _page(chunk)
    haystack = _haystack(chunk)

    if page is not None and page <= 2:
        return 0, "first_pages"
    if section_type in {"key_value_pairs", "key_value"}:
        return 1, "key_value"
    if section_type == "table" and _has_keyword(haystack, _TABLE_KEYWORDS):
        return 2, "high_signal_table"
    if _has_keyword(haystack, _HIGH_SIGNAL_KEYWORDS):
        return 3, "high_signal_text"
    if _has_keyword(haystack, _LOW_SIGNAL_KEYWORDS):
        return 9, "low_signal_boilerplate"
    return 7, "generic"


def select_om_context_chunks(
    chunks: list[Any],
    *,
    source_index: int,
    max_chars: int,
) -> OMContextSelection:
    """Select high-value OM chunks under a char budget.

    The selector is deliberately deterministic and explainable. It chooses a
    first-pass context only; extractor-level fallback protects quality.
    """
    if not chunks or max_chars <= 0:
        return OMContextSelection(selected_chunks=[], metadata={})

    id_to_index = {
        _chunk_id(chunk): index
        for index, chunk in enumerate(chunks)
        if _chunk_id(chunk)
    }
    classified: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        priority, reason = _classification(chunk)
        classified.append(
            {
                "index": index,
                "chunk": chunk,
                "chars": len(_text(chunk)),
                "priority": priority,
                "reason": reason,
            }
        )

    selected_indexes: set[int] = set()
    selected_chars = 0

    def add_candidate(candidate: dict[str, Any], reason: str | None = None) -> bool:
        nonlocal selected_chars
        index = candidate["index"]
        if index in selected_indexes:
            return True
        chars = candidate["chars"]
        if selected_indexes and selected_chars + chars > max_chars:
            return False
        selected_indexes.add(index)
        selected_chars += chars
        if reason:
            candidate["reason"] = reason
        return True

    # First pass: select high-signal candidates by priority.
    for candidate in sorted(classified, key=lambda item: (item["priority"], item["index"])):
        if candidate["priority"] >= 7:
            continue
        add_candidate(candidate)

    # Linked table narrative gives selected tables useful local context.
    for candidate in list(classified):
        if candidate["index"] not in selected_indexes or _section_type(candidate["chunk"]) != "table":
            continue
        linked_id = _metadata(candidate["chunk"]).get("linked_narrative_id")
        linked_index = id_to_index.get(linked_id)
        if linked_index is None or linked_index in selected_indexes:
            continue
        linked_candidate = classified[linked_index]
        add_candidate(linked_candidate, "linked_narrative")

    selected = [chunk for index, chunk in enumerate(chunks) if index in selected_indexes]
    reason_counts = Counter(
        item["reason"]
        for item in classified
        if item["index"] in selected_indexes
    )
    original_chars = sum(len(_text(chunk)) for chunk in chunks)
    metadata = {
        "enabled": True,
        "original_chunk_count": len(chunks),
        "selected_chunk_count": len(selected),
        "dropped_chunk_count": len(chunks) - len(selected),
        "original_char_count": original_chars,
        "selected_char_count": sum(len(_text(chunk)) for chunk in selected),
        "max_char_budget": max_chars,
        "reason_counts": dict(reason_counts),
        "selected_source_tokens": [_source_token(chunk, source_index) for chunk in selected],
        "fallback_to_full_context": False,
    }
    return OMContextSelection(selected_chunks=selected, metadata=metadata)
