/**
 * Excel Grid View Component
 * Orchestrates the Excel template viewing experience with sheet navigation and cell mapping
 */

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../components/ui/tabs';
import { FileSpreadsheet, AlertCircle, Loader2 } from 'lucide-react';
import { Badge } from '../../../components/ui/badge';
import { Sheet, SheetContent, SheetTitle, SheetDescription } from '../../../components/ui/sheet';

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

  const mappings = useMemo(() => fieldMapping?.mappings || [], [fieldMapping?.mappings]);
  const pdfFields = useMemo(() => fieldMapping?.pdf_fields || [], [fieldMapping?.pdf_fields]);
  const llmExtractedByField = useMemo(() => extractedData?.llm_extracted || {}, [extractedData?.llm_extracted]);
  const manualEditsBySheet = useMemo(() => extractedData?.manual_edits || {}, [extractedData?.manual_edits]);

  const mappingByCell = useMemo(() => {
    const lookup = new Map();
    for (const mapping of mappings) {
      if (!mapping?.excel_sheet || !mapping?.excel_cell) continue;
      lookup.set(`${mapping.excel_sheet}::${mapping.excel_cell}`, mapping);
    }
    return lookup;
  }, [mappings]);

  const yamlUnmappedCellSet = useMemo(() => {
    const lookup = new Set();
    const unmappedCells = fieldMapping?.yaml_cell_status?.unmapped_cells || [];

    for (const cell of unmappedCells) {
      if (!cell?.excel_sheet || !cell?.excel_cell) continue;
      lookup.add(`${cell.excel_sheet}::${cell.excel_cell}`);
    }

    return lookup;
  }, [fieldMapping?.yaml_cell_status?.unmapped_cells]);

  const sheetMappingCounts = useMemo(() => {
    const counts = {};
    for (const mapping of mappings) {
      if (!mapping?.excel_sheet) continue;
      counts[mapping.excel_sheet] = (counts[mapping.excel_sheet] || 0) + 1;
    }
    return counts;
  }, [mappings]);

  const pdfFieldById = useMemo(() => {
    const lookup = new Map();
    for (const field of pdfFields) {
      if (!field?.id) continue;
      lookup.set(field.id, field);
    }
    return lookup;
  }, [pdfFields]);

  // Set initial active sheet when workbook loads
  useEffect(() => {
    if (workbook && !activeSheet) {
      setActiveSheet(workbook.SheetNames[0]);
    }
  }, [workbook, activeSheet]);

  // Helper functions for cell operations
  const getCellMapping = useCallback((sheetName, cellAddress) => {
    return mappingByCell.get(`${sheetName}::${cellAddress}`);
  }, [mappingByCell]);

  const isYamlUnmappedCell = useCallback((sheetName, cellAddress) => {
    return yamlUnmappedCellSet.has(`${sheetName}::${cellAddress}`);
  }, [yamlUnmappedCellSet]);

  const getCellValue = useCallback((sheetName, cellAddress, mappingOverride = null) => {
    const mapping = mappingOverride || getCellMapping(sheetName, cellAddress);

    // If mapped, get value from LLM extracted data
    if (mapping) {
      const fieldId = mapping.pdf_field_id;
      const fieldData = llmExtractedByField?.[fieldId];
      if (fieldData?.value !== undefined) return fieldData.value;

      // Fall back to extracted_value from pdf_fields
      const pdfField = pdfFieldById.get(fieldId);
      return pdfField?.extracted_value || null;
    }

    // For unmapped cells edited directly, check manual_edits
    const manualValue = manualEditsBySheet?.[sheetName]?.[cellAddress];
    if (manualValue?.value !== undefined) return manualValue.value;

    return null;
  }, [getCellMapping, llmExtractedByField, manualEditsBySheet, pdfFieldById]);

  const getCurrentCellData = useCallback((sheetName, cellAddress) => {
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
  }, [workbook]);

  const handleCellClick = useCallback((sheetName, cellAddress, cellData) => {
    const mapping = getCellMapping(sheetName, cellAddress);

    // Allow clicking on any non-formula cell (mapped or unmapped)
    setSelectedCell({
      sheetName,
      cellAddress,
      mapping,
      pdfField: mapping ? pdfFieldById.get(mapping.pdf_field_id) : null,
      value: mapping ? getCellValue(sheetName, cellAddress, mapping) : null,
      cellData,
    });
  }, [getCellMapping, getCellValue, pdfFieldById]);

  // Refresh cellData when selectedCell changes (ensures we always show current value)
  useEffect(() => {
    if (selectedCell && workbook) {
      const currentCellData = getCurrentCellData(selectedCell.sheetName, selectedCell.cellAddress);
      if (currentCellData) {
        setSelectedCell(prev => {
          if (!prev) return prev;
          const isSameData =
            prev.cellData?.v === currentCellData.v &&
            prev.cellData?.w === currentCellData.w &&
            prev.cellData?.t === currentCellData.t &&
            prev.cellData?.f === currentCellData.f;

          if (isSameData) return prev;
          return {
            ...prev,
            cellData: currentCellData,
          };
        });
      }
    }
  }, [selectedCell, workbook, getCurrentCellData]);

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
    <div className="flex flex-col h-full min-h-0 overflow-hidden">
      {/* Sheet Navigation Tabs */}
      <Tabs value={activeSheet} onValueChange={setActiveSheet} className="flex-1 min-h-0 flex flex-col overflow-hidden">
        <TabsList className="w-full justify-start overflow-x-auto [&::-webkit-scrollbar]:h-1 [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-thumb]:rounded-full hover:[&::-webkit-scrollbar-thumb]:bg-muted-foreground/50">
          {workbook.SheetNames.map((sheetName) => {
            const sheetMappingCount = sheetMappingCounts[sheetName] || 0;
            return (
              <TabsTrigger key={sheetName} value={sheetName} className="relative">
                {sheetName}
                {sheetMappingCount > 0 && (
                  <Badge variant="secondary" className="ml-2 text-xs">
                    {sheetMappingCount}
                  </Badge>
                )}
              </TabsTrigger>
            );
          })}
        </TabsList>

        {/* Sheet Content */}
        {activeSheet && (
          <TabsContent key={activeSheet} value={activeSheet} className="flex-1 min-h-0 mt-0 overflow-hidden">
            <ExcelGrid
              workbook={workbook}
              sheetName={activeSheet}
              getCellValue={getCellValue}
              getCellMapping={getCellMapping}
              isYamlUnmappedCell={isYamlUnmappedCell}
              onCellClick={handleCellClick}
              selectedCell={selectedCell?.sheetName === activeSheet ? selectedCell : null}
            />
          </TabsContent>
        )}
      </Tabs>

      {/* Mapping Details Drawer */}
      <Sheet open={!!selectedCell} onOpenChange={(open) => !open && setSelectedCell(null)}>
        <SheetContent side="right" className="w-[400px] flex flex-col">
          <SheetTitle className="sr-only">Cell Mapping Details</SheetTitle>
          <SheetDescription className="sr-only">
            Inspect and edit mapping details for the selected spreadsheet cell.
          </SheetDescription>
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

    </div>
  );
}
