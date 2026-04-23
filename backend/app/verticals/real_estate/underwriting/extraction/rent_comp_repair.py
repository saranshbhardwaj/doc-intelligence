from __future__ import annotations

import re


_SIZE_BUCKET_RE = re.compile(r"^\d+(?:\.\d+)?\s*[x×]\s*\d+(?:\.\d+)?$")
_INLINE_COMP_ROW_RE = re.compile(
    r"^(?P<size>\d+(?:\.\d+)?\s*[x×]\s*\d+(?:\.\d+)?)\s+"
    r"(?P<sqft>\d+(?:\.\d+)?)\s+"
    r"(?P<rent>-|\$?\d+(?:,\d{3})*(?:\.\d+)?)\s+"
    r"(?P<psf>-|\$?\d+(?:,\d{3})*(?:\.\d+)?)$"
)
_CITATION_LINE_RE = re.compile(r"^\[S\d+:p\d+\]\s*\(")


def _looks_like_size_bucket(value: str | None) -> bool:
    return bool(value and _SIZE_BUCKET_RE.match(value.strip()))


def _parse_numeric_token(value: str | None) -> float | None:
    if value is None:
        return None
    token = str(value).strip()
    if not token or token in {"-", "—", "n/a", "N/A"}:
        return None
    token = token.replace("$", "").replace(",", "")
    try:
        return float(token)
    except ValueError:
        return None


def _sanitize_context_lines(source_context: str | None) -> list[str]:
    if not source_context:
        return []

    lines: list[str] = []
    for raw_line in str(source_context).splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or _CITATION_LINE_RE.match(line):
            continue
        lines.append(line)
    return lines


def _parse_comp_row(lines: list[str], start_index: int) -> tuple[dict | None, int]:
    line = lines[start_index]
    inline_match = _INLINE_COMP_ROW_RE.match(line)
    if inline_match:
        return {
            "size": inline_match.group("size").replace("×", "x"),
            "asking_rent": _parse_numeric_token(inline_match.group("rent")),
            "rent_per_sqft": _parse_numeric_token(inline_match.group("psf")),
        }, start_index + 1

    if not _looks_like_size_bucket(line) or start_index + 3 >= len(lines):
        return None, start_index

    standard_sqft = _parse_numeric_token(lines[start_index + 1])
    if standard_sqft is None:
        return None, start_index

    return {
        "size": line.replace("×", "x"),
        "asking_rent": _parse_numeric_token(lines[start_index + 2]),
        "rent_per_sqft": _parse_numeric_token(lines[start_index + 3]),
    }, start_index + 4


def _extract_comp_blocks(lines: list[str], start_index: int = 0) -> list[list[dict]]:
    blocks: list[list[dict]] = []
    index = max(start_index, 0)
    while index < len(lines):
        row, next_index = _parse_comp_row(lines, index)
        if row is None:
            index += 1
            continue

        block = [row]
        index = next_index
        while index < len(lines):
            next_row, after_next = _parse_comp_row(lines, index)
            if next_row is None:
                break
            block.append(next_row)
            index = after_next

        blocks.append(block)
    return blocks


def _row_needs_repair(row: dict) -> bool:
    size = str(row.get("size") or "").strip()
    if not size:
        return True
    if "," in size or ";" in size:
        return True
    if not _looks_like_size_bucket(size):
        return True
    return row.get("asking_rent") is None and row.get("rent_per_sqft") is None


def _expected_size_count(row: dict) -> int:
    size = str(row.get("size") or "").strip()
    if not size:
        return 0
    parts = [part.strip() for part in re.split(r"[,;]", size) if part.strip()]
    if len(parts) > 1:
        return len(parts)
    return 1 if _looks_like_size_bucket(size) else 0


def _extract_rows_for_facility(lines: list[str], facility_name: str, facility_names: list[str]) -> list[dict]:
    normalized_facility = (facility_name or "").strip().lower()
    if not normalized_facility:
        return []

    stop_markers = {
        str(name or "").strip().lower()
        for name in facility_names
        if str(name or "").strip() and str(name or "").strip().lower() != normalized_facility
    }

    for index, line in enumerate(lines):
        if line.strip().lower() != normalized_facility:
            continue
        end_index = len(lines)
        for candidate_index in range(index + 1, len(lines)):
            if lines[candidate_index].strip().lower() in stop_markers:
                end_index = candidate_index
                break

        blocks = _extract_comp_blocks(lines[index + 1:end_index], 0)
        if blocks:
            return blocks[0]
    return []


def repair_om_rent_comp_rows(rent_comps: list[dict], source_context: str | None) -> list[dict]:
    if not rent_comps:
        return rent_comps

    facilities_in_order: list[str] = []
    for row in rent_comps:
        facility = str(row.get("facility") or "").strip()
        if facility and facility not in facilities_in_order:
            facilities_in_order.append(facility)

    if not facilities_in_order:
        return rent_comps

    lines = _sanitize_context_lines(source_context)
    if not lines:
        return rent_comps

    parsed_by_facility = {
        facility: _extract_rows_for_facility(lines, facility, facilities_in_order)
        for facility in facilities_in_order
    }

    if not all(parsed_by_facility.values()):
        start_positions = [
            idx for idx, line in enumerate(lines)
            if line.strip() in facilities_in_order
        ]
        global_blocks = _extract_comp_blocks(lines, min(start_positions) if start_positions else 0)
        global_rows = [row for block in global_blocks for row in block]
        expected_counts = []
        for facility in facilities_in_order:
            source_row = next((row for row in rent_comps if str(row.get("facility") or "").strip() == facility), None)
            expected_counts.append(_expected_size_count(source_row or {}))

        if all(count > 0 for count in expected_counts) and sum(expected_counts) == len(global_rows):
            parsed_by_facility = {
                facility: []
                for facility in facilities_in_order
            }
            offset = 0
            for facility, count in zip(facilities_in_order, expected_counts):
                parsed_by_facility[facility] = global_rows[offset:offset + count]
                offset += count
        elif len(global_blocks) == len(facilities_in_order):
            parsed_by_facility = {
                facility: global_blocks[idx]
                for idx, facility in enumerate(facilities_in_order)
            }

    repaired_rows: list[dict] = []
    for row in rent_comps:
        if not _row_needs_repair(row):
            repaired_rows.append(row)
            continue

        facility = str(row.get("facility") or "").strip()
        parsed_rows = parsed_by_facility.get(facility) or []
        if not parsed_rows:
            repaired_rows.append(row)
            continue

        for parsed in parsed_rows:
            repaired_rows.append({
                "facility": facility,
                "size": parsed.get("size"),
                "asking_rent": parsed.get("asking_rent"),
                "rent_per_sqft": parsed.get("rent_per_sqft"),
                "distance_mi": row.get("distance_mi"),
                "notes": row.get("notes"),
            })

    return repaired_rows