/**
 * AuthCallbackPage
 *
 * WorkOS AuthKit redirects here after login (/callback).
 * The AuthKitProvider automatically exchanges the auth code for a session token
 * when it detects the callback parameters in the URL.
 * This page just shows a loading state while that happens, then navigates to the app.
 */
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAppAuth } from "@/hooks/useAppAuth";
import { Loader2 } from "lucide-react";

export default function AuthCallbackPage() {
  const { isLoaded, isSignedIn } = useAppAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (isLoaded && isSignedIn) {
      navigate("/app/library", { replace: true });
    }
  }, [isLoaded, isSignedIn, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-3 text-muted-foreground">
        <Loader2 className="w-8 h-8 animate-spin" />
        <p className="text-sm">Completing sign in...</p>
      </div>
    </div>
  );
}
