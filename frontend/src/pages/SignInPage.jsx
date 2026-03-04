import { useEffect } from "react";
import { useAppAuth } from "@/hooks/useAppAuth";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@workos-inc/authkit-react";
import { Loader2 } from "lucide-react";

export default function SignInPage() {
  const { isLoaded, isSignedIn } = useAppAuth();
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const shouldAutoSignIn = Boolean(location.state?.autoSignIn);

  useEffect(() => {
    if (!isLoaded) return;
    if (isSignedIn) {
      // Already signed in — redirect to app
      navigate("/app/library", { replace: true });
      return;
    }
    // Auto-redirect only when the user was bounced here from a protected route.
    if (shouldAutoSignIn) {
      signIn();
    }
  }, [isLoaded, isSignedIn, shouldAutoSignIn]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-3 text-muted-foreground">
        {shouldAutoSignIn ? (
          <>
            <Loader2 className="w-8 h-8 animate-spin" />
            <p className="text-sm">Redirecting to sign in...</p>
          </>
        ) : (
          <>
            <p className="text-sm">Sign in to continue.</p>
            <button
              type="button"
              onClick={() => signIn()}
              className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Continue to WorkOS
            </button>
          </>
        )}
      </div>
    </div>
  );
}
