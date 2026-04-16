// src/App.jsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "./components/ui/sonner";
import LandingPage from "./pages/LandingPage";
import SignInPage from "./pages/SignInPage";
import SignUpPage from "./pages/SignUpPage";
import LibraryPage from "./pages/LibraryPage";
import ChatPage from "./pages/ChatPage";
import WorkflowsPage from "./pages/WorkflowsPage";
import WorkflowSimplePage from "./pages/WorkflowSimplePage";
import WorkflowResultPage from "./pages/WorkflowResultPage";
import ExtractPage from "./pages/ExtractPage";
import ExtractionHistoryPage from "./pages/ExtractionHistoryPage";
import ExtractionDetailPage from "./pages/ExtractionDetailPage";
import DashboardPage from "./pages/DashboardPage";
import AccessPendingPage from "./pages/AccessPendingPage";
import AuthCallbackPage from "./pages/AuthCallbackPage";
import AdminTemplateFillAnalyticsPage from "./pages/AdminTemplateFillAnalyticsPage";
import AboutPage from "./pages/AboutPage";
import PrivacyPage from "./pages/PrivacyPage";
import TermsPage from "./pages/TermsPage";
import NotFound from "./pages/NotFound";
import AppNotFound from "./components/layout/AppNotFound";
import RequireAuth from "./components/common/RequireAuth";
import { Analytics } from '@vercel/analytics/react';

// Import vertical routes
import { peRoutes, reRoutes } from "./routes/verticalRoutes";
import { useUser } from "./store";

/**
 * Gates access to a vertical based on user's allowed_verticals.
 * Falls back to allow access while user info is loading (avoids flash redirect).
 */
function RequireVertical({ vertical, redirectTo, children }) {
  const userState = useUser();
  const allowedVerticals = userState?.info?.allowed_verticals;
  // If user info not yet loaded, don't redirect — wait for it
  if (!allowedVerticals) return children;
  if (!allowedVerticals.includes(vertical)) return <Navigate to={redirectTo} replace />;
  return children;
}

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Toaster position="top-right" expand={false} richColors />
        <Routes>
          {/* Public routes */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/sign-in/*" element={<SignInPage />} />
          <Route path="/sign-up/*" element={<SignUpPage />} />
          <Route path="/callback" element={<AuthCallbackPage />} />
          <Route path="/access-pending" element={<AccessPendingPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/privacy" element={<PrivacyPage />} />
          <Route path="/terms" element={<TermsPage />} />

          {/* Protected app area */}
          <Route element={<RequireAuth redirectTo="/sign-in" />}>
            {/* App routes - Library is home */}
            <Route
              path="/app"
              element={<Navigate to="/app/library" replace />}
            />
            <Route path="/app/library" element={<LibraryPage />} />
            <Route path="/app/chat" element={<ChatPage />} />

            {/* Workflows - New simplified single-page experience */}
            <Route path="/app/workflows" element={<WorkflowSimplePage />} />
            <Route path="/app/workflows/history" element={<WorkflowsPage />} />
            <Route
              path="/app/workflows/runs/:runId"
              element={<WorkflowResultPage />}
            />

            <Route path="/app/extract" element={<ExtractPage />} />
            <Route
              path="/app/extractions"
              element={<ExtractionHistoryPage />}
            />
            <Route
              path="/app/extractions/:id"
              element={<ExtractionDetailPage />}
            />
            <Route path="/app/dashboard" element={<DashboardPage />} />

            {/* Vertical-specific routes */}
            {/* Private Equity routes — gated by allowed_verticals */}
            {peRoutes.map((route, index) => (
              <Route
                key={`pe-${index}`}
                path={`/app${route.path}`}
                element={
                  <RequireVertical vertical="private_equity" redirectTo="/app/library">
                    {route.element}
                  </RequireVertical>
                }
              />
            ))}

            {/* Real Estate routes */}
            {reRoutes.map((route, index) => (
              <Route key={`re-${index}`} path={`/app${route.path}`} element={route.element} />
            ))}

            <Route path="/app/admin/template-analytics" element={<AdminTemplateFillAnalyticsPage />} />

            {/* Catch-all for anything under /app that didn't match above */}
            <Route path="/app/*" element={<AppNotFound />} />
          </Route>

          {/* Global catch-all (public 404) */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
      <Analytics />
    </QueryClientProvider>
  );
}
