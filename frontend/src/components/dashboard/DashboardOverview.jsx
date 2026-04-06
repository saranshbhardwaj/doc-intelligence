// src/components/dashboard/DashboardOverview.jsx
/**
 * Main dashboard orchestrator component
 *
 * Fetches all dashboard data and renders stat cards, charts, and insights.
 */

import { useState } from "react";
import { useAppAuth } from "@/hooks/useAppAuth";
import { useQuery } from "@tanstack/react-query";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FileText, MessageSquare, FileSpreadsheet, Database, Play, Users, AlertCircle } from "lucide-react";

import { getDashboardOverview, getDashboardActivity, getTemplateFillStats } from "../../api/dashboard";
import StatCard from "./StatCard";
import ActivityChart from "./ActivityChart";
import TemplateFillInsights from "./TemplateFillInsights";
import UsageStats from "./UsageStats";

export default function DashboardOverview() {
  const { getToken } = useAppAuth();
  const [period, setPeriod] = useState(30);

  // Fetch all 3 endpoints in parallel
  const {
    data: overview,
    isLoading: overviewLoading,
    error: overviewError,
    refetch: refetchOverview,
  } = useQuery({
    queryKey: ["dashboard-overview", period],
    queryFn: () => getDashboardOverview(getToken, period),
    staleTime: 60000, // 1 minute
  });

  const {
    data: activity,
    isLoading: activityLoading,
    error: activityError,
  } = useQuery({
    queryKey: ["dashboard-activity", period],
    queryFn: () => getDashboardActivity(getToken, period),
    staleTime: 60000,
  });

  const {
    data: templateStats,
    isLoading: templateStatsLoading,
    error: templateStatsError,
  } = useQuery({
    queryKey: ["dashboard-template-stats", period],
    queryFn: () => getTemplateFillStats(getToken, period),
    staleTime: 60000,
  });

  // We'll fetch user info separately for the UsageStats component
  // (UsageStats already handles its own data fetching)
  const {
    data: userInfo,
    isLoading: userInfoLoading,
  } = useQuery({
    queryKey: ["user-info"],
    queryFn: async () => {
      const { getUserInfo } = await import("../../api/users");
      return getUserInfo(getToken);
    },
    staleTime: 300000, // 5 minutes
  });

  const anyError = overviewError || activityError || templateStatsError;
  const anyLoading = overviewLoading || activityLoading || templateStatsLoading;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 sm:py-8 space-y-5 sm:space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="page-title text-2xl sm:text-3xl">Overview</h1>
          <p className="page-subtitle mt-1">Your organization's activity overview</p>
          {!anyLoading && overview && (overview.documents.pages_analyzed > 0 || overview.template_fills.total_fields_populated > 0) && (
            <p className="text-sm text-primary font-medium mt-1">
              {overview.documents.pages_analyzed > 0 && `${overview.documents.pages_analyzed} pages analyzed`}
              {overview.documents.pages_analyzed > 0 && overview.template_fills.total_fields_populated > 0 && " · "}
              {overview.template_fills.total_fields_populated > 0 && `${overview.template_fills.total_fields_populated} fields auto-filled`}
              {" this period"}
            </p>
          )}
        </div>

        {/* Period Selector */}
        <Tabs value={String(period)} onValueChange={(val) => setPeriod(Number(val))} className="w-full sm:w-auto">
          <TabsList className="grid w-full grid-cols-3 sm:w-auto">
            <TabsTrigger value="7">7d</TabsTrigger>
            <TabsTrigger value="30">30d</TabsTrigger>
            <TabsTrigger value="90">90d</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Error State */}
      {anyError && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <span>Failed to load dashboard data. Please try again.</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                refetchOverview();
              }}
            >
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Stat Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={FileText}
          title="Documents"
          value={overview?.documents?.total || 0}
          subtitle={overview?.documents?.pages_analyzed > 0
            ? `${overview.documents.pages_analyzed} pages analyzed`
            : `+${overview?.documents?.period || 0} this period`}
          loading={anyLoading}
          iconBg="bg-primary/10"
          iconColor="text-primary"
        />
        <StatCard
          icon={MessageSquare}
          title="Chat Messages"
          value={overview?.chat?.messages || 0}
          subtitle={`${overview?.chat?.sessions || 0} sessions`}
          loading={anyLoading}
          iconBg="bg-blue-50 dark:bg-blue-900/20"
          iconColor="text-blue-500"
        />
        <StatCard
          icon={FileSpreadsheet}
          title="Template Fills"
          value={overview?.template_fills?.total || 0}
          subtitle={overview?.template_fills?.total_fields_populated > 0
            ? `${overview.template_fills.total_fields_populated} fields auto-filled`
            : `${overview?.template_fills?.completed || 0}/${overview?.template_fills?.total || 0} completed`}
          loading={anyLoading}
          iconBg="bg-purple-50 dark:bg-purple-900/20"
          iconColor="text-purple-500"
        />
        <StatCard
          icon={Database}
          title="Extractions"
          value={overview?.extractions?.total || 0}
          subtitle={`${overview?.extractions?.completed || 0} completed`}
          loading={anyLoading}
          iconBg="bg-orange-50 dark:bg-orange-900/20"
          iconColor="text-orange-500"
        />
      </div>

      {/* Activity Chart + Workflow/Users Sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Activity Chart (3 cols) */}
        <div className="lg:col-span-3">
          <ActivityChart data={activity?.daily} loading={activityLoading} />
        </div>

        {/* Workflows & Active Users Sidebar (1 col) */}
        <div className="space-y-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1">
          <Card className="rounded-2xl glass-card border-0">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Play className="h-4 w-4 text-muted-foreground" />
                Workflows
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {anyLoading ? (
                <div className="text-sm text-muted-foreground">Loading...</div>
              ) : (
                <>
                  <div className="flex items-end gap-1">
                    <span className="text-3xl font-bold">{overview?.workflows?.total || 0}</span>
                    <span className="text-sm text-muted-foreground mb-1">total</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Completed</span>
                    <span className="font-medium text-green-600 dark:text-green-400">
                      {overview?.workflows?.completed || 0}
                    </span>
                  </div>
                  {(overview?.workflows?.failed || 0) > 0 && (
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Failed</span>
                      <span className="font-medium text-destructive">
                        {overview?.workflows?.failed}
                      </span>
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          <Card className="rounded-2xl glass-card border-0">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Users className="h-4 w-4 text-muted-foreground" />
                  Active Users
                </CardTitle>
                <span className="bg-primary/10 text-primary text-xs font-bold px-2 py-0.5 rounded border border-primary/20">
                  Period
                </span>
              </div>
            </CardHeader>
            <CardContent>
              {anyLoading ? (
                <div className="text-sm text-muted-foreground">Loading...</div>
              ) : (
                <>
                  <div className="flex items-end gap-1">
                    <span className="text-3xl font-bold">{overview?.active_users || 0}</span>
                    <span className="text-sm text-muted-foreground mb-1">users</span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">Active in this period</p>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Template Fill Insights */}
      <TemplateFillInsights stats={templateStats} loading={templateStatsLoading} />

      {/* Usage Stats (existing component) */}
      {userInfo && !userInfoLoading && <UsageStats userInfo={userInfo} />}
    </div>
  );
}
