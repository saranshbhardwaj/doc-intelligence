"""Excel template handler using openpyxl - Facade pattern.

Analyzes Excel templates to detect fillable cells, formulas, and sheets.
Fills templates with extracted data while preserving formulas and formatting.

This is a facade that delegates to specialized helper modules:
- TemplateAnalyzer: Detects key-value fields and tables
- TemplateFiller: Fills templates with extracted data
- TableDetector: Detects table structures using 3-layer approach
- StyleInspector: Analyzes cell styling for header detection
"""

import hashlib
from pathlib import Path
from typing import Any, Dict

from openpyxl import load_workbook

from app.utils.logging import logger
from .excel import TemplateAnalyzer, TemplateFiller


class ExcelHandler:
    """Handler for Excel template operations using openpyxl (Facade pattern)."""

    def __init__(self):
        """Initialize Excel handler with helper modules."""
        self._analyzer = TemplateAnalyzer()
        self._filler = TemplateFiller()

    def analyze_template(self, file_path: str) -> Dict[str, Any]:
        """
        Analyze an Excel template to detect fillable cells, tables, formulas, and structure.

        Args:
            file_path: Path to the Excel file

        Returns:
            Dictionary with template schema:
            {
                "sheets": [
                    {
                        "name": "Summary",
                        "index": 0,
                        "key_value_fields": [
                            {
                                "cell": "B2",
                                "label": "Property Name",
                                "row": 2,
                                "col": 2,
                                "type": "text",
                                "current_value": "",
                                "is_merged": false
                            }
                        ],
                        "tables": [
                            {
                                "table_name": "Rent Roll",
                                "start_row": 27,
                                "start_col": 13,
                                "header_rows": 2,
                                "row_headers_col": null,
                                "column_headers": ["Floor Plan", "Bed", "Bath"],
                                "data_rows": 5,
                                "fillable_cells": [...]
                            }
                        ],
                        "formula_cells": ["D10", "E20"],
                        "total_rows": 50,
                        "total_cols": 10
                    }
                ],
                "total_key_value_fields": 45,
                "total_tables": 3,
                "has_formulas": true
            }
        """
        logger.info(f"Analyzing Excel template: {file_path}")

        try:
            # Only use keep_vba=True for .xlsm files to avoid corruption
            is_macro_enabled = file_path.lower().endswith('.xlsm')
            workbook = load_workbook(file_path, data_only=False, keep_vba=is_macro_enabled)

            # Delegate to TemplateAnalyzer
            schema = self._analyzer.analyze_template(workbook)

            workbook.close()

            return schema

        except Exception as e:
            logger.error(f"Error analyzing Excel template: {e}", exc_info=True)
            raise

    def fill_template(
        self,
        template_path: str,
        output_path: str,
        field_mapping: Dict[str, Any],
        extracted_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Fill an Excel template with extracted data.

        Args:
            template_path: Path to the original Excel template
            output_path: Path to save the filled Excel file
            field_mapping: Field mapping structure from TemplateFillRun
                {
                    "mappings": [
                        {
                            "pdf_field_id": "f1",
                            "excel_cell": "B2",
                            "excel_sheet": "Summary",
                            "excel_label": "Property Name"
                        }
                    ]
                }
            extracted_data: Extracted data from PDF
                {
                    "f1": {
                        "value": "Sunset Plaza",
                        "confidence": 0.95
                    }
                }

        Returns:
            Summary of fill operation:
            {
                "total_cells_filled": 45,
                "sheets_modified": ["Summary", "Details"],
                "formulas_preserved": true,
                "errors": []
            }
        """
        # Delegate to TemplateFiller
        return self._filler.fill_template(template_path, output_path, field_mapping, extracted_data)

    def compute_file_hash(self, file_path: str) -> str:
        """
        Compute SHA256 hash of a file for deduplication.

        Args:
            file_path: Path to file

        Returns:
            Hex digest of SHA256 hash
        """
        sha256_hash = hashlib.sha256()

        with open(file_path, "rb") as f:
            # Read in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        return sha256_hash.hexdigest()

    def get_file_size(self, file_path: str) -> int:
        """
        Get file size in bytes.

        Args:
            file_path: Path to file

        Returns:
            File size in bytes
        """
        return Path(file_path).stat().st_size
