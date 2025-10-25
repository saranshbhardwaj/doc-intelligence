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
          <h1 className="text-5xl font-bold text-gray-900 dark:text-white mb-4">
            📄 Sand Cloud
          </h1>
          <p className="text-xl text-gray-700 dark:text-gray-300 mb-2">
            Extract structured data from investment documents in seconds
          </p>
          <p className="text-sm text-gray-500 dark:text-gray-500">
            Free demo: 2 uploads per day • Max 50 pages • 5MB limit
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
            <h3 className="text-sm font-medium text-red-800 dark:text-red-300">
              Error
            </h3>
            <p className="text-sm text-red-700 dark:text-red-200 mt-1">
              {error}
            </p>
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
