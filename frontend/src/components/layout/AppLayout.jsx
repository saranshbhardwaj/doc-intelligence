/**
 * AppLayout - Shared layout for all authenticated app pages.
 *
 * Provides:
 * - Consistent branded top bar
 * - Shared navigation and vertical switcher
 * - Optional page identity bar with actions
 * - User menu and network status
 */

import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAppAuth } from "@/hooks/useAppAuth";
import { cn } from "@/lib/utils";
import { Library, MessageSquare, Play, Zap, FileSpreadsheet, LayoutDashboard, Menu, LogOut, Sun, Moon, BarChart2, ChevronRight, Calculator, ArrowLeft, Briefcase } from "lucide-react";
import { useUser, useUserActions } from "../../store";
import { useState, useEffect } from "react";
import NetworkStatus from "../common/NetworkStatus";
import { useDarkMode } from "../../hooks/useDarkMode";
import VerticalDropdown from "../navigation/VerticalDropdown";
import { getVerticalNavigation } from "../../config/verticals";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "../ui/sheet";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuGroup,
} from "../ui/dropdown-menu";

const ROUTE_VERTICAL_TO_KEY = {
  re: "real_estate",
  pe: "private_equity",
};

const VERTICAL_LABELS = {
  real_estate: "Real Estate",
  private_equity: "Private Equity",
};

// Icon mapping for vertical navigation
const ICON_MAP = {
  'book': Library,
  'message-circle': MessageSquare,
  'flow': Play,
  'zap': Zap,
  'file-spreadsheet': FileSpreadsheet,
  'table': FileSpreadsheet,
  'dashboard': LayoutDashboard,
  'calculator': Calculator,
  'briefcase': Briefcase,
};

function getCurrentVerticalSlug(pathname, queryVertical) {
  if (queryVertical === 're' || queryVertical === 'pe') return queryVertical;
  if (pathname.startsWith('/app/re')) return 're';
  if (pathname.startsWith('/app/pe')) return 'pe';
  return null;
}

function buildContextualTarget(path, currentVerticalSlug) {
  if (!currentVerticalSlug) return path;
  if (path === '/app/library' || path === '/app/chat') {
    return {
      pathname: path,
      search: `?vertical=${currentVerticalSlug}`,
    };
  }
  return path;
}

