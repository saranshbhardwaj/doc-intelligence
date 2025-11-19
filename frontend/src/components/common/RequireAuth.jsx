// src/components/RequireAuth.jsx
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";

export default function RequireAuth({ redirectTo = "/sign-in" }) {
  const { isLoaded, userId } = useAuth();

  if (!isLoaded) return null; // or a spinner

  if (!userId) return <Navigate to={redirectTo} replace />;

  // Authenticated: render nested app routes
  return <Outlet />;
}
