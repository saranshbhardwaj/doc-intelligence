// src/pages/UploadPage.jsx
// Main upload and results page (moved from App.jsx)
import { useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { SignedIn, SignedOut, SignInButton, UserButton, useAuth } from "@clerk/clerk-react";
import FileUploader from "../components/upload/FileUploader";
import ResultsView from "../components/results/ResultViews";
import DarkModeToggle from "../components/common/DarkModeToggle";
import { useDarkMode } from "../hooks/useDarkMode";
import { getUserInfo } from "../api";

export default function UploadPage() {
  const { isDark, toggle } = useDarkMode();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { getToken, isSignedIn } = useAuth();
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [rateLimit, setRateLimit] = useState(null);
  const [phase, setPhase] = useState("idle"); // idle | uploading | processing | done
  const [isDemo, setIsDemo] = useState(false);
  const [userInfo, setUserInfo] = useState(null);

  // Fetch user info when signed in
  useEffect(() => {
    if (isSignedIn && getToken) {
      fetchUserInfo();
    }
  }, [isSignedIn, getToken]);

  const fetchUserInfo = async () => {
    try {
      const info = await getUserInfo(getToken);
      setUserInfo(info);
    } catch (err) {
      console.error('Failed to fetch user info:', err);
    }
  };

  // Load demo data if demo=true in URL
  useEffect(() => {
    if (searchParams.get("demo") === "true") {
      setIsDemo(true);
      setPhase("processing");

      // Load demo data
      fetch("/demo-data.json")
        .then(res => res.json())
        .then(demoData => {
          const demoResult = {
            success: true,
            data: demoData.data,
            metadata: {
              request_id: "demo-" + Date.now(),
              filename: "Alcatel-Lucent CIM (Sample)",
              pages: 81,
              characters_extracted: 200912,
              processing_time_seconds: 0.5,
              timestamp: new Date().toISOString()
            },
            rate_limit: {
              remaining_uploads: 2,
              reset_in_hours: 24,
              limit_per_window: 5
            },
            from_cache: false
          };
          setResult(demoResult);
          setPhase("done");
        })
        .catch(err => {
          console.error("Failed to load demo data:", err);
          setError("Failed to load demo data. Please try refreshing the page.");
          setPhase("idle");
        });
    }
  }, [searchParams]);

  const handleUploadStart = () => {
    setPhase("uploading");
    setError(null);
  };

  const handleUploadComplete = () => {
    setPhase("processing");
  };

  const handleResult = (data) => {
    setResult(data);
    setPhase("done");
    setError(null);
    // Refresh user info after successful extraction to update page count
    fetchUserInfo();
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
    <div className="min-h-screen bg-gray-50 dark:bg-[#1a1a1a] transition-colors duration-200">
      {/* Navigation Bar */}
      <nav className="sticky top-0 z-50 bg-white/80 dark:bg-gray-900/80 backdrop-blur-lg border-b border-gray-200 dark:border-gray-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            {/* Logo - clickable to go home */}
            <button
              onClick={() => navigate("/")}
              className="flex items-center gap-3 hover:opacity-80 transition-opacity"
            >
              <img
                src="/Sand_cloud_logo_dark-gray.svg"
                alt="Sand Cloud"
                className="h-8 w-auto"
              />
              <span className="text-xl font-bold text-gray-900 dark:text-white">
                Sand Cloud
              </span>
            </button>

            {/* Right side actions */}
            <div className="flex items-center gap-4">
              <DarkModeToggle
                isDark={isDark}
                toggle={toggle}
                variant="inline"
              />
              <button
                onClick={() => navigate("/")}
                className="px-4 py-2 text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors font-medium"
              >
                Back to Home
              </button>

              {/* Authentication UI */}
              <SignedOut>
                <SignInButton mode="modal">
                  <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium">
                    Sign In
                  </button>
                </SignInButton>
              </SignedOut>
              <SignedIn>
                <UserButton />
              </SignedIn>
            </div>
          </div>
        </div>
      </nav>

      <div className="py-12 px-4">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="text-center mb-12">
            <h1 className="text-4xl font-bold text-gray-900 dark:text-white mb-4">
              Upload Your CIM
            </h1>
            <p className="text-lg text-gray-700 dark:text-gray-300 mb-2">
              Stop reading CIMs manually. Extract data in minutes.
            </p>

            {/* Usage indicator for signed-in users */}
            <SignedIn>
              {userInfo && userInfo.usage ? (
                <div className="inline-flex items-center gap-3 mt-4">
                  <div className="text-sm text-gray-600 dark:text-gray-400">
                    <span className="font-semibold text-gray-900 dark:text-white">
                      {userInfo.usage.pages_remaining}
                    </span>
                    {' '}pages remaining
                    {userInfo.tier === 'free' && ' (one-time limit)'}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-500">
                    {userInfo.usage.pages_used} / {userInfo.usage.pages_limit} used • Max 5MB per document limit
                  </div>
                </div>
              ) : (
                <p className="text-sm text-gray-500 dark:text-gray-500 mt-4">
                  Loading usage info...
                </p>
              )}
            </SignedIn>

            {/* Static text for non-signed in users */}
            <SignedOut>
              <p className="text-sm text-gray-500 dark:text-gray-500">
                Free: 100 pages one-time • Max 5MB per document limit
              </p>
            </SignedOut>
          </div>

        {/* Demo Banner */}
        {isDemo && (
          <div className="bg-gradient-to-r from-blue-50 to-purple-50 dark:from-blue-900/20 dark:to-purple-900/20 border-2 border-blue-500 dark:border-blue-400 rounded-2xl p-6 mb-8">
            <div className="flex items-center gap-3 mb-4">
              <span className="text-3xl">🎯</span>
              <h3 className="text-2xl font-bold text-gray-900 dark:text-white">
                Sample CIM Analysis
              </h3>
            </div>
            <p className="text-lg text-gray-700 dark:text-gray-300 mb-4">
              You're viewing a sample extraction from Alcatel-Lucent's CIM. This demonstrates the full capability of our AI-powered analysis.
            </p>
            <p className="text-base text-gray-600 dark:text-gray-400">
              Explore the sample output below to see what Sand Cloud can extract from your documents.
            </p>
          </div>
        )}

        {/* Uploader */}
        {!isDemo && (
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
        )}

        {/* Error */}
        {error && (
          <div
            className="bg-red-50 dark:bg-red-950/30 border-l-4 border-red-400 dark:border-red-500 p-6 mb-8 rounded-r-lg backdrop-blur-sm"
            role="alert"
          >
            <h3 className="text-sm font-medium text-red-800 dark:text-red-300 mb-2">
              ⚠️ Processing Error
            </h3>
            <p className="text-sm text-red-700 dark:text-red-200 mb-3">{error}</p>

            <div className="mt-4 pt-4 border-t border-red-200 dark:border-red-800">
              <p className="text-sm font-semibold text-red-800 dark:text-red-300 mb-2">
                💡 What to try:
              </p>
              <ul className="text-sm text-red-700 dark:text-red-200 space-y-1 list-disc list-inside">
                <li>
                  <strong>Try a different CIM document</strong> - Each document has unique formatting
                </li>
                <li>Check file size is under 5MB and has fewer than 60 pages</li>
              </ul>
            </div>
          </div>
        )}

        {/* Results */}
        {result && (
          <div className="mb-8">
            {/* <div className="flex justify-end mb-3">
              <button
                onClick={clearResults}
                className="text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 transition-colors"
              >
                Clear results / analyze another file
              </button>
            </div> */}

            <ResultsView result={result} />
          </div>
        )}
        </div>
      </div>
    </div>
  );
}
