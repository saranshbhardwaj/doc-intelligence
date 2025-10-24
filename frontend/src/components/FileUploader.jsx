/* eslint-disable no-unused-vars */
// src/components/FileUploader.jsx
import { useRef, useState, useEffect } from "react";
import { uploadFile } from "../api";
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
  const [loading, setLoading] = useState(false); // true while axios.post is in-flight
  const [awaitingResponse, setAwaitingResponse] = useState(false); // show overlay after upload completes
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

            // When the file bytes are fully sent (100%), we go into awaitingResponse.
            if (pct >= 100 && !uploadCompleteCalled.current) {
              uploadCompleteCalled.current = true;
              setAwaitingResponse(true);
              onUploadComplete?.();
            }
          }
        },
        signal: controllerRef.current.signal,
      });

      // Ensure overlay is active while backend is processing (if any)
      // If the server is fast this will be short-lived.
      if (!uploadCompleteCalled.current) {
        // In some environments progress events may not reach 100%, ensure we still signal completion
        uploadCompleteCalled.current = true;
        setAwaitingResponse(true);
        onUploadComplete?.();
      }

      // Handle HTTP errors
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

      // === DEV: fake server/LLM processing delay so spinner is visible without calling LLM ===
      // Use Vite's import.meta.env.DEV or optional VITE_FAKE_LLM_DELAY_MS

      // if (import.meta.env.DEV) {
      //   const devDelay = Number(import.meta.env.VITE_FAKE_LLM_DELAY_MS || 8000);
      //   // only wait if delay > 0
      //   if (devDelay > 0) {
      //     await new Promise((r) => setTimeout(r, devDelay));
      //   }
      // }

      // done waiting — server returned final data
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
          "border-2 border-dashed rounded-lg p-6 text-center relative",
          {
            "border-blue-400": !!file,
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
              className="w-12 h-12 text-gray-400 mb-3"
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
            <div className="text-sm text-gray-600">
              Click to select or drag and drop a PDF
            </div>
            <div className="text-xs text-gray-500 mt-1">PDF up to 5MB</div>
          </div>
        </label>

        {localError && <div className="text-red-600 mt-3">{localError}</div>}

        {file && (
          <div className="mt-4 p-3 bg-blue-50 rounded flex items-center justify-between">
            <div>
              <div className="font-medium text-gray-900">{file.name}</div>
              <div className="text-xs text-gray-600">
                {(file.size / 1024).toFixed(0)} KB
              </div>
            </div>

            <div className="flex items-center gap-3">
              {loading ? (
                <div className="w-48">
                  <div className="h-2 bg-gray-200 rounded">
                    <div
                      className="h-2 bg-blue-600 rounded"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                  <div className="text-xs text-gray-600 mt-1">{progress}%</div>
                </div>
              ) : null}

              {!loading && !awaitingResponse && (
                <>
                  <button
                    onClick={() => {
                      setFile(null);
                      setLocalError(null);
                    }}
                    className="text-gray-500 hover:text-gray-700"
                  >
                    Remove
                  </button>
                  <button
                    onClick={upload}
                    className="bg-blue-600 text-white px-4 py-2 rounded"
                  >
                    Upload
                  </button>
                </>
              )}
            </div>
          </div>
        )}

        {/* overlay + spinner shown while awaiting server processing */}
        {awaitingResponse && (
          <div className="absolute inset-0 bg-white/85 flex flex-col items-center justify-center rounded-lg pointer-events-auto">
            <svg
              className="animate-spin h-10 w-10 text-blue-600 mb-4"
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
            <p className="text-lg font-medium">
              Analyzing document (this may take 1 minute)…
            </p>
            <p className="text-sm text-gray-600 mt-2">
              Please don’t close this tab
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
