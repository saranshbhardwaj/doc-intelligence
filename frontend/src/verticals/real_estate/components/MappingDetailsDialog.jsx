/**
 * MappingDetailsDialog Component
 * Drawer dialog for viewing and editing cell mapping details
 * Handles 3 modes: unmapped cell view, mapped cell view (read-only), and edit mode
 */

import { useState } from 'react';
import { useAuth } from '@clerk/clerk-react';
import { useTemplateFillActions } from '../../../store';
import {
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from '../../../components/ui/sheet';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../../../components/ui/alert-dialog';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { Input } from '../../../components/ui/input';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '../../../components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '../../../components/ui/popover';
import { Loader2, Info, Check, ChevronsUpDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { CitationSection } from './CitationBadge';

export default function MappingDetailsDialog({
  selectedCell,
  fillRunId,
  fieldMapping,
  extractedData,
  onClose,
  onCitationClick,
}) {
  const { getToken } = useAuth();
  const { updateMappings, updateFieldData, loadFillRun } = useTemplateFillActions();
  const { mapping, pdfField, value, cellAddress, cellData, sheetName } = selectedCell;

  const allPdfFields = fieldMapping?.pdf_fields || [];

  const [isEditMode, setIsEditMode] = useState(false);
  const [isRemoving, setIsRemoving] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [showDeleteAlert, setShowDeleteAlert] = useState(false);

  // Edit mode state
  const [selectedFieldId, setSelectedFieldId] = useState(mapping?.pdf_field_id);
  const [editedValue, setEditedValue] = useState(() => {
    if (mapping?.pdf_field_id) {
      // Mapped cell: get from llm_extracted
      const fieldData = extractedData?.llm_extracted?.[mapping.pdf_field_id];
      if (fieldData?.value !== undefined) return fieldData.value;
    } else {
      // Unmapped cell: check manual_edits
      const manualValue = extractedData?.manual_edits?.[sheetName]?.[cellAddress];
      if (manualValue?.value !== undefined) return manualValue.value;
    }
    return pdfField?.sample_value || '';
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
    setSelectedFieldId(mapping?.pdf_field_id);
    if (mapping?.pdf_field_id) {
      const fieldData = extractedData?.llm_extracted?.[mapping.pdf_field_id];
      setEditedValue(fieldData?.value !== undefined ? fieldData.value : (pdfField?.sample_value || ''));
    } else {
      // For unmapped cells, check manual_edits first
      const manualValue = extractedData?.manual_edits?.[sheetName]?.[cellAddress];
      setEditedValue(manualValue?.value !== undefined ? manualValue.value : (pdfField?.sample_value || ''));
    }
  }

  // When user selects different field in edit mode
  function handleFieldChange(newFieldId) {
    setSelectedFieldId(newFieldId);
    const newField = allPdfFields.find(f => f.id === newFieldId);
    const fieldData = extractedData?.llm_extracted?.[newFieldId];
    setEditedValue(fieldData?.value !== undefined ? fieldData.value : (newField?.sample_value || ''));
  }

  async function handleSave() {
    try {
      setIsSaving(true);

      if (mapping) {
        // MAPPED CELL: Update mapping or value

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
        const currentValue = extractedData?.llm_extracted?.[selectedFieldId]?.value ||
                            allPdfFields.find(f => f.id === selectedFieldId)?.sample_value;

        if (editedValue !== currentValue) {
          const updatedData = {
            llm_extracted: {
              ...(extractedData?.llm_extracted || {}),
              [selectedFieldId]: {
                value: editedValue,
                confidence: 1.0,
                user_edited: true,
                citations: currentField?.citations || []
              }
            },
            manual_edits: extractedData?.manual_edits || {}
          };
          await updateFieldData(fillRunId, updatedData, getToken);
        }
      } else {
        // UNMAPPED CELL: Either create a mapping or just save the value

        if (selectedFieldId && editedValue) {
          // Create a mapping for this cell
          const newMapping = {
            excel_sheet: sheetName,
            excel_cell: cellAddress,
            excel_label: `${cellAddress} (Manual)`,
            pdf_field_id: selectedFieldId,
            pdf_field_name: allPdfFields.find(f => f.id === selectedFieldId)?.name,
            confidence: 1.0,
            user_edited: true,
          };

          const updatedMappings = [...fieldMapping.mappings, newMapping];
          await updateMappings(fillRunId, updatedMappings, getToken);
        }

        // Update extracted data with the value
        if (editedValue) {
          if (selectedFieldId) {
            // If a field was selected, add to llm_extracted
            const updatedData = {
              llm_extracted: {
                ...(extractedData?.llm_extracted || {}),
                [selectedFieldId]: {
                  value: editedValue,
                  confidence: 1.0,
                  user_edited: true,
                  citations: []
                }
              },
              manual_edits: extractedData?.manual_edits || {}
            };
            await updateFieldData(fillRunId, updatedData, getToken);
          } else {
            // No field selected, add to manual_edits
            const updatedData = {
              llm_extracted: extractedData?.llm_extracted || {},
              manual_edits: {
                ...(extractedData?.manual_edits || {}),
                [sheetName]: {
                  ...(extractedData?.manual_edits?.[sheetName] || {}),
                  [cellAddress]: {
                    value: editedValue,
                    confidence: 1.0,
                    user_edited: true,
                    citations: []
                  }
                }
              }
            };
            await updateFieldData(fillRunId, updatedData, getToken);
          }
        }
      }

      // Reload fill run to get updated status (might have reset to awaiting_review)
      await loadFillRun(fillRunId, getToken, { silent: true, skipPdf: true });

      onClose();
    } catch (err) {
      console.error('Failed to save changes:', err);
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

      const updatedMappings = currentMappings.filter(
        m => !(m.excel_sheet === mapping.excel_sheet &&
               m.excel_cell === mapping.excel_cell)
      );

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
          {mapping ? (
            <Badge variant="outline" className="text-xs">
              {mapping.excel_label || 'Unlabeled'}
            </Badge>
          ) : (
            <Badge variant="secondary" className="text-xs">
              No Mapping
            </Badge>
          )}
        </SheetTitle>
        <SheetDescription className="text-xs">
          {mapping ? (
            isEditMode
              ? 'Edit the mapping or change the value'
              : 'Review and manage the mapping between Excel cell and PDF field'
          ) : (
            'Edit this cell directly or add a mapping to a PDF field'
          )}
        </SheetDescription>
      </SheetHeader>

      {/* Scrollable Content */}
      <div className="flex-1 overflow-auto px-4 py-3 scrollbar-thin">

        {/* UNMAPPED CELL VIEW */}
        {!mapping && (
          <>
            {/* Current Cell Value */}
            {cellData && (cellData.v || cellData.w) && (
              <div className="mb-3">
                <h4 className="text-xs font-semibold text-foreground mb-1.5">Current Excel Value</h4>
                <div className="bg-muted/50 rounded-lg p-2.5 border">
                  <p className="text-xs text-foreground font-mono break-words">{cellData.w || cellData.v}</p>
                </div>
              </div>
            )}

            {/* Edit Value Section */}
            <div className="mb-4 p-3 rounded-lg border border-primary/30 bg-primary/5">
              <h4 className="text-xs font-semibold text-foreground mb-2">Edit Cell Value</h4>
              <Input
                type="text"
                value={editedValue}
                onChange={(e) => setEditedValue(e.target.value)}
                placeholder="Enter a value..."
                className="w-full text-xs h-8 mb-2"
              />
              <p className="text-xs text-muted-foreground">
                Type or paste a value directly into this cell. Changes will be saved when you click Save below.
              </p>
            </div>

            {/* Optional: Add Mapping */}
            <div className="mb-3 p-3 rounded-lg border bg-card">
              <h4 className="text-xs font-semibold text-foreground mb-2">Add a Mapping (Optional)</h4>
              <p className="text-xs text-muted-foreground mb-3">
                Optionally map this cell to a PDF field. This will automatically fill the cell with extracted data.
              </p>
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
                      : 'Select PDF field...'}
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
                              setSelectedFieldId(field.id);
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
            </div>

            {/* Selected Field Preview */}
            {selectedFieldId && (
              <div className="mb-3 p-2.5 rounded-lg border bg-muted/50">
                <h4 className="text-xs font-semibold text-foreground mb-2">Selected PDF Field</h4>
                {(() => {
                  const selectedField = allPdfFields.find((f) => f.id === selectedFieldId);
                  if (!selectedField) return null;
                  return (
                    <div className="space-y-2">
                      <div>
                        <span className="text-xs font-medium text-muted-foreground block mb-0.5">Name</span>
                        <p className="text-xs text-foreground font-mono">{selectedField.name}</p>
                      </div>
                      {selectedField.sample_value && (
                        <div>
                          <span className="text-xs font-medium text-muted-foreground block mb-1">Sample Value</span>
                          <p className="text-xs text-foreground bg-background p-2 rounded-md border break-words">
                            {selectedField.sample_value}
                          </p>
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            )}
          </>
        )}

        {/* MAPPED CELL VIEW */}
        {mapping && !isEditMode && (
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
          <CitationSection
            citations={pdfField.citations}
            onCitationClick={onCitationClick}
            label="Source Citations"
            extractedData={pdfField}
          />
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
        {/* Unmapped Cell Actions */}
        {!mapping && (
          <>
            <Button
              variant="outline"
              onClick={() => onClose()}
              className="flex-1"
              disabled={isSaving}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              className="flex-1"
              disabled={isSaving || !editedValue}
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

        {/* Mapped Cell Actions - Edit/Remove Mapping */}
        {mapping && !isEditMode && (
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
        )}

        {/* Mapped Cell Actions - Edit Mode Save/Cancel */}
        {mapping && isEditMode && (
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
      {mapping && (
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
      )}
    </>
  );
}
