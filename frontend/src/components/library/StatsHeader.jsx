import { FileText, Folder, Clock, CheckCircle } from "lucide-react";

export default function StatsHeader({
  totalDocuments = 0,
  totalCollections = 0,
  processingCount = 0,
  readyCount = 0,
}) {
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
    <section className="library-shell mb-5 px-5 py-4 sm:px-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          <p className="shell-eyebrow">Workspace</p>
          <h1 className="shell-title">Library</h1>
          <p className="shell-subtitle">
            Review collections, upload source files, and track indexing status in one place.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-x-5 gap-y-4 sm:grid-cols-4 lg:min-w-[32rem]">
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
    </section>
  );
}
