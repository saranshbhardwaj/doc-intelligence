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
import { Library, MessageSquare, Play, Zap, FileSpreadsheet, LayoutDashboard } from "lucide-react";
import DarkModeToggle from "../common/DarkModeToggle";
import { useDarkMode } from "../../hooks/useDarkMode";
import VerticalDropdown from "../navigation/VerticalDropdown";
import { getVerticalNavigation } from "../../config/verticals";

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

export default function AppLayout({ children, breadcrumbs }) {
  const location = useLocation();
  const { isDark, toggle } = useDarkMode();

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
        <div className="max-w-7xl mx-auto px-6 py-2">
          <div className="flex items-center justify-between">
            {/* Logo / Home Link */}
            <Link
              to="/app/library"
              className="flex items-center gap-3 hover:opacity-80 transition-opacity"
            >
              <img
                src="/Sand_cloud_logo_dark-gray.svg"
                alt="SandCloud"
                className="h-8 w-auto"
              />
              <span className="text-xl font-bold text-foreground">
                SandCloud
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

      {/* Main Content */}
      <main className="flex-1 flex flex-col">{children}</main>
    </div>
  );
}
