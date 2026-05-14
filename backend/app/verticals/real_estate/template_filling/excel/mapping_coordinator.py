"""Coordinator for Excel field mapping - handles schema-based + generic fallback."""

import re
from typing import Any, Dict, List, Optional

from openpyxl import Workbook

from app.utils.logging import logger
from app.services.citations import normalize_citations

from .schema_based import SchemaLoader, SchemaMapper, TemplateIdentifier
from .schema_based.schema_loader import _normalize_field_name


_SOURCE_BASIS_LABELS = {
    "om_operating_statement": "Operating Statement",
    "om_property_summary": "Property Summary",
    "om_unit_mix": "Unit Mix",
    "om_rent_roll": "Rent Roll",
    "om_rent_comps": "Rent Comps",
    "om_market_summary": "Market Summary",
    "om_capex_schedule": "CapEx Schedule",
}

_SOURCE_PERIOD_LABELS = {
    "static": "Static",
    "current": "Current",
    "t12": "T12",
    "year1": "Year 1",
    "pro_forma": "Pro Forma",
    "stabilized": "Stabilized",
}


def _humanize_identifier(value: str) -> str:
    """Convert internal ids/sheet names into compact analyst-facing labels."""

    if not value:
        return ""

    cleaned = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(value))
    cleaned = cleaned.replace("&", " & ")
    cleaned = re.sub(r"[_:/-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.title()


def _friendly_sheet_name(sheet: str) -> str:
    return _humanize_identifier(sheet).replace(" And ", " & ")


def _field_label(field: Dict[str, Any]) -> str:
    for alias in field.get("pdf_aliases") or []:
        if alias:
            label = str(alias)
            for prefix in ("Actuals & Unit Mix ", "Napkin ", "P&L ", "Rediq "):
                if label.lower().startswith(prefix.lower()):
                    label = label[len(prefix):]
                    break
            return label

    field_id = str(field.get("id") or "")
    for prefix in (
        "actuals_unit_mix_",
        "napkin_",
        "pnl_",
        "rediq_",
        "dashboard_",
    ):
        if field_id.startswith(prefix):
            field_id = field_id[len(prefix):]
            break
    return _humanize_identifier(field_id)


def _section_label_from_id(field_id: str) -> Optional[str]:
    normalized = f"_{field_id.lower()}_"
    if "_expenses_" in normalized or "_expense_" in normalized:
        return "Expenses"
    if "_income_" in normalized or "_revenue_" in normalized:
        return "Income"
    if "_unit_mix_" in normalized:
        return "Unit Mix"
    if "_rent_comps_" in normalized:
        return "Rent Comps"
    if "_market_" in normalized:
        return "Market"
    return None


def _first_citation_page(citations: List[str]) -> Optional[int]:
    for citation in citations:
        match = re.search(r"\[[SD](?:\d+):p(\d+)\]", str(citation))
        if match:
            return int(match.group(1))
    return None


def _source_note(
    *,
    source_basis: Optional[str],
    source_period: Optional[str],
    section_label: Optional[str],
    citations: List[str],
) -> str:
    parts = []
    if source_basis:
        basis = _SOURCE_BASIS_LABELS.get(source_basis, _humanize_identifier(source_basis))
        parts.append("Operating statement" if basis == "Operating Statement" else basis)
    if section_label and section_label.lower() != (parts[0].lower() if parts else ""):
        parts.append(f"{section_label} section" if source_basis else section_label)
    if source_period and source_period != "static":
        period = _SOURCE_PERIOD_LABELS.get(source_period, _humanize_identifier(source_period))
        parts.append(f"{period} period")

    page = _first_citation_page(citations)
    if page is not None:
        parts.append(f"Page {page}")

    return " · ".join(parts)


def _display_context(field: Dict[str, Any]) -> str:
    parts = [_friendly_sheet_name(field.get("sheet", ""))]
    source_basis = field.get("source_basis")
    source_period = field.get("source_period")
    section_label = _section_label_from_id(str(field.get("id") or ""))

    if source_basis:
        parts.append(_SOURCE_BASIS_LABELS.get(source_basis, _humanize_identifier(source_basis)))
    if section_label:
        parts.append(section_label)
    if source_period and source_period != "static":
        parts.append(_SOURCE_PERIOD_LABELS.get(source_period, _humanize_identifier(source_period)))

    return " · ".join(part for part in parts if part)


class MappingCoordinator:
    """
    Coordinates schema-based and generic mapping strategies.

    Workflow:
    1. Try schema-based mapping (deterministic, no LLM)
    2. Fallback to generic analyzer + LLM for unmapped cells
    3. Merge results (schema takes priority)
    """

    def __init__(self):
        """Initialize coordinator with schema loader."""
        self.schema_loader = SchemaLoader()
        self.identifier = TemplateIdentifier(self.schema_loader)

    def identify_template(self, workbook: Workbook) -> Optional[str]:
        """
        Identify template by fingerprint.

        Args:
            workbook: openpyxl Workbook

        Returns:
            Schema ID if matched, None otherwise
        """
        return self.identifier.identify(workbook)

    def create_schema_mappings(
        self, schema_id: str, pdf_fields: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Create mappings using schema definition.

        Args:
            schema_id: Schema identifier
            pdf_fields: List of PDF field dicts

        Returns:
            List of mapping dicts with source="schema"
        """
        schema = self.schema_loader.load_schema(schema_id)
        if not schema:
            logger.warning(f"Schema '{schema_id}' not found")
            return []

        mapper = SchemaMapper(schema)
        mappings = mapper.map_fields(pdf_fields)

        logger.info(f"✓ Schema mapping: {len(mappings)} fields mapped from schema '{schema_id}'")

        return mappings

    def get_schema_mapped_cells(self, schema_mappings: List[Dict[str, Any]]) -> set:
        """
        Get set of cells that have been mapped by schema.

        Args:
            schema_mappings: Mappings from create_schema_mappings()

        Returns:
            Set of "SHEET!CELL" strings
        """
        return {f"{m['excel_sheet']}!{m['excel_cell']}" for m in schema_mappings}

    def filter_generic_schema(
        self, generic_schema: Dict[str, Any], schema_mapped_cells: set
    ) -> Dict[str, Any]:
        """
        Filter generic schema to exclude cells already mapped by schema.

        Args:
            generic_schema: Canonical schema from TemplateAnalyzer.analyze() —
                            {"sheets": [{"name": str, "key_value_fields": [...], ...}], ...}
            schema_mapped_cells: Set of "SHEET!CELL" strings from get_schema_mapped_cells()

        Returns:
            Same canonical format with schema-mapped cells removed from key_value_fields.
            Passes directly to LLM service without further conversion.
        """
        original_count = 0
        filtered_count = 0
        filtered_sheets = []

        for sheet_data in generic_schema.get("sheets", []):
            sheet_name = sheet_data.get("name", "")
            kv_fields = sheet_data.get("key_value_fields", [])
            original_count += len(kv_fields)

            kept = [
                kv for kv in kv_fields
                if f"{sheet_name}!{kv['cell']}" not in schema_mapped_cells
            ]
            filtered_count += len(kept)

            # Preserve all other sheet keys (tables, formula_cells, etc.)
            filtered_sheets.append({**sheet_data, "key_value_fields": kept})

        logger.info(
            f"Filtered generic schema: {original_count} → {filtered_count} cells "
            f"({original_count - filtered_count} excluded by schema)"
        )

        # Preserve top-level keys (total_key_value_fields, total_tables, has_formulas)
        return {**generic_schema, "sheets": filtered_sheets}

    def create_targeted_schema_mappings(
        self,
        unmapped_fields: List[Dict[str, Any]],
        targeted_values: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Convert Stage 2 LLM results into mapping dicts using schema cell positions.

        Unlike generic LLM mappings (which find both which cell AND what value),
        Stage 2 returns only values — cell positions come from the YAML schema.

        Args:
            unmapped_fields: Schema field defs from TemplateSchema.fields that weren't
                             matched in Stage 1 alias matching.
            targeted_values: {field_id: {"value": str, "confidence": float, "citations": list}}
                             Return value of LLMService.extract_schema_field_values().

        Returns:
            List of mapping dicts with source="targeted_schema".
        """
        mappings = []
        for field in unmapped_fields:
            field_id = field["id"]
            result = targeted_values.get(field_id)
            if not result or not result.get("value"):
                continue
            citations = normalize_citations(result.get("citations", []))
            section_label = _section_label_from_id(field_id)

            mappings.append({
                "pdf_field_id": f"targeted_{field_id}",
                "pdf_field_name": field_id,
                "excel_cell": field["value_cell"],
                "excel_sheet": field["sheet"],
                "excel_label": f"{field['sheet']}!{field.get('label_cell', '')}",
                "confidence": result["confidence"],
                "source": "targeted_schema",
                "reasoning": result.get("reasoning") or f"Stage 2 targeted extraction for schema field '{field_id}'",
                "citations": citations,
                "extracted_value": result["value"],
                "data_type": field.get("data_type", "text"),
                "display_label": _field_label(field),
                "display_context": _display_context(field),
                "source_note": _source_note(
                    source_basis=field.get("source_basis"),
                    source_period=field.get("source_period"),
                    section_label=section_label,
                    citations=citations,
                ),
            })

        logger.info(
            f"✓ Targeted schema mappings: {len(mappings)}/{len(unmapped_fields)} fields found by LLM"
        )
        return mappings

    def create_targeted_schema_table_mappings(
        self,
        schema_tables: List[Dict[str, Any]],
        targeted_table_values: Dict[str, Any],
        table_row_labels: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Convert Stage 2 LLM table results into mapping dicts using schema table cell positions.

        Args:
            schema_tables: Table defs from TemplateSchema.tables
            targeted_table_values: {table_id: {"rows": [...]}}
            table_row_labels: Optional map of table_id -> {row_labels: [...], start_row, end_row}

        Returns:
            List of mapping dicts with source="targeted_schema".
        """
        if not schema_tables or not targeted_table_values:
            return []

        table_row_labels = table_row_labels or {}
        table_by_id = {t.get("id"): t for t in schema_tables if t.get("id")}
        mappings: List[Dict[str, Any]] = []

        for table_id, table_result in targeted_table_values.items():
            table_def = table_by_id.get(table_id)
            if not table_def:
                continue

            start_row = table_def.get("data_start_row")
            end_row = table_def.get("data_end_row", start_row)
            row_id_col = table_def.get("row_identifier_column")
            row_labels = table_row_labels.get(table_id, {}).get("row_labels", [])
            if row_labels:
                seen_labels = {}
                duplicates = set()
                for idx, label in enumerate(row_labels):
                    normalized_label = _normalize_field_name(str(label or ""))
                    if not normalized_label:
                        continue
                    if normalized_label in seen_labels:
                        duplicates.add(normalized_label)
                    else:
                        seen_labels[normalized_label] = idx
                if duplicates:
                    logger.warning(
                        f"Duplicate row labels detected in schema table '{table_id}': "
                        f"{', '.join(sorted(duplicates))}"
                    )

            columns = table_def.get("columns", [])
            column_defs = {c.get("excel_column"): c for c in columns if c.get("excel_column")}

            for row in table_result.get("rows", []):
                row_index = row.get("row_index")
                row_label = row.get("row_label")
                values = row.get("values", {}) or {}
                confidence = row.get("confidence", 0.7)
                citations = row.get("citations", [])

                excel_row = None
                if row_labels and row_label:
                    normalized_target = _normalize_field_name(str(row_label))
                    for idx, label in enumerate(row_labels):
                        normalized_label = _normalize_field_name(str(label or ""))
                        if normalized_label and (
                            normalized_label == normalized_target
                            or normalized_target in normalized_label
                            or normalized_label in normalized_target
                        ):
                            excel_row = (start_row or 0) + idx
                            break

                if excel_row is None:
                    if start_row is None or row_index is None:
                        continue
                    excel_row = start_row + int(row_index)

                if end_row is not None and excel_row > end_row:
                    continue

                for excel_col, value in values.items():
                    if value is None or str(value).strip() == "":
                        continue
                    if row_id_col and row_label and excel_col == row_id_col:
                        # Skip writing the row label column when labels are already present
                        continue

                    col_def = column_defs.get(excel_col, {})
                    excel_cell = f"{excel_col}{excel_row}"
                    data_type = col_def.get("data_type", "text")
                    citations = normalize_citations(citations)
                    column_label = str(col_def.get("header") or excel_col)
                    display_label = column_label
                    if row_label:
                        display_label = f"{column_label} · {row_label}"
                    table_description = str(
                        table_def.get("description") or _humanize_identifier(table_id)
                    )
                    mappings.append({
                        "pdf_field_id": f"targeted_table_{table_id}_{excel_cell}",
                        "pdf_field_name": f"{table_id}:{excel_cell}",
                        "excel_cell": excel_cell,
                        "excel_sheet": table_def.get("sheet"),
                        "excel_label": f"{table_id}:{col_def.get('header', excel_col)} ({row_label or excel_row})",
                        "confidence": confidence,
                        "source": "targeted_schema",
                        "reasoning": row.get("reasoning") or f"Stage 2 targeted table extraction for '{table_id}'",
                        "citations": citations,
                        "extracted_value": value,
                        "data_type": data_type,
                        "schema_table_id": table_id,
                        "schema_table_row_label": row_label,
                        "schema_table_row_index": row_index,
                        "schema_table_column": excel_col,
                        "display_label": display_label,
                        "display_context": (
                            f"{_friendly_sheet_name(table_def.get('sheet', ''))} · "
                            f"{table_description}"
                        ),
                        "source_note": _source_note(
                            source_basis=None,
                            source_period=None,
                            section_label=table_description,
                            citations=citations,
                        ),
                    })

        logger.info(
            f"✓ Targeted schema table mappings: {len(mappings)} cells mapped "
            f"across {len(targeted_table_values)} tables"
        )
        return mappings

    def merge_mappings(
        self, schema_mappings: List[Dict[str, Any]], generic_mappings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Merge schema and generic mappings (schema takes priority on conflicts).

        Args:
            schema_mappings: Mappings from schema
            generic_mappings: Mappings from generic + LLM

        Returns:
            Merged list
        """
        # Build set of cells mapped by schema
        schema_cells = {f"{m['excel_sheet']}!{m['excel_cell']}" for m in schema_mappings}

        # Filter generic mappings to exclude schema cells
        filtered_generic = []
        conflicts = 0
        for mapping in generic_mappings:
            cell_key = f"{mapping['excel_sheet']}!{mapping['excel_cell']}"
            if cell_key in schema_cells:
                conflicts += 1
                logger.debug(f"Conflict: Generic mapping for {cell_key} overridden by schema")
            else:
                filtered_generic.append(mapping)

        merged = schema_mappings + filtered_generic

        logger.info(
            f"Merged mappings: {len(schema_mappings)} schema + {len(filtered_generic)} generic "
            f"= {len(merged)} total ({conflicts} conflicts resolved)"
        )

        return merged


# Singleton instance for easy import
coordinator = MappingCoordinator()
