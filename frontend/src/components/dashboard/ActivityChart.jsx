// src/components/dashboard/ActivityChart.jsx
/**
 * Activity over time area chart
 *
 * Shows daily chat messages, template fills, and extractions as stacked areas.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { Skeleton } from "@/components/ui/skeleton";
import { BarChart3 } from "lucide-react";

const chartConfig = {
  chat_messages: {
    label: "Chat Messages",
    color: "hsl(var(--primary))",
  },
  template_fills: {
    label: "Template Fills",
    color: "hsl(var(--chart-2))",
  },
  extractions: {
    label: "Extractions",
    color: "hsl(var(--chart-1))",
  },
  workflow_runs: {
    label: "Workflows",
    color: "hsl(var(--chart-3))",
  },
};

export default function ActivityChart({ data, loading }) {
  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Activity Over Time</CardTitle>
          <CardDescription>Daily activity breakdown</CardDescription>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-[240px] sm:h-[300px] w-full" />
        </CardContent>
      </Card>
    );
  }

  // Empty state
  if (!data || data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Activity Over Time</CardTitle>
          <CardDescription>Daily activity breakdown</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center h-[240px] sm:h-[300px] text-center">
            <BarChart3 className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-sm text-muted-foreground">No activity in this period</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Format date for display (e.g., "Feb 1")
  const formatDate = (dateStr) => {
    const date = new Date(dateStr);
    return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(date);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Activity Over Time</CardTitle>
        <CardDescription>Daily chat messages, template fills, extractions, and workflows</CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className="h-[240px] sm:h-[300px]">
          <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="fillChat" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0.05} />
              </linearGradient>
              <linearGradient id="fillFills" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(var(--chart-2))" stopOpacity={0.3} />
                <stop offset="95%" stopColor="hsl(var(--chart-2))" stopOpacity={0.05} />
              </linearGradient>
              <linearGradient id="fillExtractions" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(var(--chart-1))" stopOpacity={0.3} />
                <stop offset="95%" stopColor="hsl(var(--chart-1))" stopOpacity={0.05} />
              </linearGradient>
              <linearGradient id="fillWorkflows" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(var(--chart-3))" stopOpacity={0.3} />
                <stop offset="95%" stopColor="hsl(var(--chart-3))" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-muted" />
            <XAxis
              dataKey="date"
              tickFormatter={formatDate}
              className="text-[10px] sm:text-xs"
              minTickGap={24}
              interval="preserveStartEnd"
              tickLine={false}
              axisLine={false}
            />
            <YAxis className="text-[10px] sm:text-xs" tickLine={false} axisLine={false} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Area
              type="monotone"
              dataKey="chat_messages"
              stroke="hsl(var(--primary))"
              fill="url(#fillChat)"
              strokeWidth={2.5}
            />
            <Area
              type="monotone"
              dataKey="template_fills"
              stroke="hsl(var(--chart-2))"
              fill="url(#fillFills)"
              strokeWidth={2.5}
            />
            <Area
              type="monotone"
              dataKey="extractions"
              stroke="hsl(var(--chart-1))"
              fill="url(#fillExtractions)"
              strokeWidth={2.5}
            />
            <Area
              type="monotone"
              dataKey="workflow_runs"
              stroke="hsl(var(--chart-3))"
              fill="url(#fillWorkflows)"
              strokeWidth={2.5}
            />
          </AreaChart>
        </ChartContainer>
      </CardContent>
    </Card>
  );
}
