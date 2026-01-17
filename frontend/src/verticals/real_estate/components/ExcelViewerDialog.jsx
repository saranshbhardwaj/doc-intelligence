/**
 * Excel Viewer Dialog
 * Display uploaded Excel templates with professional grid view
 * Similar to ExcelGridView but without mapping features
 */

import React, { useState, useEffect } from 'react';
import { useAuth } from '@clerk/clerk-react';
import * as XLSX from 'xlsx';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../../../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../components/ui/tabs';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { Loader2, AlertCircle, FileSpreadsheet, Download, Table, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import { downloadRETemplate } from '../../../api/re-templates';

export default function ExcelViewerDialog({ open, onOpenChange, templateId, templateName }) {
  const { getToken } = useAuth();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [workbook, setWorkbook] = useState(null);
  const [activeSheet, setActiveSheet] = useState(null);
  const [fileBlob, setFileBlob] = useState(null);

  useEffect(() => {
    if (open && templateId) {
      loadExcelFile();
    } else {
      // Reset when dialog closes
      setWorkbook(null);
      setActiveSheet(null);
      setError(null);
      setFileBlob(null);
    }
  }, [open, templateId]);

  async function loadExcelFile() {
    try {
      setLoading(true);
      setError(null);

      // Download Excel file (streams through backend to avoid CORS)
      const arrayBuffer = await downloadRETemplate(getToken, templateId);

      // Create blob for download button
      const blob = new Blob([arrayBuffer], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });
      setFileBlob(blob);

      // Parse with XLSX
      const wb = XLSX.read(arrayBuffer, { type: 'array' });
      setWorkbook(wb);
      setActiveSheet(wb.SheetNames[0]); // Set first sheet as active
    } catch (err) {
      console.error('Failed to load Excel file:', err);
      setError(err.message || 'Failed to load Excel file');
    } finally {
      setLoading(false);
    }
  }

  function handleDownload() {
    if (fileBlob) {
      const url = URL.createObjectURL(fileBlob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${templateName || 'template'}.xlsx`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url); // Clean up
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-7xl max-h-[90vh] flex flex-col p-0">
        {/* Header */}
        <DialogHeader className="flex-shrink-0 px-6 pt-6 pb-4 border-b">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-primary/10 rounded-lg">
                <FileSpreadsheet className="h-5 w-5 text-primary" />
              </div>
              <div>
                <DialogTitle className="text-lg">{templateName || 'Excel Template'}</DialogTitle>
                <p className="text-xs text-muted-foreground mt-0.5">Read-only preview</p>
              </div>
            </div>
            {fileBlob && (
              <Button size="sm" variant="outline" onClick={handleDownload}>
                <Download className="h-4 w-4 mr-2" />
                Download
              </Button>
            )}
          </div>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="flex flex-col items-center gap-3">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <span className="text-sm text-muted-foreground">Loading template...</span>
            </div>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-16">
            <AlertCircle className="h-12 w-12 text-destructive mb-3" />
            <p className="text-destructive text-sm">{error}</p>
            <Button onClick={loadExcelFile} variant="outline" size="sm" className="mt-4">
              Try Again
            </Button>
          </div>
        ) : workbook && activeSheet ? (
          <div className="flex-1 flex flex-col overflow-hidden">
            <ExcelGridDisplay
              workbook={workbook}
              activeSheet={activeSheet}
              onSheetChange={setActiveSheet}
            />
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

// Excel Grid Display Component (simplified version of ExcelGridView)
function ExcelGridDisplay({ workbook, activeSheet, onSheetChange }) {
  const [displayRowEnd, setDisplayRowEnd] = useState(50);
  const [displayColEnd, setDisplayColEnd] = useState(15);

  const worksheet = workbook.Sheets[activeSheet];
  const range = XLSX.utils.decode_range(worksheet['!ref'] || 'A1');

  const totalRows = range.e.r + 1;
  const totalCols = range.e.c + 1;
  const hasMoreRows = displayRowEnd < range.e.r;
  const hasMoreCols = displayColEnd < range.e.c;

  function handleLoadMoreRows() {
    setDisplayRowEnd(prev => Math.min(prev + 50, range.e.r));
  }

  function handleLoadMoreCols() {
    setDisplayColEnd(prev => Math.min(prev + 10, range.e.c));
  }

  // Reset when sheet changes
  useEffect(() => {
    setDisplayRowEnd(50);
    setDisplayColEnd(15);
  }, [activeSheet]);

  // Count fillable cells (cells with labels)
  const fillableCells = Object.keys(worksheet).filter(key => {
    if (key.startsWith('!')) return false;
    const cell = worksheet[key];
    return cell && cell.v && typeof cell.v === 'string' && cell.v.trim().length > 0;
  }).length;

  return (
    <Tabs
      value={activeSheet}
      onValueChange={onSheetChange}
      className="flex-1 flex flex-col overflow-hidden"
    >
      {/* Sheet Tabs */}
      <div className="flex-shrink-0 bg-card border-b">
        <TabsList className="w-full justify-start bg-transparent rounded-none p-0 h-auto border-b-0 overflow-x-auto flex-nowrap">
          {workbook.SheetNames.map((sheetName) => {
            const sheet = workbook.Sheets[sheetName];
            const sheetRange = XLSX.utils.decode_range(sheet['!ref'] || 'A1');

            // Count only filled cells
            const filledCells = Object.keys(sheet).filter(key => {
              if (key.startsWith('!')) return false;
              const cell = sheet[key];
              return cell && cell.v !== undefined && cell.v !== '';
            }).length;

            return (
              <TabsTrigger
                key={sheetName}
                value={sheetName}
                className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-3 gap-2 whitespace-nowrap"
              >
                <Table className="h-4 w-4" />
                <span className="text-sm font-medium">{sheetName}</span>
                {filledCells > 0 && (
                  <Badge variant="secondary" className="text-xs">
                    {filledCells}
                  </Badge>
                )}
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
          className="flex-1 overflow-auto m-0 p-4 data-[state=inactive]:hidden"
        >
          <div className="inline-block min-w-full">
            {/* Excel Table */}
            <div className="border rounded-lg overflow-hidden bg-card">
              <table className="border-collapse w-full text-sm">
                <thead className="sticky top-0 z-10">
                  <tr>
                    <th className="border border-border bg-muted px-2 py-1.5 text-center font-semibold text-xs w-12 sticky left-0 z-20">
                      #
                    </th>
                    {Array.from({ length: Math.min(displayColEnd + 1, totalCols) }, (_, colIdx) => (
                      <th
                        key={colIdx}
                        className="border border-border bg-muted px-2 py-1.5 text-center font-semibold text-xs min-w-[100px]"
                      >
                        {XLSX.utils.encode_col(colIdx)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: Math.min(displayRowEnd + 1, totalRows) }, (_, rowIdx) => (
                    <tr key={rowIdx} className="hover:bg-muted/50">
                      <td className="border border-border bg-muted/30 px-2 py-1.5 text-center font-semibold text-xs sticky left-0 z-10">
                        {rowIdx + 1}
                      </td>
                      {Array.from({ length: Math.min(displayColEnd + 1, totalCols) }, (_, colIdx) => {
                        const cellAddress = XLSX.utils.encode_cell({ r: rowIdx, c: colIdx });
                        const cellData = worksheet[cellAddress];
                        const cellValue = cellData ? (cellData.w || cellData.v) : '';

                        return (
                          <td
                            key={cellAddress}
                            className={cn(
                              'border border-border px-2 py-1.5 text-foreground transition-colors',
                              cellData ? 'bg-background' : 'bg-muted/20'
                            )}
                          >
                            {cellValue}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Load More Controls */}
            <div className="mt-4 flex items-center gap-3 flex-wrap">
              {hasMoreRows && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleLoadMoreRows}
                  className="text-xs"
                >
                  Load 50 More Rows ({displayRowEnd + 1} / {totalRows})
                </Button>
              )}
              {hasMoreCols && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleLoadMoreCols}
                  className="text-xs"
                >
                  Load 10 More Columns ({XLSX.utils.encode_col(displayColEnd)} / {XLSX.utils.encode_col(range.e.c)})
                </Button>
              )}
              {!hasMoreRows && !hasMoreCols && (
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <Info className="h-3 w-3" />
                  All rows and columns loaded ({totalRows} rows × {totalCols} columns)
                </p>
              )}
            </div>
          </div>
        </TabsContent>
      ))}
    </Tabs>
  );
}
