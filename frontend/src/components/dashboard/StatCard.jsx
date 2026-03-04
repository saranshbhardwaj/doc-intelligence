// src/components/dashboard/StatCard.jsx
/**
 * Reusable stat card component for dashboard metrics
 *
 * Displays an icon, title, large value, and subtitle in a card layout.
 */

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function StatCard({ icon: Icon, title, value, subtitle, loading, iconBg, iconColor }) {
  if (loading) {
    return (
      <Card className="rounded-2xl">
        <CardContent className="p-5">
          <div className="space-y-3">
            <Skeleton className="h-10 w-10 rounded-xl" />
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-8 w-16" />
            <Skeleton className="h-3 w-24" />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="rounded-2xl hover:shadow-md transition-shadow">
      <CardContent className="p-5">
        <div className="flex flex-col justify-between h-full gap-4">
          {Icon && (
            <div className={`p-2.5 rounded-xl w-fit ${iconBg || "bg-primary/10"}`}>
              <Icon className={`h-6 w-6 ${iconColor || "text-primary"}`} />
            </div>
          )}
          <div>
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            <h3 className="text-3xl font-bold text-foreground mt-1">{value}</h3>
            {subtitle && (
              <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
