// src/components/RequireAuth.jsx
import { Navigate, Outlet } from "react-router-dom";
import { OrganizationSwitcher, useAuth } from "@clerk/clerk-react";

export default function RequireAuth({ redirectTo = "/sign-in" }) {
  const { isLoaded, userId, orgId } = useAuth();

  if (!isLoaded) return null; // or a spinner

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

  // Authenticated: render nested app routes
  return <Outlet />;
}
