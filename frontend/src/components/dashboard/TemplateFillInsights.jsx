// src/components/dashboard/TemplateFillInsights.jsx
/**
 * Template fill insights and top templates
 *
 * Shows status breakdown, average metrics, and ranked templates.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { BarChart3, Target, Clock, FileSpreadsheet } from "lucide-react";

export default function TemplateFillInsights({ stats, loading }) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Template Fill Insights</CardTitle>
          </CardHeader>
          <CardContent>
            <Skeleton className="h-40 w-full" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Top Templates</CardTitle>
          </CardHeader>
          <CardContent>
            <Skeleton className="h-40 w-full" />
          </CardContent>
        </Card>
      </div>
    );
  }

  const { by_status = {}, avg_fields_filled, avg_auto_map_rate, avg_processing_time_seconds, top_templates = [] } = stats || {};

  const total = Object.values(by_status).reduce((sum, count) => sum + count, 0);
  const completedCount = by_status.completed || 0;
  const failedCount = by_status.failed || 0;
  const runningCount = by_status.running || 0;

  const completedPercent = total > 0 ? (completedCount / total) * 100 : 0;
  const failedPercent = total > 0 ? (failedCount / total) * 100 : 0;
  const runningPercent = total > 0 ? (runningCount / total) * 100 : 0;

  const maxCount = top_templates.length > 0 ? Math.max(...top_templates.map(t => t.fill_count)) : 1;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
      {/* Left: Stats */}
      <Card className="lg:col-span-3">
        <CardHeader>
          <CardTitle>Template Fill Insights</CardTitle>
          <CardDescription>Performance metrics for template fills</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Status Bar */}
          {total > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Status Breakdown</span>
                <span className="font-medium">{total} total</span>
              </div>
              <div className="flex h-2 rounded-full overflow-hidden bg-muted">
                {completedPercent > 0 && (
                  <div
                    className="bg-green-500"
                    style={{ width: `${completedPercent}%` }}
                    title={`${completedCount} completed`}
                  />
                )}
                {failedPercent > 0 && (
                  <div
                    className="bg-red-500"
                    style={{ width: `${failedPercent}%` }}
                    title={`${failedCount} failed`}
                  />
                )}
                {runningPercent > 0 && (
                  <div
                    className="bg-yellow-500"
                    style={{ width: `${runningPercent}%` }}
                    title={`${runningCount} running`}
                  />
                )}
              </div>
              <div className="flex items-center gap-4 text-xs">
                <div className="flex items-center gap-1.5">
                  <div className="h-2 w-2 rounded-full bg-green-500" />
                  <span className="text-muted-foreground">Completed: {completedCount}</span>
                </div>
                {failedCount > 0 && (
                  <div className="flex items-center gap-1.5">
                    <div className="h-2 w-2 rounded-full bg-red-500" />
                    <span className="text-muted-foreground">Failed: {failedCount}</span>
                  </div>
                )}
                {runningCount > 0 && (
                  <div className="flex items-center gap-1.5">
                    <div className="h-2 w-2 rounded-full bg-yellow-500" />
                    <span className="text-muted-foreground">Running: {runningCount}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Metrics Row */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {/* Avg Fields */}
            <div className="flex items-start gap-3 p-4 rounded-lg bg-muted/30">
              <div className="flex items-center justify-center h-10 w-10 rounded-full bg-primary/10">
                <BarChart3 className="h-5 w-5 text-primary" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Avg Fields Filled</p>
                <p className="text-2xl font-bold">{avg_fields_filled?.toFixed(1) || "0.0"}</p>
              </div>
            </div>

            {/* Auto-Map Rate */}
            <div className="flex items-start gap-3 p-4 rounded-lg bg-muted/30">
              <div className="flex items-center justify-center h-10 w-10 rounded-full bg-primary/10">
                <Target className="h-5 w-5 text-primary" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Auto-Map Rate</p>
                <p className="text-2xl font-bold">{avg_auto_map_rate ? `${(avg_auto_map_rate * 100).toFixed(0)}%` : "0%"}</p>
              </div>
            </div>

            {/* Avg Processing Time */}
            <div className="flex items-start gap-3 p-4 rounded-lg bg-muted/30">
              <div className="flex items-center justify-center h-10 w-10 rounded-full bg-primary/10">
                <Clock className="h-5 w-5 text-primary" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Avg Time</p>
                <p className="text-2xl font-bold">{avg_processing_time_seconds?.toFixed(1) || "0.0"}s</p>
                {avg_processing_time_seconds > 0 && (
                  <p className="text-xs text-muted-foreground mt-0.5">vs ~20 min manually</p>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Right: Top Templates */}
      <Card>
        <CardHeader>
          <CardTitle>Top Templates</CardTitle>
          <CardDescription>Most used templates</CardDescription>
        </CardHeader>
        <CardContent>
          {top_templates.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <FileSpreadsheet className="h-10 w-10 text-muted-foreground mb-3" />
              <p className="text-sm text-muted-foreground">No template fills yet</p>
            </div>
          ) : (
            <div className="space-y-4">
              {top_templates.slice(0, 5).map((template, index) => (
                <div key={index} className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium truncate pr-2">{template.template_name}</span>
                    <span className="text-muted-foreground whitespace-nowrap">{template.fill_count}x</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full transition-all"
                      style={{ width: `${(template.fill_count / maxCount) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
