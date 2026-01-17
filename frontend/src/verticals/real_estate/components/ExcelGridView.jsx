/**
 * Excel Grid View Component
 * Displays the actual Excel file with mapping overlays
 */

import React, { useState, useEffect, useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';
import * as XLSX from 'xlsx';
import { downloadRETemplate } from '../../../api/re-templates';
import { useTemplateFillActions } from '../../../store';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../components/ui/tabs';
import { FileSpreadsheet, AlertCircle, Loader2, CheckCircle2, AlertTriangle, Info, Search, Check, ChevronsUpDown } from 'lucide-react';
import { Badge } from '../../../components/ui/badge';
import { Button } from '../../../components/ui/button';
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '../../../components/ui/sheet';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '../../../components/ui/alert-dialog';
import { Input } from '../../../components/ui/input';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '../../../components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '../../../components/ui/popover';
import { cn } from '@/lib/utils';

export default function ExcelGridView({
  fillRunId,
  extractedData = {},
  fieldMapping = {},
  templateId,
  onCitationClick,
}) {
  const { getToken } = useAuth();
  const [workbook, setWorkbook] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeSheet, setActiveSheet] = useState(null);
  const [selectedCell, setSelectedCell] = useState(null);

  const mappings = fieldMapping?.mappings || [];
  const pdfFields = fieldMapping?.pdf_fields || [];

  // Debug logging for mapping issues
  React.useEffect(() => {
    if (mappings.length > 0) {
      console.log('📊 Total mappings received:', mappings.length);

      // Group by sheet
      const bySheet = {};
      mappings.forEach(m => {
        if (!bySheet[m.excel_sheet]) {
          bySheet[m.excel_sheet] = [];
        }
        bySheet[m.excel_sheet].push(m);
      });
      console.log('📊 Mappings by sheet:', Object.entries(bySheet).map(([sheet, maps]) => `${sheet}: ${maps.length}`).join(', '));

      // Check for duplicates
      const cellAddresses = mappings.map(m => `${m.excel_sheet}!${m.excel_cell}`);
      const uniqueCells = new Set(cellAddresses);
      console.log('📊 Unique cell addresses:', uniqueCells.size, 'vs Total mappings:', mappings.length);

      if (uniqueCells.size < mappings.length) {
        console.warn('⚠️ Duplicate cell mappings detected!');
        const duplicates = {};
        cellAddresses.forEach(cell => {
          duplicates[cell] = (duplicates[cell] || 0) + 1;
        });
        const dups = Object.entries(duplicates).filter(([_, count]) => count > 1);
        console.log('📊 Duplicate cells:', dups);

        // Show which PDF fields are mapped to each duplicate cell
        console.log('📊 Duplicate cell details:');
        dups.forEach(([cellAddr, count]) => {
          const fields = mappings.filter(m => `${m.excel_sheet}!${m.excel_cell}` === cellAddr);
          const fieldNames = fields.map(f => {
            const pdfField = pdfFields.find(p => p.id === f.pdf_field_id);
            return pdfField?.name || f.excel_label || f.pdf_field_id;
          });
          console.log(`   ${cellAddr} (${count} fields):`, fieldNames);
        });
      }

      // Check for null/empty cells
      const invalidMappings = mappings.filter(m => !m.excel_cell || !m.excel_sheet);
      if (invalidMappings.length > 0) {
        console.warn('⚠️ Invalid mappings (null/empty cell or sheet):', invalidMappings.length);
        console.log('📊 Invalid mappings:', invalidMappings);
      }

      // Sample first 5 mappings
      console.log('📊 Sample mappings:', mappings.slice(0, 5));
    }
  }, [mappings]);

  useEffect(() => {
    loadExcelFile();
  }, [templateId]);

  useEffect(() => {
    if (workbook && !activeSheet) {
      setActiveSheet(workbook.SheetNames[0]);
    }
  }, [workbook]);

  async function loadExcelFile() {
    try {
      setLoading(true);
      setError(null);

      console.log('📊 Loading Excel file for template:', templateId);
      const arrayBuffer = await downloadRETemplate(getToken, templateId);

      // Parse Excel file
      const wb = XLSX.read(arrayBuffer, { type: 'array', cellFormula: true, cellStyles: true });
      console.log('📊 Excel workbook loaded:', wb.SheetNames);
      setWorkbook(wb);
    } catch (err) {
      console.error('❌ Failed to load Excel file:', err);
      setError('Failed to load Excel file');
    } finally {
      setLoading(false);
    }
  }

  function getCellMapping(sheetName, cellAddress) {
    return mappings.find(
      (m) => m.excel_sheet === sheetName && m.excel_cell === cellAddress
    );
  }

  function getCellValue(sheetName, cellAddress) {
    const mapping = getCellMapping(sheetName, cellAddress);
    if (!mapping) return null;

    // Try extracted data first
    const fieldData = extractedData[mapping.pdf_field_id];
    if (fieldData?.value) return fieldData.value;

    // Fall back to sample_value from pdf_fields
    const pdfField = pdfFields.find(f => f.id === mapping.pdf_field_id);
    return pdfField?.sample_value || null;
  }

  function handleCellClick(sheetName, cellAddress, cellData) {
    const mapping = getCellMapping(sheetName, cellAddress);
    if (mapping) {
      const pdfField = pdfFields.find(f => f.id === mapping.pdf_field_id);
      setSelectedCell({
        sheetName,
        cellAddress,
        mapping,
        pdfField,
        value: getCellValue(sheetName, cellAddress),
        cellData,
      });
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <span className="text-sm text-muted-foreground">Loading Excel file...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-6 text-destructive">
        <AlertCircle className="h-10 w-10 mb-3" />
        <p className="text-sm">{error}</p>
      </div>
    );
  }

  if (!workbook) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-6 text-muted-foreground">
        <FileSpreadsheet className="h-10 w-10 mb-3 text-muted-foreground/50" />
        <p className="text-sm">No Excel file available</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-auto">
      {/* Sheet Tabs */}
      <Tabs value={activeSheet} onValueChange={setActiveSheet} className="flex-1 flex flex-col">
        <div className="sticky top-0 z-10 bg-card flex-shrink-0">
          <TabsList className="w-full justify-start bg-transparent border-b rounded-none p-0 h-auto">
            {workbook.SheetNames.map((sheetName) => {
              const sheetMappings = mappings.filter(m => m.excel_sheet === sheetName);
              return (
                <TabsTrigger
                  key={sheetName}
                  value={sheetName}
                  className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-3 py-2"
                >
                  <span className="text-xs font-medium">{sheetName}</span>
                  <Badge variant="secondary" className="ml-1.5 text-xs h-4 px-1.5">
                    {sheetMappings.length}
                  </Badge>
                </TabsTrigger>
              );
            })}
          </TabsList>
        </div>

        {/* Sheet Content */}
        {workbook.SheetNames.map((sheetName) => (
          <TabsContent
            key={sheetName}
            value={sheetName}
            className="flex-1 m-0"
          >
            <div className="p-4">
              <ExcelGrid
                workbook={workbook}
                sheetName={sheetName}
                mappings={mappings}
                pdfFields={pdfFields}
                getCellValue={getCellValue}
                getCellMapping={getCellMapping}
                onCellClick={handleCellClick}
                selectedCell={selectedCell}
              />
            </div>
          </TabsContent>
        ))}
      </Tabs>

      {/* Mapping Details Sheet (Bottom Drawer) */}
      <Sheet open={!!selectedCell} onOpenChange={(open) => !open && setSelectedCell(null)}>
        <SheetContent side="bottom" className="h-[55vh] flex flex-col p-0">
          {selectedCell && (
            <MappingDetailsDialog
              selectedCell={selectedCell}
              fillRunId={fillRunId}
              fieldMapping={fieldMapping}
              extractedData={extractedData}
              onClose={() => setSelectedCell(null)}
              onCitationClick={onCitationClick}
            />
          )}
        </SheetContent>
      </Sheet>

      {/* Legend */}
      <div className="border-t bg-muted/30 p-2.5">
        <p className="text-xs font-medium text-foreground mb-1.5">Legend:</p>
        <div className="flex gap-3 text-xs flex-wrap">
          <div className="flex items-center gap-1.5">
            <div className="w-4 h-4 bg-background rounded" style={{ boxShadow: 'inset 0 0 0 2px hsl(var(--success))' }}></div>
            <span className="text-muted-foreground">High Confidence (&gt;80%)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-4 h-4 bg-background rounded" style={{ boxShadow: 'inset 0 0 0 2px hsl(var(--warning))' }}></div>
            <span className="text-muted-foreground">Medium (50-80%)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-4 h-4 bg-background rounded" style={{ boxShadow: 'inset 0 0 0 2px hsl(var(--destructive))' }}></div>
            <span className="text-muted-foreground">Low (&lt;50%)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-4 h-4 bg-muted border border-border rounded italic flex items-center justify-center">
              <span className="text-xs">ƒ</span>
            </div>
            <span className="text-muted-foreground">Formula (preserved)</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// Helper function to calculate luminance and determine if text should be light or dark
function getLuminance(hexColor) {
  // Remove # if present
  const hex = hexColor.replace('#', '');

  // Parse RGB
  const r = parseInt(hex.substr(0, 2), 16) / 255;
  const g = parseInt(hex.substr(2, 2), 16) / 255;
  const b = parseInt(hex.substr(4, 2), 16) / 255;

  // Calculate relative luminance
  const [rs, gs, bs] = [r, g, b].map(c =>
    c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
  );

  return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
}

// Helper function to extract Excel cell styling
function getExcelCellStyle(cell) {
  if (!cell || !cell.s) return {};

  const style = {};

  // Background color
  if (cell.s.fgColor) {
    const rgb = cell.s.fgColor.rgb;
    if (rgb) {
      const bgColor = `#${rgb}`;
      style.backgroundColor = bgColor;

      // Auto-adjust text color for contrast if no explicit font color
      if (!cell.s.font || !cell.s.font.color) {
        const luminance = getLuminance(bgColor);
        // If background is dark (luminance < 0.5), use white text
        style.color = luminance < 0.5 ? '#FFFFFF' : '#000000';
      }
    }
  }

  // Font styling
  if (cell.s.font) {
    const font = cell.s.font;

    // Font weight (bold)
    if (font.bold) {
      style.fontWeight = 'bold';
    }

    // Font style (italic)
    if (font.italic) {
      style.fontStyle = 'italic';
    }

    // Font color (overrides auto-calculated color)
    if (font.color && font.color.rgb) {
      style.color = `#${font.color.rgb}`;
    }
  }

  return style;
}

function ExcelGrid({
  workbook,
  sheetName,
  mappings,
  pdfFields,
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

    console.log(`📏 Loaded ${Object.keys(widths).length} column widths from Excel:`, widths);
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
  const totalRows = range.e.r - range.s.r + 1;
  const displayRowEnd = Math.min(visibleRowEnd, range.e.r);
  const rows = [];
  for (let R = range.s.r; R <= displayRowEnd; R++) {
    rows.push(R);
  }

  // Determine which columns to display (with buffer)
  const totalCols = range.e.c - range.s.c + 1;
  const displayColEnd = Math.min(visibleColEnd, range.e.c);
  const cols = [];
  for (let C = range.s.c; C <= displayColEnd; C++) {
    cols.push(C);
  }

  const hasMoreRows = displayRowEnd < range.e.r;
  const hasMoreCols = displayColEnd < range.e.c;

  function handleLoadMoreRows() {
    setVisibleRowEnd(prev => Math.min(prev + 20, range.e.r));
  }

  function handleLoadMoreCols() {
    setVisibleColEnd(prev => Math.min(prev + 5, range.e.c));
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
    <div style={{ cursor: resizing ? 'col-resize' : 'default', userSelect: resizing ? 'none' : 'auto' }}>
      <div className="flex items-stretch gap-2">
        {/* Table Container */}
        <div className="border border-border rounded-lg overflow-auto bg-background shadow-sm flex-1">
          <table className="border-collapse w-auto">
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
                  } else if (mapping) {
                    cellClasses += ' cursor-pointer hover:ring-2 hover:ring-primary/50';
                  } else {
                    cellClasses += ' hover:bg-muted/30';
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

        {/* Right-side Load More Columns Button */}
        {hasMoreCols && (
          <div className="flex items-center">
            <Button
              variant="outline"
              size="sm"
              onClick={handleLoadMoreCols}
              className="text-xs writing-mode-vertical transform whitespace-nowrap px-2 py-3"
              title={`Load 5 More Columns (${XLSX.utils.encode_col(displayColEnd)} / ${XLSX.utils.encode_col(range.e.c)})`}
            >
              <span className="inline-block" style={{ writingMode: 'vertical-rl', textOrientation: 'mixed' }}>
                →
              </span>
            </Button>
          </div>
        )}
      </div>

      {/* Load More Controls - Bottom */}
      <div className="mt-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          {hasMoreRows && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleLoadMoreRows}
              className="text-xs"
            >
              Load 20 More Rows ({displayRowEnd + 1} / {range.e.r + 1})
            </Button>
          )}
          {hasMoreCols && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleLoadMoreCols}
              className="text-xs"
            >
              Load 5 More Columns ({XLSX.utils.encode_col(displayColEnd)} / {XLSX.utils.encode_col(range.e.c)})
            </Button>
          )}
          {!hasMoreRows && !hasMoreCols && (
            <p className="text-xs text-muted-foreground">
              <Info className="h-3 w-3 inline mr-1" />
              All rows and columns loaded ({totalRows} rows × {totalCols} columns)
            </p>
          )}
        </div>

        {/* Bottom-right Load More Rows Button */}
        {hasMoreRows && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleLoadMoreRows}
            className="text-xs px-3 py-1"
            title={`Load 20 More Rows (${displayRowEnd + 1} / ${range.e.r + 1})`}
          >
            ↓
          </Button>
        )}
      </div>
    </div>
  );
}

