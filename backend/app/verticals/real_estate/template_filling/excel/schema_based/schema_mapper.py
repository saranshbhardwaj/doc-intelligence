"""Schema-based field mapper - direct alias matching without LLM."""

from typing import Any, Dict, List

from app.utils.logging import logger

from .schema_loader import TemplateSchema


class SchemaMapper:
    """Maps PDF fields to Excel cells using predefined schema (no LLM required)."""

    def __init__(self, schema: TemplateSchema):
        """
        Initialize schema mapper.

        Args:
            schema: TemplateSchema object
        """
        self.schema = schema

    def map_fields(self, pdf_fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Map PDF fields to Excel cells using schema definitions.

        This is a deterministic, rule-based mapping - no LLM involved.

        Args:
            pdf_fields: List of PDF field dicts from extraction
                Each dict has: id, name, value, citations, etc.

        Returns:
            List of mapping dicts with:
                - pdf_field_id: ID from PDF
                - pdf_field_name: Name from PDF
                - excel_cell: Target cell (e.g., "C6")
                - excel_sheet: Target sheet name
                - excel_label: Field label from schema
                - confidence: Always 1.0 (schema match = perfect)
                - source: "schema"
                - reasoning: Match explanation
                - citations: Copied from PDF field
        """
        mappings = []
        matched_field_ids = set()  # Track which schema fields got matched

        logger.info(f"Schema mapping: {len(pdf_fields)} PDF fields against {len(self.schema.fields)} schema fields")

        for pdf_field in pdf_fields:
            pdf_field_id = pdf_field.get("id")
            pdf_field_name = pdf_field.get("name")
            pdf_value = pdf_field.get("value")

            if not pdf_field_name:
                continue

            # Find matching schema field by alias
            schema_field = self.schema.find_field_by_alias(pdf_field_name)

            if schema_field:
                field_id = schema_field["id"]

                # Skip if this schema field was already mapped
                # (One PDF field per schema field - if multiple PDF fields match, first wins)
                if field_id in matched_field_ids:
                    logger.debug(
                        f"Skipping duplicate schema field match: '{pdf_field_name}' → '{field_id}' "
                        f"(already mapped)"
                    )
                    continue

                # Create mapping
                mapping = {
                    "pdf_field_id": pdf_field_id,
                    "pdf_field_name": pdf_field_name,
                    "excel_cell": schema_field["value_cell"],
                    "excel_sheet": schema_field["sheet"],
                    "excel_label": f"{schema_field['sheet']}!{schema_field['label_cell']}",
                    "confidence": 1.0,  # Schema match = perfect confidence
                    "source": "schema",
                    "reasoning": f"Schema match: '{pdf_field_name}' → field '{field_id}'",
                    "citations": pdf_field.get("citations", []),
                }

                mappings.append(mapping)
                matched_field_ids.add(field_id)

                logger.debug(
                    f"✓ Schema mapping: '{pdf_field_name}' → "
                    f"{schema_field['sheet']}!{schema_field['value_cell']} "
                    f"(field '{field_id}', value='{pdf_value}')"
                )

        logger.info(
            f"Schema mapping complete: {len(mappings)} mappings created "
            f"({len(mappings)}/{len(self.schema.fields)} schema fields matched)"
        )

        return mappings

    def get_unmapped_schema_fields(self, mappings: List[Dict[str, Any]]) -> List[str]:
        """
        Get list of schema field IDs that were not mapped.

        Useful for diagnostics - shows which expected fields are missing from PDF.

        Args:
            mappings: List of mappings from map_fields()

        Returns:
            List of unmapped field IDs
        """
        mapped_cells = {f"{m['excel_sheet']}!{m['excel_cell']}" for m in mappings}

        unmapped_field_ids = []
        for field in self.schema.fields:
            cell_key = f"{field['sheet']}!{field['value_cell']}"
            if cell_key not in mapped_cells:
                unmapped_field_ids.append(field["id"])

        return unmapped_field_ids
