// src/components/dashboard/StatCard.jsx
/**
 * Reusable stat card component for dashboard metrics
 *
 * Displays an icon, title, large value, and subtitle in a card layout.
 */

import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export default function StatCard({ icon: Icon, title, value, subtitle, loading }) {
  if (loading) {
    return (
      <Card>
        <CardContent className="p-4 sm:p-6">
          <div className="space-y-3">
            <Skeleton className="h-8 w-8 rounded-full" />
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-8 w-16" />
            <Skeleton className="h-3 w-24" />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-4 sm:p-6">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-3 sm:mb-4">
              {Icon && (
                <div className="flex items-center justify-center h-9 w-9 sm:h-10 sm:w-10 rounded-full bg-primary/10">
                  <Icon className="h-4 w-4 sm:h-5 sm:w-5 text-primary" />
                </div>
              )}
              <p className="text-sm font-medium text-muted-foreground">{title}</p>
            </div>
            <div className="space-y-1">
              <p className="text-2xl sm:text-3xl font-bold tracking-tight">{value}</p>
              {subtitle && (
                <p className="text-xs sm:text-sm text-muted-foreground">{subtitle}</p>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
