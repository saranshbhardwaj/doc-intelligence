/**
 * Page-specific skeleton loaders
 * Each component mirrors the actual page structure for consistent loading states
 */

import { Skeleton } from '@/components/ui/skeleton';

/**
 * UnderwritingWizard Skeleton
 * 3-panel layout: left nav + center form + right source panel
 */
export function UnderwritingWizardSkeleton() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr_350px] gap-0 h-full">
      {/* Left Panel: Navigation */}
      <div className="border-r border-border p-4 space-y-3 bg-muted/20">
        <Skeleton className="h-10 w-32" />
        <div className="space-y-2 pt-4">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-8 w-full rounded-lg" />
          ))}
        </div>
      </div>

      {/* Center Panel: Form */}
      <div className="p-6 space-y-6 overflow-auto">
        <div className="space-y-3">
          <Skeleton className="h-6 w-48" />
          <Skeleton className="h-4 w-72" />
        </div>

        {/* Form fields */}
        <div className="space-y-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-10 w-full rounded-lg" />
            </div>
          ))}
        </div>

        {/* Action buttons */}
        <div className="flex gap-3 pt-4">
          <Skeleton className="h-10 w-24 rounded-lg" />
          <Skeleton className="h-10 w-24 rounded-lg" />
        </div>
      </div>

      {/* Right Panel: Source Document */}
      <div className="border-l border-border p-4 space-y-4 bg-muted/10">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-64 w-full rounded-lg" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
      </div>
    </div>
  );
}

/**
 * UnderwritingDashboard Skeleton
 * Header + quick action cards + info cards
 */
export function UnderwritingDashboardSkeleton() {
  return (
    <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
      {/* Header */}
      <div className="space-y-3">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96" />
      </div>

      {/* Quick Action Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="p-6 border border-border rounded-lg space-y-3">
            <div className="flex items-center gap-4">
              <Skeleton className="h-12 w-12 rounded-lg" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-3 w-32" />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Info Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {[...Array(2)].map((_, i) => (
          <div key={i} className="border border-border rounded-lg p-6 space-y-3">
            <Skeleton className="h-5 w-48" />
            <div className="space-y-2">
              {[...Array(3)].map((_, j) => (
                <div key={j} className="flex gap-2">
                  <Skeleton className="h-4 w-4 flex-shrink-0 rounded" />
                  <Skeleton className="h-4 flex-1" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * UnderwritingResult Skeleton
 * Header + key returns metrics + operating benchmarks + returns section
 */
export function UnderwritingResultSkeleton() {
  return (
    <div className="underwriting-shell page-enter p-5 sm:p-6 space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-5 w-96" />
      </div>

      {/* Key Returns Section */}
      <div className="mt-5">
        <Skeleton className="h-5 w-32 mb-3" />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-32 rounded-3xl" />
          ))}
        </div>
      </div>

      {/* Operating Benchmarks Section */}
      <div className="mt-4">
        <Skeleton className="h-5 w-40 mb-3" />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-3xl" />
          ))}
        </div>
      </div>

      {/* Returns & Capital Structure Section */}
      <div className="mt-6">
        <Skeleton className="h-5 w-48 mb-3" />
        <div className="grid gap-4 xl:grid-cols-[1.7fr,1fr]">
          <Skeleton className="h-80 rounded-3xl" />
          <Skeleton className="h-80 rounded-3xl" />
        </div>
      </div>

      {/* Operations Section */}
      <div className="mt-6">
        <Skeleton className="h-5 w-32 mb-3" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-64 rounded-lg" />
          <Skeleton className="h-64 rounded-lg" />
        </div>
      </div>
    </div>
  );
}

/**
 * LibraryPage Skeleton
 * Header + stats + sidebar + documents table
 */
