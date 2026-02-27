/**
 * AppLayout - Shared layout for all authenticated app pages
 *
 * Provides:
 * - Consistent header navigation
 * - Logo/home link
 * - Dark mode toggle
 * - User menu
 * - Breadcrumb support
 */

import { Link, useLocation } from "react-router-dom";
import { UserButton } from "@clerk/clerk-react";
import { Library, MessageSquare, Play, Zap, FileSpreadsheet, LayoutDashboard, Menu } from "lucide-react";
import { useState } from "react";
import DarkModeToggle from "../common/DarkModeToggle";
import NetworkStatus from "../common/NetworkStatus";
import { useDarkMode } from "../../hooks/useDarkMode";
import VerticalDropdown from "../navigation/VerticalDropdown";
import { getVerticalNavigation } from "../../config/verticals";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "../ui/sheet";

// Icon mapping for vertical navigation
const ICON_MAP = {
  'book': Library,
  'message-circle': MessageSquare,
  'flow': Play,
  'zap': Zap,
  'file-spreadsheet': FileSpreadsheet,
  'table': FileSpreadsheet,
  'dashboard': LayoutDashboard,
};

export default function AppLayout({ children }) {
  const location = useLocation();
  const { isDark, toggle } = useDarkMode();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  // Detect current vertical from URL
  const currentVertical = (() => {
    if (location.pathname.startsWith('/app/re')) return 're';
    if (location.pathname.startsWith('/app/pe')) return 'pe';
    return null;
  })();

  const isActive = (path) => {
    if (path === "/app/library") {
      return (
        location.pathname === "/app/library" || location.pathname === "/app"
      );
    }
    return location.pathname.startsWith(path);
  };

  // Core navigation (when not in a vertical)
  const coreNavLinks = [
    { path: "/app/library", label: "Library", icon: Library },
    { path: "/app/chat", label: "Chat", icon: MessageSquare },
    { path: "/app/workflows", label: "Workflows", icon: Play },
    { path: "/app/extract", label: "Extract", icon: Zap },
    { path: "/app/dashboard", label: "Dashboard", icon: LayoutDashboard },
  ];

  // Get vertical-specific navigation
  const verticalNavItems = currentVertical
    ? getVerticalNavigation(currentVertical).map(item => ({
        path: `/app${item.path}`,
        label: item.label,
        icon: ICON_MAP[item.icon] || LayoutDashboard,
        comingSoon: item.comingSoon,
      }))
    : [];

  // Determine which navigation to show
  const navLinks = currentVertical ? verticalNavItems : coreNavLinks;

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <header className="bg-card border-b border-border sticky top-0 z-40">
        <div className="w-full px-4 md:px-6 py-2">
          <div className="flex items-center justify-between">
            {/* Logo / Home Link */}
            <Link
              to="/app/library"
              className="flex items-center gap-3 hover:opacity-80 transition-opacity"
            >
              <span className="relative h-8 w-8 shrink-0 overflow-hidden rounded-md">
                <img
                  src="/Freara%20ai%20logo.png"
                  alt="frearaAI"
                  className="absolute inset-0 h-full w-full scale-[1.78] object-cover"
                />
              </span>
              <span className="text-xl font-extrabold tracking-tight bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
                frearaAI
              </span>
            </Link>

            {/* Navigation */}
            <nav className="hidden md:flex items-center gap-1">
              {/* Vertical Dropdown - shown first */}
              <VerticalDropdown currentVertical={currentVertical} />

              {/* Separator if in vertical */}
              {currentVertical && (
                <div className="h-6 w-px bg-border mx-2" />
              )}

              {/* Navigation Links */}
              {navLinks.map((link) => {
                const Icon = link.icon;
                const active = isActive(link.path);
                const isComingSoon = link.comingSoon;

                return (
                  <Link
                    key={link.path}
                    to={link.path}
                    onClick={(e) => {
                      if (isComingSoon) {
                        e.preventDefault();
                      }
                    }}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                      isComingSoon
                        ? "text-muted-foreground/50 cursor-not-allowed"
                        : active
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-popover"
                    }`}
                    aria-current={active ? "page" : undefined}
                    aria-disabled={isComingSoon}
                  >
                    <Icon className="w-4 h-4" />
                    {link.label}
                    {isComingSoon && (
                      <span className="text-xs bg-muted px-1.5 py-0.5 rounded">
                        Soon
                      </span>
                    )}
                  </Link>
                );
              })}
            </nav>

            {/* Right Actions */}
            <div className="flex items-center gap-4">
              <button
                type="button"
                onClick={() => setMobileNavOpen(true)}
                className="md:hidden p-2 rounded-lg border border-border bg-card text-foreground"
                aria-label="Open navigation menu"
              >
                <Menu className="w-5 h-5" />
              </button>
              <DarkModeToggle
                isDark={isDark}
                toggle={toggle}
                variant="inline"
              />
              <UserButton
                appearance={{
                  elements: {
                    avatarBox: "w-10 h-10",
                  },
                }}
              />
            </div>
          </div>
        </div>
      </header>

      <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <SheetContent side="right" className="w-[85vw] max-w-sm p-4">
          <SheetTitle className="sr-only">Mobile Navigation</SheetTitle>
          <SheetDescription className="sr-only">
            Navigate between core app pages and vertical sections.
          </SheetDescription>
          <div className="space-y-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Navigation
            </div>

            <div className="space-y-1">
              {coreNavLinks.map((link) => {
                const Icon = link.icon;
                const active = isActive(link.path);
                const isComingSoon = link.comingSoon;

                return (
                  <Link
                    key={link.path}
                    to={link.path}
                    onClick={(e) => {
                      if (isComingSoon) {
                        e.preventDefault();
                        return;
                      }
                      setMobileNavOpen(false);
                    }}
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                      isComingSoon
                        ? "text-muted-foreground/50 cursor-not-allowed"
                        : active
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-popover"
                    }`}
                    aria-current={active ? "page" : undefined}
                    aria-disabled={isComingSoon}
                  >
                    <Icon className="w-4 h-4" />
                    {link.label}
                    {isComingSoon && (
                      <span className="text-xs bg-muted px-1.5 py-0.5 rounded ml-auto">
                        Soon
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>

            <div className="pt-3 border-t border-border">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                Verticals
              </div>
              <div className="space-y-1">
                {currentVertical && (
                  <Link
                    to="/app/library"
                    onClick={() => setMobileNavOpen(false)}
                    className="block px-3 py-2 rounded-lg text-sm text-muted-foreground hover:bg-popover transition-colors"
                  >
                    Back to Core Features
                  </Link>
                )}
                <Link
                  to="/app/re"
                  onClick={() => setMobileNavOpen(false)}
                  className={`block px-3 py-2 rounded-lg text-sm transition-colors ${
                    currentVertical === "re"
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-popover"
                  }`}
                >
                  Real Estate
                </Link>
                <Link
                  to="/app/pe"
                  onClick={() => setMobileNavOpen(false)}
                  className={`block px-3 py-2 rounded-lg text-sm transition-colors ${
                    currentVertical === "pe"
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-popover"
                  }`}
                >
                  Private Equity
                </Link>
              </div>
            </div>
          </div>
        </SheetContent>
      </Sheet>

      {/* Network health banner — shown when /api/health is unreachable */}
      <NetworkStatus />

      {/* Main Content */}
      <main className="flex-1 flex flex-col">{children}</main>
    </div>
  );
}
