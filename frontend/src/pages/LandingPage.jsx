// src/pages/LandingPage.jsx
import { useNavigate } from "react-router-dom";
import {
  SignedIn,
  SignedOut,
  SignInButton,
  UserButton,
  useAuth,
} from "@clerk/clerk-react";
import { useEffect } from "react";
import Hero from "../components/landing/Hero";
import Features from "../components/landing/Features";
import Pricing from "../components/landing/Pricing";
import FAQ from "../components/landing/FAQ";
import DarkModeToggle from "../components/common/DarkModeToggle";
import { useDarkMode } from "../hooks/useDarkMode";

export default function LandingPage() {
  const navigate = useNavigate();
  const { isDark, toggle } = useDarkMode();
  const { isSignedIn, isLoaded } = useAuth();

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

  const handleSelectPlan = (planName) => {
    if (planName === "free") {
      navigate("/app");
    } else if (planName === "pro") {
      // TODO: Navigate to signup with pro plan pre-selected
      navigate("/app");
    } else {
      // Enterprise - open contact form or mailto
      window.location.href =
        "mailto:saranshbhardwaj@gmail.com?subject=Enterprise Plan Inquiry";
    }
  };

  return (
    <div className="min-h-screen bg-background  transition-colors duration-200">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 bg-background/80 /80 backdrop-blur-lg border-b border-border dark:border-gray-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            {/* Logo */}
            <div className="flex items-center gap-3">
              <img
                src="/Sand_cloud_logo_dark-gray.svg"
                alt="Sand Cloud"
                className="h-8 w-auto"
              />
              <span className="text-xl font-bold text-foreground">
                Sand Cloud
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
              {/* <a
                href="#pricing"
                className="text-muted-foreground dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
              >
                Pricing
              </a> */}
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
              <button className="text-muted-foreground dark:text-gray-300">
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
      </nav>

      {/* Hero Section */}
      <Hero onGetStarted={handleGetStarted} onTryDemo={handleTryDemo} />

      {/* Features Section */}
      <div id="features">
        <Features />
      </div>

      {/* Pricing Section */}
      <div id="pricing">
        <Pricing onSelectPlan={handleSelectPlan} />
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
            Join PE analysts who are saving hours on every deal.
          </p>
          <SignedOut>
            <button
              onClick={handleGetStarted}
              className="px-10 py-4 bg-background hover:bg-popover text-blue-600 font-bold rounded-xl shadow-xl hover:shadow-2xl transform hover:scale-105 transition-all duration-200"
            >
              Get Started Free
            </button>
            <p className="text-sm text-blue-100 mt-4">
              No credit card required • 100 pages free
            </p>
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
                <span className="text-2xl font-bold text-foreground">
                  Sand Cloud
                </span>
              </div>
              <p className="text-sm">
                AI-powered CIM analysis for PE analysts.
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
            <p>&copy; 2025 Sand Cloud. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
