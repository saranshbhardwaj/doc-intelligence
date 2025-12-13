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
import { Library, MessageSquare, Play, Zap } from "lucide-react";
import DarkModeToggle from "../common/DarkModeToggle";
import { useDarkMode } from "../../hooks/useDarkMode";

export default function AppLayout({ children, breadcrumbs }) {
  const location = useLocation();
  const { isDark, toggle } = useDarkMode();

  const isActive = (path) => {
    if (path === "/app/library") {
      return (
        location.pathname === "/app/library" || location.pathname === "/app"
      );
    }
    return location.pathname.startsWith(path);
  };

  const navLinks = [
    { path: "/app/library", label: "Library", icon: Library },
    { path: "/app/chat", label: "Chat", icon: MessageSquare },
    { path: "/app/workflows", label: "Workflows", icon: Play },
    { path: "/app/extract", label: "Extract", icon: Zap },
  ];

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <header className="bg-card border-b border-border sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 py-4">
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
              {navLinks.map((link) => {
                const Icon = link.icon;
                const active = isActive(link.path);
                return (
                  <Link
                    key={link.path}
                    to={link.path}
                    // onClick={(e) =>
                    //   console.log("nav click:", link.path, e.target)
                    // }
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                      active
                        ? "bg-primary/10 text-primary" // active: subtle primary background + primary text
                        : "text-muted-foreground hover:bg-popover" // inactive: muted text, subtle hover surface
                    }`}
                    aria-current={active ? "page" : undefined}
                  >
                    <Icon className="w-4 h-4" />
                    {link.label}
                  </Link>
                );
              })}
            </nav>

            {/* Right Actions */}
            <div className="flex items-center gap-4">
              <DarkModeToggle isDark={isDark} toggle={toggle} />
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
