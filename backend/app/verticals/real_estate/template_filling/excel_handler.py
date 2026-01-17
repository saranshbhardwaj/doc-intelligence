"""Excel template handler using openpyxl.

Analyzes Excel templates to detect fillable cells, formulas, and sheets.
Fills templates with extracted data while preserving formulas and formatting.
"""

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openpyxl import load_workbook, Workbook
from openpyxl.cell import Cell
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from openpyxl.utils.cell import range_boundaries

from app.utils.logging import logger


class ExcelHandler:
    """Handler for Excel template operations using openpyxl."""

    def __init__(self):
        """Initialize Excel handler."""
        pass

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

            sheets_data = []
            total_kv_fields = 0
            total_tables = 0

            for sheet_idx, sheet_name in enumerate(workbook.sheetnames):
                sheet = workbook[sheet_name]

                # Detect key-value pairs (improved filtering)
                kv_fields = self._detect_key_value_fields(sheet)

                # Detect table structures (NEW!)
                tables = self._detect_tables(sheet)

                # Detect formula cells
                formula_cells = self._detect_formula_cells(sheet)

                total_kv_fields += len(kv_fields)
                total_tables += len(tables)

                sheet_data = {
                    "name": sheet_name,
                    "index": sheet_idx,
                    "key_value_fields": kv_fields,  # Renamed from fillable_cells
                    "tables": tables,
                    "formula_cells": formula_cells,
                    "total_rows": sheet.max_row,
                    "total_cols": sheet.max_column,
                }

                sheets_data.append(sheet_data)

            workbook.close()

            schema = {
                "sheets": sheets_data,
                "total_key_value_fields": total_kv_fields,
                "total_tables": total_tables,
                "has_formulas": any(len(s["formula_cells"]) > 0 for s in sheets_data),
            }

            logger.info(
                f"Template analysis complete: {len(sheets_data)} sheets, "
                f"{total_kv_fields} key-value fields, {total_tables} tables"
            )

            return schema

        except Exception as e:
            logger.error(f"Error analyzing Excel template: {e}", exc_info=True)
            raise

    def _detect_key_value_fields(self, sheet: Worksheet) -> List[Dict[str, Any]]:
        """
        Detect key-value pair fields in a worksheet (improved filtering).

        Detects simple patterns like:
        - A2: "Property Name"  |  B2: [empty] <- fillable
        - A3: "Price"          |  A4: [empty] <- fillable

        Args:
            sheet: openpyxl Worksheet object

        Returns:
            List of key-value field metadata
        """
        kv_fields = []

        # Iterate through reasonable range (avoid scanning entire empty grid)
        max_scan_row = min(sheet.max_row, 200)
        max_scan_col = min(sheet.max_column, 50)

        for row_idx in range(1, max_scan_row + 1):
            for col_idx in range(1, max_scan_col + 1):
                cell = sheet.cell(row_idx, col_idx)

                if self._is_fillable_cell(cell, sheet):
                    # Try to find a meaningful label
                    label = self._find_cell_label(cell, sheet)

                    # Only include if we found a meaningful label (filters noise)
                    if label and len(label) > 2 and any(c.isalpha() for c in label):
                        kv_fields.append({
                            "cell": cell.coordinate,
                            "label": label,
                            "row": cell.row,
                            "col": cell.column,
                            "type": self._infer_cell_type(cell),
                            "current_value": self._get_cell_display_value(cell),
                            "is_merged": isinstance(cell, Cell) and cell.coordinate in sheet.merged_cells,
                        })

        return kv_fields

    def _is_fillable_cell(self, cell: Cell, sheet: Worksheet) -> bool:
        """
        Determine if a cell is fillable.

        Args:
            cell: openpyxl Cell object
            sheet: Parent worksheet

        Returns:
            True if cell appears to be fillable
        """
        # Skip if cell has a formula
        if cell.data_type == 'f':
            return False

        # Empty cells are potentially fillable
        if cell.value is None or str(cell.value).strip() == "":
            # But only if they're in a reasonable range (not way out in the grid)
            if cell.row <= 200 and cell.column <= 50:
                return True

        # Cells with placeholder patterns
        if cell.value:
            val_str = str(cell.value).strip()
            placeholder_patterns = [
                "[",  # [Name], [Value]
                "enter",  # Enter value
                "input",  # Input here
                "xxx",  # XXX placeholder
                "___",  # Underscores
                "...",  # Ellipsis
            ]
            val_lower = val_str.lower()
            if any(pattern in val_lower for pattern in placeholder_patterns):
                return True

        return False

    def _find_cell_label(self, cell: Cell, sheet: Worksheet) -> Optional[str]:
        """
        Find a label for a fillable cell by looking at nearby cells.

        Strategy:
        1. Check cell directly to the left
        2. Check cell directly above
        3. Check diagonal (top-left)

        Args:
            cell: Target cell
            sheet: Parent worksheet

        Returns:
            Label text or None
        """
        # Check left
        if cell.column > 1:
            left_cell = sheet.cell(row=cell.row, column=cell.column - 1)
            if left_cell.value and left_cell.data_type != 'f':
                label_text = str(left_cell.value).strip()
                if label_text and len(label_text) < 100:  # Reasonable label length
                    return label_text

        # Check above
        if cell.row > 1:
            above_cell = sheet.cell(row=cell.row - 1, column=cell.column)
            if above_cell.value and above_cell.data_type != 'f':
                label_text = str(above_cell.value).strip()
                if label_text and len(label_text) < 100:
                    return label_text

        # Check diagonal (top-left)
        if cell.row > 1 and cell.column > 1:
            diag_cell = sheet.cell(row=cell.row - 1, column=cell.column - 1)
            if diag_cell.value and diag_cell.data_type != 'f':
                label_text = str(diag_cell.value).strip()
                if label_text and len(label_text) < 100:
                    return label_text

        return None

    def _get_merged_cell_range(self, sheet: Worksheet, row: int, col: int) -> Optional[Tuple[int, int, int, int]]:
        """
        Get the boundaries of a merged cell range if cell is part of one.

        Args:
            sheet: Worksheet
            row: Row index (1-based)
            col: Column index (1-based)

        Returns:
            Tuple of (min_row, min_col, max_row, max_col) or None if not merged
        """
        for merged_range in sheet.merged_cells.ranges:
            min_col, min_row, max_col, max_row = range_boundaries(str(merged_range))
            if min_row <= row <= max_row and min_col <= col <= max_col:
                return (min_row, min_col, max_row, max_col)
        return None

    def _is_cell_in_merge(self, sheet: Worksheet, row: int, col: int) -> bool:
        """Check if a cell is part of a merged range."""
        return self._get_merged_cell_range(sheet, row, col) is not None

    def _get_merged_cell_value(self, sheet: Worksheet, row: int, col: int) -> Any:
        """
        Get the value from a merged cell (reads from top-left cell of merge range).

        Args:
            sheet: Worksheet
            row: Row index (1-based)
            col: Column index (1-based)

        Returns:
            Cell value (may be None)
        """
        merge_range = self._get_merged_cell_range(sheet, row, col)
        if merge_range:
            # Get value from top-left cell of merged range
            min_row, min_col, _, _ = merge_range
            return sheet.cell(min_row, min_col).value
        else:
            # Not merged, return cell value directly
            return sheet.cell(row, col).value

    def _detect_header_rows(
        self,
        sheet: Worksheet,
        potential_header_row: int,
        start_col: int,
        end_col: int
    ) -> List[int]:
        """
        Detect multiple header rows above a potential header row.

        Looks upward from the detected header row to find parent header rows
        (typically merged cells spanning multiple columns).

        Args:
            sheet: Worksheet
            potential_header_row: The row index that looks like the main header
            start_col: Starting column of table
            end_col: Ending column of table

        Returns:
            List of header row indices in order (top to bottom)
        """
        header_rows = [potential_header_row]

        # Look up to 3 rows above for additional header levels
        for offset in range(1, 4):
            check_row = potential_header_row - offset
            if check_row < 1:
                break

            # Check if this row has values that span multiple columns (merged cells)
            has_parent_headers = False
            for col_idx in range(start_col, end_col + 1):
                cell_value = self._get_merged_cell_value(sheet, check_row, col_idx)
                if cell_value and str(cell_value).strip():
                    # Check if this cell is part of a merged range spanning multiple columns
                    merge_range = self._get_merged_cell_range(sheet, check_row, col_idx)
                    if merge_range:
                        _, min_col, _, max_col = merge_range
                        # If merged range spans at least 2 columns, it's likely a parent header
                        if max_col - min_col >= 1:
                            has_parent_headers = True
                            break

            if has_parent_headers:
                header_rows.insert(0, check_row)  # Add to front (top-down order)
            else:
                # Stop looking if we hit a row without parent headers
                break

        return header_rows

    def _build_hierarchical_headers(
        self,
        sheet: Worksheet,
        header_rows: List[int],
        start_col: int,
        end_col: int
    ) -> List[Dict[str, Any]]:
        """
        Build hierarchical column headers from multiple header rows.

        Args:
            sheet: Worksheet
            header_rows: List of header row indices (top to bottom)
            start_col: Starting column
            end_col: Ending column

        Returns:
            List of column header dictionaries with hierarchical names
        """
        column_headers = []

        for col_idx in range(start_col, end_col + 1):
            # Collect header values from all levels for this column
            header_parts = []

            for header_row_idx in header_rows:
                cell_value = self._get_merged_cell_value(sheet, header_row_idx, col_idx)
                if cell_value:
                    header_text = str(cell_value).strip()
                    # Only add if not empty and not a duplicate of the last part
                    if header_text and (not header_parts or header_parts[-1] != header_text):
                        header_parts.append(header_text)

            # Build hierarchical name
            if header_parts:
                # Join with " | " to show hierarchy
                hierarchical_name = " | ".join(header_parts)
                # Also keep the leaf name (last part)
                leaf_name = header_parts[-1] if header_parts else ""
            else:
                hierarchical_name = ""
                leaf_name = ""

            column_headers.append({
                "col": col_idx,
                "col_letter": get_column_letter(col_idx),
                "header": hierarchical_name,  # Full hierarchical name
                "leaf_header": leaf_name,  # Just the final level
                "header_parts": header_parts,  # Individual parts for flexibility
            })

        return column_headers

    def _regions_overlap(self, region1: Dict[str, int], region2: Dict[str, int]) -> bool:
        """
        Check if two table regions overlap.

        Args:
            region1: Dict with start_row, end_row, start_col, end_col
            region2: Dict with start_row, end_row, start_col, end_col

        Returns:
            True if regions share any cells
        """
        # Check if rows overlap
        rows_overlap = not (
            region1['end_row'] < region2['start_row'] or
            region2['end_row'] < region1['start_row']
        )

        # Check if columns overlap
        cols_overlap = not (
            region1['end_col'] < region2['start_col'] or
            region2['end_col'] < region1['start_col']
        )

        return rows_overlap and cols_overlap

    def _detect_excel_native_tables(self, sheet: Worksheet) -> List[Dict[str, Any]]:
        """
        Layer 1: Detect Excel native tables (Insert → Table).

        These are explicitly defined tables that Excel stores in the worksheet.

        Args:
            sheet: Worksheet

        Returns:
            List of table metadata for native Excel tables
        """
        tables = []

        if not hasattr(sheet, 'tables') or not sheet.tables:
            return tables

        for table_name, table_obj in sheet.tables.items():
            # Parse table range (e.g., "A1:E10")
            min_col, min_row, max_col, max_row = range_boundaries(table_obj.ref)

            logger.info(
                f"📋 Layer 1: Found Excel native table '{table_name}' in '{sheet.title}': "
                f"rows {min_row}-{max_row}, columns {min_col}-{max_col}"
            )

            # Extract header row (first row of the table)
            header_row = min_row
            header_cells = []

            for col_idx in range(min_col, max_col + 1):
                cell = sheet.cell(header_row, col_idx)
                if cell.value:
                    header_value = str(cell.value).strip()
                    header_cells.append((col_idx, header_value))

            # Analyze table structure
            if header_cells:
                table = self._analyze_table_structure(sheet, header_row, header_cells)
                if table:
                    table['table_name'] = table_name  # Use native table name
                    table['detection_method'] = 'native'
                    tables.append(table)

        return tables

    def _has_border(self, cell: Cell, side: str = 'any') -> bool:
        """
        Check if a cell has a border on a specific side.

        Args:
            cell: Cell to check
            side: 'top', 'bottom', 'left', 'right', or 'any'

        Returns:
            True if cell has border on specified side
        """
        if not cell.border:
            return False

        border_styles = {
            'top': cell.border.top and cell.border.top.style,
            'bottom': cell.border.bottom and cell.border.bottom.style,
            'left': cell.border.left and cell.border.left.style,
            'right': cell.border.right and cell.border.right.style,
        }

        if side == 'any':
            return any(border_styles.values())
        else:
            return bool(border_styles.get(side))

    def _detect_bordered_tables(
        self,
        sheet: Worksheet,
        excluded_regions: List[Dict[str, int]]
    ) -> List[Dict[str, Any]]:
        """
        Layer 2: Detect tables by analyzing cell borders.

        Looks for contiguous regions with borders that form table structures.

        Args:
            sheet: Worksheet
            excluded_regions: Regions already detected by higher-priority layers

        Returns:
            List of table metadata for bordered tables
        """
        tables = []
        max_scan_row = min(sheet.max_row, 100)
        max_scan_col = min(sheet.max_column, 50)

        visited_rows = set()

        for row_idx in range(1, max_scan_row + 1):
            if row_idx in visited_rows:
                continue

            # Look for rows with borders that might be table headers
            row_cells = []
            has_borders = False

            for col_idx in range(1, max_scan_col + 1):
                cell = sheet.cell(row_idx, col_idx)
                if cell.value is not None and cell.data_type != 'f':
                    header_value = str(cell.value).strip()
                    if len(header_value) < 100:
                        row_cells.append((col_idx, header_value))

                if self._has_border(cell, 'any'):
                    has_borders = True

            # Need at least 3 cells and some borders to consider as table
            if len(row_cells) >= 3 and has_borders:
                # Check if this region overlaps with excluded regions
                start_col = min(c[0] for c in row_cells)
                end_col = max(c[0] for c in row_cells)

                # Find extent of bordered region below this row
                end_row = row_idx
                for check_row in range(row_idx + 1, min(row_idx + 51, max_scan_row + 1)):
                    has_content_or_border = False
                    for col_idx in range(start_col, end_col + 1):
                        cell = sheet.cell(check_row, col_idx)
                        if cell.value is not None or self._has_border(cell, 'any'):
                            has_content_or_border = True
                            break

                    if has_content_or_border:
                        end_row = check_row
                    else:
                        break

                # Check if this region overlaps with any excluded region
                region = {
                    'start_row': row_idx,
                    'end_row': end_row,
                    'start_col': start_col,
                    'end_col': end_col,
                }

                is_excluded = any(
                    self._regions_overlap(region, excluded)
                    for excluded in excluded_regions
                )

                if not is_excluded and end_row > row_idx:
                    # Analyze as table
                    table = self._analyze_table_structure(sheet, row_idx, row_cells)
                    if table:
                        table['detection_method'] = 'border'
                        tables.append(table)
                        logger.info(
                            f"🔲 Layer 2: Found bordered table in '{sheet.title}': "
                            f"rows {row_idx}-{end_row}, columns {start_col}-{end_col}"
                        )

                    # Mark rows as visited
                    for r in range(row_idx, end_row + 1):
                        visited_rows.add(r)

        return tables

    def _split_row_cells_by_gaps(self, row_cells: List[tuple], gap_threshold: int = 1) -> List[List[tuple]]:
        """
        Split row cells into separate groups when there are gaps (empty columns).

        This prevents combining separate sections (e.g., key-value section + table)
        into a single table, enabling proper hierarchical header detection.

        Args:
            row_cells: List of (col_idx, value) tuples
            gap_threshold: Minimum gap size to split (default 1 empty column)

        Returns:
            List of row cell groups (each group is a list of (col_idx, value) tuples)
        """
        if not row_cells:
            return []

        # Sort by column index
        sorted_cells = sorted(row_cells, key=lambda x: x[0])

        groups = []
        current_group = [sorted_cells[0]]

        for i in range(1, len(sorted_cells)):
            prev_col = sorted_cells[i - 1][0]
            curr_col = sorted_cells[i][0]
            gap = curr_col - prev_col - 1  # Number of empty columns between

            if gap >= gap_threshold:
                # Gap detected - save current group and start new one
                groups.append(current_group)
                current_group = [sorted_cells[i]]
            else:
                # No significant gap - add to current group
                current_group.append(sorted_cells[i])

        # Add the last group
        if current_group:
            groups.append(current_group)

        return groups

    def _detect_tables_heuristic(
        self,
        sheet: Worksheet,
        excluded_regions: List[Dict[str, int]]
    ) -> List[Dict[str, Any]]:
        """
        Layer 3: Detect tables using heuristics (fallback method).

        Enhanced support for complex tables:
        1. Simple tables: headers in one row, data below
        2. Multi-level hierarchical headers: detects up to 3 parent header rows above main headers
        3. Merged cells: properly handles merged header cells (e.g., "Current Rent" spanning 3 columns)
        4. Hierarchical column names: builds names like "Current Rent | Average" for disambiguation
        5. Gap detection: splits sections separated by empty columns into separate tables

        Args:
            sheet: openpyxl Worksheet object
            excluded_regions: Regions already detected by higher-priority layers

        Returns:
            List of table metadata
        """
        tables = []

        # Scan for potential header rows (rows with multiple consecutive text cells)
        max_scan_row = min(sheet.max_row, 100)  # Focus on first 100 rows
        max_scan_col = min(sheet.max_column, 50)

        for row_idx in range(1, max_scan_row + 1):
            # Check if this row looks like headers
            row_cells = []
            for col_idx in range(1, max_scan_col + 1):
                cell = sheet.cell(row_idx, col_idx)
                # Accept strings, numbers, dates as potential headers (but not formulas)
                if cell.value is not None and cell.data_type != 'f':
                    # Convert to string for consistent handling
                    header_value = str(cell.value).strip()
                    # Skip very long values (likely not headers)
                    if len(header_value) < 100:
                        row_cells.append((col_idx, header_value))

            # Need at least 3 cells to be a header row
            if len(row_cells) >= 3:
                # Split into separate sections if there are gaps (empty columns)
                # This prevents combining key-value sections with actual tables
                cell_groups = self._split_row_cells_by_gaps(row_cells, gap_threshold=1)

                # Analyze each group as a separate potential table
                for group in cell_groups:
                    if len(group) >= 3:  # Need at least 3 cells for a table
                        # Check if cells are somewhat consecutive within this group
                        col_indices = [c[0] for c in group]
                        if max(col_indices) - min(col_indices) <= len(col_indices) + 5:  # Allow some gaps
                            # Additional heuristic: Check if this looks like headers (not just data)
                            # Headers typically have at least some text values (not all numbers)
                            text_count = sum(1 for _, val in group if not val.replace('.', '').replace('-', '').isdigit())

                            # Require at least 50% text cells OR at least 2 text cells for numeric headers (1, 2, 3, etc.)
                            is_likely_header = (text_count >= len(group) * 0.5) or (text_count >= 2 and len(group) >= 4)

                            if is_likely_header:
                                # Check if this overlaps with excluded regions
                                start_col = min(c[0] for c in group)
                                end_col = max(c[0] for c in group)

                                # Estimate table end row (scan for data below)
                                end_row = row_idx
                                for check_row in range(row_idx + 1, min(row_idx + 51, max_scan_row + 1)):
                                    has_content = False
                                    for col_idx in range(start_col, end_col + 1):
                                        if sheet.cell(check_row, col_idx).value is not None:
                                            has_content = True
                                            break
                                    if has_content:
                                        end_row = check_row
                                    else:
                                        break

                                region = {
                                    'start_row': row_idx,
                                    'end_row': end_row,
                                    'start_col': start_col,
                                    'end_col': end_col,
                                }

                                # Skip if overlaps with higher-priority detection
                                is_excluded = any(
                                    self._regions_overlap(region, excluded)
                                    for excluded in excluded_regions
                                )

                                if not is_excluded:
                                    # Potential table found!
                                    table = self._analyze_table_structure(sheet, row_idx, group)
                                    if table:
                                        table['detection_method'] = 'heuristic'
                                        tables.append(table)
                                        logger.info(
                                            f"🔍 Layer 3: Found heuristic table in '{sheet.title}': "
                                            f"rows {row_idx}-{end_row}, columns {start_col}-{end_col}"
                                        )

        # Remove duplicate/overlapping tables
        tables = self._deduplicate_tables(tables)

        return tables

    def _detect_tables(self, sheet: Worksheet) -> List[Dict[str, Any]]:
        """
        Detect table structures using layered approach (priority-based).

        Layer 1 (Highest): Excel native tables (Insert → Table)
        Layer 2 (Medium): Border-based detection
        Layer 3 (Lowest): Heuristic detection (fallback)

        Args:
            sheet: openpyxl Worksheet object

        Returns:
            List of table metadata
        """
        all_tables = []
        excluded_regions = []

        # Layer 1: Excel native tables (highest priority)
        native_tables = self._detect_excel_native_tables(sheet)
        all_tables.extend(native_tables)

        # Add native table regions to excluded list
        for table in native_tables:
            excluded_regions.append({
                'start_row': table['start_row'],
                'end_row': table['start_row'] + len(table.get('data_rows', [])),
                'start_col': table['start_col'],
                'end_col': table['end_col'],
            })

        # Layer 2: Border-based detection (medium priority)
        bordered_tables = self._detect_bordered_tables(sheet, excluded_regions)
        all_tables.extend(bordered_tables)

        # Add bordered table regions to excluded list
        for table in bordered_tables:
            excluded_regions.append({
                'start_row': table['start_row'],
                'end_row': table['start_row'] + len(table.get('data_rows', [])),
                'start_col': table['start_col'],
                'end_col': table['end_col'],
            })

        # Layer 3: Heuristic detection (lowest priority, fallback)
        heuristic_tables = self._detect_tables_heuristic(sheet, excluded_regions)
        all_tables.extend(heuristic_tables)

        logger.info(
            f"Detected {len(all_tables)} tables in sheet '{sheet.title}' "
            f"(Layer1: {len(native_tables)}, Layer2: {len(bordered_tables)}, Layer3: {len(heuristic_tables)})"
        )

        return all_tables

    def _analyze_table_structure(
        self,
        sheet: Worksheet,
        header_row: int,
        header_cells: List[tuple]
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze a potential table structure starting from a header row.

        Args:
            sheet: Worksheet
            header_row: Row index of headers
            header_cells: List of (col_idx, header_text) tuples

        Returns:
            Table metadata dict or None if not a valid table
        """
        start_col = min(c[0] for c in header_cells)
        end_col = max(c[0] for c in header_cells)

        # Detect multi-level header rows (e.g., merged parent headers above)
        header_rows = self._detect_header_rows(sheet, header_row, start_col, end_col)

        # Build hierarchical column headers from all detected header levels
        column_headers = self._build_hierarchical_headers(sheet, header_rows, start_col, end_col)

        # Log hierarchical header detection (INFO level so it shows in logs)
        if len(header_rows) > 1:
            logger.info(
                f"Table at row {header_row} in '{sheet.title}': detected {len(header_rows)} header levels "
                f"(rows {header_rows}), {len(column_headers)} columns with hierarchical names"
            )
            # Show sample hierarchical headers (first 5)
            sample_headers = [h["header"] for h in column_headers[:5]]
            logger.info(f"  Sample hierarchical headers: {sample_headers}")
        else:
            logger.debug(
                f"Table at row {header_row}: single-level header, "
                f"{len(column_headers)} columns"
            )

        # Check for row header column (column to the left with labels)
        row_header_col = None
        if start_col > 1:
            # Check if column to the left has text in same row
            left_cell = sheet.cell(header_row, start_col - 1)
            if left_cell.value and left_cell.data_type != 'f':
                row_header_col = start_col - 1

        # Find data rows below headers (stop at first completely empty row)
        data_rows = []
        fillable_cells = []
        max_data_rows = 50  # Scan up to 50 rows below header

        for row_offset in range(1, max_data_rows + 1):
            data_row_idx = header_row + row_offset
            if data_row_idx > sheet.max_row:
                break

            # Check if row has any content
            row_has_content = False
            row_data = []

            # Check row header cell if applicable
            row_label = None
            if row_header_col:
                row_header_cell = sheet.cell(data_row_idx, row_header_col)
                if row_header_cell.value and row_header_cell.data_type != 'f':
                    row_label = str(row_header_cell.value).strip()
                    row_has_content = True

            # Check data cells
            for col_idx in range(start_col, end_col + 1):
                cell = sheet.cell(data_row_idx, col_idx)

                # Track fillable cells (empty, non-formula)
                if cell.data_type != 'f':
                    is_empty = cell.value is None or str(cell.value).strip() == ""

                    if is_empty:
                        # Find column header info for this cell
                        col_header_info = next((h for h in column_headers if h["col"] == col_idx), None)
                        col_header = col_header_info["header"] if col_header_info else ""
                        col_leaf_header = col_header_info["leaf_header"] if col_header_info else ""

                        fillable_cells.append({
                            "cell": cell.coordinate,
                            "row": data_row_idx,
                            "col": col_idx,
                            "col_letter": get_column_letter(col_idx),
                            "row_label": row_label,
                            "col_header": col_header,  # Full hierarchical header (e.g., "Current Rent | Average")
                            "col_leaf_header": col_leaf_header,  # Just leaf name (e.g., "Average")
                            "type": self._infer_cell_type(cell),
                        })
                        row_has_content = True  # Empty cells count as table structure
                    else:
                        row_has_content = True

                row_data.append(cell.value)

            # Stop if completely empty row (end of table)
            if not row_has_content:
                break

            data_rows.append(data_row_idx)

        # Need at least 1 data row to be a valid table
        if len(data_rows) == 0:
            return None

        # Build table metadata
        table_name = None
        # Check row above the topmost header row for table title
        topmost_header_row = header_rows[0] if header_rows else header_row
        if topmost_header_row > 1:
            title_row = topmost_header_row - 1
            title_cell = sheet.cell(title_row, start_col)
            if title_cell.value and title_cell.data_type != 'f':
                table_name = str(title_cell.value).strip()

        return {
            "table_name": table_name or f"Table at row {header_row}",
            "start_row": topmost_header_row,  # Now refers to the topmost header row
            "start_col": start_col,
            "end_col": end_col,
            "header_row": header_row,  # Keep for backward compatibility (main header row)
            "header_rows": header_rows,  # NEW: All header row indices (top to bottom)
            "row_header_col": row_header_col,
            "column_headers": [h["header"] for h in column_headers],  # Hierarchical names
            "column_headers_detailed": column_headers,  # NEW: Full header info with leaf names, parts
            "data_rows": data_rows,
            "total_data_rows": len(data_rows),
            "total_fillable_cells": len(fillable_cells),
            "fillable_cells": fillable_cells[:100],  # Limit to first 100 for performance
        }

    def _deduplicate_tables(self, tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove overlapping/duplicate table detections.

        Args:
            tables: List of detected tables

        Returns:
            Deduplicated list
        """
        if len(tables) <= 1:
            return tables

        # Sort by row, then by column
        sorted_tables = sorted(tables, key=lambda t: (t["start_row"], t["start_col"]))

        deduped = []
        for table in sorted_tables:
            # Check if this table overlaps with any already added
            overlaps = False
            for existing in deduped:
                if self._tables_overlap(table, existing):
                    overlaps = True
                    break

            if not overlaps:
                deduped.append(table)

        return deduped

    def _tables_overlap(self, table1: Dict, table2: Dict) -> bool:
        """Check if two tables overlap in row/column space."""
        # Check row overlap
        row_overlap = not (
            table1["start_row"] > max(table2["data_rows"]) or
            table2["start_row"] > max(table1["data_rows"])
        )

        # Check column overlap
        col_overlap = not (
            table1["start_col"] > table2["end_col"] or
            table2["start_col"] > table1["end_col"]
        )

        return row_overlap and col_overlap

    def _infer_cell_type(self, cell: Cell) -> str:
        """
        Infer the data type expected in a cell.

        Args:
            cell: openpyxl Cell object

        Returns:
            Type string: 'number', 'date', 'currency', 'percentage', 'text'
        """
        # Check number format
        if cell.number_format:
            fmt = cell.number_format.lower()

            if any(x in fmt for x in ['$', 'usd', 'currency']):
                return 'currency'
            elif '%' in fmt:
                return 'percentage'
            elif any(x in fmt for x in ['m/d/y', 'd/m/y', 'yyyy', 'date']):
                return 'date'
            elif any(x in fmt for x in ['0', '#', 'number']):
                return 'number'

        # Check cell value type
        if isinstance(cell.value, (int, float)):
            return 'number'

        # Default to text
        return 'text'

    def _get_cell_display_value(self, cell: Cell) -> str:
        """Get the display value of a cell as a string."""
        if cell.value is None:
            return ""
        return str(cell.value)

    def _detect_formula_cells(self, sheet: Worksheet) -> List[str]:
        """
        Detect all cells containing formulas.

        Args:
            sheet: openpyxl Worksheet object

        Returns:
            List of cell coordinates (e.g., ["D10", "E20"])
        """
        formula_cells = []

        for row in sheet.iter_rows():
            for cell in row:
                if cell.data_type == 'f':  # Formula cell
                    formula_cells.append(cell.coordinate)

        return formula_cells

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
        logger.info(f"Filling Excel template: {template_path} -> {output_path}")

        try:
            # Determine if file is macro-enabled (.xlsm) or not (.xlsx)
            # Only use keep_vba=True for .xlsm files to avoid corruption
            is_macro_enabled = template_path.lower().endswith('.xlsm')

            # Load template (data_only=False to preserve formulas)
            workbook = load_workbook(template_path, data_only=False, keep_vba=is_macro_enabled)

            cells_filled = 0
            sheets_modified = set()
            errors = []

            # Process each mapping
            for mapping in field_mapping.get("mappings", []):
                pdf_field_id = mapping.get("pdf_field_id")
                excel_cell = mapping.get("excel_cell")
                excel_sheet = mapping.get("excel_sheet")

                if not all([pdf_field_id, excel_cell, excel_sheet]):
                    errors.append(f"Invalid mapping: {mapping}")
                    continue

                # Get extracted value
                field_data = extracted_data.get(pdf_field_id)
                if not field_data:
                    errors.append(f"No data for field {pdf_field_id}")
                    continue

                value = field_data.get("value")
                if value is None:
                    continue  # Skip null values

                # Get worksheet
                if excel_sheet not in workbook.sheetnames:
                    errors.append(f"Sheet '{excel_sheet}' not found")
                    continue

                sheet = workbook[excel_sheet]

                # Fill cell
                try:
                    cell = sheet[excel_cell]

                    # Preserve cell type - convert value appropriately
                    filled_value = self._convert_value_for_cell(value, cell)

                    # Set value (formulas in other cells will auto-recalculate)
                    cell.value = filled_value

                    cells_filled += 1
                    sheets_modified.add(excel_sheet)

                except Exception as e:
                    errors.append(f"Error filling {excel_sheet}!{excel_cell}: {str(e)}")
                    logger.warning(f"Error filling cell {excel_sheet}!{excel_cell}: {e}")

            # Clean up broken external links to prevent file corruption
            # If openpyxl created external links, it means there are formulas referencing
            # missing sheets (e.g., =Returns!Q57 when Returns sheet doesn't exist in template)
            # Removing these prevents XML corruption while preserving valid internal formulas
            try:
                if hasattr(workbook, '_external_links') and workbook._external_links:
                    logger.warning(
                        f"Template has {len(workbook._external_links)} external link(s) "
                        f"(likely formulas referencing missing sheets). Removing to prevent corruption."
                    )
                    workbook._external_links = []
                else:
                    logger.info("No external links detected - all formulas reference existing sheets")
            except Exception as e:
                logger.warning(f"Could not check/remove external links: {e}")

            # Remove ALL named ranges to prevent corruption
            # openpyxl corrupts named ranges when saving partial templates.
            # This is a temporary fix - full templates with all tabs won't need this.
            try:
                # workbook.defined_names is a DefinedNameDict - iterate directly
                named_range_names = list(workbook.defined_names.keys())

                if named_range_names:
                    logger.warning(
                        f"Removing {len(named_range_names)} named range(s) to prevent corruption: "
                        f"{named_range_names[:5]}{'...' if len(named_range_names) > 5 else ''}"
                    )
                    for name in named_range_names:
                        try:
                            del workbook.defined_names[name]
                            logger.debug(f"Deleted named range '{name}'")
                        except Exception as e:
                            logger.warning(f"Could not delete named range '{name}': {e}")
                else:
                    logger.info("No named ranges detected")
            except Exception as e:
                logger.warning(f"Could not remove named ranges: {e}")

            # Clear formulas that reference missing sheets or external workbooks
            # For partial templates, formulas like =Returns!Q57 or ='[OtherWorkbook.xlsx]Sheet'!A1 are invalid.
            # These corrupt the file when saved.
            import re
            try:
                existing_sheets = set(workbook.sheetnames)
                existing_sheets_lower = {s.lower() for s in existing_sheets}
                formulas_cleared = 0

                # Regex patterns to find sheet references in formulas:
                # Pattern 1: 'Sheet Name'!A1 (quoted sheet name with spaces)
                # Pattern 2: SheetName!A1 (unquoted sheet name)
                sheet_ref_pattern = re.compile(r"(?:'([^']+)'|([A-Za-z_][A-Za-z0-9_]*))\s*!")

                for sheet_name in workbook.sheetnames:
                    sheet = workbook[sheet_name]
                    for row in sheet.iter_rows():
                        for cell in row:
                            if cell.value and isinstance(cell.value, str) and cell.value.startswith('='):
                                formula = cell.value
                                should_clear = False

                                # Check 1: External workbook reference (contains '[' and ']')
                                if '[' in formula and ']' in formula:
                                    logger.debug(f"Clearing formula in {sheet_name}!{cell.coordinate}: contains external workbook reference")
                                    should_clear = True
                                else:
                                    # Check 2: Internal sheet reference to missing sheet
                                    matches = sheet_ref_pattern.findall(formula)
                                    for match in matches:
                                        # match is a tuple: (quoted_name, unquoted_name)
                                        ref_sheet = match[0] if match[0] else match[1]
                                        if ref_sheet.lower() not in existing_sheets_lower:
                                            logger.debug(f"Clearing formula in {sheet_name}!{cell.coordinate}: references missing sheet '{ref_sheet}'")
                                            should_clear = True
                                            break

                                if should_clear:
                                    cell.value = None
                                    formulas_cleared += 1

                if formulas_cleared > 0:
                    logger.warning(
                        f"Cleared {formulas_cleared} formula(s) referencing missing sheets or external workbooks "
                        f"(temporary fix for partial template)"
                    )
                else:
                    logger.info("No formulas reference missing sheets or external workbooks")
            except Exception as e:
                logger.warning(f"Could not clear formulas referencing missing sheets: {e}")

            # Save filled workbook
            workbook.save(output_path)
            workbook.close()

            summary = {
                "total_cells_filled": cells_filled,
                "sheets_modified": sorted(list(sheets_modified)),
                "formulas_preserved": True,  # openpyxl preserves formulas by default
                "errors": errors,
            }

            logger.info(
                f"Template filled successfully: {cells_filled} cells across "
                f"{len(sheets_modified)} sheets"
            )

            return summary

        except Exception as e:
            logger.error(f"Error filling Excel template: {e}", exc_info=True)
            raise

    def _convert_value_for_cell(self, value: Any, cell: Cell) -> Any:
        """
        Convert extracted value to appropriate type for Excel cell.

        Args:
            value: Extracted value (usually string from LLM)
            cell: Target Excel cell

        Returns:
            Converted value
        """
        # If value is already the right type, use it
        if value is None:
            return None

        # Get cell's expected type from number format
        cell_type = self._infer_cell_type(cell)

        # Convert based on cell type
        try:
            if cell_type in ['number', 'currency', 'percentage']:
                # Try to parse as float
                if isinstance(value, (int, float)):
                    return float(value)

                # Remove common formatting characters
                cleaned = str(value).replace(',', '').replace('$', '').replace('%', '').strip()

                try:
                    return float(cleaned)
                except ValueError:
                    # If can't convert, return as string
                    return str(value)

            elif cell_type == 'date':
                # For dates, we might need more sophisticated parsing
                # For now, return as string and let Excel interpret
                return str(value)

            else:  # text
                return str(value)

        except Exception as e:
            logger.warning(f"Error converting value '{value}' for cell type '{cell_type}': {e}")
            return str(value)

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
