// src/components/RequireAuth.jsx
import { useState, useEffect } from "react";
import { Navigate, Outlet, useNavigate } from "react-router-dom";
import { OrganizationSwitcher, useAuth } from "@clerk/clerk-react";
import { createAuthenticatedApi } from "../../api/client";

export default function RequireAuth({ redirectTo = "/sign-in" }) {
  const { isLoaded, userId, orgId, getToken } = useAuth();
  const navigate = useNavigate();
  const [statusChecked, setStatusChecked] = useState(false);

  useEffect(() => {
    // Only run the status check once Clerk is loaded, user is signed in, and has an org
    if (!isLoaded || !userId || !orgId) return;

    const checkStatus = async () => {
      try {
        const authApi = createAuthenticatedApi(getToken);
        await authApi.get("/api/users/me");
        setStatusChecked(true);
      } catch (error) {
        if (
          error.response?.status === 403 &&
          error.response?.data?.detail === "access_pending"
        ) {
          navigate("/access-pending", { replace: true });
        } else {
          // Any other error (network, 500, etc.) — let the app render and
          // individual pages will handle their own errors.
          setStatusChecked(true);
        }
      }
    };

    checkStatus();
  }, [isLoaded, userId, orgId, getToken, navigate]);

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

  // Block rendering until status check completes
  if (!statusChecked) return null;

  return <Outlet />;
}
