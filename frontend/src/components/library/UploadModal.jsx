/**
 * UploadModal Component
 *
 * Beautiful upload modal with drag-and-drop, file preview, and progress tracking
 * ChatGPT-inspired design
 *
 * Input:
 *   - open: boolean
 *   - collections: Array<{id, name}>
 *   - selectedCollectionId: string
 *   - onOpenChange: (open: boolean) => void
 *   - onCollectionChange: (collectionId: string) => void
 *   - onUpload: (files: File[]) => void
 */

import { useState, useRef, useCallback } from "react";
import {
  Upload,
  X,
  FileText,
  CheckCircle,
  AlertCircle,
  Folder,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Label } from "../ui/label";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "../ui/select";
import { Badge } from "../ui/badge";

export default function UploadModal({
  open = false,
  collections = [],
  selectedCollectionId = null,
  onOpenChange,
  onCollectionChange,
  onUpload,
}) {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

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

    if (file.type !== "application/pdf") {
      errors.push("Only PDF files are allowed");
    }

    if (file.size > 50 * 1024 * 1024) {
      errors.push("File size must be less than 50MB");
    }

    return errors;
  };

  const handleFiles = (files) => {
    const fileArray = Array.from(files);
    const filesWithValidation = fileArray.map((file) => ({
      file,
      id: Math.random().toString(36).substr(2, 9),
      name: file.name,
      size: file.size,
      errors: validateFile(file),
      status: "pending", // pending, uploading, success, error
    }));

    setSelectedFiles((prev) => [...prev, ...filesWithValidation]);
  };

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      e.stopPropagation();
      setDragActive(false);

      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFiles(e.dataTransfer.files);
      }
    },
    []
  );

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFiles(e.target.files);
    }
  };

  const removeFile = (fileId) => {
    setSelectedFiles((prev) => prev.filter((f) => f.id !== fileId));
  };

  const handleUpload = () => {
    if (!selectedCollectionId) {
      alert("Please select a collection");
      return;
    }

    const validFiles = selectedFiles.filter((f) => f.errors.length === 0);
    if (validFiles.length === 0) {
      alert("No valid files to upload");
      return;
    }

    onUpload?.(validFiles.map((f) => f.file));
    setSelectedFiles([]);
    onOpenChange?.(false);
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  const validFilesCount = selectedFiles.filter((f) => f.errors.length === 0).length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-xl">Upload Documents</DialogTitle>
          <DialogDescription>
            Upload PDF documents to your collection. Files will be automatically
            parsed, chunked, and embedded.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 mt-4">
          {/* Collection Selector */}
          <div>
            <Label className="text-sm font-medium mb-2 block">
              Upload to Collection
            </Label>
            <Select
              value={selectedCollectionId || ""}
              onValueChange={onCollectionChange}
            >
              <SelectTrigger className="h-10">
                <Folder className="w-4 h-4 mr-2" />
                <SelectValue placeholder="Select a collection..." />
              </SelectTrigger>
              <SelectContent>
                {collections.map((col) => (
                  <SelectItem key={col.id} value={col.id}>
                    <div className="flex items-center justify-between w-full pr-2">
                      <span>{col.name}</span>
                      <span className="text-xs text-muted-foreground ml-3">
                        {col.document_count || 0} docs
                      </span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

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
              accept=".pdf"
              multiple
              onChange={handleFileInput}
              className="hidden"
            />

            <div className="flex flex-col items-center justify-center py-12 px-4">
              <div
                className={`w-16 h-16 rounded-full flex items-center justify-center mb-4 transition-colors ${
                  dragActive ? "bg-primary/20" : "bg-muted"
                }`}
              >
                <Upload
                  className={`w-8 h-8 transition-colors ${
                    dragActive ? "text-primary" : "text-muted-foreground"
                  }`}
                />
              </div>

              <h3 className="text-base font-medium text-foreground mb-1">
                {dragActive ? "Drop files here" : "Drag & drop PDF files"}
              </h3>
              <p className="text-sm text-muted-foreground mb-4">
                or click to browse
              </p>

              <Button
                variant="outline"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
              >
                Choose Files
              </Button>

              <p className="text-xs text-muted-foreground mt-4">
                Max file size: 50MB • PDF only
              </p>
            </div>
          </div>

          {/* File List */}
          {selectedFiles.length > 0 && (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              <div className="flex items-center justify-between mb-2">
                <Label className="text-sm font-medium">
                  Selected Files ({selectedFiles.length})
                </Label>
                {validFilesCount < selectedFiles.length && (
                  <span className="text-xs text-destructive">
                    {selectedFiles.length - validFilesCount} invalid
                  </span>
                )}
              </div>

              {selectedFiles.map((fileObj) => (
                <div
                  key={fileObj.id}
                  className={`flex items-start gap-3 p-3 rounded-lg border transition-colors ${
                    fileObj.errors.length > 0
                      ? "border-destructive/30 bg-destructive/5"
                      : "border-border bg-card"
                  }`}
                >
                  {/* Icon */}
                  <div
                    className={`p-2 rounded-lg ${
                      fileObj.errors.length > 0
                        ? "bg-destructive/10"
                        : "bg-primary/10"
                    }`}
                  >
                    <FileText
                      className={`w-4 h-4 ${
                        fileObj.errors.length > 0
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
                          {fileObj.name}
                        </p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {formatFileSize(fileObj.size)}
                        </p>
                      </div>

                      {fileObj.errors.length === 0 ? (
                        <Badge
                          variant="secondary"
                          className="text-xs flex-shrink-0"
                        >
                          <CheckCircle className="w-3 h-3 mr-1" />
                          Ready
                        </Badge>
                      ) : (
                        <Badge
                          variant="destructive"
                          className="text-xs flex-shrink-0"
                        >
                          <AlertCircle className="w-3 h-3 mr-1" />
                          Invalid
                        </Badge>
                      )}
                    </div>

                    {/* Errors */}
                    {fileObj.errors.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {fileObj.errors.map((error, idx) => (
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
                    onClick={() => removeFile(fileObj.id)}
                    className="p-1 hover:bg-destructive/10 rounded transition-colors flex-shrink-0"
                  >
                    <X className="w-4 h-4 text-muted-foreground hover:text-destructive" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between pt-4 border-t border-border mt-6">
          <div className="text-sm text-muted-foreground">
            {selectedFiles.length > 0 && (
              <span>
                {validFilesCount} valid file{validFilesCount !== 1 ? "s" : ""}{" "}
                ready to upload
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange?.(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleUpload}
              disabled={!selectedCollectionId || validFilesCount === 0}
            >
              <Upload className="w-4 h-4 mr-2" />
              Upload {validFilesCount > 0 ? `(${validFilesCount})` : ""}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
