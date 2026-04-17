/**
 * Fields List Component
 * Airtable-style grid table of extracted PDF fields with search, filtering, and pagination.
 */

import React, { useState, useMemo } from 'react';
import { useAppAuth } from "@/hooks/useAppAuth";
import { useTemplateFillActions } from '../../../store';
import { Copy, Check, AlertCircle, Loader2, Search, ChevronLeft, ChevronRight, Filter, FileText } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Popover, PopoverContent, PopoverTrigger } from '../../../components/ui/popover';
import { cn } from '@/lib/utils';
import { CitationSection } from './CitationBadge';

const EDIT_SOURCE_PDF_PASTE = 'pdf_paste';
const EDIT_SOURCE_MANUAL_INPUT = 'manual_input';

/** Colored confidence dot + numeric label */
function ConfidenceIndicator({ confidence }) {
  const pct = Math.round((confidence || 0) * 100);
  const dotClass =
    pct >= 80 ? 'bg-green-500' : pct >= 50 ? 'bg-amber-500' : 'bg-destructive';
  const textClass =
    pct >= 80
      ? 'text-green-600 dark:text-green-400'
      : pct >= 50
      ? 'text-amber-600 dark:text-amber-400'
      : 'text-destructive';
  return (
    <span className="flex items-center gap-1.5">
      <span className={cn('inline-block h-1.5 w-1.5 rounded-full shrink-0', dotClass)} />
      <span className={cn('text-xs tabular-nums tracking-[0.07px]', textClass)}>{pct}%</span>
    </span>
  );
}

