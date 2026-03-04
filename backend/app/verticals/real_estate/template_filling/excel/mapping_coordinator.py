"""Coordinator for Excel field mapping - handles schema-based + generic fallback."""

from typing import Any, Dict, List, Optional

from openpyxl import Workbook

from app.utils.logging import logger

from .schema_based import SchemaLoader, SchemaMapper, TemplateIdentifier


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

            mappings.append({
                "pdf_field_id": f"targeted_{field_id}",
                "pdf_field_name": field_id,
                "excel_cell": field["value_cell"],
                "excel_sheet": field["sheet"],
                "excel_label": f"{field['sheet']}!{field.get('label_cell', '')}",
                "confidence": result["confidence"],
                "source": "targeted_schema",
                "reasoning": f"Stage 2 targeted extraction for schema field '{field_id}'",
                "citations": result.get("citations", []),
            })

        logger.info(
            f"✓ Targeted schema mappings: {len(mappings)}/{len(unmapped_fields)} fields found by LLM"
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
