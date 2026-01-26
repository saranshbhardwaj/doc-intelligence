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
            generic_schema: Schema from TemplateAnalyzer.analyze()
            schema_mapped_cells: Set from get_schema_mapped_cells()

        Returns:
            Filtered schema dict
        """
        filtered_schema = {}

        for sheet_name, sheet_data in generic_schema.items():
            filtered_kv_pairs = []
            for kv_pair in sheet_data.get("key_value_pairs", []):
                cell_key = f"{sheet_name}!{kv_pair['cell']}"
                if cell_key not in schema_mapped_cells:
                    filtered_kv_pairs.append(kv_pair)

            # Keep tables as-is (schema doesn't handle dynamic tables yet)
            filtered_schema[sheet_name] = {
                "key_value_pairs": filtered_kv_pairs,
                "tables": sheet_data.get("tables", []),
            }

        # Count filtered cells
        original_count = sum(len(sheet.get("key_value_pairs", [])) for sheet in generic_schema.values())
        filtered_count = sum(len(sheet.get("key_value_pairs", [])) for sheet in filtered_schema.values())

        logger.info(
            f"Filtered generic schema: {original_count} → {filtered_count} cells "
            f"({original_count - filtered_count} excluded by schema)"
        )

        return filtered_schema

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
