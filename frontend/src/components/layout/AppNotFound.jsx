// src/components/AppNotFound.jsx
import AppLayout from "./AppLayout";
import { Link } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";

export default function AppNotFound() {
  const { isLoaded, userId } = useAuth();

  if (!isLoaded) return null;

  return (
    <AppLayout>
      <div className="py-24">
        <div className="max-w-3xl mx-auto text-center">
          <h1 className="text-4xl font-bold text-foreground mb-4">
            404 — Page not found
          </h1>
          <p className="text-muted-foreground mb-6">
            We couldn't find that page inside the app. Try going back to a known
            place below.
          </p>

          <div className="flex items-center justify-center gap-3">
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
              Workflows
            </Link>

            <Link
              to="/app/extract"
              className="px-6 py-3 rounded-lg border border-border text-muted-foreground"
            >
              Extract
            </Link>
          </div>

          <div className="mt-8 text-sm text-muted-foreground">
            {userId ? (
              <span>Still stuck? Contact support or try another page.</span>
            ) : (
              <span>
                Not signed in?{" "}
                <Link to="/sign-in" className="text-primary">
                  Sign in
                </Link>
                .
              </span>
            )}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
