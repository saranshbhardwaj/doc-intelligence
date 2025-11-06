// src/pages/DashboardPage.jsx
import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { SignedIn, SignedOut, SignInButton, UserButton, useAuth } from "@clerk/clerk-react";
import DarkModeToggle from "../components/common/DarkModeToggle";
import { useDarkMode } from "../hooks/useDarkMode";
import { getUserInfo, getUserExtractions } from "../api";
import ExtractionHistory from "../components/dashboard/ExtractionHistory";
import UsageStats from "../components/dashboard/UsageStats";
import { Skeleton } from "@/components/ui/skeleton";

export default function DashboardPage() {
  const { isDark, toggle } = useDarkMode();
  const navigate = useNavigate();
  const { getToken, isSignedIn, isLoaded } = useAuth();
  const [userInfo, setUserInfo] = useState(null);
  const [extractions, setExtractions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pagination, setPagination] = useState({
    total: 0,
    limit: 50,
    offset: 0,
    has_more: false
  });

  // Redirect to sign-in if not authenticated (only after Clerk finishes loading)
  useEffect(() => {
    if (isLoaded && !isSignedIn) {
      navigate("/sign-in");
    }
  }, [isLoaded, isSignedIn, navigate]);

  // Fetch user info and extractions
  useEffect(() => {
    if (isSignedIn) {
      fetchDashboardData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSignedIn]);

  const fetchDashboardData = async () => {
    setLoading(true);
    setError(null);

    try {
      const token = await getToken();
      // Fetch user info and extractions in parallel
      const [userInfoData, extractionsData] = await Promise.all([
        getUserInfo(token),
        getUserExtractions(token, { limit: pagination.limit, offset: pagination.offset })
      ]);

      setUserInfo(userInfoData);
      setExtractions(extractionsData.extractions);
      setPagination({
        total: extractionsData.total,
        limit: extractionsData.limit,
        offset: extractionsData.offset,
        has_more: extractionsData.has_more
      });
    } catch (err) {
      console.error("Failed to fetch dashboard data:", err);
      setError(err.response?.data?.detail || "Failed to load dashboard data");
    } finally {
      setLoading(false);
    }
  };

  const handleLoadMore = async () => {
    try {
      const token = await getToken();
      const newOffset = pagination.offset + pagination.limit;
      const extractionsData = await getUserExtractions(token, {
        limit: pagination.limit,
        offset: newOffset
      });

      setExtractions([...extractions, ...extractionsData.extractions]);
      setPagination({
        total: extractionsData.total,
        limit: extractionsData.limit,
        offset: extractionsData.offset,
        has_more: extractionsData.has_more
      });
    } catch (err) {
      console.error("Failed to load more extractions:", err);
    }
  };

  const handleDeleteSuccess = () => {
    // Refresh the data after deletion
    fetchDashboardData();
  };

  return (
    <div className="min-h-screen bg-white dark:bg-[#121212] text-gray-900 dark:text-[#ececec] transition-colors duration-200">
      {/* Header */}
      <header className="border-b border-gray-200 dark:border-[#2a2a2a]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-4">
            <div className="flex items-center gap-8">
              <button
                onClick={() => navigate(isSignedIn ? "/app/dashboard" : "/")}
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
              <nav className="hidden md:flex gap-6">
                <Link
                  to="/app"
                  className="text-sm font-medium text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
                >
                  Upload
                </Link>
                <Link
                  to="/app/dashboard"
                  className="text-sm font-medium text-gray-900 dark:text-white transition-colors"
                >
                  Dashboard
                </Link>
              </nav>
            </div>

            <div className="flex items-center gap-4">
              <DarkModeToggle isDark={isDark} toggle={toggle} />

              <SignedOut>
                <SignInButton mode="modal">
                  <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium">
                    Sign In
                  </button>
                </SignInButton>
              </SignedOut>

              <SignedIn>
                <UserButton
                  appearance={{
                    elements: {
                      avatarBox: "w-10 h-10",
                    },
                  }}
                />
              </SignedIn>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Dashboard</h1>
          <p className="text-muted-foreground">
            View and manage your extraction history
          </p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive">
            {error}
          </div>
        )}

        {loading ? (
          <div className="space-y-6">
            {/* Loading skeleton */}
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        ) : (
          <div className="space-y-6">
            {/* Usage Stats */}
            {userInfo && <UsageStats userInfo={userInfo} />}

            {/* Extraction History */}
            <ExtractionHistory
              extractions={extractions}
              pagination={pagination}
              onLoadMore={handleLoadMore}
              onDeleteSuccess={handleDeleteSuccess}
              getToken={getToken}
            />
          </div>
        )}
      </main>
    </div>
  );
}