function formatSegment(segment) {
  return segment
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function derivePageHeader(pathname, currentVerticalKey, navLinks) {
  const eyebrow = currentVerticalKey ? VERTICAL_LABELS[currentVerticalKey] : 'Workspace';
  const explicitMatches = [
    { match: /^\/app\/dashboard(?:\/.*)?$/, title: 'Overview', eyebrow: 'Workspace' },
    { match: /^\/app(?:\/)?$/, title: 'Library', eyebrow: 'Workspace' },
    { match: /^\/app\/library(?:\/.*)?$/, title: 'Library', eyebrow: 'Workspace' },
    { match: /^\/app\/re\/fills\/[^/]+(?:\/.*)?$/, title: 'Template Fill', eyebrow: 'Real Estate' },
    { match: /^\/app\/re\/underwriting\/new(?:\/.*)?$/, title: 'New Analysis', eyebrow: 'Real Estate' },
    { match: /^\/app\/re\/underwriting\/[^/]+(?:\/.*)?$/, title: 'Underwriting Analysis', eyebrow: 'Real Estate' },
    { match: /^\/app\/re(?:\/)?$/, title: 'Home', eyebrow: 'Real Estate' },
    { match: /^\/app\/pe(?:\/)?$/, title: 'Deal Rooms', eyebrow: 'Private Equity' },
  ];

  const explicitHeader = explicitMatches.find((item) => item.match.test(pathname));
  if (explicitHeader) {
    return {
      eyebrow: explicitHeader.eyebrow,
      title: explicitHeader.title,
    };
  }

  const matchedLink = [...navLinks]
    .sort((left, right) => right.path.length - left.path.length)
    .find((link) => pathname === link.path || pathname.startsWith(`${link.path}/`));

  if (matchedLink) {
    return {
      eyebrow,
      title: matchedLink.label,
    };
  }

  const segments = pathname.replace(/^\/app\/?/, '').split('/').filter(Boolean);
  return {
    eyebrow,
    title: formatSegment(segments.at(-1) || 'library'),
  };
}

function UsageBar({ label, used, limit }) {
  if (!limit) return null;
  const pct = Math.min((used / limit) * 100, 100);
  const barColor = pct >= 90 ? 'bg-destructive' : pct >= 80 ? 'bg-yellow-500' : 'bg-primary';
  const textColor = pct >= 90 ? 'text-destructive' : pct >= 80 ? 'text-yellow-500' : 'text-muted-foreground';
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className={`text-xs font-medium tabular-nums ${textColor}`}>{used}<span className="opacity-50">/{limit}</span></span>
      </div>
      <div className="h-1 w-full rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function TierBadge({ tier }) {
  if (!tier) return null;
  const variants = {
    admin: 'bg-primary/10 text-primary border-primary/20',
    pro: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
    standard: 'bg-muted text-muted-foreground border-border',
    free: 'bg-muted text-muted-foreground border-border',
  };
  const cls = variants[tier] ?? variants.free;
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide border ${cls}`}>
      {tier}
    </span>
  );
}

export default function AppLayout({
  children,
  lockViewport = false,
  headerLeft = null,
  headerRight = null,
  hideNav = false,
  pageHeader = null,
  suppressPageHeader = false,
}) {
  const location = useLocation();
  const { isDark, toggle } = useDarkMode();
  const { user, signOut, getToken } = useAppAuth();
  const userState = useUser();
  const userLimits = userState?.info?.limits;
  const allowedVerticals = userState?.info?.allowed_verticals || ['real_estate'];
  const { fetchUserInfo } = useUserActions();

  useEffect(() => {
    if (!userState?.info) {
      fetchUserInfo(getToken);
    }
  }, []);
  const navigate = useNavigate();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const searchParams = new URLSearchParams(location.search);
  const currentVerticalSlug = getCurrentVerticalSlug(location.pathname, searchParams.get('vertical'));
  const currentVerticalKey = currentVerticalSlug ? ROUTE_VERTICAL_TO_KEY[currentVerticalSlug] : null;

  const isActive = (path) => {
    if (path === "/app/re") {
      return location.pathname === "/app/re";
    }
    if (path === "/app/pe") {
      return location.pathname === "/app/pe";
    }
    if (path === "/app/library") {
      return (
        location.pathname === "/app/library" || location.pathname === "/app"
      );
    }
    if (path === "/app/re/templates") {
      return (
        location.pathname.startsWith("/app/re/templates") ||
        location.pathname.startsWith("/app/re/fills/")
      );
    }
    return location.pathname === path || location.pathname.startsWith(`${path}/`);
  };

  const hasPE = allowedVerticals.includes('private_equity');

  // Core navigation (when not in a vertical) — PE-only items hidden for RE-only users
  const coreNavLinks = [
    { path: "/app/library", label: "Library", icon: Library },
    { path: "/app/chat", label: "Chat", icon: MessageSquare },
    ...(hasPE ? [
      { path: "/app/workflows", label: "Workflows", icon: Play },
      { path: "/app/extract", label: "Extract", icon: Zap },
    ] : []),
    { path: "/app/dashboard", label: "Overview", icon: LayoutDashboard },
  ];

  // Get vertical-specific navigation
  const verticalNavItems = currentVerticalKey
    ? getVerticalNavigation(currentVerticalKey).map(item => ({
        path: `/app${item.path}`,
        label: item.label,
        icon: ICON_MAP[item.icon] || LayoutDashboard,
        comingSoon: item.comingSoon,
      }))
    : [];

  // Determine which navigation to show
  const navLinks = currentVerticalKey ? verticalNavItems : coreNavLinks;
  const derivedPageHeader = !suppressPageHeader && !pageHeader && !headerLeft
    ? derivePageHeader(location.pathname, currentVerticalKey, navLinks)
    : null;
  const resolvedPageHeader = pageHeader ?? derivedPageHeader;
  const resolvedHeaderRight = pageHeader?.actions ?? headerRight;
  const isCompactPageHeader = Boolean(resolvedPageHeader?.compact);
  const shouldShowPageBar = !suppressPageHeader && Boolean(resolvedPageHeader || headerLeft || resolvedHeaderRight);

  return (
    <div className={`${lockViewport ? "h-[100dvh] overflow-hidden" : "min-h-screen"} bg-background flex flex-col`}>
      {/* Header */}
      <header className="app-topbar">
        <div className="app-topbar-inner">
          <div className="app-topbar-row">
            {/* Logo / Home Link */}
            <Link
              to={buildContextualTarget('/app/library', currentVerticalSlug)}
              className="app-brand"
            >
              <span className="app-brand-mark">
                <img
                  src="/Freara%20ai%20logo.png"
                  alt="Basilfy"
                  className="absolute inset-0 h-full w-full scale-[1.78] object-cover"
                />
              </span>
              <span className="app-brand-wordmark">Basilfy</span>
            </Link>

            {/* Navigation */}
            {!hideNav && (
              <nav className="app-topbar-nav">
                {/* Vertical Dropdown - shown first */}
                <VerticalDropdown currentVertical={currentVerticalSlug} allowedVerticals={allowedVerticals} />

                {/* Separator if in vertical */}
                {currentVerticalKey && (
                  <div className="mx-1 h-6 w-px bg-border/70" />
                )}

                {/* Navigation Links */}
                {navLinks.map((link) => {
                  const Icon = link.icon;
                  const active = isActive(link.path);
                  const isComingSoon = link.comingSoon;

                  return (
                    <Link
                      key={link.path}
                      to={buildContextualTarget(link.path, currentVerticalSlug)}
                      onClick={(e) => {
                        if (isComingSoon) {
                          e.preventDefault();
                        }
                      }}
                      className={cn(
                        "topbar-nav-button",
                        active && !isComingSoon && "topbar-nav-button-active",
                        isComingSoon && "cursor-not-allowed text-muted-foreground/50"
                      )}
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
            )}

            {/* Right Actions */}
            <div className="flex items-center gap-4">
              <button
                type="button"
                onClick={() => setMobileNavOpen(true)}
                className="rounded-xl border border-border/70 bg-card/80 p-2 text-foreground shadow-sm md:hidden"
                aria-label="Open navigation menu"
              >
                <Menu className="w-5 h-5" />
              </button>
              {/* User avatar / menu */}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    className="w-8 h-8 rounded-full overflow-hidden bg-gradient-to-br from-primary/20 to-primary/10 text-primary font-semibold text-sm flex items-center justify-center hover:opacity-90 ring-1 ring-primary/20 hover:ring-primary/40 transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                    aria-label="User menu"
                  >
                    {user?.profilePictureUrl
                      ? <img src={user.profilePictureUrl} alt="" className="w-full h-full object-cover" />
                      : (user?.firstName?.[0] ?? user?.email?.[0]?.toUpperCase() ?? "U")
                    }
                  </button>
                </DropdownMenuTrigger>

                <DropdownMenuContent align="end" sideOffset={8} className="w-64 p-0 overflow-hidden">
                  {/* Profile header */}
                  <div className="px-4 pt-4 pb-3 bg-gradient-to-b from-primary/5 to-transparent border-b border-border">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full overflow-hidden bg-gradient-to-br from-primary/25 to-primary/10 ring-2 ring-primary/20 text-primary font-bold text-base flex items-center justify-center shrink-0">
                        {user?.profilePictureUrl
                          ? <img src={user.profilePictureUrl} alt="" className="w-full h-full object-cover" />
                          : (user?.firstName?.[0] ?? user?.email?.[0]?.toUpperCase() ?? "U")
                        }
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-semibold text-foreground truncate leading-tight">
                            {user?.firstName} {user?.lastName}
                          </p>
                          <TierBadge tier={userState?.info?.tier} />
                        </div>
                        <p className="text-xs text-muted-foreground truncate mt-0.5">{user?.email}</p>
                      </div>
                    </div>
                  </div>

                  {/* Usage */}
                  {userLimits && (
                    <>
                      <DropdownMenuItem
                        className="flex-col items-stretch gap-2.5 px-4 py-3 cursor-pointer focus:bg-muted/60 rounded-none"
                        onSelect={() => navigate('/app/dashboard')}
                      >
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="text-xs font-medium text-foreground">Usage</span>
                          <span className="flex items-center gap-1 text-xs text-primary">
                            <BarChart2 className="w-3 h-3" />
                            View details
                            <ChevronRight className="w-3 h-3" />
                          </span>
                        </div>
                        <UsageBar
                          label="Template fills this month"
                          used={userLimits.template_fill_runs?.used ?? 0}
                          limit={userLimits.template_fill_runs?.limit ?? 0}
                        />
                        <UsageBar
                          label="Chat messages today"
                          used={userLimits.chat_messages?.used ?? 0}
                          limit={userLimits.chat_messages?.limit ?? 0}
                        />
                      </DropdownMenuItem>
                      <DropdownMenuSeparator className="my-0" />
                    </>
                  )}

                  <DropdownMenuGroup className="p-1">
                    <DropdownMenuItem asChild>
                      <Link to="/app/dashboard" className="flex items-center gap-2.5 cursor-pointer">
                        <LayoutDashboard className="w-4 h-4 text-muted-foreground" />
                        <span>Overview</span>
                      </Link>
                    </DropdownMenuItem>
                    <DropdownMenuItem asChild>
                      <Link to={buildContextualTarget('/app/library', currentVerticalSlug)} className="flex items-center gap-2.5 cursor-pointer">
                        <Library className="w-4 h-4 text-muted-foreground" />
                        <span>Library</span>
                      </Link>
                    </DropdownMenuItem>
                  </DropdownMenuGroup>

                  <DropdownMenuSeparator className="my-0" />

                  {/* Appearance */}
                  <DropdownMenuGroup className="p-1">
                    <DropdownMenuItem onSelect={(e) => { e.preventDefault(); toggle(); }} className="flex items-center gap-2.5 cursor-pointer">
                      {isDark ? <Sun className="w-4 h-4 text-muted-foreground" /> : <Moon className="w-4 h-4 text-muted-foreground" />}
                      <span>{isDark ? 'Light mode' : 'Dark mode'}</span>
                    </DropdownMenuItem>
                  </DropdownMenuGroup>

                  <DropdownMenuSeparator className="my-0" />

                  {/* Sign out */}
                  <DropdownMenuGroup className="p-1">
                    <DropdownMenuItem
                      onSelect={() => signOut?.()}
                      className="flex items-center gap-2.5 cursor-pointer text-destructive focus:text-destructive focus:bg-destructive/8"
                    >
                      <LogOut className="w-4 h-4" />
                      <span>Sign out</span>
                    </DropdownMenuItem>
                  </DropdownMenuGroup>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>

          {shouldShowPageBar && (
            <div className={cn("app-pagebar", isCompactPageHeader && "app-pagebar-compact")}>
              <div className="min-w-0 flex-1">
                {resolvedPageHeader ? (
                  <div className={cn("app-pagebar-main", isCompactPageHeader && "app-pagebar-main-compact")}>
                    {resolvedPageHeader.backTo ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => navigate(resolvedPageHeader.backTo)}
                        className={cn("app-pagebar-back", isCompactPageHeader && "app-pagebar-back-compact")}
                      >
                        <ArrowLeft className="h-4 w-4" />
                        <span className="hidden sm:inline">{resolvedPageHeader.backLabel || 'Back'}</span>
                      </Button>
                    ) : null}

                    <div className={cn("min-w-0 flex-1", isCompactPageHeader && "app-pagebar-content-compact")}>
                      {!isCompactPageHeader ? (
                        <p className="app-pagebar-eyebrow">
                          {resolvedPageHeader.eyebrow || (currentVerticalKey ? VERTICAL_LABELS[currentVerticalKey] : 'Workspace')}
                        </p>
                      ) : null}
                      <div className={cn("app-pagebar-title-row", isCompactPageHeader && "app-pagebar-title-row-compact")}>
                        {isCompactPageHeader ? (
                          <p className={cn("app-pagebar-eyebrow", "app-pagebar-eyebrow-inline", "app-pagebar-eyebrow-compact")}>
                            {resolvedPageHeader.eyebrow || (currentVerticalKey ? VERTICAL_LABELS[currentVerticalKey] : 'Workspace')}
                          </p>
                        ) : null}
                        <h1 className={cn("app-pagebar-title", isCompactPageHeader && "app-pagebar-title-compact")}>
                          {resolvedPageHeader.title}
                        </h1>
                        {resolvedPageHeader.meta ? (
                          <div className={cn("app-pagebar-meta", isCompactPageHeader && "app-pagebar-meta-compact")}>
                            {resolvedPageHeader.meta}
                          </div>
                        ) : null}
                      </div>
                      {resolvedPageHeader.subtitle && !isCompactPageHeader ? (
                        <p className="app-pagebar-subtitle">{resolvedPageHeader.subtitle}</p>
                      ) : null}
                    </div>
                  </div>
                ) : headerLeft ? (
                  <div className="app-pagebar-legacy">{headerLeft}</div>
                ) : null}
              </div>

              {resolvedHeaderRight ? (
                <div className={cn("app-pagebar-actions", isCompactPageHeader && "app-pagebar-actions-compact")}>{resolvedHeaderRight}</div>
              ) : null}
            </div>
          )}
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
              {navLinks.map((link) => {
                const Icon = link.icon;
                const active = isActive(link.path);
                const isComingSoon = link.comingSoon;

                return (
                  <Link
                    key={link.path}
                    to={buildContextualTarget(link.path, currentVerticalSlug)}
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
                {currentVerticalKey && (
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
                    currentVerticalSlug === "re"
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-popover"
                  }`}
                >
                  Real Estate
                </Link>
                {hasPE && (
                  <Link
                    to="/app/pe"
                    onClick={() => setMobileNavOpen(false)}
                    className={`block px-3 py-2 rounded-lg text-sm transition-colors ${
                      currentVerticalSlug === "pe"
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-popover"
                    }`}
                  >
                    Private Equity
                  </Link>
                )}
              </div>
            </div>
          </div>
        </SheetContent>
      </Sheet>

      {/* Network health banner — shown when /api/health is unreachable */}
      <NetworkStatus />

      {/* Main Content */}
      <main className={`${lockViewport ? "flex-1 min-h-0 flex flex-col overflow-hidden" : "flex-1 flex flex-col"} page-enter`}>
        {children}
      </main>
    </div>
  );
}