function MappingDetailsDialog({
  selectedCell,
  fillRunId,
  fieldMapping,
  extractedData,
  onClose,
  onCitationClick,
}) {
  const { getToken } = useAuth();
  const { updateMappings, updateFieldData, loadFillRun } = useTemplateFillActions();
  const { mapping, pdfField, value, cellAddress, cellData } = selectedCell;

  const allPdfFields = fieldMapping?.pdf_fields || [];

  const [isEditMode, setIsEditMode] = useState(false);
  const [isRemoving, setIsRemoving] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [showDeleteAlert, setShowDeleteAlert] = useState(false);

  // Edit mode state
  const [selectedFieldId, setSelectedFieldId] = useState(mapping.pdf_field_id);
  const [editedValue, setEditedValue] = useState(() => {
    const extractedVal = extractedData?.[mapping.pdf_field_id]?.value;
    return extractedVal || pdfField?.sample_value || '';
  });
  const [open, setOpen] = useState(false);

  // Get currently selected field (for edit mode)
  const currentField = allPdfFields.find(f => f.id === selectedFieldId) || pdfField;

  function handleEditMapping() {
    setIsEditMode(true);
  }

  function handleCancelEdit() {
    setIsEditMode(false);
    // Reset to original values
    setSelectedFieldId(mapping.pdf_field_id);
    const extractedVal = extractedData?.[mapping.pdf_field_id]?.value;
    setEditedValue(extractedVal || pdfField?.sample_value || '');
  }

  // When user selects different field in edit mode
  function handleFieldChange(newFieldId) {
    setSelectedFieldId(newFieldId);
    const newField = allPdfFields.find(f => f.id === newFieldId);
    const extractedVal = extractedData?.[newFieldId]?.value;
    setEditedValue(extractedVal || newField?.sample_value || '');
  }

  async function handleSave() {
    try {
      setIsSaving(true);

      // If field changed, update mappings
      if (selectedFieldId !== mapping.pdf_field_id) {
        const updatedMappings = fieldMapping.mappings.map(m =>
          m.excel_cell === mapping.excel_cell && m.excel_sheet === mapping.excel_sheet
            ? { ...m, pdf_field_id: selectedFieldId, pdf_field_name: currentField?.name }
            : m
        );
        await updateMappings(fillRunId, updatedMappings, getToken);
      }

      // If value changed, update extracted data
      const currentValue = extractedData?.[selectedFieldId]?.value ||
                          allPdfFields.find(f => f.id === selectedFieldId)?.sample_value;

      if (editedValue !== currentValue) {
        const updatedData = {
          ...extractedData,
          [selectedFieldId]: {
            value: editedValue,
            confidence: 1.0,
            user_edited: true,
            citations: currentField?.citations || []
          }
        };
        await updateFieldData(fillRunId, updatedData, getToken);
      }

      // Reload fill run to get updated status (might have reset to awaiting_review)
      await loadFillRun(fillRunId, getToken, { silent: true, skipPdf: true });

      onClose();
    } catch (err) {
      console.error('Failed to save mapping:', err);
      alert('Failed to save changes');
    } finally {
      setIsSaving(false);
    }
  }

  function handleRemoveMappingClick() {
    setShowDeleteAlert(true);
  }

  async function confirmRemoveMapping() {
    try {
      setIsRemoving(true);
      setShowDeleteAlert(false);

      const currentMappings = fieldMapping.mappings || [];

      // Debug: Log the mapping we're trying to remove
      console.log('🗑️ Removing mapping:', {
        excel_sheet: mapping.excel_sheet,
        excel_cell: mapping.excel_cell,
        pdf_field_id: mapping.pdf_field_id
      });
      console.log('📋 Current mappings count:', currentMappings.length);
      console.log('📋 All mappings:', currentMappings.map(m => ({
        sheet: m.excel_sheet,
        cell: m.excel_cell,
        field: m.pdf_field_id
      })));

      const updatedMappings = currentMappings.filter(
        m => !(m.excel_sheet === mapping.excel_sheet &&
               m.excel_cell === mapping.excel_cell)
      );

      console.log('✅ Updated mappings count:', updatedMappings.length);
      console.log('✅ Filtered mappings:', updatedMappings.map(m => ({
        sheet: m.excel_sheet,
        cell: m.excel_cell,
        field: m.pdf_field_id
      })));

      await updateMappings(fillRunId, updatedMappings, getToken);

      // Reload fill run to get updated status (might have reset to awaiting_review)
      await loadFillRun(fillRunId, getToken, { silent: true, skipPdf: true });

      onClose();
    } catch (err) {
      console.error('Failed to remove mapping:', err);
      alert('Failed to remove mapping');
    } finally {
      setIsRemoving(false);
    }
  }

  return (
    <>
      {/* Header */}
      <SheetHeader className="px-4 pt-4 pb-2 border-b">
        <SheetTitle className="flex items-center gap-2">
          <span className="font-semibold text-base">Cell {cellAddress}</span>
          <Badge variant="outline" className="text-xs">
            {mapping.excel_label || 'Unlabeled'}
          </Badge>
        </SheetTitle>
        <SheetDescription className="text-xs">
          {isEditMode
            ? 'Edit the mapping or change the value'
            : 'Review and manage the mapping between Excel cell and PDF field'
          }
        </SheetDescription>
      </SheetHeader>

      {/* Scrollable Content */}
      <div className="flex-1 overflow-auto px-4 py-3 scrollbar-thin">

        {/* VIEW MODE */}
        {!isEditMode && (
          <>

      {/* Confidence Score - Prominent Card */}
      <div className="mb-3 p-2.5 rounded-lg border bg-card">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs font-semibold text-foreground">Mapping Confidence</span>
          <Badge
            variant={
              mapping.confidence >= 0.8 ? 'default' :
              mapping.confidence >= 0.5 ? 'secondary' : 'destructive'
            }
            className={cn(
              "text-xs px-2 py-0.5 font-semibold",
              mapping.confidence >= 0.8 && 'bg-green-500 hover:bg-green-600 text-white',
              mapping.confidence >= 0.5 && mapping.confidence < 0.8 && 'bg-yellow-500 hover:bg-yellow-600 text-white'
            )}
          >
            {Math.round((mapping.confidence || 0) * 100)}%
          </Badge>
        </div>
        <div className="w-full bg-muted rounded-full h-2">
          <div
            className={cn(
              "h-2 rounded-full transition-all",
              mapping.confidence >= 0.8 ? 'bg-green-500' :
              mapping.confidence >= 0.5 ? 'bg-yellow-500' : 'bg-destructive'
            )}
            style={{ width: `${(mapping.confidence || 0) * 100}%` }}
          />
        </div>
      </div>

      {/* Current Excel Value */}
      {cellData && cellData.v && (
        <div className="mb-3">
          <h4 className="text-xs font-semibold text-foreground mb-1.5">Current Excel Value</h4>
          <div className="bg-muted/50 rounded-lg p-2.5 border">
            <p className="text-xs text-foreground font-mono">{cellData.w || cellData.v}</p>
          </div>
        </div>
      )}

      {/* PDF Field Info */}
      <div className="mb-3">
        <h4 className="text-xs font-semibold text-foreground mb-1.5">Mapped PDF Field</h4>
        <div className="bg-muted/50 rounded-lg p-2.5 border space-y-2">
          <div>
            <span className="text-xs font-medium text-muted-foreground block mb-0.5">Field Name</span>
            <p className="text-xs text-foreground font-mono">{pdfField?.name || 'Unknown'}</p>
          </div>
          {value && (
            <div>
              <span className="text-xs font-medium text-muted-foreground block mb-1">
                Extracted Value
              </span>
              <p className="text-xs text-foreground break-words bg-background p-2 rounded-md border font-medium">
                {value}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* LLM Reasoning */}
      {mapping.reasoning && (
        <div className="mb-3">
          <h4 className="text-xs font-semibold text-foreground mb-1.5 flex items-center gap-1.5">
            <Info className="h-3.5 w-3.5 text-primary" />
            AI Reasoning
          </h4>
          <div className="bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-lg p-2.5">
            <p className="text-xs text-foreground leading-relaxed">
              {mapping.reasoning}
            </p>
          </div>
        </div>
      )}

      {/* Citations */}
      {pdfField?.citations && pdfField.citations.length > 0 && (
        <div className="mb-3">
          <h4 className="text-xs font-semibold text-foreground mb-1.5">Source Citations</h4>
          <div className="flex flex-wrap gap-1.5">
            {pdfField.citations.map((citation, idx) => {
              // Parse citation format: [D1:p2] -> Document 1, Page 2
              const match = citation.match(/\[D(\d+):p(\d+)\]/);
              const pageNum = match ? parseInt(match[2], 10) : null;

              const handleClick = () => {
                console.log('🔗 Citation clicked:', citation, '→ Page:', pageNum);
                if (pageNum) {
                  onCitationClick(pageNum);
                } else {
                  console.warn('⚠️ Could not parse page number from citation:', citation);
                }
              };

              return (
                <Button
                  key={idx}
                  onClick={handleClick}
                  variant="outline"
                  size="sm"
                  className="h-7 px-2.5 text-xs font-mono hover:bg-primary/10"
                >
                  📄 Page {pageNum}
                </Button>
              );
            })}
          </div>
        </div>
      )}
          </>
        )}

        {/* EDIT MODE */}
        {isEditMode && (
          <>
            {/* Edit Value Directly */}
            <div className="mb-3">
              <h4 className="text-xs font-semibold text-foreground mb-1.5">Edit Value</h4>
              <Input
                type="text"
                value={editedValue}
                onChange={(e) => setEditedValue(e.target.value)}
                placeholder="Enter new value..."
                className="w-full text-xs h-8"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Directly edit the value that will be filled in the Excel cell
              </p>
            </div>

            {/* Or Select Different PDF Field */}
            <div className="mb-3">
              <h4 className="text-xs font-semibold text-foreground mb-1.5">Or Select Different Field</h4>
              <Popover open={open} onOpenChange={setOpen}>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    role="combobox"
                    aria-expanded={open}
                    className="w-full justify-between h-8 text-xs"
                  >
                    {selectedFieldId
                      ? allPdfFields.find((f) => f.id === selectedFieldId)?.name || 'Select field...'
                      : 'Select field...'}
                    <ChevronsUpDown className="ml-2 h-3.5 w-3.5 shrink-0 opacity-50" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-full p-0">
                  <Command>
                    <CommandInput placeholder="Search fields..." className="text-xs h-8" />
                    <CommandList>
                      <CommandEmpty className="text-xs">No field found.</CommandEmpty>
                      <CommandGroup>
                        {allPdfFields.map((field) => (
                          <CommandItem
                            key={field.id}
                            value={field.name}
                            onSelect={() => {
                              handleFieldChange(field.id);
                              setOpen(false);
                            }}
                            className="text-xs"
                          >
                            <Check
                              className={cn(
                                'mr-2 h-3.5 w-3.5',
                                selectedFieldId === field.id ? 'opacity-100' : 'opacity-0'
                              )}
                            />
                            <div className="flex flex-col flex-1 min-w-0">
                              <span className="text-xs font-medium truncate">{field.name}</span>
                              <span className="text-xs text-muted-foreground truncate">
                                {field.sample_value}
                              </span>
                            </div>
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
              <p className="text-xs text-muted-foreground mt-1">
                Search and select a different PDF field to map to this cell
              </p>
            </div>

            {/* Show selected field metadata */}
            {selectedFieldId && selectedFieldId !== mapping.pdf_field_id && (
              <div className="mb-3">
                <h4 className="text-xs font-semibold text-foreground mb-1.5">Selected Field Details</h4>
                <div className="bg-muted/50 rounded-lg p-2.5 border space-y-2">
                  {(() => {
                    const selectedField = allPdfFields.find((f) => f.id === selectedFieldId);
                    if (!selectedField) return null;
                    return (
                      <>
                        <div>
                          <span className="text-xs font-medium text-muted-foreground block mb-0.5">
                            Field Name
                          </span>
                          <p className="text-xs text-foreground font-mono">{selectedField.name}</p>
                        </div>
                        <div>
                          <span className="text-xs font-medium text-muted-foreground block mb-1">
                            Extracted Value
                          </span>
                          <p className="text-xs text-foreground break-words bg-background p-2 rounded-md border font-medium">
                            {selectedField.sample_value}
                          </p>
                        </div>
                        {selectedField.confidence && (
                          <div>
                            <span className="text-xs font-medium text-muted-foreground block mb-1">
                              Confidence
                            </span>
                            <Badge variant="outline" className="text-xs font-medium">
                              {Math.round(selectedField.confidence * 100)}%
                            </Badge>
                          </div>
                        )}
                      </>
                    );
                  })()}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Actions Footer */}
      <SheetFooter className="gap-2 px-4 py-3 border-t">
        {!isEditMode ? (
          <>
            <Button
              variant="outline"
              onClick={handleEditMapping}
              className="flex-1"
              disabled={isRemoving}
            >
              Edit Mapping
            </Button>
            <Button
              variant="destructive"
              onClick={handleRemoveMappingClick}
              className="flex-1"
              disabled={isRemoving}
            >
              Remove Mapping
            </Button>
          </>
        ) : (
          <>
            <Button
              variant="outline"
              onClick={handleCancelEdit}
              className="flex-1"
              disabled={isSaving}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              className="flex-1"
              disabled={isSaving}
            >
              {isSaving ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Saving...
                </>
              ) : (
                'Save Changes'
              )}
            </Button>
          </>
        )}
      </SheetFooter>

      {/* Delete Confirmation Alert Dialog */}
      <AlertDialog open={showDeleteAlert} onOpenChange={setShowDeleteAlert}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove Mapping?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently remove the mapping for <strong>"{mapping.pdf_field_name}"</strong> from cell <strong>{cellAddress}</strong>. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isRemoving}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmRemoveMapping}
              disabled={isRemoving}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isRemoving ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Removing...
                </>
              ) : (
                'Remove Mapping'
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
