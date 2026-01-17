/**
 * Fields List Component
 * Displays extracted PDF fields with search, filtering, and pagination
 */

import React, { useState, useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';
import { useTemplateFillActions } from '../../../store';
import { Copy, Check, AlertCircle, Loader2, Search, ChevronLeft, ChevronRight, Filter } from 'lucide-react';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { Input } from '../../../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { cn } from '@/lib/utils';
import { CitationSection } from './CitationBadge';

export default function FieldsList({
  fillRunId,
  extractedData = {},
  fieldMapping = {},
  selectedText,
  onCitationClick,
}) {
  const { getToken } = useAuth();
  const { updateFieldData } = useTemplateFillActions();
  const [editingField, setEditingField] = useState(null);
  const [savingField, setSavingField] = useState(null);
  const [error, setError] = useState(null);

  // Pagination and filtering state
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState('all'); // all, mapped, unmapped
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  // Use pdf_fields from field_mapping (available after field detection)
  // Fall back to extractedData (available after extraction phase)
  const pdfFields = fieldMapping?.pdf_fields || [];
  const allFields = pdfFields.length > 0
    ? pdfFields.map(f => [f.id, {
        value: extractedData[f.id]?.value || f.sample_value,
        confidence: extractedData[f.id]?.confidence || f.confidence,
        source_page: extractedData[f.id]?.source_page,
        user_edited: extractedData[f.id]?.user_edited || false,
        field_name: f.name,
        field_type: f.type,
        citations: f.citations || extractedData[f.id]?.citations,
      }])
    : Object.entries(extractedData).map(([id, data]) => [id, data]);

  const mappings = fieldMapping?.mappings || [];

  function getFieldMapping(fieldId) {
    return mappings.find((m) => m.pdf_field_id === fieldId);
  }

  // Filter and search fields
  const filteredFields = useMemo(() => {
    let filtered = allFields;

    // Apply search filter
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

    // Apply status filter
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
    const end = start + pageSize;
    return filteredFields.slice(start, end);
  }, [filteredFields, currentPage, pageSize]);

  // Reset to page 1 when filters change
  React.useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, filterStatus, pageSize]);

  function getConfidenceBadgeVariant(confidence) {
    if (confidence >= 0.8) return 'success';
    if (confidence >= 0.5) return 'warning';
    return 'destructive';
  }

  async function handlePasteText(fieldId) {
    if (!selectedText?.text) return;

    try {
      setSavingField(fieldId);
      setError(null);

      const currentField = extractedData[fieldId] || {};
      const updatedField = {
        ...currentField,
        value: selectedText.text,
        confidence: 1.0,
        user_edited: true,
        source_page: selectedText.page,
      };

      const updatedData = {
        ...extractedData,
        [fieldId]: updatedField,
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
      const updatedField = {
        ...currentField,
        value: newValue,
        confidence: 1.0,
        user_edited: true,
      };

      const updatedData = {
        ...extractedData,
        [fieldId]: updatedField,
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

  if (allFields.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-6 text-muted-foreground">
        <AlertCircle className="h-10 w-10 mb-3 text-muted-foreground/50" />
        <p className="text-center text-sm">No fields detected yet</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header with Search and Filters */}
      <div className="p-3 space-y-2 border-b bg-muted/20">
        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search fields by name, value, or cell..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 h-9 text-sm"
          />
        </div>

        {/* Filters and Stats */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 flex-1">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <Select value={filterStatus} onValueChange={setFilterStatus}>
              <SelectTrigger className="h-8 text-xs w-[140px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Fields</SelectItem>
                <SelectItem value="mapped">Mapped Only</SelectItem>
                <SelectItem value="unmapped">Unmapped Only</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Stats Badge */}
          <Badge variant="outline" className="text-xs font-normal">
            {filteredFields.length} of {allFields.length}
          </Badge>
        </div>
      </div>

      {error && (
        <div className="mx-3 mt-2 bg-destructive/10 text-destructive p-2.5 rounded-md text-xs border border-destructive/20">
          {error}
        </div>
      )}

      {selectedText && (
        <div className="mx-3 mt-2 bg-primary/5 border border-primary/20 p-2.5 rounded-md">
          <p className="text-xs text-primary font-medium mb-1">Selected Text (Page {selectedText.page})</p>
          <p className="text-xs text-foreground break-words">{selectedText.text}</p>
        </div>
      )}

      {/* Fields List (Scrollable) */}
      <div className="flex-1 overflow-auto p-3 space-y-2">
        {paginatedFields.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Search className="h-10 w-10 mb-3 text-muted-foreground/50" />
            <p className="text-center text-sm">No fields match your search</p>
          </div>
        ) : (
          paginatedFields.map(([fieldId, fieldData]) => {
            const mapping = getFieldMapping(fieldId);
            const isEditing = editingField === fieldId;
            const isSaving = savingField === fieldId;

            return (
              <div
                key={fieldId}
                className={cn(
                  "border rounded-md p-2.5 transition-colors",
                  "hover:bg-accent/50",
                  isSaving && "opacity-60"
                )}
              >
                {/* Field Header */}
                <div className="flex items-start justify-between mb-1.5">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-foreground truncate">
                      {fieldData.field_name || fieldData.label || fieldId}
                    </p>
                    {mapping && (
                      <p className="text-xs text-muted-foreground mt-0.5">
                        → {mapping.excel_sheet}!{mapping.excel_cell}
                      </p>
                    )}
                  </div>

                  {/* Confidence Score */}
                  <Badge
                    variant={getConfidenceBadgeVariant(fieldData.confidence || 0)}
                    className="ml-2 text-xs h-5"
                  >
                    {Math.round((fieldData.confidence || 0) * 100)}%
                  </Badge>
                </div>

                {/* Field Value */}
                {isEditing ? (
                  <div className="mb-2">
                    <Input
                      type="text"
                      defaultValue={fieldData.value || ''}
                      onBlur={(e) => {
                        if (e.target.value !== fieldData.value) {
                          handleFieldEdit(fieldId, e.target.value);
                        } else {
                          setEditingField(null);
                        }
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          handleFieldEdit(fieldId, e.target.value);
                        } else if (e.key === 'Escape') {
                          setEditingField(null);
                        }
                      }}
                      autoFocus
                      className="h-7 text-xs"
                    />
                  </div>
                ) : (
                  <div
                    onClick={() => setEditingField(fieldId)}
                    className="mb-2 cursor-pointer"
                  >
                    <p className="text-xs text-foreground break-words">
                      {fieldData.value || (
                        <span className="text-muted-foreground italic">No value</span>
                      )}
                    </p>
                  </div>
                )}

                {/* Actions */}
                <div className="flex items-center gap-1.5 flex-wrap">
                  {selectedText && (
                    <Button
                      size="sm"
                      onClick={() => handlePasteText(fieldId)}
                      disabled={isSaving}
                      className="h-6 text-xs px-2"
                    >
                      {isSaving ? (
                        <>
                          <Loader2 className="h-3 w-3 animate-spin mr-1" />
                          <span>Saving...</span>
                        </>
                      ) : (
                        <>
                          <Copy className="h-3 w-3 mr-1" />
                          <span>Paste</span>
                        </>
                      )}
                    </Button>
                  )}

                  {fieldData.user_edited && (
                    <Badge variant="success" className="h-6 text-xs">
                      <Check className="h-3 w-3 mr-1" />
                      <span>Edited</span>
                    </Badge>
                  )}
                </div>

                {/* Citations */}
                {fieldData.citations && fieldData.citations.length > 0 && (
                  <CitationSection
                    citations={fieldData.citations}
                    onCitationClick={onCitationClick}
                    extractedData={fieldData}
                    className="mt-0 pt-2"
                  />
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Pagination Footer */}
      {filteredFields.length > 0 && (
        <div className="border-t p-3 bg-muted/20">
          <div className="flex items-center justify-between gap-3">
            {/* Page Size Selector */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Show</span>
              <Select
                value={pageSize.toString()}
                onValueChange={(value) => setPageSize(parseInt(value))}
              >
                <SelectTrigger className="h-8 w-[70px] text-xs">
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

            {/* Page Info and Navigation */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">
                Page {currentPage} of {totalPages}
              </span>

              <div className="flex gap-1">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="h-8 w-8 p-0"
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="h-8 w-8 p-0"
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
