/**
 * Excel Grid View Component
 * Orchestrates the Excel template viewing experience with sheet navigation and cell mapping
 */

import React, { useState, useEffect } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../components/ui/tabs';
import { FileSpreadsheet, AlertCircle, Loader2, Info } from 'lucide-react';
import { Badge } from '../../../components/ui/badge';
import { Sheet, SheetContent } from '../../../components/ui/sheet';

import { useExcelWorkbook } from '../hooks/useExcelWorkbook';
import ExcelGrid from './ExcelGrid';
import MappingDetailsDialog from './MappingDetailsDialog';

export default function ExcelGridView({
  fillRunId,
  extractedData = {},
  fieldMapping = {},
  templateId,
  onCitationClick,
}) {
  // Load Excel workbook using custom hook
  const { workbook, loading, error } = useExcelWorkbook(templateId);

  const [activeSheet, setActiveSheet] = useState(null);
  const [selectedCell, setSelectedCell] = useState(null);

  const mappings = fieldMapping?.mappings || [];
  const pdfFields = fieldMapping?.pdf_fields || [];

  // Debug logging for mapping issues
  React.useEffect(() => {
    if (mappings.length > 0) {
      // Group by sheet
      const bySheet = {};
      mappings.forEach(m => {
        if (!bySheet[m.excel_sheet]) {
          bySheet[m.excel_sheet] = [];
        }
        bySheet[m.excel_sheet].push(m);
      });

      // Check for duplicates
      const cellAddresses = mappings.map(m => `${m.excel_sheet}!${m.excel_cell}`);
      const uniqueCells = new Set(cellAddresses);

      if (uniqueCells.size < mappings.length) {
        console.warn('⚠️ Duplicate cell mappings detected!');
        const duplicates = {};
        cellAddresses.forEach(cell => {
          duplicates[cell] = (duplicates[cell] || 0) + 1;
        });
        const dups = Object.entries(duplicates).filter(([_, count]) => count > 1);

        // Show which PDF fields are mapped to each duplicate cell
        dups.forEach(([cellAddr, count]) => {
          const fields = mappings.filter(m => `${m.excel_sheet}!${m.excel_cell}` === cellAddr);
          const fieldNames = fields.map(f => {
            const pdfField = pdfFields.find(p => p.id === f.pdf_field_id);
            return pdfField?.name || f.excel_label || f.pdf_field_id;
          });
        });
      }

      // Check for null/empty cells
      const invalidMappings = mappings.filter(m => !m.excel_cell || !m.excel_sheet);
      if (invalidMappings.length > 0) {
        console.warn('⚠️ Invalid mappings (null/empty cell or sheet):', invalidMappings.length);
      }
    }
  }, [mappings]);

  // Set initial active sheet when workbook loads
  useEffect(() => {
    if (workbook && !activeSheet) {
      setActiveSheet(workbook.SheetNames[0]);
    }
  }, [workbook]);

  // Helper functions for cell operations
  function getCellMapping(sheetName, cellAddress) {
    return mappings.find(
      (m) => m.excel_sheet === sheetName && m.excel_cell === cellAddress
    );
  }

  function getCellValue(sheetName, cellAddress) {
    const mapping = getCellMapping(sheetName, cellAddress);

    // If mapped, get value from LLM extracted data
    if (mapping) {
      const fieldId = mapping.pdf_field_id;
      const fieldData = extractedData?.llm_extracted?.[fieldId];
      if (fieldData?.value !== undefined) return fieldData.value;

      // Fall back to sample_value from pdf_fields
      const pdfField = pdfFields.find(f => f.id === fieldId);
      return pdfField?.sample_value || null;
    }

    // For unmapped cells edited directly, check manual_edits
    const manualValue = extractedData?.manual_edits?.[sheetName]?.[cellAddress];
    if (manualValue?.value !== undefined) return manualValue.value;

    return null;
  }

  function getCurrentCellData(sheetName, cellAddress) {
    if (!workbook) return null;

    try {
      const sheet = workbook.Sheets[sheetName];
      if (!sheet) return null;

      const cell = sheet[cellAddress];
      if (!cell) return null;

      // Return the current cell data from workbook (reading fresh value)
      return {
        v: cell.v,          // Value
        w: cell.w,          // Formatted/display value
        t: cell.t,          // Type (b, n, e, s, d, bl, g)
        f: cell.f,          // Formula (if applicable)
      };
    } catch (err) {
      console.warn(`Error reading cell ${sheetName}!${cellAddress}:`, err);
      return null;
    }
  }

  function handleCellClick(sheetName, cellAddress, cellData) {
    const mapping = getCellMapping(sheetName, cellAddress);

    // Allow clicking on any non-formula cell (mapped or unmapped)
    setSelectedCell({
      sheetName,
      cellAddress,
      mapping,
      pdfField: mapping ? pdfFields.find(f => f.id === mapping.pdf_field_id) : null,
      value: mapping ? getCellValue(sheetName, cellAddress) : null,
      cellData,
    });
  }

  // Refresh cellData when selectedCell changes (ensures we always show current value)
  useEffect(() => {
    if (selectedCell && workbook) {
      const currentCellData = getCurrentCellData(selectedCell.sheetName, selectedCell.cellAddress);
      if (currentCellData) {
        setSelectedCell(prev => ({
          ...prev,
          cellData: currentCellData,
        }));
      }
    }
  }, [selectedCell?.cellAddress, selectedCell?.sheetName, workbook]);

  // Loading state
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

  // Error state
  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-3">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <span className="text-sm text-foreground">Error: {error}</span>
        </div>
      </div>
    );
  }

  // Empty state
  if (!workbook) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-3">
          <FileSpreadsheet className="h-8 w-8 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">No Excel file loaded</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full gap-4">
      {/* Sheet Navigation Tabs */}
      <Tabs value={activeSheet} onValueChange={setActiveSheet} className="flex-1 flex flex-col">
        <TabsList className="w-full justify-start overflow-x-auto [&::-webkit-scrollbar]:h-1 [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-thumb]:rounded-full hover:[&::-webkit-scrollbar-thumb]:bg-muted-foreground/50">
          {workbook.SheetNames.map((sheetName) => {
            const sheetMappings = mappings.filter(m => m.excel_sheet === sheetName);
            return (
              <TabsTrigger key={sheetName} value={sheetName} className="relative">
                {sheetName}
                {sheetMappings.length > 0 && (
                  <Badge variant="secondary" className="ml-2 text-xs">
                    {sheetMappings.length}
                  </Badge>
                )}
              </TabsTrigger>
            );
          })}
        </TabsList>

        {/* Sheet Content */}
        {workbook.SheetNames.map((sheetName) => (
          <TabsContent key={sheetName} value={sheetName} className="flex-1 mt-4">
            <ExcelGrid
              workbook={workbook}
              sheetName={sheetName}
              mappings={mappings}
              pdfFields={pdfFields}
              getCellValue={getCellValue}
              getCellMapping={getCellMapping}
              onCellClick={handleCellClick}
              selectedCell={selectedCell?.sheetName === sheetName ? selectedCell : null}
            />
          </TabsContent>
        ))}
      </Tabs>

      {/* Mapping Details Drawer */}
      <Sheet open={!!selectedCell} onOpenChange={(open) => !open && setSelectedCell(null)}>
        <SheetContent side="right" className="w-[400px] flex flex-col">
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
      <div className="border-t pt-2 px-2">
        <div className="flex items-center gap-4 flex-wrap text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded border-2 border-green-500" />
            <span>High Confidence (80%+)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded border-2 border-yellow-500" />
            <span>Medium Confidence (50-80%)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded border-2 border-red-500" />
            <span>Low Confidence (&lt;50%)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="bg-muted px-1.5 py-0.5 rounded text-xs">Formula</span>
            <span>Formula Cell (Read-Only)</span>
          </div>
          <div className="flex items-center gap-2">
            <Info className="h-3 w-3" />
            <span>Click any cell to edit or add mapping</span>
          </div>
        </div>
      </div>
    </div>
  );
}