export default function FieldsList({
  fillRunId,
  extractedData = {},
  fieldMapping = {},
  citationContext = null,
  selectedText,
  onCitationClick,
}) {
  const { getToken } = useAppAuth();
  const { updateFieldData } = useTemplateFillActions();
  const [editingField, setEditingField] = useState(null);
  const [editDraft, setEditDraft] = useState('');
  const [savingField, setSavingField] = useState(null);
  const [error, setError] = useState(null);

  // Pagination and filtering state
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState('all'); // all, mapped, unmapped
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // Use pdf_fields from field_mapping (available after field detection)
  // Fall back to extractedData (available after extraction phase)
  const pdfFields = fieldMapping?.pdf_fields || [];
  const allFields = pdfFields.length > 0
    ? pdfFields.map(f => [f.id, {
        value: extractedData[f.id]?.value || f.extracted_value,
        confidence: extractedData[f.id]?.confidence || f.confidence,
        source_page: extractedData[f.id]?.source_page,
        user_edited: extractedData[f.id]?.user_edited || false,
        field_name: f.name,
        field_type: f.type,
        citations: f.citations || extractedData[f.id]?.citations,
        bbox: f.bbox || extractedData[f.id]?.bbox,
      }])
    : Object.entries(extractedData).map(([id, data]) => [id, data]);

  const mappings = fieldMapping?.mappings || [];

  function getFieldMapping(fieldId) {
    return mappings.find((m) => m.pdf_field_id === fieldId);
  }

  function getOriginalValue(fieldId) {
    const pdfField = pdfFields.find(f => f.id === fieldId);
    return pdfField?.extracted_value ?? null;
  }

  function resolveOriginalValue(fieldId, currentField) {
    return 'original_value' in currentField
      ? currentField.original_value
      : getOriginalValue(fieldId);
  }

  // Filter and search fields
  const filteredFields = useMemo(() => {
    let filtered = allFields;

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(([fieldId, fieldData]) => {
        const mapping = getFieldMapping(fieldId);
        return (
          (fieldData.field_name || '').toLowerCase().includes(query) ||
          (fieldData.value || '').toLowerCase().includes(query) ||
          (mapping?.excel_cell || '').toLowerCase().includes(query) ||
          (mapping?.excel_label || '').toLowerCase().includes(query)
        );
      });
    }

    if (filterStatus === 'mapped') {
      filtered = filtered.filter(([fieldId]) => getFieldMapping(fieldId));
    } else if (filterStatus === 'unmapped') {
      filtered = filtered.filter(([fieldId]) => !getFieldMapping(fieldId));
    }

    return filtered;
  }, [allFields, searchQuery, filterStatus, mappings]);

  // Pagination
  const totalPages = Math.ceil(filteredFields.length / pageSize);
  const paginatedFields = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredFields.slice(start, start + pageSize);
  }, [filteredFields, currentPage, pageSize]);

  React.useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, filterStatus, pageSize]);

  async function handlePasteText(fieldId) {
    if (!selectedText?.text) return;
    try {
      setSavingField(fieldId);
      setError(null);
      const currentField = extractedData[fieldId] || {};
      const updatedData = {
        ...extractedData,
        [fieldId]: {
          ...currentField,
          value: selectedText.text,
          confidence: 1.0,
          user_edited: true,
          source_page: selectedText.page,
          source: EDIT_SOURCE_PDF_PASTE,
          original_value: resolveOriginalValue(fieldId, currentField),
        },
      };
      await updateFieldData(fillRunId, updatedData, getToken);
    } catch (err) {
      console.error('Failed to update field:', err);
      setError('Failed to save field value');
    } finally {
      setSavingField(null);
    }
  }

  async function handleFieldEdit(fieldId, newValue) {
    try {
      setSavingField(fieldId);
      setError(null);
      const currentField = extractedData[fieldId] || {};
      const updatedData = {
        ...extractedData,
        [fieldId]: {
          ...currentField,
          value: newValue,
          confidence: 1.0,
          user_edited: true,
          source: EDIT_SOURCE_MANUAL_INPUT,
          original_value: resolveOriginalValue(fieldId, currentField),
        },
      };
      await updateFieldData(fillRunId, updatedData, getToken);
      setEditingField(null);
    } catch (err) {
      console.error('Failed to update field:', err);
      setError('Failed to save field value');
    } finally {
      setSavingField(null);
    }
  }

  function startEdit(fieldId, currentValue) {
    setEditingField(fieldId);
    setEditDraft(currentValue || '');
  }

  if (allFields.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-6 text-muted-foreground">
        <AlertCircle className="h-10 w-10 mb-3 text-muted-foreground/50" />
        <p className="text-center text-sm tracking-[0.07px]">No fields detected yet</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="px-3 py-2.5 space-y-2 border-b bg-muted/20 flex-shrink-0">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search by name, value, or cell…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 h-8 text-xs tracking-[0.07px]"
          />
        </div>
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Filter className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <Select value={filterStatus} onValueChange={setFilterStatus}>
              <SelectTrigger className="h-7 text-xs w-[130px] tracking-[0.07px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Fields</SelectItem>
                <SelectItem value="mapped">Mapped Only</SelectItem>
                <SelectItem value="unmapped">Unmapped Only</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <span className="text-[11px] text-muted-foreground tracking-[0.28px] tabular-nums">
            {filteredFields.length} / {allFields.length}
          </span>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mx-3 mt-2 bg-destructive/10 text-destructive p-2.5 rounded-lg text-xs border border-destructive/20 tracking-[0.07px] flex-shrink-0">
          {error}
        </div>
      )}

      {/* Selected text banner */}
      {selectedText && (
        <div className="mx-3 mt-2 bg-primary/5 border border-primary/20 p-2.5 rounded-lg flex-shrink-0">
          <p className="text-[11px] text-primary font-medium mb-1 tracking-[0.12px]">
            Selected · Page {selectedText.page}
          </p>
          <p className="text-xs text-foreground break-words tracking-[0.07px] line-clamp-2">
            {selectedText.text}
          </p>
        </div>
      )}

      {/* Table */}
      <div className="flex-1 overflow-auto">
        {paginatedFields.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Search className="h-8 w-8 mb-3 text-muted-foreground/50" />
            <p className="text-sm tracking-[0.07px]">No fields match your search</p>
          </div>
        ) : (
          <table className="w-full table-fixed border-collapse">
            <thead className="sticky top-0 z-10 bg-card border-b border-border">
              <tr>
                <th className="w-[36%] px-3 py-2 text-left text-[11px] font-medium text-muted-foreground tracking-[0.28px] uppercase">
                  Field Name
                </th>
                <th className="w-[32%] px-3 py-2 text-left text-[11px] font-medium text-muted-foreground tracking-[0.28px] uppercase">
                  Value
                </th>
                <th className="w-[12%] px-3 py-2 text-left text-[11px] font-medium text-muted-foreground tracking-[0.28px] uppercase">
                  Conf.
                </th>
                <th className="w-[20%] px-3 py-2 text-left text-[11px] font-medium text-muted-foreground tracking-[0.28px] uppercase">
                  Maps To
                </th>
              </tr>
            </thead>
            <tbody>
              {paginatedFields.map(([fieldId, fieldData]) => {
                const mapping = getFieldMapping(fieldId);
                const isEditing = editingField === fieldId;
                const isSaving = savingField === fieldId;
                const hasCitations = fieldData.citations && fieldData.citations.length > 0;

                return (
                  <tr
                    key={fieldId}
                    className={cn(
                      'border-b border-border/50 transition-colors group',
                      'hover:bg-accent/30',
                      isSaving && 'opacity-60',
                    )}
                  >
                    {/* Field Name */}
                    <td className="px-3 py-2 align-top">
                      <div className="flex flex-col gap-0.5 min-w-0">
                        <span className="text-xs font-medium text-foreground truncate tracking-[0.07px]">
                          {fieldData.field_name || fieldData.label || fieldId}
                        </span>
                        {fieldData.field_type && (
                          <span className="text-[10px] text-muted-foreground/70 tracking-[0.28px] uppercase">
                            {fieldData.field_type}
                          </span>
                        )}
                        {fieldData.user_edited && (
                          <span className="inline-flex items-center gap-0.5 text-[10px] text-green-600 dark:text-green-400 tracking-[0.07px]">
                            <Check className="h-2.5 w-2.5" />
                            edited
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Value — inline editable */}
                    <td className="px-3 py-2 align-top">
                      {isEditing ? (
                        <Input
                          type="text"
                          value={editDraft}
                          onChange={(e) => setEditDraft(e.target.value)}
                          onBlur={() => {
                            if (editDraft !== (fieldData.value || '')) {
                              handleFieldEdit(fieldId, editDraft);
                            } else {
                              setEditingField(null);
                            }
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleFieldEdit(fieldId, editDraft);
                            else if (e.key === 'Escape') setEditingField(null);
                          }}
                          autoFocus
                          className="h-7 text-xs px-2 tracking-[0.07px]"
                        />
                      ) : (
                        <div className="flex items-start gap-1 min-w-0">
                          <span
                            onClick={() => startEdit(fieldId, fieldData.value)}
                            title="Click to edit"
                            className={cn(
                              'text-xs break-words cursor-pointer rounded px-1 -mx-1 py-0.5 -my-0.5',
                              'hover:bg-muted/60 transition-colors tracking-[0.07px]',
                              fieldData.value ? 'text-foreground' : 'text-muted-foreground italic',
                            )}
                          >
                            {fieldData.value || 'No value'}
                          </span>
                          {isSaving && (
                            <Loader2 className="h-3 w-3 animate-spin text-muted-foreground shrink-0 mt-0.5" />
                          )}
                          {selectedText && !isSaving && (
                            <button
                              onClick={() => handlePasteText(fieldId)}
                              title="Paste selected text"
                              className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mt-0.5"
                            >
                              <Copy className="h-3 w-3 text-muted-foreground hover:text-foreground" />
                            </button>
                          )}
                        </div>
                      )}
                    </td>

                    {/* Confidence */}
                    <td className="px-3 py-2 align-top">
                      <ConfidenceIndicator confidence={fieldData.confidence} />
                    </td>

                    {/* Maps To + citations popover */}
                    <td className="px-3 py-2 align-top">
                      <div className="flex items-center gap-1.5 min-w-0">
                        {mapping ? (
                          <span className="font-mono text-[11px] text-muted-foreground tracking-[0.07px] truncate">
                            {mapping.excel_sheet}!{mapping.excel_cell}
                          </span>
                        ) : (
                          <span className="text-[11px] text-muted-foreground/50 tracking-[0.07px]">—</span>
                        )}
                        {hasCitations && (
                          <Popover>
                            <PopoverTrigger asChild>
                              <button
                                className="shrink-0 text-muted-foreground/60 hover:text-muted-foreground transition-colors"
                                title="View citations"
                              >
                                <FileText className="h-3 w-3" />
                              </button>
                            </PopoverTrigger>
                            <PopoverContent
                              side="left"
                              align="start"
                              className="w-72 p-3"
                            >
                              <p className="text-[11px] font-medium text-muted-foreground tracking-[0.28px] uppercase mb-2">
                                Citations
                              </p>
                              <CitationSection
                                citations={fieldData.citations}
                                onCitationClick={onCitationClick}
                                extractedData={fieldData}
                                citationContext={citationContext}
                                className="mt-0 pt-0"
                              />
                            </PopoverContent>
                          </Popover>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination Footer */}
      {filteredFields.length > 0 && (
        <div className="border-t px-3 py-2 bg-muted/20 flex-shrink-0">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-muted-foreground tracking-[0.07px]">Show</span>
              <Select
                value={pageSize.toString()}
                onValueChange={(value) => setPageSize(parseInt(value))}
              >
                <SelectTrigger className="h-7 w-[60px] text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="10">10</SelectItem>
                  <SelectItem value="20">20</SelectItem>
                  <SelectItem value="50">50</SelectItem>
                  <SelectItem value="100">100</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-muted-foreground tabular-nums tracking-[0.07px]">
                {currentPage} / {totalPages}
              </span>
              <div className="flex gap-1">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="h-7 w-7 p-0"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="h-7 w-7 p-0"
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
