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
import NotFound from "./pages/NotFound";
import AppNotFound from "./components/layout/AppNotFound";
import RequireAuth from "./components/common/RequireAuth";

// Import vertical routes
import { peRoutes, reRoutes } from "./routes/verticalRoutes";

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

            {/* Vertical-specific routes */}
            {/* Private Equity routes */}
            {peRoutes.map((route, index) => (
              <Route key={`pe-${index}`} path={`/app${route.path}`} element={route.element} />
            ))}

            {/* Real Estate routes */}
            {reRoutes.map((route, index) => (
              <Route key={`re-${index}`} path={`/app${route.path}`} element={route.element} />
            ))}

            {/* Catch-all for anything under /app that didn't match above */}
            <Route path="/app/*" element={<AppNotFound />} />
          </Route>

          {/* Global catch-all (public 404) */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
