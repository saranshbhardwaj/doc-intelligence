/**
 * UploadTemplateModal Component
 *
 * Beautiful upload modal for Excel templates with drag-and-drop
 * ChatGPT-inspired design
 *
 * Input:
 *   - open: boolean
 *   - onOpenChange: (open: boolean) => void
 *   - onUpload: (file: File, metadata: {name, description, category}) => Promise<void>
 */

import { useState, useRef, useCallback } from "react";
import {
  Upload,
  X,
  FileSpreadsheet,
  CheckCircle,
  AlertCircle,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../../../components/ui/dialog";
import { Button } from "../../../components/ui/button";
import { Label } from "../../../components/ui/label";
import { Input } from "../../../components/ui/input";
import { Textarea } from "../../../components/ui/textarea";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "../../../components/ui/select";
import { Badge } from "../../../components/ui/badge";

const TEMPLATE_CATEGORIES = [
  { value: "custom", label: "Custom" },
  { value: "financial", label: "Financial Analysis" },
  { value: "property", label: "Property Info" },
  { value: "underwriting", label: "Underwriting" },
  { value: "valuation", label: "Valuation" },
];

export default function UploadTemplateModal({
  open = false,
  onOpenChange,
  onUpload,
}) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);

  // Form fields
  const [templateName, setTemplateName] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("custom");

  const handleDrag = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const validateFile = (file) => {
    const errors = [];

    const validTypes = [
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "application/vnd.ms-excel",
    ];

    if (!validTypes.includes(file.type) && !file.name.endsWith(".xlsx")) {
      errors.push("Only Excel (.xlsx) files are allowed");
    }

    if (file.size > 10 * 1024 * 1024) {
      errors.push("File size must be less than 10MB");
    }

    return errors;
  };

  const handleFile = (file) => {
    if (!file) return;

    const errors = validateFile(file);
    const fileObj = {
      file,
      id: Math.random().toString(36).slice(2, 11),
      name: file.name,
      size: file.size,
      errors,
    };

    setSelectedFile(fileObj);

    // Auto-populate template name from filename
    if (!templateName) {
      setTemplateName(file.name.replace(/\.xlsx?$/i, ""));
    }
  };

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      e.stopPropagation();
      setDragActive(false);

      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFile(e.dataTransfer.files[0]);
      }
    },
    [templateName]
  );

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFile(e.target.files[0]);
    }
  };

  const removeFile = () => {
    setSelectedFile(null);
  };

  const handleUpload = async () => {
    if (!selectedFile || selectedFile.errors.length > 0) {
      return;
    }

    try {
      setUploading(true);
      await onUpload?.(selectedFile.file, {
        name: templateName || selectedFile.name.replace(/\.xlsx?$/i, ""),
        description,
        category,
      });

      // Reset form
      setSelectedFile(null);
      setTemplateName("");
      setDescription("");
      setCategory("custom");
      onOpenChange?.(false);
    } catch (error) {
      console.error("Upload failed:", error);
      alert(`Upload failed: ${error.message}`);
    } finally {
      setUploading(false);
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  const isValid = selectedFile && selectedFile.errors.length === 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] flex flex-col">
        <DialogHeader className="flex-shrink-0">
          <DialogTitle className="text-xl">Upload Excel Template</DialogTitle>
          <DialogDescription>
            Upload an Excel template with fillable fields. The template will be
            analyzed and ready to use for document filling.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 overflow-y-auto flex-1 px-1">
          {/* Drag & Drop Zone */}
          <div
            className={`relative border-2 border-dashed rounded-lg transition-all ${
              dragActive
                ? "border-primary bg-primary/5"
                : "border-border hover:border-muted-foreground/50"
            }`}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls"
              onChange={handleFileInput}
              className="hidden"
            />

            <div className="flex flex-col items-center justify-center py-8 px-4">
              <div
                className={`w-12 h-12 rounded-full flex items-center justify-center mb-3 transition-colors ${
                  dragActive ? "bg-primary/20" : "bg-muted"
                }`}
              >
                <Upload
                  className={`w-6 h-6 transition-colors ${
                    dragActive ? "text-primary" : "text-muted-foreground"
                  }`}
                />
              </div>

              <h3 className="text-sm font-medium text-foreground mb-1">
                {dragActive ? "Drop file here" : "Drag & drop Excel template"}
              </h3>
              <p className="text-xs text-muted-foreground mb-3">
                or click to browse
              </p>

              <Button
                variant="outline"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
              >
                Choose File
              </Button>

              <p className="text-xs text-muted-foreground mt-3">
                Max file size: 10MB • Excel (.xlsx) only
              </p>
            </div>
          </div>

          {/* Selected File */}
          {selectedFile && (
            <div
              className={`flex items-start gap-3 p-4 rounded-lg border transition-colors ${
                selectedFile.errors.length > 0
                  ? "border-destructive/30 bg-destructive/5"
                  : "border-border bg-card"
              }`}
            >
              {/* Icon */}
              <div
                className={`p-2 rounded-lg ${
                  selectedFile.errors.length > 0
                    ? "bg-destructive/10"
                    : "bg-primary/10"
                }`}
              >
                <FileSpreadsheet
                  className={`w-5 h-5 ${
                    selectedFile.errors.length > 0
                      ? "text-destructive"
                      : "text-primary"
                  }`}
                />
              </div>

              {/* File Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {selectedFile.name}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {formatFileSize(selectedFile.size)}
                    </p>
                  </div>

                  {selectedFile.errors.length === 0 ? (
                    <Badge variant="secondary" className="text-xs flex-shrink-0">
                      <CheckCircle className="w-3 h-3 mr-1" />
                      Ready
                    </Badge>
                  ) : (
                    <Badge variant="destructive" className="text-xs flex-shrink-0">
                      <AlertCircle className="w-3 h-3 mr-1" />
                      Invalid
                    </Badge>
                  )}
                </div>

                {/* Errors */}
                {selectedFile.errors.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {selectedFile.errors.map((error, idx) => (
                      <p
                        key={idx}
                        className="text-xs text-destructive flex items-center gap-1"
                      >
                        <AlertCircle className="w-3 h-3 flex-shrink-0" />
                        {error}
                      </p>
                    ))}
                  </div>
                )}
              </div>

              {/* Remove Button */}
              <button
                onClick={removeFile}
                className="p-1 hover:bg-destructive/10 rounded transition-colors flex-shrink-0"
              >
                <X className="w-4 h-4 text-muted-foreground hover:text-destructive" />
              </button>
            </div>
          )}

          {/* Template Metadata Form */}
          {selectedFile && selectedFile.errors.length === 0 && (
            <div className="space-y-4 pt-4 border-t border-border">
              <div>
                <Label className="text-sm font-medium mb-2 block">
                  Template Name
                </Label>
                <Input
                  type="text"
                  placeholder="e.g., Property Underwriting Template"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                />
              </div>

              <div>
                <Label className="text-sm font-medium mb-2 block">
                  Description (Optional)
                </Label>
                <Textarea
                  placeholder="Brief description of what this template is used for..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={3}
                  className="resize-none"
                />
              </div>

              <div>
                <Label className="text-sm font-medium mb-2 block">
                  Category
                </Label>
                <Select value={category} onValueChange={setCategory}>
                  <SelectTrigger className="h-10">
                    <SelectValue placeholder="Select category..." />
                  </SelectTrigger>
                  <SelectContent>
                    {TEMPLATE_CATEGORIES.map((cat) => (
                      <SelectItem key={cat.value} value={cat.value}>
                        {cat.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between pt-4 border-t border-border flex-shrink-0">
          <div className="text-sm text-muted-foreground">
            {isValid && <span>Ready to upload template</span>}
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => onOpenChange?.(false)}
              disabled={uploading}
            >
              Cancel
            </Button>
            <Button onClick={handleUpload} disabled={!isValid || uploading}>
              {uploading ? (
                <>
                  <Upload className="w-4 h-4 mr-2 animate-spin" />
                  Uploading...
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4 mr-2" />
                  Upload Template
                </>
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
