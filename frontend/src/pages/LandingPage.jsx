// src/pages/LandingPage.jsx
import { useNavigate } from "react-router-dom";
import {
  SignedIn,
  SignedOut,
  SignInButton,
  UserButton,
  useAuth,
} from "@clerk/clerk-react";
import { useEffect, useState } from "react";
import Hero from "../components/landing/Hero";
import Features from "../components/landing/Features";
import WorkflowShowcase from "../components/landing/WorkflowShowcase";
import FAQ from "../components/landing/FAQ";
import DarkModeToggle from "../components/common/DarkModeToggle";
import { useDarkMode } from "../hooks/useDarkMode";

export default function LandingPage() {
  const navigate = useNavigate();
  const { isDark, toggle } = useDarkMode();
  const { isSignedIn, isLoaded } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Redirect signed-in users to library (only after Clerk finishes loading)
  useEffect(() => {
    if (isLoaded && isSignedIn) {
      navigate("/app/library");
    }
  }, [isLoaded, isSignedIn, navigate]);

  const handleGetStarted = () => {
    // Navigate to sign-up page
    navigate("/sign-up");
  };

  const handleTryDemo = () => {
    // Navigate to app with demo flag
    navigate("/app?demo=true");
  };


  return (
    <div className="min-h-screen bg-background  transition-colors duration-200">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 bg-background/80 backdrop-blur-lg border-b border-border dark:border-gray-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            {/* Logo */}
            <div className="flex items-center gap-3">
              <img
                src="/Sand_cloud_logo_dark-gray.svg"
                alt="FrearaAI"
                className="h-8 w-auto"
              />
              <span className="text-xl font-extrabold tracking-tight bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                FrearaAI
              </span>
            </div>

            {/* Nav links */}
            <div className="hidden md:flex items-center gap-8">
              <a
                href="#features"
                className="text-muted-foreground dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
              >
                Features
              </a>
              <a
                href="#workflows"
                className="text-muted-foreground dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
              >
                Workflows
              </a>
              <a
                href="#faq"
                className="text-muted-foreground dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
              >
                FAQ
              </a>
              <DarkModeToggle
                isDark={isDark}
                toggle={toggle}
                variant="inline"
              />

              {/* Authentication buttons */}
              <SignedOut>
                <SignInButton mode="modal">
                  <button className="px-4 py-2 text-muted-foreground dark:text-gray-300 hover:text-foreground dark:hover:text-foreground font-medium transition-colors">
                    Sign In
                  </button>
                </SignInButton>
                <button
                  onClick={handleGetStarted}
                  className="px-6 py-2 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-foreground font-semibold rounded-lg transition-all duration-200"
                >
                  Get Started Free
                </button>
              </SignedOut>
              <SignedIn>
                <button
                  onClick={() => navigate("/app/library")}
                  className="px-6 py-2 bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-700 hover:to-purple-700 text-foreground font-semibold rounded-lg transition-all duration-200"
                >
                  Go to App
                </button>
                <UserButton />
              </SignedIn>
            </div>

            {/* Mobile menu button + dark mode */}
            <div className="md:hidden flex items-center gap-4">
              <DarkModeToggle
                isDark={isDark}
                toggle={toggle}
                variant="inline"
              />
              <button
                type="button"
                onClick={() => setMobileMenuOpen((prev) => !prev)}
                className="text-muted-foreground dark:text-gray-300"
                aria-label="Toggle mobile menu"
                aria-expanded={mobileMenuOpen}
              >
                <svg
                  className="w-6 h-6"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 6h16M4 12h16M4 18h16"
                  />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* Mobile Menu Panel */}
        {mobileMenuOpen && (
          <div className="md:hidden border-t border-border bg-background/95 backdrop-blur">
            <div className="max-w-7xl mx-auto px-4 py-3 flex flex-col gap-3">
              <a
                href="#features"
                className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Features
              </a>
              <a
                href="#workflows"
                className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Workflows
              </a>
              <a
                href="#faq"
                className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                FAQ
              </a>

              <SignedOut>
                <SignInButton mode="modal">
                  <button className="w-full text-left px-3 py-2 rounded-md text-sm text-muted-foreground hover:bg-muted transition-colors">
                    Sign In
                  </button>
                </SignInButton>
                <button
                  onClick={() => {
                    setMobileMenuOpen(false);
                    handleGetStarted();
                  }}
                  className="w-full px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-foreground font-semibold rounded-lg"
                >
                  Get Started Free
                </button>
              </SignedOut>

              <SignedIn>
                <button
                  onClick={() => {
                    setMobileMenuOpen(false);
                    navigate("/app/library");
                  }}
                  className="w-full px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-foreground font-semibold rounded-lg"
                >
                  Go to App
                </button>
              </SignedIn>
            </div>
          </div>
        )}
      </nav>

      {/* Hero Section */}
      <Hero onGetStarted={handleGetStarted} onTryDemo={handleTryDemo} />

      {/* Features Section */}
      <div id="features">
        <Features />
      </div>

      {/* Workflow Showcase Section */}
      <div id="workflows">
        <WorkflowShowcase />
      </div>

      {/* FAQ Section */}
      <FAQ />

      {/* CTA Section */}
      <div className="py-24 bg-gradient-to-r from-blue-600 to-purple-600">
        <div className="max-w-4xl mx-auto text-center px-4">
          <h2 className="text-4xl sm:text-5xl font-bold text-foreground mb-6">
            Ready to 10x Your Deal Analysis?
          </h2>
          <p className="text-xl text-blue-100 mb-8">
            Join PE and real estate analysts who are saving hours on every deal.
          </p>
          <SignedOut>
            <button
              onClick={handleGetStarted}
              className="px-10 py-4 bg-background hover:bg-popover text-blue-600 font-bold rounded-xl shadow-xl hover:shadow-2xl transform hover:scale-105 transition-all duration-200"
            >
              Get Started Free
            </button>
          </SignedOut>
          <SignedIn>
            <button
              onClick={() => navigate("/app/library")}
              className="px-10 py-4 bg-background hover:bg-popover text-blue-600 font-bold rounded-xl shadow-xl hover:shadow-2xl transform hover:scale-105 transition-all duration-200"
            >
              Go to App
            </button>
          </SignedIn>
        </div>
      </div>

      {/* Footer */}
      <footer className="bg-background dark:bg-black text-muted-foreground py-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
            {/* Company */}
            <div>
              <div className="mb-4">
                <span className="text-2xl font-extrabold tracking-tight bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                  FrearaAI
                </span>
              </div>
              <p className="text-sm">
                AI-powered document intelligence for PE and real estate.
              </p>
            </div>

            {/* Product */}
            <div>
              <h3 className="text-foreground font-semibold mb-4">Product</h3>
              <ul className="space-y-2 text-sm">
                <li>
                  <a
                    href="#features"
                    className="hover:text-foreground transition-colors"
                  >
                    Features
                  </a>
                </li>
                {/* <li>
                  <a
                    href="#pricing"
                    className="hover:text-foreground transition-colors"
                  >
                    Pricing
                  </a>
                </li> */}
                <li>
                  <a
                    href="#"
                    className="hover:text-foreground transition-colors"
                  >
                    Changelog
                  </a>
                </li>
                <li>
                  <a
                    href="#"
                    className="hover:text-foreground transition-colors"
                  >
                    Roadmap
                  </a>
                </li>
              </ul>
            </div>

            {/* Company */}
            <div>
              <h3 className="text-foreground font-semibold mb-4">Company</h3>
              <ul className="space-y-2 text-sm">
                <li>
                  <a
                    href="#"
                    className="hover:text-foreground transition-colors"
                  >
                    About
                  </a>
                </li>
                <li>
                  <a
                    href="#"
                    className="hover:text-foreground transition-colors"
                  >
                    Blog
                  </a>
                </li>
                <li>
                  <a
                    href="#"
                    className="hover:text-foreground transition-colors"
                  >
                    Careers
                  </a>
                </li>
                <li>
                  <a
                    href="#"
                    className="hover:text-foreground transition-colors"
                  >
                    Contact
                  </a>
                </li>
              </ul>
            </div>

            {/* Legal */}
            <div>
              <h3 className="text-foreground font-semibold mb-4">Legal</h3>
              <ul className="space-y-2 text-sm">
                <li>
                  <a
                    href="#"
                    className="hover:text-foreground transition-colors"
                  >
                    Privacy Policy
                  </a>
                </li>
                <li>
                  <a
                    href="#"
                    className="hover:text-foreground transition-colors"
                  >
                    Terms of Service
                  </a>
                </li>
                <li>
                  <a
                    href="#"
                    className="hover:text-foreground transition-colors"
                  >
                    Security
                  </a>
                </li>
              </ul>
            </div>
          </div>

          <div className="border-t border-gray-800 mt-12 pt-8 text-center text-sm">
            <p>&copy; 2026 FrearaAI. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
