// src/components/RequireAuth.jsx
import { useState, useEffect, useRef } from "react";
import { Navigate, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@workos-inc/authkit-react";
import { useAppAuth } from "@/hooks/useAppAuth";
import { api, createAuthenticatedApi } from "../../api/client";
import { Loader2, LogOut, AlertCircle } from "lucide-react";

// How long to wait for /api/users/me before letting the user through anyway.
// Only a 403 access_pending response blocks the user — everything else
// (timeout, network error, 5xx) degrades gracefully: individual pages
// handle their own error states.
const CHECK_TIMEOUT_MS = 10_000;
const ORG_ID_CLAIM = "urn:myapp:org_id";

function getOrgIdFromJwt(token) {
  try {
    if (!token) return null;
    const payloadPart = token.split(".")[1];
    if (!payloadPart) return null;

    const normalized = payloadPart.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
    const payload = JSON.parse(atob(padded));
    return payload?.[ORG_ID_CLAIM] || payload?.org_id || payload?.organization_id || null;
  } catch {
    return null;
  }
}

export default function RequireAuth() {
  const { isLoaded, userId, orgId, getToken, signOut } = useAppAuth();
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [sessionVerified, setSessionVerified] = useState(false);
  const [statusChecked, setStatusChecked] = useState(false);
  const controllerRef = useRef(null);

  // Auto-provisioning state (for users with no org)
  const [provisioning, setProvisioning] = useState(false);
  const [provisionError, setProvisionError] = useState(null);
  const [provisionDone, setProvisionDone] = useState(false);
  const [provisionedOrgId, setProvisionedOrgId] = useState(null);
  const [tokenOrgId, setTokenOrgId] = useState(null);
  const [authCheckError, setAuthCheckError] = useState(null);
  const [authCheckRetry, setAuthCheckRetry] = useState(0);

  // ✅ DEV: Bypass auth for local testing with VITE_DEV_BYPASS_AUTH=true
  const devBypassAuth = import.meta.env.VITE_DEV_BYPASS_AUTH === "true";
  const effectiveOrgId = orgId || tokenOrgId;

  // Verify session is fully restored before allowing any redirect.
  // WorkOS sets isLoading:false before hydrating userId from the cookie — calling
  // getToken() is the authoritative check for whether a live session exists.
  useEffect(() => {
    if (!isLoaded) return;
    if (devBypassAuth) {
      setSessionVerified(true);
      return;
    }
    getToken()
      .then(() => setSessionVerified(true))
      .catch(() => setSessionVerified(true));
  }, [isLoaded]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-provision org when user has no org yet
  useEffect(() => {
    if (!isLoaded || !userId || effectiveOrgId || devBypassAuth) return;
    if (provisioning || provisionDone || provisionError) return;

    const run = async () => {
      setProvisioning(true);
      try {
        const token = await Promise.race([
          getToken(),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error("getToken timeout")), 5000)
          ),
        ]);

        if (!token) {
          setProvisionError("Failed to get auth token");
          return;
        }

        const claimOrgId = getOrgIdFromJwt(token);
        if (claimOrgId) {
          // Auth token already carries org context; no provisioning needed.
          setTokenOrgId(claimOrgId);
          setProvisioning(false);
          setProvisionDone(false);
          return;
        }

        // Use the token we already fetched to avoid a second getToken() call.
        const response = await api.post(
          "/api/users/provision-org",
          {},
          {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          }
        );
        console.log("✅ [RequireAuth] Org provisioned:", response.data);
        const newOrgId = response?.data?.org_id;
        if (newOrgId) {
          setTokenOrgId(newOrgId);
          setProvisionedOrgId(newOrgId);
        }
        setAuthCheckError(null);
        setProvisioning(false);
        // Automatically re-authenticate with the new org context — no click required.
        signIn({ organizationId: newOrgId });
      } catch (error) {
        console.error("❌ [RequireAuth] Org provisioning failed:", error);
        setProvisioning(false);
        setProvisionError(error.response?.data?.detail || "Failed to set up workspace");
      }
    };

    run();
  }, [isLoaded, userId, effectiveOrgId, devBypassAuth, getToken, provisioning, provisionDone, provisionError]);

  useEffect(() => {
    if (devBypassAuth) {
      // Skip auth entirely in dev mode
      setStatusChecked(true);
      return;
    }

    if (!isLoaded || !userId) return;

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
      // Degrade gracefully when backend is slow/unavailable during startup.
      setAuthCheckError(null);
      setStatusChecked(true);
    }, CHECK_TIMEOUT_MS);

    const run = async () => {
      try {
        // Pre-fetch token with timeout BEFORE creating API instance.
        const token = await Promise.race([
          getToken(),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error("getToken timeout")), 5000)
          ),
        ]);

        if (!token) {
          console.warn("⚠️ [RequireAuth] No token available from getToken()");
          setAuthCheckError("Authentication token unavailable. Please sign in again.");
          return;
        }

        const claimOrgId = getOrgIdFromJwt(token);
        if (claimOrgId && claimOrgId !== tokenOrgId) {
          setTokenOrgId(claimOrgId);
        }

        // Now create API and make request
        const authApi = createAuthenticatedApi(getToken);
        await authApi.get("/api/users/me", { signal: controller.signal });
        setAuthCheckError(null);
        setStatusChecked(true);
      } catch (error) {
        if (
          error.name === "AbortError" ||
          error.name === "CanceledError" ||
          error.code === "ERR_CANCELED"
        ) {
          return;
        }

        if (error.message === "getToken timeout") {
          console.warn("⚠️ [RequireAuth] getToken timed out");
          setAuthCheckError("Authentication timed out. Please try again.");
          return;
        }

        if (error.response?.status === 401) {
          // Most common after first-time provisioning: token not refreshed with org claim yet.
          // If we just provisioned an org, re-authenticate silently without showing a prompt.
          if (provisionedOrgId) {
            signIn({ organizationId: provisionedOrgId });
            return;
          }
          setTokenOrgId(null);
          setProvisionDone(true);
          setAuthCheckError("Please continue sign-in to refresh your workspace access.");
          return;
        }

        if (
          error.response?.status === 403 &&
          error.response?.data?.detail === "access_pending"
        ) {
          // Only hard-block for explicit access denial.
          navigate("/access-pending", { replace: true });
        } else {
          // For backend/network/5xx issues, allow app shell to render and let
          // global NetworkStatus + per-page loading/error states handle it.
          setAuthCheckError(null);
          setStatusChecked(true);
        }
      } finally {
        clearTimeout(timer);
      }
    };

    run();

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [isLoaded, userId, tokenOrgId, authCheckRetry]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!isLoaded) return null;

  if (devBypassAuth) return <Outlet />;

  if (!sessionVerified) {
    return (
      <div className="min-h-screen w-full flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <Loader2 className="w-8 h-8 animate-spin" />
        </div>
      </div>
    );
  }

  if (!userId) return <Navigate to="/" replace />;

  if (!effectiveOrgId) {
    // Provisioning in progress
    if (provisioning) {
      return (
        <div className="min-h-screen w-full flex items-center justify-center bg-background">
          <div className="flex flex-col items-center gap-3 text-muted-foreground">
            <Loader2 className="w-8 h-8 animate-spin" />
            <p className="text-sm">Setting up your workspace...</p>
          </div>
        </div>
      );
    }

    // Provisioning done — show re-auth prompt
    if (provisionDone) {
      return (
        <div className="min-h-screen w-full flex items-center justify-center bg-background">
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm max-w-sm w-full mx-4">
            <h2 className="mb-2 text-lg font-semibold text-foreground">
              Workspace ready!
            </h2>
            <p className="mb-4 text-sm text-muted-foreground">
              Your workspace has been created. Sign in again to continue.
            </p>
            <button
              onClick={() => signIn({ organizationId: provisionedOrgId })}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary hover:bg-primary/90 rounded-md transition-colors"
            >
              Continue
            </button>
          </div>
        </div>
      );
    }

    // Error during provisioning
    if (provisionError) {
      return (
        <div className="min-h-screen w-full flex items-center justify-center bg-background">
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6 shadow-sm max-w-sm w-full mx-4">
            <div className="flex items-start gap-3 mb-4">
              <AlertCircle className="w-5 h-5 text-destructive shrink-0 mt-0.5" />
              <div>
                <h2 className="text-sm font-semibold text-destructive">Setup failed</h2>
                <p className="mt-1 text-sm text-muted-foreground">{provisionError}</p>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  setProvisionError(null);
                  setProvisioning(false);
                  setProvisionDone(false);
                }}
                className="flex-1 px-3 py-2 text-sm font-medium text-foreground border border-border rounded-md hover:bg-muted transition-colors"
              >
                Retry
              </button>
              <button
                onClick={() => signOut?.()}
                className="flex-1 inline-flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-foreground border border-border rounded-md hover:bg-muted transition-colors"
              >
                <LogOut className="w-4 h-4" />
                Sign out
              </button>
            </div>
          </div>
        </div>
      );
    }

    // Default fallback (shouldn't normally show — effect fires immediately)
    return (
      <div className="min-h-screen w-full flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <Loader2 className="w-8 h-8 animate-spin" />
          <p className="text-sm">Setting up your workspace...</p>
        </div>
      </div>
    );
  }

  if (!statusChecked) {
    if (authCheckError) {
      return (
        <div className="min-h-screen w-full flex items-center justify-center bg-background">
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6 shadow-sm max-w-sm w-full mx-4">
            <div className="flex items-start gap-3 mb-4">
              <AlertCircle className="w-5 h-5 text-destructive shrink-0 mt-0.5" />
              <div>
                <h2 className="text-sm font-semibold text-destructive">Authentication issue</h2>
                <p className="mt-1 text-sm text-muted-foreground">{authCheckError}</p>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  setAuthCheckError(null);
                  setAuthCheckRetry((v) => v + 1);
                }}
                className="flex-1 px-3 py-2 text-sm font-medium text-foreground border border-border rounded-md hover:bg-muted transition-colors"
              >
                Retry
              </button>
              <button
                onClick={() => signOut?.()}
                className="flex-1 inline-flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-foreground border border-border rounded-md hover:bg-muted transition-colors"
              >
                <LogOut className="w-4 h-4" />
                Sign out
              </button>
            </div>
          </div>
        </div>
      );
    }

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
