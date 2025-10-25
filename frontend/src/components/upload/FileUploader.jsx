/* eslint-disable no-unused-vars */
// src/components/upload/FileUploader.jsx
import { useRef, useState, useEffect } from "react";
import { uploadFile } from "../../api";
import classNames from "classnames";

export default function FileUploader({
  onResult,
  onError,
  onUploadStart,
  onUploadComplete,
  setRateLimit,
}) {
  const [file, setFile] = useState(null);
  const [progress, setProgress] = useState(0);
  const [loading, setLoading] = useState(false);
  const [awaitingResponse, setAwaitingResponse] = useState(false);
  const [localError, setLocalError] = useState(null);
  const controllerRef = useRef(null);
  const inputRef = useRef(null);
  const uploadCompleteCalled = useRef(false);

  useEffect(() => {
    return () => {
      if (controllerRef.current) {
        try {
          controllerRef.current.abort();
        } catch (e) {
          /* ignore */
        }
      }
    };
  }, []);

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
    setProgress(0);
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

  const upload = async () => {
    if (!file) return;
    onUploadStart?.();
    setLoading(true);
    setProgress(0);
    setLocalError(null);
    setAwaitingResponse(false);
    uploadCompleteCalled.current = false;

    controllerRef.current = new AbortController();
    try {
      const resp = await uploadFile(file, {
        onUploadProgress: (evt) => {
          if (evt.total) {
            const pct = Math.round((evt.loaded / evt.total) * 100);
            setProgress(pct);

            if (pct >= 100 && !uploadCompleteCalled.current) {
              uploadCompleteCalled.current = true;
              setAwaitingResponse(true);
              onUploadComplete?.();
            }
          }
        },
        signal: controllerRef.current.signal,
      });

      if (!uploadCompleteCalled.current) {
        uploadCompleteCalled.current = true;
        setAwaitingResponse(true);
        onUploadComplete?.();
      }

      if (!resp || resp.status >= 400) {
        setAwaitingResponse(false);
        const body = resp?.data;
        if (resp?.status === 429) {
          onError?.(`Rate limit exceeded. ${body?.detail?.message || ""}`);
          setRateLimit?.(body?.rate_limit || null);
        } else {
          onError?.(body?.detail || `Upload failed (${resp?.status})`);
        }
        return;
      }

      setAwaitingResponse(false);
      onResult?.(resp.data);
      setRateLimit?.(resp.data?.rate_limit || null);
    } catch (err) {
      setAwaitingResponse(false);
      if (
        err.name === "CanceledError" ||
        err.message === "canceled" ||
        err.code === "ERR_CANCELED"
      ) {
        onError?.("Upload canceled.");
      } else {
        onError?.(`Network error: ${err.message || String(err)}`);
      }
    } finally {
      setLoading(false);
      setAwaitingResponse(false);
      controllerRef.current = null;
      uploadCompleteCalled.current = false;
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

        {file && (
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
              {loading ? (
                <div className="w-48">
                  <div className="h-2 bg-gray-200 dark:bg-[#3f3f3f] rounded">
                    <div
                      className="h-2 bg-blue-500 dark:bg-blue-500 rounded transition-all duration-200"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                  <div className="text-xs text-gray-600 dark:text-[#a8a8a8] mt-1">
                    {progress}%
                  </div>
                </div>
              ) : null}

              {!loading && !awaitingResponse && (
                <>
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
                    onClick={upload}
                    className="bg-blue-600 dark:bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 dark:hover:bg-blue-500 transition-colors"
                  >
                    Upload
                  </button>
                </>
              )}
            </div>
          </div>
        )}

        {/* Overlay + spinner shown while awaiting server processing */}
        {awaitingResponse && (
          <div className="absolute inset-0 bg-white/90 dark:bg-[#212121]/90 backdrop-blur-sm flex flex-col items-center justify-center rounded-lg pointer-events-auto transition-colors duration-200">
            <svg
              className="animate-spin h-10 w-10 text-blue-600 dark:text-blue-400 mb-4"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              ></circle>
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
              ></path>
            </svg>
            <p className="text-lg font-medium text-gray-900 dark:text-[#ececec]">
              Analyzing document (this may take 1 minute)…
            </p>
            <p className="text-sm text-gray-600 dark:text-[#a8a8a8] mt-2">
              Please don't close this tab
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
