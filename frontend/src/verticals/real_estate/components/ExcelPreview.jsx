/**
 * Excel Preview Component
 * Displays a simplified preview of the Excel template with mapped fields
 */

import React, { useState, useEffect } from 'react';
import { useAuth } from '@clerk/clerk-react';
import { getRETemplate } from '../../../api/re-templates';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../components/ui/tabs';
import { FileSpreadsheet, AlertCircle, Loader2 } from 'lucide-react';
import { Badge } from '../../../components/ui/badge';
import { cn } from '@/lib/utils';

export default function ExcelPreview({
  fillRunId,
  extractedData = {},
  fieldMapping = {},
  templateId,
}) {
  const { getToken } = useAuth();
  const [template, setTemplate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeSheet, setActiveSheet] = useState(null);

  const mappings = fieldMapping?.mappings || [];

  useEffect(() => {
    loadTemplate();
  }, [templateId]);

  useEffect(() => {
    // Set first sheet as active when template loads
    if (template?.schema_metadata?.sheets?.length > 0 && !activeSheet) {
      setActiveSheet(template.schema_metadata.sheets[0].name);
    }
  }, [template]);

  async function loadTemplate() {
    try {
      setLoading(true);
      setError(null);

      const data = await getRETemplate(getToken, templateId);
      setTemplate(data);
    } catch (err) {
      console.error('❌ Failed to load template:', err);
      console.error('❌ Error details:', err.response?.data);
      setError('Failed to load template schema');
    } finally {
      setLoading(false);
    }
  }

  function getCellValue(sheetName, cellAddress) {
    // Find mapping for this cell
    const mapping = mappings.find(
      (m) => m.excel_sheet === sheetName && m.excel_cell === cellAddress
    );

    if (!mapping) return null;

    // Get extracted data value (if available from extraction phase)
    const fieldData = extractedData[mapping.pdf_field_id];
    if (fieldData?.value) {
      return fieldData.value;
    }

    // Fall back to sample_value from pdf_fields (available after field detection)
    const pdfFields = fieldMapping?.pdf_fields || [];
    const pdfField = pdfFields.find(f => f.id === mapping.pdf_field_id);
    return pdfField?.sample_value || null;
  }

  function isCellMapped(sheetName, cellAddress) {
    return mappings.some(
      (m) => m.excel_sheet === sheetName && m.excel_cell === cellAddress
    );
  }

  function getCellClasses(sheetName, cellAddress, cellType) {
    const isMapped = isCellMapped(sheetName, cellAddress);
    const hasValue = getCellValue(sheetName, cellAddress);

    if (cellType === 'formula') {
      return 'bg-muted text-muted-foreground italic';
    }

    if (isMapped && hasValue) {
      return 'bg-success/10 border-success/30 text-success-foreground';
    }

    if (isMapped) {
      return 'bg-warning/10 border-warning/30 text-foreground';
    }

    return 'bg-card text-foreground';
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
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

  if (!template?.schema_metadata?.sheets) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-6 text-muted-foreground">
        <FileSpreadsheet className="h-10 w-10 mb-3 text-muted-foreground/50" />
        <p className="text-sm">No template schema available</p>
      </div>
    );
  }

  const sheets = template.schema_metadata.sheets;

  return (
    <div className="h-full flex flex-col">
      {/* Sheet Tabs */}
      <Tabs value={activeSheet} onValueChange={setActiveSheet} className="flex-1 flex flex-col">
        <TabsList className="w-full justify-start bg-transparent border-b rounded-none p-0 h-auto">
          {sheets.map((sheet) => {
            // Calculate total fillable cells from key_value_fields and tables
            const keyValueCount = sheet.key_value_fields?.length || 0;
            const tableCount = sheet.tables?.reduce((sum, table) =>
              sum + (table.fillable_cells?.length || 0), 0) || 0;
            const totalFillable = keyValueCount + tableCount;

            return (
              <TabsTrigger
                key={sheet.name}
                value={sheet.name}
                className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-3 py-2"
              >
                <span className="text-xs font-medium">{sheet.name}</span>
                <Badge variant="secondary" className="ml-1.5 text-xs h-4 px-1.5">
                  {totalFillable}
                </Badge>
              </TabsTrigger>
            );
          })}
        </TabsList>

        {/* Sheet Content */}
        {sheets.map((sheet) => (
          <TabsContent
            key={sheet.name}
            value={sheet.name}
            className="flex-1 overflow-auto p-3 mt-0"
          >
            <SheetPreview
              sheet={sheet}
              extractedData={extractedData}
              mappings={mappings}
              getCellValue={getCellValue}
              getCellClasses={getCellClasses}
            />
          </TabsContent>
        ))}
      </Tabs>

      {/* Legend */}
      <div className="border-t bg-muted/30 p-2.5">
        <p className="text-xs font-medium text-foreground mb-1.5">Legend:</p>
        <div className="flex gap-3 text-xs flex-wrap">
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 bg-success/10 border border-success/30 rounded"></div>
            <span className="text-muted-foreground">Filled</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 bg-warning/10 border border-warning/30 rounded"></div>
            <span className="text-muted-foreground">Mapped</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 bg-muted border border-border rounded"></div>
            <span className="text-muted-foreground">Formula</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 bg-card border border-border rounded"></div>
            <span className="text-muted-foreground">Static</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function SheetPreview({ sheet, extractedData, mappings, getCellValue, getCellClasses }) {
  // Combine key_value_fields and all table fillable_cells into one array
  const allCells = [
    ...(sheet.key_value_fields || []),
    ...(sheet.tables?.flatMap(table => table.fillable_cells || []) || [])
  ];

  // Deduplicate by cell address (keep first occurrence)
  const seenAddresses = new Set();
  const fillableCells = allCells.filter((cell) => {
    const cellAddress = cell.address || cell.cell;
    if (seenAddresses.has(cellAddress)) {
      return false;
    }
    seenAddresses.add(cellAddress);
    return true;
  });

  if (fillableCells.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        <p className="text-sm">No fillable cells in this sheet</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {fillableCells.map((cell) => {
        const cellAddress = cell.address || cell.cell;
        const value = getCellValue(sheet.name, cellAddress);
        const cellClasses = getCellClasses(sheet.name, cellAddress, cell.type);

        return (
          <div
            key={cellAddress}
            className={cn(
              "border rounded-md p-2.5 transition-colors",
              cellClasses
            )}
          >
            <div className="flex items-start justify-between mb-1">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="font-mono text-xs h-5 px-1.5">
                  {cellAddress}
                </Badge>
                {cell.label && (
                  <span className="text-xs font-medium">{cell.label}</span>
                )}
              </div>
              {cell.type && (
                <Badge variant="secondary" className="text-xs h-5">
                  {cell.type}
                </Badge>
              )}
            </div>

            <div className="text-xs">
              {cell.type === 'formula' ? (
                <code className="font-mono">{cell.formula || 'Formula'}</code>
              ) : value ? (
                <span className="font-medium">{value}</span>
              ) : (
                <span className="text-muted-foreground italic">
                  {cell.placeholder || 'No value yet'}
                </span>
              )}
            </div>

            {cell.validation && (
              <p className="text-xs text-muted-foreground mt-1">
                Validation: {cell.validation}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
