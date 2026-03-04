/**
 * ExcelGrid Component
 * Renders Excel sheet as a virtualized grid table with column resizing, cell expansion, and mapping overlays
 */

import React from 'react';
import * as XLSX from 'xlsx';
import { Badge } from '../../../components/ui/badge';
import { Button } from '../../../components/ui/button';
import { AlertCircle, AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Columns3, Info, Rows3 } from 'lucide-react';
import { getExcelCellStyle } from '../utils/excelCellStyles';

export default function ExcelGrid({
  workbook,
  sheetName,
  getCellValue,
  getCellMapping,
  onCellClick,
  selectedCell,
}) {
  const worksheet = workbook.Sheets[sheetName];
  const [expandedCells, setExpandedCells] = React.useState(new Set());
  const [visibleRowEnd, setVisibleRowEnd] = React.useState(20); // Show first 20 rows initially
  const [visibleColEnd, setVisibleColEnd] = React.useState(10); // Show first 10 columns initially
  const [resizing, setResizing] = React.useState(null); // { col: number, startX: number, startWidth: number }

  // Extract column widths from Excel file
  const initialColumnWidths = React.useMemo(() => {
    const widths = {};
    const cols = worksheet['!cols'] || [];

    // Convert Excel character width to pixels
    // Excel character width (wch) is based on the default font
    // Approximate conversion: 1 character ≈ 7.5 pixels (can vary by font)
    const charToPixels = 7.5;

    cols.forEach((colInfo, index) => {
      if (colInfo && colInfo.wch) {
        // Convert character width to pixels, with min/max bounds
        const pixels = Math.max(64, Math.min(400, colInfo.wch * charToPixels));
        widths[index] = Math.round(pixels);
      }
    });

    return widths;
  }, [worksheet]);

  const [columnWidths, setColumnWidths] = React.useState(initialColumnWidths); // Track custom column widths

  // Reset column widths when sheet changes
  React.useEffect(() => {
    setColumnWidths(initialColumnWidths);
  }, [sheetName, initialColumnWidths]);

  // Get the FULL range of cells in the sheet
  const range = XLSX.utils.decode_range(worksheet['!ref'] || 'A1');

  // Determine which rows to display (with buffer)
  const displayRowEnd = Math.min(visibleRowEnd, range.e.r);
  const rows = [];
  for (let R = range.s.r; R <= displayRowEnd; R++) {
    rows.push(R);
  }

  // Determine which columns to display (with buffer)
  const displayColEnd = Math.min(visibleColEnd, range.e.c);
  const cols = [];
  for (let C = range.s.c; C <= displayColEnd; C++) {
    cols.push(C);
  }

  const hasMoreRows = displayRowEnd < range.e.r;
  const hasMoreCols = displayColEnd < range.e.c;
  const rowBatchSize = 20;
  const colBatchSize = 5;

  function handleLoadMoreRows() {
    setVisibleRowEnd(prev => Math.min(prev + rowBatchSize, range.e.r));
  }

  function handleLoadMoreCols() {
    setVisibleColEnd(prev => Math.min(prev + colBatchSize, range.e.c));
  }

  function toggleCellExpansion(cellAddress) {
    setExpandedCells(prev => {
      const next = new Set(prev);
      if (next.has(cellAddress)) {
        next.delete(cellAddress);
      } else {
        next.add(cellAddress);
      }
      return next;
    });
  }

  // Get column width (custom, from Excel, or default)
  function getColumnWidth(col) {
    // Priority: 1) User-resized width, 2) Excel file width, 3) Default 128px
    return columnWidths[col] || initialColumnWidths[col] || 128;
  }

  // Column resize handlers
  function handleResizeStart(col, e) {
    e.preventDefault();
    e.stopPropagation();
    // Get current width (from state, Excel file, or default)
    const currentWidth = getColumnWidth(col);
    setResizing({
      col,
      startX: e.clientX,
      startWidth: currentWidth,
    });
  }

  React.useEffect(() => {
    if (!resizing) return;

    function handleMouseMove(e) {
      const delta = e.clientX - resizing.startX;
      const newWidth = Math.max(64, resizing.startWidth + delta); // Min width 64px
      setColumnWidths(prev => ({
        ...prev,
        [resizing.col]: newWidth,
      }));
    }

    function handleMouseUp() {
      setResizing(null);
    }

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [resizing]);

  return (
    <div
      className="h-full min-h-0 flex flex-col"
      style={{ cursor: resizing ? 'col-resize' : 'default', userSelect: resizing ? 'none' : 'auto' }}
    >
      <div className="flex-1 min-h-0">
        {/* Table Container with thin scrollbar */}
        <div className="h-full border border-border rounded-lg overflow-auto bg-background shadow-sm flex-1 min-h-0 [&::-webkit-scrollbar]:h-1 [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-thumb]:rounded-full hover:[&::-webkit-scrollbar-thumb]:bg-muted-foreground/50">
          <table className="border-collapse w-full min-w-fit">
          <thead>
            <tr className="bg-muted/50">
              <th className="border border-border bg-muted/70 p-2 text-xs font-medium text-muted-foreground sticky top-0 left-0 z-20 w-12">
                {/* Empty corner */}
              </th>
              {cols.map(C => (
                <th
                  key={C}
                  className="border border-border bg-muted/70 p-2 text-xs font-medium text-muted-foreground sticky top-0 z-10 relative"
                  style={{ width: `${getColumnWidth(C)}px`, minWidth: `${getColumnWidth(C)}px`, maxWidth: `${getColumnWidth(C)}px` }}
                >
                  <div className="flex items-center justify-center">
                    {XLSX.utils.encode_col(C)}
                  </div>
                  {/* Resize Handle */}
                  <div
                    className="absolute top-0 right-0 h-full w-1 cursor-col-resize hover:bg-primary/50 group"
                    onMouseDown={(e) => handleResizeStart(C, e)}
                    title="Drag to resize column"
                  >
                    <div className="absolute top-0 right-0 h-full w-1 bg-primary opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(R => (
              <tr key={R}>
                <td className="border border-border bg-muted/50 p-2 text-xs font-medium text-muted-foreground text-center sticky left-0 z-10">
                  {R + 1}
                </td>
                {cols.map(C => {
                  const cellAddress = XLSX.utils.encode_cell({ r: R, c: C });
                  const cell = worksheet[cellAddress];
                  const mapping = getCellMapping(sheetName, cellAddress);
                  const mappedValue = getCellValue(sheetName, cellAddress);
                  const isSelected = selectedCell?.cellAddress === cellAddress;
                  const isExpanded = expandedCells.has(cellAddress);

                  // Determine if cell has a formula
                  const hasFormula = cell && cell.f;

                  // Get display value
                  let displayValue = '';
                  if (hasFormula) {
                    displayValue = `=${cell.f}`;
                  } else if (mappedValue) {
                    displayValue = mappedValue;
                  } else if (cell) {
                    displayValue = cell.w || cell.v || '';
                  }

                  // Check if value is long enough to need expansion
                  const needsExpansion = displayValue && displayValue.length > 30;

                  // Get Excel cell styling (colors, bold, italic)
                  const excelStyle = getExcelCellStyle(cell);

                  // Base cell classes
                  let cellClasses = 'border border-border p-2 text-xs transition-all relative';

                  // Add cursor and interaction classes
                  if (hasFormula) {
                    cellClasses += ' cursor-not-allowed';
                  } else {
                    // All non-formula cells are clickable (mapped or unmapped)
                    cellClasses += ' cursor-pointer hover:ring-2 hover:ring-primary/50';
                  }

                  if (isSelected) {
                    cellClasses += ' ring-2 ring-primary';
                  }

                  // Prepare inline styles combining Excel styles and confidence overlay
                  const inlineStyles = { ...excelStyle };

                  // Add confidence color overlay (semi-transparent) without overwriting Excel background
                  let overlayColor = null;
                  if (hasFormula) {
                    // Formula cells - subtle gray overlay if no Excel background
                    if (!excelStyle.backgroundColor) {
                      inlineStyles.backgroundColor = 'hsl(var(--muted))';
                      inlineStyles.fontStyle = 'italic';
                    }
                  } else if (mapping) {
                    const confidence = mapping.confidence || 0;
                    // Use box-shadow for overlay effect (doesn't override background)
                    if (confidence >= 0.8) {
                      overlayColor = 'inset 0 0 0 2px hsl(var(--success))';
                    } else if (confidence >= 0.5) {
                      overlayColor = 'inset 0 0 0 2px hsl(var(--warning))';
                    } else {
                      overlayColor = 'inset 0 0 0 2px hsl(var(--destructive))';
                    }
                  }

                  if (overlayColor) {
                    inlineStyles.boxShadow = overlayColor;
                  }

                  return (
                    <td
                      key={C}
                      className={cellClasses}
                      style={{
                        ...inlineStyles,
                        width: `${getColumnWidth(C)}px`,
                        minWidth: `${getColumnWidth(C)}px`,
                        maxWidth: `${getColumnWidth(C)}px`,
                      }}
                      onClick={() => !hasFormula && onCellClick(sheetName, cellAddress, cell)}
                      title={
                        hasFormula
                          ? `Formula: ${displayValue}`
                          : mapping
                          ? `${mapping.excel_label || ''} (${Math.round((mapping.confidence || 0) * 100)}% confidence)`
                          : cellAddress
                      }
                    >
                      <div className="flex flex-col gap-1 min-h-6">
                        {hasFormula ? (
                          <div className="flex items-center gap-1">
                            <Badge variant="secondary" className="text-xs h-4 px-1">
                              Formula
                            </Badge>
                            <code className="font-mono text-xs truncate">{displayValue}</code>
                          </div>
                        ) : (
                          <>
                            <div className={isExpanded ? "whitespace-pre-wrap" : "truncate"} style={{
                              fontWeight: excelStyle.fontWeight,
                              fontStyle: excelStyle.fontStyle,
                              color: excelStyle.color
                            }}>
                              {displayValue || <span className="text-muted-foreground/40">—</span>}
                            </div>
                            <div className="flex items-center gap-1 justify-between">
                              {mapping && (
                                <div className="flex items-center gap-1">
                                  {mapping.confidence >= 0.8 ? (
                                    <CheckCircle2 className="h-3 w-3 text-success" />
                                  ) : mapping.confidence >= 0.5 ? (
                                    <AlertTriangle className="h-3 w-3 text-warning" />
                                  ) : (
                                    <AlertCircle className="h-3 w-3 text-destructive" />
                                  )}
                                  <span className="text-xs text-muted-foreground">
                                    {Math.round((mapping.confidence || 0) * 100)}%
                                  </span>
                                </div>
                              )}
                              {needsExpansion && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    toggleCellExpansion(cellAddress);
                                  }}
                                  className="text-xs text-primary hover:underline"
                                >
                                  {isExpanded ? '△' : '▽'}
                                </button>
                              )}
                            </div>
                          </>
                        )}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      </div>

      {/* Bottom Bar: Legend + Expand Controls */}
      <div className="mt-2 flex-shrink-0 relative z-10 bg-background flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 flex-wrap text-[11px] text-muted-foreground leading-none">
          <div className="flex items-center gap-1">
            <div className="w-2.5 h-2.5 rounded border-2 border-green-500" />
            <span>High</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-2.5 h-2.5 rounded border-2 border-yellow-500" />
            <span>Medium</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-2.5 h-2.5 rounded border-2 border-red-500" />
            <span>Low</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="bg-muted px-1 rounded text-[10px]">Formula</span>
            <span>Read-only</span>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {hasMoreRows && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleLoadMoreRows}
              className="text-xs"
            >
              <Rows3 className="h-3.5 w-3.5 mr-1.5" />
              <ChevronDown className="h-3 w-3 mr-1" />
              Show {rowBatchSize} more rows
            </Button>
          )}
          {hasMoreCols && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleLoadMoreCols}
              className="text-xs"
            >
              <Columns3 className="h-3.5 w-3.5 mr-1.5" />
              <ChevronRight className="h-3 w-3 mr-1" />
              Show more columns
            </Button>
          )}
          {!hasMoreRows && !hasMoreCols && (
            <p className="text-xs text-muted-foreground">
              <Info className="h-3 w-3 inline mr-1" />
              All rows and columns loaded
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
