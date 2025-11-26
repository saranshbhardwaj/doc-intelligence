/**
 * StatsHeader Component
 *
 * Displays key metrics at the top of Library page
 * ChatGPT-inspired design with stat cards
 * Uses Tailwind tokenized animations from tailwind.config.js
 *
 * Input:
 *   - totalDocuments: number
 *   - totalCollections: number
 *   - processingCount: number
 *   - readyCount: number
 */

import { FileText, Folder, Clock, CheckCircle } from "lucide-react";
import { Card } from "../ui/card";

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
      bgColor: "bg-primary/10",
    },
    {
      label: "Collections",
      value: totalCollections,
      icon: Folder,
      color: "text-blue-600 dark:text-blue-400",
      bgColor: "bg-blue-500/10",
    },
    {
      label: "Processing",
      value: processingCount,
      icon: Clock,
      color: "text-warning",
      bgColor: "bg-warning/10",
    },
    {
      label: "Ready",
      value: readyCount,
      icon: CheckCircle,
      color: "text-success",
      bgColor: "bg-success/10",
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {stats.map((stat, index) => {
        const Icon = stat.icon;
        return (
          <Card
            key={stat.label}
            // Using Tailwind utilities instead of custom classes:
            // - animate-scale-up from tailwind.config.js
            // - transition-all for smooth hover
            // - hover:shadow-md for hover effect
            className="p-4 transition-all hover:shadow-md animate-scale-up"
            style={{ animationDelay: `${index * 50}ms` }}
          >
            <div className="flex items-center gap-3">
              <div className={`p-2.5 rounded-lg ${stat.bgColor}`}>
                <Icon className={`w-5 h-5 ${stat.color}`} />
              </div>
              <div className="flex-1">
                <p className="text-sm text-muted-foreground">{stat.label}</p>
                <p className="text-2xl font-semibold text-foreground">
                  {stat.value}
                </p>
              </div>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