export function LibraryPageSkeleton() {
  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="border-b border-border p-4 space-y-3">
        <Skeleton className="h-6 w-40" />
        <div className="flex gap-2">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-4 w-20" />
          ))}
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex gap-4 p-4">
        {/* Sidebar */}
        <div className="w-64 border-r border-border space-y-3 pr-4">
          <Skeleton className="h-10 w-full rounded-lg" />
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-8 w-full rounded-lg" />
            ))}
          </div>
        </div>

        {/* Documents Table */}
        <div className="flex-1 space-y-4">
          {/* Table header */}
          <div className="flex gap-4 pb-3 border-b border-border">
            {[...Array(4)].map((_, i) => (
              <Skeleton key={i} className="h-4 flex-1" />
            ))}
          </div>

          {/* Table rows */}
          {[...Array(8)].map((_, i) => (
            <div key={i} className="flex gap-4 py-3 border-b border-border/50">
              {[...Array(4)].map((_, j) => (
                <Skeleton key={j} className="h-4 flex-1" />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * ChatPage Skeleton
 * Sidebar + chat area with messages
 */
export function ChatPageSkeleton() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-0 h-full">
      {/* Sidebar */}
      <div className="border-r border-border p-4 space-y-4 bg-muted/10">
        <Skeleton className="h-10 w-full rounded-lg" />
        <Skeleton className="h-4 w-32" />
        <div className="space-y-2">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-10 w-full rounded-lg" />
          ))}
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex flex-col">
        {/* Chat header */}
        <div className="border-b border-border p-4 flex justify-between items-center">
          <div className="space-y-2 flex-1">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-3 w-64" />
          </div>
          <Skeleton className="h-8 w-8 rounded-lg" />
        </div>

        {/* Messages area */}
        <div className="flex-1 p-4 space-y-4 overflow-auto">
          {[...Array(5)].map((_, i) => (
            <div key={i} className={`flex ${i % 2 === 0 ? 'justify-start' : 'justify-end'}`}>
              <Skeleton className={`h-10 ${i % 2 === 0 ? 'w-48' : 'w-40'} rounded-lg`} />
            </div>
          ))}
        </div>

        {/* Input area */}
        <div className="border-t border-border p-4 space-y-2">
          <Skeleton className="h-10 w-full rounded-lg" />
          <Skeleton className="h-8 w-24 rounded-lg" />
        </div>
      </div>
    </div>
  );
}

/**
 * REHomePage Skeleton
 * Same as UnderwritingDashboard
 */
export function REHomePageSkeleton() {
  return <UnderwritingDashboardSkeleton />;
}

/**
 * TemplateFillRunPage Skeleton
 * Split layout: PDF viewer + tabs (Fields/Excel)
 */
export function TemplateFillRunPageSkeleton() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 h-full p-4">
      {/* PDF Viewer Section */}
      <div className="border border-border rounded-lg p-4 space-y-3 overflow-hidden flex flex-col">
        <div className="flex items-center justify-between">
          <Skeleton className="h-5 w-32" />
          <div className="flex gap-2">
            <Skeleton className="h-8 w-8 rounded" />
            <Skeleton className="h-8 w-8 rounded" />
          </div>
        </div>
        <Skeleton className="flex-1 w-full rounded-lg" />
      </div>

      {/* Right Section: Tabs + Content */}
      <div className="border border-border rounded-lg overflow-hidden flex flex-col">
        {/* Tab headers */}
        <div className="flex border-b border-border">
          {[...Array(2)].map((_, i) => (
            <Skeleton key={i} className="h-10 w-24 rounded-none border-r border-border last:border-r-0" />
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 p-4 space-y-3 overflow-auto">
          {/* Status badge */}
          <Skeleton className="h-6 w-32 rounded-full" />

          {/* Fields list or Excel grid */}
          <div className="space-y-3">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="space-y-2 p-3 border border-border/50 rounded-lg">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-8 w-full rounded" />
              </div>
            ))}
          </div>
        </div>

        {/* Footer buttons */}
        <div className="border-t border-border p-4 flex gap-2">
          <Skeleton className="h-10 w-24 rounded-lg" />
          <Skeleton className="h-10 w-24 rounded-lg" />
        </div>
      </div>
    </div>
  );
}

/**
 * TemplatesPage Skeleton
 * Tabs + table or list view
 */
export function TemplatesPageSkeleton() {
  return (
    <div className="max-w-7xl mx-auto space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-64" />
        </div>
        <Skeleton className="h-10 w-32 rounded-lg" />
      </div>

      {/* Tabs */}
      <div className="flex gap-4 border-b border-border">
        {[...Array(2)].map((_, i) => (
          <Skeleton key={i} className="h-10 w-32 rounded-none border-b-2 border-transparent" />
        ))}
      </div>

      {/* Search + Filter */}
      <div className="flex gap-3">
        <Skeleton className="h-10 flex-1 rounded-lg" />
        <Skeleton className="h-10 w-32 rounded-lg" />
      </div>

      {/* Table */}
      <div className="border border-border rounded-lg overflow-hidden">
        {/* Table header */}
        <div className="flex gap-4 p-4 bg-muted/50 border-b border-border">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-4 flex-1" />
          ))}
        </div>

        {/* Table rows */}
        {[...Array(8)].map((_, i) => (
          <div key={i} className="flex gap-4 p-4 border-b border-border/50 last:border-b-0">
            {[...Array(4)].map((_, j) => (
              <Skeleton key={j} className="h-4 flex-1" />
            ))}
          </div>
        ))}
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between pt-4">
        <Skeleton className="h-4 w-32" />
        <div className="flex gap-2">
          <Skeleton className="h-10 w-10 rounded-lg" />
          <Skeleton className="h-10 w-10 rounded-lg" />
        </div>
      </div>
    </div>
  );
}

