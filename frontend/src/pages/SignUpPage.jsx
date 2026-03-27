import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@workos-inc/authkit-react";
import { ArrowLeft, Loader2, Sparkles } from "lucide-react";

import { useAppAuth } from "@/hooks/useAppAuth";

export default function SignUpPage() {
  const { isLoaded, isSignedIn } = useAppAuth();
  const { signIn } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isLoaded) return;
    if (isSignedIn) {
      navigate("/app/library", { replace: true });
      return;
    }
    signIn();
  }, [isLoaded, isSignedIn, navigate, signIn]);

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
              Workspace Setup
            </p>
            <h1 className="mt-4 text-4xl font-semibold tracking-tight text-white sm:text-5xl">
              Creating your entry point into faster document review.
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-white/72 sm:text-lg">
              Once authentication completes, you land inside the same polished
              workspace used for library management, chat, extraction, and
              workflows.
            </p>
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
                  Setting up your secure access
                </p>
              </div>
            </div>

            <div className="public-divider my-6" />

            <div className="flex min-h-[220px] flex-col items-center justify-center gap-4 text-center">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <div>
                <p className="text-base font-semibold text-foreground">
                  Redirecting to sign up
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  You are being taken to the hosted authentication flow.
                </p>
              </div>

              <div className="mt-4 inline-flex items-center gap-2 rounded-full border border-primary/15 bg-primary/6 px-3 py-1.5 text-xs font-medium text-primary">
                <Sparkles className="h-4 w-4" />
                One account for library, chat, extract, and workflows
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
