import { useState } from "react";
import { FileText, Folder, Clock, CheckCircle, ChevronDown, ChevronUp } from "lucide-react";

export default function StatsHeader({
  totalDocuments = 0,
  totalCollections = 0,
  processingCount = 0,
  readyCount = 0,
}) {
  const [expanded, setExpanded] = useState(false);

  const stats = [
    {
      label: "Total Documents",
      value: totalDocuments,
      icon: FileText,
      color: "text-primary",
    },
    {
      label: "Collections",
      value: totalCollections,
      icon: Folder,
      color: "text-blue-600 dark:text-blue-400",
    },
    {
      label: "Processing",
      value: processingCount,
      icon: Clock,
      color: "text-warning",
    },
    {
      label: "Ready",
      value: readyCount,
      icon: CheckCircle,
      color: "text-success",
    },
  ];

  return (
    <section className="library-shell mb-2 px-4 py-2.5 sm:mb-3 sm:px-5 sm:py-3">
      {/* Mobile: compact row with toggle */}
      <div className="flex items-center justify-between lg:hidden">
        <p className="pr-4 text-sm text-muted-foreground">
          Review collections, upload source files, and track indexing status in one place.
        </p>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1 rounded-full border border-border/70 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted"
          aria-label={expanded ? "Collapse stats" : "Expand stats"}
        >
          {expanded ? (
            <>Collapse <ChevronUp className="h-3.5 w-3.5" /></>
          ) : (
            <>Stats <ChevronDown className="h-3.5 w-3.5" /></>
          )}
        </button>
      </div>

      {/* Mobile: expandable content */}
      {expanded && (
        <div className="mt-3 lg:hidden">
          <div className="grid grid-cols-2 gap-x-5 gap-y-4 sm:grid-cols-4">
            {stats.map((stat) => {
              const Icon = stat.icon;
              return (
                <div key={stat.label} className="library-metric">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Icon className={`h-4 w-4 ${stat.color}`} />
                    <span className="library-metric-label">{stat.label}</span>
                  </div>
                  <p className="library-metric-value">{stat.value}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Desktop: always visible */}
      <div className="hidden lg:flex flex-col gap-2.5">
        <p className="text-sm leading-5 text-muted-foreground">
          Review collections, upload source files, and track indexing status in one place.
        </p>

        <div className="grid grid-cols-4 gap-x-4">
          {stats.map((stat) => {
            const Icon = stat.icon;
            return (
              <div key={stat.label} className="flex min-w-0 items-center gap-2 border-l border-border/60 pl-4 first:border-l-0 first:pl-0">
                <Icon className={`h-4 w-4 shrink-0 ${stat.color}`} />
                <div className="min-w-0">
                  <div className="library-metric-label truncate">{stat.label}</div>
                  <p className="text-base font-semibold leading-tight tracking-tight text-foreground">
                    {stat.value}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
