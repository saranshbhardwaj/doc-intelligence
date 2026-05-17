"""Citation parsing and context building for template fill runs."""

import re
from typing import Any, Dict, List, Optional, Tuple


def build_citation_context(detected_fields: list, document_filename: str) -> dict:
    """
    Build S{n}→{bbox, page, filename} lookup from detected fields.

    Parallel to rag_service._build_citation_context() for RAG chunks.
    Built once at detect_fields_task time and persisted to DB so the frontend
    can resolve [S{n}:p{N}] citation tokens → exact bbox without any array searching.

    Only includes non-targeted fields (targeted_schema entries are appended later
    in auto_map_fields_task after their bboxes are resolved).
    """
    citations = []
    for field in detected_fields:
        if field.get("source") == "targeted_schema":
            continue
        m = re.search(r'_(\d+)$', field.get("id", ""))
        if not m:
            continue
        bbox = field.get("bbox")
        citations.append({
            "source_index": int(m.group(1)),
            "field_id": field["id"],
            "page": get_field_page(field),
            "filename": document_filename,
            "bbox": bbox,
        })
    return {"citations": citations}


def parse_citation_pages(citations: List[Any]) -> List[int]:
    """Parse citation strings like '[S3:p15]' or 'Page 15' into page numbers."""
    pages: List[int] = []
    for cit in (citations or []):
        for m in re.finditer(r":p(\d+)|[Pp]age\s*(\d+)", str(cit)):
            pages.append(int(m.group(1) or m.group(2)))
    return pages


def _coerce_page_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _unique_pages(pages: List[Optional[int]]) -> List[int]:
    unique: List[int] = []
    for page in pages:
        parsed = _coerce_page_int(page)
        if parsed is not None and parsed not in unique:
            unique.append(parsed)
    return unique


def _expand_page_range(page_range: Any) -> List[int]:
    if not isinstance(page_range, list) or not page_range:
        return []
    pages = _unique_pages(page_range)
    if len(pages) >= 2:
        start, end = min(pages[0], pages[-1]), max(pages[0], pages[-1])
        return list(range(start, end + 1))
    return pages


def resolve_pdf_field_page_info(field: Dict[str, Any]) -> Tuple[Optional[int], List[int]]:
    """Resolve a pdf_field anchor page and known pages.

    Mirrors DocumentChunk.resolve_page_info semantics for TemplateFill's derived
    field dicts. Table/narrative-derived fields prefer their explicit derived
    page provenance because chunk/table bboxes can be broader than the logical
    source page. KV fields keep bbox-first behavior for precise highlighting.
    """

    field = field or {}
    bbox_page = None
    bbox = field.get("bbox")
    if isinstance(bbox, dict):
        bbox_page = _coerce_page_int(bbox.get("page"))

    range_pages = _unique_pages(field.get("page_range") if isinstance(field.get("page_range"), list) else [])

    region_pages: List[int] = []
    for key in ("value_bounding_regions", "bounding_regions", "key_bounding_regions"):
        regions = field.get(key)
        if not isinstance(regions, list):
            continue
        for region in regions:
            if isinstance(region, dict):
                parsed = _coerce_page_int(region.get("page_number"))
                if parsed is not None:
                    region_pages.append(parsed)

    fallback_page = _coerce_page_int(field.get("page_number"))
    source = str(field.get("source") or "")
    prefers_explicit_page = source in {"table", "table_block", "narrative_block"}

    candidates: List[Optional[int]] = []
    if prefers_explicit_page:
        candidates.append(fallback_page)
        if range_pages:
            candidates.append(range_pages[0])
        if region_pages:
            candidates.append(region_pages[0])
        candidates.append(bbox_page)
    else:
        candidates.append(bbox_page)
        if range_pages:
            candidates.append(range_pages[0])
        if region_pages:
            candidates.append(region_pages[0])
        candidates.append(fallback_page)

    anchor_page = next((page for page in candidates if page is not None), None)
    all_pages = _unique_pages([anchor_page, *range_pages, *region_pages, fallback_page, bbox_page])
    return anchor_page, all_pages


def _structure_entry_for_key(om_structure: Dict[str, Any], section_key: str) -> Optional[Dict[str, Any]]:
    if not om_structure:
        return None
    for bucket in ("section_presence", "column_map"):
        entry = (om_structure.get(bucket) or {}).get(section_key)
        if isinstance(entry, dict):
            return entry
    return None


def get_section_citation_pages(om_structure: Dict[str, Any], section_key: str) -> List[int]:
    """Return page numbers cited by the structure detection entry for a given section key."""
    entry = _structure_entry_for_key(om_structure, section_key)
    return parse_citation_pages(entry.get("citations") or []) if entry else []


def get_structure_routing_pages(om_structure: Dict[str, Any], section_key: str) -> List[int]:
    """Return extraction routing pages for a Source Map key.

    routing_pages are explicit extraction hints. page_range is a section span.
    Citations remain the audit fallback and get the legacy +/- 1 page window.
    """

    entry = _structure_entry_for_key(om_structure, section_key)
    if not entry:
        return []

    routing_pages = _unique_pages(entry.get("routing_pages") if isinstance(entry.get("routing_pages"), list) else [])
    if routing_pages:
        return sorted(routing_pages)

    range_pages = _expand_page_range(entry.get("page_range"))
    if range_pages:
        return range_pages

    citation_pages = sorted(set(parse_citation_pages(entry.get("citations") or [])))
    window_pages: set[int] = set()
    for page in citation_pages:
        window_pages.update({page - 1, page, page + 1})
    return sorted(page for page in window_pages if page > 0)


def get_field_page(field: Dict[str, Any]) -> Optional[int]:
    """Return the page number for a raw pdf_field regardless of source type."""
    anchor_page, _ = resolve_pdf_field_page_info(field)
    return anchor_page


def _parse_source_citation(citation: Any) -> tuple[Optional[int], Optional[int]]:
    """Parse citation token into (source_index, page)."""
    match = re.search(r"\[(?:S|D)(\d+):p(\d+)\]", str(citation))
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def resolve_bbox_from_citations(
    citations: List[Any],
    citation_context: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Resolve the first valid citation token to a bbox from citation_context.

    The citation token and bbox must agree on page. This prevents stale or locally
    renumbered citations from highlighting a valid bbox on the wrong page.
    """
    context_entries = (citation_context or {}).get("citations") or []
    if not context_entries:
        return None

    by_source_index: Dict[int, Dict[str, Any]] = {}
    for entry in context_entries:
        source_index = entry.get("source_index")
        if isinstance(source_index, int):
            by_source_index[source_index] = entry

    for citation in citations or []:
        source_index, citation_page = _parse_source_citation(citation)
        if source_index is None:
            continue

        entry = by_source_index.get(source_index)
        if not entry:
            continue

        bbox = entry.get("bbox")
        if not isinstance(bbox, dict):
            continue

        bbox_page = bbox.get("page") or entry.get("page")
        if isinstance(bbox_page, str) and bbox_page.isdigit():
            bbox_page = int(bbox_page)

        if citation_page is not None and bbox_page is not None and int(bbox_page) != citation_page:
            continue

        return bbox

    return None
