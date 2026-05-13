"""Citation parsing and context building for template fill runs."""

import re
from typing import Any, Dict, List, Optional


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
            "page": (bbox or {}).get("page"),
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


def get_section_citation_pages(om_structure: Dict[str, Any], section_key: str) -> List[int]:
    """Return page numbers cited by the structure detection entry for a given section key."""
    if not om_structure:
        return []
    for bucket in ("section_presence", "column_map"):
        entry = (om_structure.get(bucket) or {}).get(section_key)
        if entry:
            return parse_citation_pages(entry.get("citations") or [])
    return []


def get_field_page(field: Dict[str, Any]) -> Optional[int]:
    """Return the page number for a raw pdf_field regardless of source type."""
    source = field.get("source")
    if source == "key_value_pairs":
        return (field.get("bbox") or {}).get("page") or field.get("page_number")
    return field.get("page_number")
