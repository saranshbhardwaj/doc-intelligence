// src/components/RequireAuth.jsx
import { useState, useEffect, useRef } from "react";
import { Navigate, Outlet, useNavigate } from "react-router-dom";
import { OrganizationSwitcher, useAuth } from "@clerk/clerk-react";
import { createAuthenticatedApi } from "../../api/client";
import { Loader2 } from "lucide-react";

// How long to wait for /api/users/me before letting the user through anyway.
// Only a 403 access_pending response blocks the user — everything else
// (timeout, network error, 5xx) degrades gracefully: individual pages
// handle their own error states.
const CHECK_TIMEOUT_MS = 10_000;

export default function RequireAuth({ redirectTo = "/sign-in" }) {
  const { isLoaded, userId, orgId, getToken } = useAuth();
  const navigate = useNavigate();
  const [statusChecked, setStatusChecked] = useState(false);
  const controllerRef = useRef(null);

  useEffect(() => {
    if (!isLoaded || !userId || !orgId) return;

    // Cancel any in-flight request from a previous run of this effect.
    if (controllerRef.current) {
      controllerRef.current.abort();
    }

    const controller = new AbortController();
    controllerRef.current = controller;

    // After CHECK_TIMEOUT_MS, abort the request and let the user through.
    // Individual pages will show their own error states if the API is down.
    const timer = setTimeout(() => {
      controller.abort();
      setStatusChecked(true);
    }, CHECK_TIMEOUT_MS);

    const run = async () => {
      try {
        const authApi = createAuthenticatedApi(getToken);
        await authApi.get("/api/users/me", { signal: controller.signal });
        setStatusChecked(true);
      } catch (error) {
        if (error.name === "AbortError" || error.code === "ERR_CANCELED") {
          // Aborted by our timer (timeout) or by a new effect run.
          // setStatusChecked(true) is handled by the timer callback on timeout,
          // and by the new effect run's own logic on abort-for-retry.
          return;
        }

        if (
          error.response?.status === 403 &&
          error.response?.data?.detail === "access_pending"
        ) {
          // Only hard-block for explicit access denial.
          navigate("/access-pending", { replace: true });
        } else {
          // Network error, 500, etc. — let user through; pages handle their errors.
          setStatusChecked(true);
        }
      } finally {
        clearTimeout(timer);
      }
    };

    run();

    return () => {
      // Abort on unmount or before the next effect run.
      controller.abort();
      clearTimeout(timer);
    };
  }, [isLoaded, userId, orgId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!isLoaded) return null;

  if (!userId) return <Navigate to={redirectTo} replace />;

  if (!orgId) {
    return (
      <div className="min-h-screen w-full flex items-center justify-center bg-slate-50">
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="mb-2 text-lg font-semibold text-slate-900">
            Select an organization
          </h2>
          <p className="mb-4 text-sm text-slate-600">
            Please choose an organization to continue.
          </p>
          <OrganizationSwitcher hidePersonal afterSelectOrganizationUrl="/app/dashboard" />
        </div>
      </div>
    );
  }

  if (!statusChecked) {
    return (
      <div className="min-h-screen w-full flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <Loader2 className="w-8 h-8 animate-spin" />
          <p className="text-sm">Loading...</p>
        </div>
      </div>
    );
  }

  return <Outlet />;
}
