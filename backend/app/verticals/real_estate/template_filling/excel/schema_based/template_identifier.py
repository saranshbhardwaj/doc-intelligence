"""Template identification using fingerprint matching."""

from typing import Optional

from openpyxl import Workbook

from app.utils.logging import logger

from .schema_loader import SchemaLoader


class TemplateIdentifier:
    """Identifies Excel templates by fingerprinting specific cells."""

    def __init__(self, schema_loader: SchemaLoader):
        """
        Initialize template identifier.

        Args:
            schema_loader: SchemaLoader instance
        """
        self.schema_loader = schema_loader

    def identify(self, workbook: Workbook) -> Optional[str]:
        """
        Identify template by checking fingerprint cells against all known schemas.

        Args:
            workbook: openpyxl Workbook object

        Returns:
            Schema ID if matched, None otherwise
        """
        available_schemas = self.schema_loader.list_available_schemas()

        if not available_schemas:
            logger.debug("No schemas available for identification")
            return None

        logger.debug(f"Checking template against {len(available_schemas)} schema(s)")

        # Check each schema
        for schema_id in available_schemas:
            schema = self.schema_loader.load_schema(schema_id)
            if not schema:
                continue

            if self._check_fingerprint(workbook, schema):
                logger.info(f"✓ Template matched schema: {schema_id} ({schema.name})")
                return schema_id

        logger.info("✗ Template did not match any known schema")
        return None

    def _check_fingerprint(self, workbook: Workbook, schema) -> bool:
        """
        Check if workbook matches schema fingerprint.

        Args:
            workbook: openpyxl Workbook
            schema: TemplateSchema object

        Returns:
            True if all fingerprint cells match
        """
        fingerprint_cells = schema.get_fingerprint_cells()

        if not fingerprint_cells:
            logger.warning(f"Schema '{schema.schema_id}' has no fingerprint cells")
            return False

        matched = 0
        total = len(fingerprint_cells)

        for fp_cell in fingerprint_cells:
            sheet_name = fp_cell["sheet"]
            cell_address = fp_cell["cell"]
            expected_value = fp_cell["expected_value"]

            # Check if sheet exists
            if sheet_name not in workbook.sheetnames:
                logger.debug(
                    f"Fingerprint mismatch: Sheet '{sheet_name}' not found "
                    f"(expected for schema '{schema.schema_id}')"
                )
                return False

            # Get cell value
            sheet = workbook[sheet_name]
            cell = sheet[cell_address]
            actual_value = cell.value

            # Normalize for comparison (case-insensitive, strip whitespace)
            actual_normalized = str(actual_value).strip() if actual_value else ""
            expected_normalized = str(expected_value).strip()

            # Check match
            if actual_normalized.lower() == expected_normalized.lower():
                matched += 1
                logger.debug(
                    f"Fingerprint match: {sheet_name}!{cell_address} = '{actual_value}' "
                    f"(expected '{expected_value}')"
                )
            else:
                logger.debug(
                    f"Fingerprint mismatch: {sheet_name}!{cell_address} = '{actual_value}' "
                    f"(expected '{expected_value}')"
                )
                return False

        # All fingerprint cells must match
        logger.debug(f"Fingerprint check: {matched}/{total} cells matched for schema '{schema.schema_id}'")
        return matched == total
