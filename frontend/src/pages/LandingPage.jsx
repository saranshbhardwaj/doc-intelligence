// src/pages/LandingPage.jsx
import { useNavigate, Link } from "react-router-dom";
import { useAppAuth } from "@/hooks/useAppAuth";
import { useEffect, useState } from "react";
import { usePostHog } from '@posthog/react';
import Hero from "../components/landing/Hero";
import Features from "../components/landing/Features";
import WorkflowShowcase from "../components/landing/WorkflowShowcase";
import FAQ from "../components/landing/FAQ";
import DarkModeToggle from "../components/common/DarkModeToggle";
import { useDarkMode } from "../hooks/useDarkMode";
import { Menu, X } from "lucide-react";

export default function LandingPage() {
  const navigate = useNavigate();
  const { isDark, toggle } = useDarkMode();
  const { isSignedIn, isLoaded } = useAppAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const posthog = usePostHog();

  useEffect(() => {
    if (isLoaded && isSignedIn) {
      navigate("/app/library");
    }
  }, [isLoaded, isSignedIn, navigate]);

  const handleGetStarted = () => {
    posthog?.capture('get_started_clicked');
    navigate("/sign-up");
  };

  return (
    <div className="min-h-screen bg-background transition-colors duration-200">
      {/* Floating Glass Nav */}
      <div className="fixed top-4 left-1/2 -translate-x-1/2 w-[92%] max-w-4xl z-50">
        <div className="glass-card rounded-full px-5 py-2.5 shadow-lg flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-2.5">
            <span className="relative h-8 w-8 shrink-0 overflow-hidden rounded-md">
              <img
                src="/Freara%20ai%20logo.png"
                alt="Basilfy"
                className="absolute inset-0 h-full w-full scale-[1.78] object-cover"
              />
            </span>
            <span className="text-xl font-extrabold tracking-tight bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
              Basilfy
            </span>
          </div>

          {/* Desktop Nav links */}
          <div className="hidden md:flex items-center gap-7 text-sm font-medium text-muted-foreground">
            <a href="#features" className="hover:text-primary transition-colors">Features</a>
            <a href="#workflows" className="hover:text-primary transition-colors">Workflows</a>
            <a href="#faq" className="hover:text-primary transition-colors">FAQ</a>
            <Link to="/about" className="hover:text-primary transition-colors">About</Link>
          </div>

          {/* Desktop Auth + dark mode */}
          <div className="hidden md:flex items-center gap-2">
            <DarkModeToggle isDark={isDark} toggle={toggle} variant="inline" />
            {isLoaded && !isSignedIn && (
              <>
                <button
                  onClick={() => {
                    posthog?.capture('sign_in_clicked');
                    navigate("/sign-in", { state: { autoSignIn: true } });
                  }}
                  className="px-4 py-2 text-sm font-semibold text-muted-foreground hover:text-foreground transition-colors"
                >
                  Sign In
                </button>
                <button
                  onClick={handleGetStarted}
                  className="px-5 py-2 bg-primary text-primary-foreground text-sm font-semibold rounded-full shadow-md hover:bg-primary/90 hover:scale-105 transition-all duration-200"
                >
                  Get Started Free
                </button>
              </>
            )}
            {isSignedIn && (
              <button
                onClick={() => navigate("/app/library")}
                className="px-5 py-2 bg-primary text-primary-foreground text-sm font-semibold rounded-full shadow-md hover:bg-primary/90 transition-all duration-200"
              >
                Go to App
              </button>
            )}
          </div>

          {/* Mobile: dark mode + hamburger */}
          <div className="md:hidden flex items-center gap-2">
            <DarkModeToggle isDark={isDark} toggle={toggle} variant="inline" />
            <button
              type="button"
              onClick={() => setMobileMenuOpen((prev) => !prev)}
              className="p-2 rounded-full text-muted-foreground hover:bg-muted transition-colors"
              aria-label="Toggle mobile menu"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {/* Mobile dropdown */}
        {mobileMenuOpen && (
          <div className="mt-2 glass-card rounded-2xl px-4 py-3 flex flex-col gap-2 shadow-lg md:hidden">
            <a
              href="#features"
              className="text-sm text-muted-foreground hover:text-foreground py-2 transition-colors"
              onClick={() => setMobileMenuOpen(false)}
            >
              Features
            </a>
            <a
              href="#workflows"
              className="text-sm text-muted-foreground hover:text-foreground py-2 transition-colors"
              onClick={() => setMobileMenuOpen(false)}
            >
              Workflows
            </a>
            <a
              href="#faq"
              className="text-sm text-muted-foreground hover:text-foreground py-2 transition-colors"
              onClick={() => setMobileMenuOpen(false)}
            >
              FAQ
            </a>
            <Link
              to="/about"
              className="text-sm text-muted-foreground hover:text-foreground py-2 transition-colors"
              onClick={() => setMobileMenuOpen(false)}
            >
              About
            </Link>
            <div className="border-t border-border pt-2 flex flex-col gap-2">
              {isLoaded && !isSignedIn && (
                <>
                  <button
                    onClick={() => {
                      setMobileMenuOpen(false);
                      posthog?.capture('sign_in_clicked');
                      navigate("/sign-in", { state: { autoSignIn: true } });
                    }}
                    className="w-full text-left px-3 py-2 rounded-xl text-sm text-muted-foreground hover:bg-muted transition-colors"
                  >
                    Sign In
                  </button>
                  <button
                    onClick={() => { setMobileMenuOpen(false); handleGetStarted(); }}
                    className="w-full px-4 py-2.5 bg-primary text-primary-foreground text-sm font-semibold rounded-full"
                  >
                    Get Started Free
                  </button>
                </>
              )}
              {isSignedIn && (
                <button
                  onClick={() => { setMobileMenuOpen(false); navigate("/app/library"); }}
                  className="w-full px-4 py-2.5 bg-primary text-primary-foreground text-sm font-semibold rounded-full"
                >
                  Go to App
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Main content — offset for floating nav */}
      <main className="pt-24">
        <Hero onGetStarted={handleGetStarted} />

        <div id="features">
          <Features />
        </div>

        <div id="workflows">
          <WorkflowShowcase />
        </div>

        <FAQ />

        {/* CTA Section */}
        <div className="py-28 bg-gradient-to-br from-primary to-accent relative overflow-hidden">
          <div className="absolute top-0 right-0 w-96 h-96 bg-white/10 rounded-full -mr-20 -mt-20 blur-3xl pointer-events-none" />
          <div className="absolute bottom-0 left-0 w-96 h-96 bg-black/10 rounded-full -ml-20 -mb-20 blur-3xl pointer-events-none" />
          <div className="max-w-4xl mx-auto text-center px-4 relative z-10">
            <h2 className="font-display text-4xl sm:text-5xl font-bold text-primary-foreground mb-6">
              Ready to 10x Your Deal Analysis?
            </h2>
            <p className="text-xl text-primary-foreground/80 mb-10">
              Join real estate analysts who are saving hours on every deal.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              {isSignedIn ? (
                <button
                  onClick={() => navigate("/app/library")}
                  className="px-10 py-4 bg-background text-primary font-bold rounded-full shadow-xl hover:bg-popover hover:scale-105 transition-all duration-200"
                >
                  Go to App
                </button>
              ) : (
                <button
                  onClick={handleGetStarted}
                  className="px-10 py-4 bg-background text-primary font-bold rounded-full shadow-xl hover:bg-popover hover:scale-105 transition-all duration-200"
                >
                  Get Started Free
                </button>
              )}
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-background border-t border-border text-muted-foreground py-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
            <div>
              <span className="text-2xl font-extrabold tracking-tight bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
                Basilfy
              </span>
              <p className="text-sm mt-3">
                AI-powered document intelligence for real estate professionals.
              </p>
            </div>

            <div>
              <h3 className="font-display text-foreground font-semibold mb-4">Product</h3>
              <ul className="space-y-2 text-sm">
                <li><a href="#features" className="hover:text-foreground transition-colors">Features</a></li>
                <li><a href="#faq" className="hover:text-foreground transition-colors">FAQ</a></li>
              </ul>
            </div>

            <div>
              <h3 className="font-display text-foreground font-semibold mb-4">Company</h3>
              <ul className="space-y-2 text-sm">
                <li><Link to="/about" className="hover:text-foreground transition-colors">About</Link></li>
                <li><a href="mailto:saranshbhardwaj@gmail.com" className="hover:text-foreground transition-colors">Contact</a></li>
              </ul>
            </div>

            <div>
              <h3 className="font-display text-foreground font-semibold mb-4">Legal</h3>
              <ul className="space-y-2 text-sm">
                <li><Link to="/privacy" className="hover:text-foreground transition-colors">Privacy Policy</Link></li>
                <li><Link to="/terms" className="hover:text-foreground transition-colors">Terms of Service</Link></li>
              </ul>
            </div>
          </div>

          <div className="border-t border-border mt-12 pt-8 flex flex-col md:flex-row items-center justify-between gap-4 text-sm">
            <p>&copy; 2026 Basilfy. All rights reserved.</p>
            <p className="text-xs text-muted-foreground/60">Built for real estate professionals.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
