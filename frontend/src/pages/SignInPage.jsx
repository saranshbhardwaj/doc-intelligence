import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@workos-inc/authkit-react";
import { ArrowLeft, Loader2, ShieldCheck, Sparkles } from "lucide-react";

import { useAppAuth } from "@/hooks/useAppAuth";

export default function SignInPage() {
  const { isLoaded, isSignedIn } = useAppAuth();
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const shouldAutoSignIn = Boolean(location.state?.autoSignIn);

  useEffect(() => {
    if (!isLoaded) return;
    if (isSignedIn) {
      navigate("/app/library", { replace: true });
      return;
    }
    if (shouldAutoSignIn) {
      signIn();
    }
  }, [isLoaded, isSignedIn, navigate, shouldAutoSignIn, signIn]);

  return (
    <div className="public-shell relative min-h-screen overflow-hidden">
      <div className="hero-sheen" />
      <div className="section-wrap flex min-h-screen items-center py-16">
        <div className="grid w-full gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
          <div className="max-w-2xl text-white">
            <button
              type="button"
              onClick={() => navigate("/")}
              className="mb-8 inline-flex items-center gap-2 text-sm font-medium text-white/72 transition-colors hover:text-white"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to frearaAI
            </button>

            <p className="text-[0.72rem] font-semibold uppercase tracking-[0.3em] text-white/64">
              Secure Access
            </p>
            <h1 className="mt-4 text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              Step back into the deal room with less friction.
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-white/72 sm:text-lg">
              Continue into your workspace to review documents, run workflows,
              and keep cited answers close to the source material.
            </p>

            <div className="mt-8 grid gap-3 sm:max-w-lg">
              <div className="hero-rail-item">
                <span className="flex items-center gap-3">
                  <Sparkles className="h-5 w-5 text-white" />
                  <span>Shared visual system across landing, auth, and app</span>
                </span>
              </div>
              <div className="hero-rail-item">
                <span className="flex items-center gap-3">
                  <ShieldCheck className="h-5 w-5 text-white" />
                  <span>Hosted authentication flow with the same product entry point</span>
                </span>
              </div>
            </div>
          </div>

          <div className="shell-panel-strong mx-auto w-full max-w-xl p-6 sm:p-8">
            <div className="flex items-center gap-3">
              <span className="relative h-11 w-11 shrink-0 overflow-hidden rounded-xl bg-primary/10">
                <img
                  src="/Freara%20ai%20logo.png"
                  alt="frearaAI"
                  className="absolute inset-0 h-full w-full scale-[1.78] object-cover"
                />
              </span>
              <div>
                <p className="font-display text-xl font-semibold text-foreground">
                  frearaAI
                </p>
                <p className="text-sm text-muted-foreground">
                  AI-powered document intelligence
                </p>
              </div>
            </div>

            <div className="public-divider my-6" />

            {shouldAutoSignIn ? (
              <div className="flex min-h-[220px] flex-col items-center justify-center gap-4 text-center">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <div>
                  <p className="text-base font-semibold text-foreground">
                    Redirecting to sign in
                  </p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Taking you to the secure hosted login flow.
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-5">
                <div>
                  <h2 className="text-2xl font-semibold tracking-tight text-foreground">
                    Sign in to continue
                  </h2>
                  <p className="mt-2 text-sm leading-7 text-muted-foreground">
                    Open your workspace, continue active reviews, and return to
                    your last document or workflow without losing context.
                  </p>
                </div>

                <button
                  type="button"
                  onClick={() => signIn()}
                  className="inline-flex h-12 w-full items-center justify-center rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground transition-all hover:-translate-y-0.5"
                >
                  Continue to WorkOS
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