/**
 * DashboardOverview Skeleton
 * Header + stat cards (4 col) + activity chart + sidebar
 */
export function DashboardOverviewSkeleton() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 sm:py-8 space-y-5 sm:space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2 flex-1">
          <Skeleton className="h-8 w-40" />
          <Skeleton className="h-4 w-64" />
          <Skeleton className="h-3 w-96 mt-2" />
        </div>
        <div className="flex gap-2">
          <Skeleton className="h-10 w-12 rounded-lg" />
          <Skeleton className="h-10 w-12 rounded-lg" />
          <Skeleton className="h-10 w-12 rounded-lg" />
        </div>
      </div>

      {/* Stat Cards (4 columns) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="border border-border rounded-2xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <Skeleton className="h-8 w-8 rounded-lg" />
              <Skeleton className="h-4 w-16" />
            </div>
            <div className="space-y-2">
              <Skeleton className="h-6 w-20" />
              <Skeleton className="h-3 w-32" />
            </div>
          </div>
        ))}
      </div>

      {/* Activity Chart + Sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Chart (3 cols) */}
        <div className="lg:col-span-3 border border-border rounded-2xl p-6 space-y-3">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-64 w-full rounded-lg" />
        </div>

        {/* Sidebar (1 col) */}
        <div className="space-y-4">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="border border-border rounded-2xl p-4 space-y-3">
              <div className="flex items-center gap-2">
                <Skeleton className="h-4 w-4 rounded" />
                <Skeleton className="h-5 w-24" />
              </div>
              <div className="space-y-2">
                {[...Array(3)].map((_, j) => (
                  <Skeleton key={j} className="h-4 w-full" />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Template Fill Insights (if RE enabled) */}
      <div className="border border-border rounded-2xl p-6 space-y-3">
        <Skeleton className="h-5 w-48" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-lg" />
          ))}
        </div>
      </div>

      {/* Usage Stats */}
      <div className="border border-border rounded-2xl p-6 space-y-3">
        <Skeleton className="h-5 w-40" />
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-2 w-full rounded-full" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * UploadPage Skeleton
 * Navigation bar + upload area + results section
 */
export function UploadPageSkeleton() {
  return (
    <div className="min-h-screen bg-background">
      {/* Navigation Bar */}
      <nav className="sticky top-0 z-50 bg-background/80 backdrop-blur-lg border-b border-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Skeleton className="h-8 w-32" />
            <div className="flex gap-4">
              <Skeleton className="h-10 w-20 rounded-lg" />
              <Skeleton className="h-10 w-20 rounded-lg" />
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-16 space-y-12">
        {/* Header */}
        <div className="text-center space-y-3">
          <Skeleton className="h-10 w-64 mx-auto" />
          <Skeleton className="h-4 w-96 mx-auto" />
        </div>

        {/* Upload Area */}
        <div className="border-2 border-dashed border-border rounded-2xl p-12 space-y-4 text-center">
          <Skeleton className="h-12 w-12 rounded-lg mx-auto" />
          <div className="space-y-2">
            <Skeleton className="h-5 w-48 mx-auto" />
            <Skeleton className="h-4 w-64 mx-auto" />
          </div>
          <Skeleton className="h-10 w-40 rounded-lg mx-auto" />
        </div>

        {/* Demo or Results Section */}
        <div className="border border-border rounded-2xl p-6 space-y-4">
          <Skeleton className="h-6 w-40" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="space-y-2 p-4 border border-border/50 rounded-lg">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-8 w-full" />
              </div>
            ))}
          </div>
        </div>

        {/* Results Preview */}
        <div className="border border-border rounded-2xl p-6 space-y-4">
          <Skeleton className="h-6 w-48" />
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="space-y-2">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-10 w-full rounded-lg" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
