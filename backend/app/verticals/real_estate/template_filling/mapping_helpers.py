"""Scalar and table batch mapping helpers for template fill runs."""

from typing import Any, Dict, List, Optional, Tuple

from app.verticals.real_estate.template_filling.citations import get_section_citation_pages
from app.verticals.real_estate.template_filling.context_budget import build_budgeted_pdf_fields
from app.verticals.real_estate.template_filling.source_map import as_list


def get_table_batch_key(table_def: Dict[str, Any]) -> str:
    sheet = table_def.get("sheet") or "unknown"
    return sheet.lower()


def get_scalar_batch_key(field_def: Dict[str, Any]) -> str:
    source_basis = field_def.get("source_basis") or "om_property_summary"
    fill_when = "|".join(str(value) for value in as_list(field_def.get("fill_when")) if value)
    return f"{source_basis}:{fill_when or 'always'}"


def build_narrative_pdf_field(
    *,
    field_id_counter: int,
    narrative_text: str,
    section_heading: str,
    narrative_page: Optional[int],
) -> Dict[str, Any]:
    citation = f"[S{field_id_counter}:p{narrative_page}]"
    return {
        "id": f"narrative_block_{field_id_counter}",
        "name": f"narrative: {section_heading}" if section_heading else "narrative",
        "type": "narrative",
        "extracted_value": narrative_text[:300],
        "confidence": 0.8,
        "citations": [citation],
        "source": "narrative_block",
        "full_text": narrative_text,
        "section": section_heading,
        "page_number": narrative_page,
    }


def build_scalar_context_for_batch(
    pdf_fields: List[Dict[str, Any]],
    om_structure: Dict[str, Any],
    batch_fields: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Build scalar extraction context from the full evidence pool.

    Structure-gated batches are routed to cited pages first, then budgeted.
    Always/static batches keep the full pool and only apply budget limits.
    """
    fill_when_keys: set[str] = set()
    for field_def in batch_fields or []:
        for fill_when in as_list(field_def.get("fill_when")):
            if fill_when and fill_when != "always":
                fill_when_keys.add(str(fill_when))

    citation_pages: List[int] = []
    for key in sorted(fill_when_keys):
        citation_pages.extend(get_section_citation_pages(om_structure or {}, key))
    unique_citation_pages = sorted(set(citation_pages))

    routed_fields = pdf_fields
    routing_applied = False
    if unique_citation_pages:
        routing_applied = True
        routed_fields = [
            field
            for field in pdf_fields
            if (page := _field_page_for_routing(field)) is None
            or any(abs(page - citation_page) <= 1 for citation_page in unique_citation_pages)
        ]

    budgeted_fields, budget_metadata = build_budgeted_pdf_fields(routed_fields)
    budget_metadata = {
        **budget_metadata,
        "routing_applied": routing_applied,
        "citation_pages": unique_citation_pages,
        "source_field_count_before_routing": len(pdf_fields),
        "source_field_count_after_routing": len(routed_fields),
    }
    return budgeted_fields, budget_metadata


def _field_page_for_routing(field: Dict[str, Any]) -> Optional[int]:
    """Return page number for routing purposes (same logic as citations.get_field_page)."""
    source = field.get("source")
    if source == "key_value_pairs":
        return (field.get("bbox") or {}).get("page") or field.get("page_number")
    return field.get("page_number")


def scalar_context_signature(context_fields: List[Dict[str, Any]]) -> Tuple[str, ...]:
    """Build a stable exact-match signature from routed scalar context ids."""
    return tuple(str(field.get("id") or "") for field in context_fields or [])


def consolidate_scalar_batches_by_context(
    prepared_batches: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge scalar batches only when their routed contexts are exactly identical."""
    consolidated_by_signature: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    consolidated_order: List[Tuple[str, ...]] = []

    for prepared in prepared_batches or []:
        signature = scalar_context_signature(prepared.get("context") or [])
        if signature not in consolidated_by_signature:
            consolidated_by_signature[signature] = {
                "context_signature": signature,
                "batch_keys": [],
                "fields": [],
                "context": prepared.get("context") or [],
                "budgets": [],
            }
            consolidated_order.append(signature)

        consolidated = consolidated_by_signature[signature]
        consolidated["batch_keys"].append(prepared.get("batch_key"))
        consolidated["fields"].extend(prepared.get("fields") or [])
        consolidated["budgets"].append(prepared.get("budget") or {})

    return [consolidated_by_signature[signature] for signature in consolidated_order]


def extract_schema_table_row_labels(schema_obj: Any, workbook: Any) -> Dict[str, Any]:
    """
    Extract row labels for schema tables from the Excel template.

    Returns:
        Dict: {table_id: {"row_labels": [...], "start_row": int, "end_row": int}}
    """
    labels_by_table: Dict[str, Any] = {}
    if not schema_obj or not workbook:
        return labels_by_table

    for table in getattr(schema_obj, "tables", []) or []:
        table_id = table.get("id")
        sheet_name = table.get("sheet")
        row_id_col = table.get("row_identifier_column")
        start_row = table.get("data_start_row")
        end_row = table.get("data_end_row", start_row)

        if not table_id or not sheet_name or not row_id_col or not start_row:
            continue
        if sheet_name not in workbook.sheetnames:
            continue

        sheet = workbook[sheet_name]
        row_labels = []
        for row in range(start_row, (end_row or start_row) + 1):
            cell_value = sheet[f"{row_id_col}{row}"].value
            row_labels.append(str(cell_value).strip() if cell_value is not None else "")

        labels_by_table[table_id] = {
            "row_labels": row_labels,
            "start_row": start_row,
            "end_row": end_row,
        }

    return labels_by_table
