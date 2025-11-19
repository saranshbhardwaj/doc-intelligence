// src/components/NotFound.jsx
import { Link } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";

export default function NotFound() {
  const { isLoaded, userId } = useAuth();

  // Wait until Clerk loads so we don't flash the wrong CTA
  if (!isLoaded) return null;

  return (
    <div className="min-h-screen flex items-center justify-center bg-background text-foreground p-6">
      <div className="max-w-xl text-center">
        <h1 className="text-4xl font-bold mb-4">404 — Page not found</h1>
        <p className="text-muted-foreground mb-6">
          The page you were looking for doesn't exist or has been moved.
        </p>

        {userId ? (
          <div className="flex justify-center gap-3">
            <Link
              to="/app/library"
              className="px-6 py-3 rounded-lg bg-primary text-primary-foreground font-semibold"
            >
              Go to Library
            </Link>
            <Link
              to="/app/workflows"
              className="px-6 py-3 rounded-lg border border-border text-muted-foreground"
            >
              View Workflows
            </Link>
          </div>
        ) : (
          <div className="flex justify-center gap-3">
            <Link
              to="/"
              className="px-6 py-3 rounded-lg bg-primary text-primary-foreground font-semibold"
            >
              Back to Home
            </Link>
            <Link
              to="/sign-in"
              className="px-6 py-3 rounded-lg border border-border text-muted-foreground"
            >
              Sign in
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
