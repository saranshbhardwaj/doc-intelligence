/* eslint-disable no-unused-vars */
// src/components/upload/FileUploader.jsx
import { useRef, useState, useEffect } from "react";
import classNames from "classnames";
import { useAuth } from "@clerk/clerk-react";
import useExtractionProgress from "../../hooks/useExtractionProgress";
import ProgressTracker from "./ProgressTracker";

export default function FileUploader({
  onResult,
  onError,
  onUploadStart,
  onUploadComplete,
  setRateLimit,
}) {
  const [file, setFile] = useState(null);
  const [localError, setLocalError] = useState(null);
  const inputRef = useRef(null);

  // Get Clerk authentication token
  const { getToken } = useAuth();

  const {
    upload: uploadDocument,
    retry: retryExtraction,
    progress,
    result,
    error: extractionError,
    isProcessing
  } = useExtractionProgress(getToken);

  // Handle successful extraction result
  useEffect(() => {
    if (result) {
      onResult?.(result);
      onUploadComplete?.();
    }
  }, [result, onResult, onUploadComplete]);

  // Handle extraction errors
  useEffect(() => {
    if (extractionError) {
      onError?.(extractionError.message);
    }
  }, [extractionError, onError]);

  const validate = (f) => {
    if (!f) return "No file selected";
    if (f.type !== "application/pdf") return "Please select a PDF file";
    if (f.size > 5 * 1024 * 1024) return "File too large. Maximum size is 5MB.";
    return null;
  };

  const handleFile = (f) => {
    const err = validate(f);
    if (err) {
      setLocalError(err);
      return;
    }
    setFile(f);
    setLocalError(null);
  };

  const onDrop = (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  };

  const onChoose = (e) => {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  };

  const handleUpload = async () => {
    if (!file) return;

    setLocalError(null);
    onUploadStart?.();

    try {
      await uploadDocument(file);
    } catch (err) {
      // Error handling is done in the hook and useEffect above
      console.error("Upload failed:", err);
    }
  };

  const handleRetry = async () => {
    try {
      await retryExtraction();
    } catch (err) {
      console.error("Retry failed:", err);
    }
  };

  return (
    <div>
      <div
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
        className={classNames(
          "border-2 border-dashed rounded-lg p-6 text-center relative transition-colors duration-200",
          "bg-white dark:bg-[#2f2f2f]",
          "border-gray-300 dark:border-[#4a4a4a]",
          {
            "border-blue-400 dark:border-blue-500 bg-blue-50 dark:bg-[#1a2332]":
              !!file,
          }
        )}
      >
        <input
          ref={inputRef}
          id="file-input"
          type="file"
          accept="application/pdf"
          onChange={onChoose}
          className="hidden"
          disabled={isProcessing}
        />
        <label htmlFor="file-input" className="cursor-pointer block">
          <div className="flex flex-col items-center">
            <svg
              className="w-12 h-12 text-gray-400 dark:text-[#8e8e8e] mb-3"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>
            <div className="text-sm text-gray-700 dark:text-[#ececec]">
              Click to select or drag and drop a PDF
            </div>
            <div className="text-xs text-gray-500 dark:text-[#a8a8a8] mt-1">
              PDF up to 5MB
            </div>
          </div>
        </label>

        {localError && (
          <div className="text-red-600 dark:text-[#ff6b6b] mt-3">
            {localError}
          </div>
        )}

        {file && !isProcessing && (
          <div className="mt-4 p-3 bg-gray-100 dark:bg-[#1a1a1a] rounded flex items-center justify-between border border-gray-200 dark:border-[#3f3f3f] transition-colors duration-200">
            <div>
              <div className="font-medium text-gray-900 dark:text-[#ececec]">
                {file.name}
              </div>
              <div className="text-xs text-gray-600 dark:text-[#a8a8a8]">
                {(file.size / 1024).toFixed(0)} KB
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={() => {
                  setFile(null);
                  setLocalError(null);
                }}
                className="text-gray-600 dark:text-[#a8a8a8] hover:text-gray-900 dark:hover:text-[#ececec] transition-colors"
              >
                Remove
              </button>
              <button
                onClick={handleUpload}
                className="bg-blue-600 dark:bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 dark:hover:bg-blue-500 transition-colors"
              >
                Upload
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Progress Tracker - replaces the old static spinner */}
      {(progress || extractionError) && (
        <ProgressTracker
          progress={progress}
          error={extractionError}
          onRetry={handleRetry}
        />
      )}
    </div>
  );
}
