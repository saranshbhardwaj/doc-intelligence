// src/App.jsx
import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import FileUploader from "./components/upload/FileUploader";
import ResultsView from "./components//results/ResultViews";
import DarkModeToggle from "./components/common/DarkModeToggle";
import { useDarkMode } from "./hooks/useDarkMode";

const queryClient = new QueryClient();

function AppInner() {
  const { isDark, toggle } = useDarkMode();
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [rateLimit, setRateLimit] = useState(null);
  // eslint-disable-next-line no-unused-vars
  const [phase, setPhase] = useState("idle"); // idle | uploading | processing | done

  const handleUploadStart = () => {
    setPhase("uploading");
    setError(null);
  };

  const handleUploadComplete = () => {
    // upload finished (file bytes sent) and server is likely processing
    setPhase("processing");
  };

  const handleResult = (data) => {
    setResult(data);
    setPhase("done");
    setError(null);
  };

  const handleError = (msg) => {
    setError(msg);
    setPhase("idle");
  };

  const clearResults = () => {
    setResult(null);
    setPhase("idle");
    setError(null);
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-[#1a1a1a] py-12 px-4 transition-colors duration-200">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12">
          {/* Logo + Brand Name */}
          <div className="flex items-center justify-center gap-4 mb-4">
            {/* Logo - switches based on dark mode */}
            <img
              src="/Sand_cloud_logo_dark-gray.svg"
              alt="Sand Cloud Logo"
              className="h-16 w-auto dark:hidden"
            />
            <img
              src="/Sand_cloud_logo_dark-gray.svg"
              alt="Sand Cloud Logo"
              className="h-16 w-auto hidden dark:block"
            />
            <h1 className="text-5xl font-bold text-gray-900 dark:text-white">
              Sand Cloud
            </h1>
          </div>
          <p className="text-xl text-gray-700 dark:text-gray-300 mb-2">
            Stop reading CIMs manually. Extract data in minutes.
          </p>
          <p className="text-sm text-gray-500 dark:text-gray-500">
            Free demo: 2 uploads per day • Max 60 pages • 5MB limit
          </p>
        </div>

        {/* Uploader */}
        <div className="bg-white dark:bg-[#2f2f2f] rounded-2xl shadow-2xl p-8 mb-8 relative transition-colors duration-200 border border-gray-200 dark:border-gray-700/50">
          <FileUploader
            onUploadStart={handleUploadStart}
            onUploadComplete={handleUploadComplete}
            onResult={handleResult}
            onError={handleError}
            setRateLimit={setRateLimit}
          />

          {rateLimit && rateLimit.remaining_uploads !== undefined && (
            <p className="mt-4 text-center text-sm text-gray-600 dark:text-gray-400">
              {rateLimit.remaining_uploads} upload
              {rateLimit.remaining_uploads !== 1 ? "s" : ""} remaining today
            </p>
          )}
        </div>

        {/* Error */}
        {error && (
          <div
            className="bg-red-50 dark:bg-red-950/30 border-l-4 border-red-400 dark:border-red-500 p-6 mb-8 rounded-r-lg backdrop-blur-sm"
            role="alert"
          >
            <h3 className="text-sm font-medium text-red-800 dark:text-red-300 mb-2">
              ⚠️ Processing Error
            </h3>
            <p className="text-sm text-red-700 dark:text-red-200 mb-3">
              {error}
            </p>

            {/* Helpful guidance */}
            <div className="mt-4 pt-4 border-t border-red-200 dark:border-red-800">
              <p className="text-sm font-semibold text-red-800 dark:text-red-300 mb-2">
                💡 What to try:
              </p>
              <ul className="text-sm text-red-700 dark:text-red-200 space-y-1 list-disc list-inside">
                <li>
                  <strong>Try a different CIM document</strong> - Each document
                  has unique formatting
                </li>
                <li>
                  Ensure your PDF is text-based (not scanned images - we don't
                  support OCR yet)
                </li>
                <li>
                  Check file size is under 5MB and has fewer than 100 pages
                </li>
              </ul>
              <p className="text-xs text-red-600 dark:text-red-400 mt-3 italic">
                Note: Re-uploading the same file won't fix the issue. The system
                uses the same processing logic each time.
              </p>
            </div>
          </div>
        )}

        {/* Results */}
        {result && (
          <div className="mb-8">
            <div className="flex justify-end mb-3">
              <button
                onClick={clearResults}
                className="text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 transition-colors"
              >
                Clear results / analyze another file
              </button>
            </div>

            <ResultsView result={result} />
          </div>
        )}
      </div>

      {/* Dark Mode Toggle */}
      <DarkModeToggle isDark={isDark} toggle={toggle} />
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppInner />
    </QueryClientProvider>
  );
}
