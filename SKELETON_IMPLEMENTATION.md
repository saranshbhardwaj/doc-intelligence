# Skeleton Loaders Implementation — 7 Pages

## Overview
Created a comprehensive skeleton system for all 7 pages using shadcn `<Skeleton>` components. No new dependencies added. All skeletons mirror the actual page structure for visual accuracy during loading states.

## Architecture

### Single Source: `PageSkeletons.jsx`
**Location:** `frontend/src/components/skeletons/PageSkeletons.jsx`

Contains 10 skeleton components (9 for pages + 1 alias), each matching its page structure:
- `DashboardOverviewSkeleton` — Header + stat cards (4 col) + activity chart + sidebar + insights + usage stats
- `UploadPageSkeleton` — Navigation + upload area + demo/results section
- `UnderwritingWizardSkeleton` — 3-panel layout (left nav + center form + right source)
- `UnderwritingDashboardSkeleton` — Header + quick actions + info cards
- `UnderwritingResultSkeleton` — Header + metrics grid + operating benchmarks + returns sections
- `LibraryPageSkeleton` — Sidebar + stats + documents table
- `ChatPageSkeleton` — Sidebar + chat area + messages
- `REHomePageSkeleton` — Alias for UnderwritingDashboardSkeleton
- `TemplateFillRunPageSkeleton` — Split layout: PDF viewer + tabs (Fields/Excel)
- `TemplatesPageSkeleton` — Tabs + search + table with pagination

## Pages Updated

### 1. **DashboardOverview** (`frontend/src/components/dashboard/DashboardOverview.jsx`)
```jsx
// Import added
import { DashboardOverviewSkeleton } from '../skeletons/PageSkeletons';

// Loading check added at start of return (before main JSX)
if (anyLoading) {
  return <DashboardOverviewSkeleton />;
}
```
**Trigger:** Shows skeleton when `anyLoading` is true (any of 3 React Query queries loading)
**Structure:** Stat cards (4 col) + activity chart (3 col) + sidebar (1 col) + template fill insights + usage stats

---

### 2. **UploadPage** (`frontend/src/pages/UploadPage.jsx`)
```jsx
// Import added
import { UploadPageSkeleton } from '../components/skeletons/PageSkeletons';

// State added
const [isInitializing, setIsInitializing] = useState(true);

// useEffect to mark initialization complete
useEffect(() => {
  setIsInitializing(false);
}, []);

// Loading check added
if (isInitializing) {
  return <UploadPageSkeleton />;
}
```
**Trigger:** Shows skeleton during initial page load (`isInitializing`)
**Structure:** Navigation + upload area + demo/results section

---

### 3. **UnderwritingWizard** (`frontend/src/verticals/real_estate/pages/UnderwritingWizard.jsx`)
```jsx
// Import added
import { UnderwritingWizardSkeleton } from '../../../components/skeletons/PageSkeletons';

// Loading check added (after line 1242)
if (runIdFromUrl && !currentRun) {
  return (
    <AppLayout lockViewport>
      <div className="h-full">
        <UnderwritingWizardSkeleton />
      </div>
    </AppLayout>
  );
}
```
**Trigger:** Shows skeleton when URL has `run_id` but `currentRun` not yet loaded

---

### 4. **UnderwritingResult** (`frontend/src/verticals/real_estate/pages/UnderwritingResult.jsx`)
```jsx
// Import added
import { UnderwritingResultSkeleton } from '../../../components/skeletons/PageSkeletons';

// Skeleton replaced inline skeleton (line ~767)
if (!currentRun) {
  return (
    <AppLayout>
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
        <UnderwritingResultSkeleton />
      </div>
    </AppLayout>
  );
}
```
**Trigger:** Shows skeleton when `currentRun` is null/undefined

---

### 5. **UnderwritingDashboard (RE Home)** (`frontend/src/verticals/real_estate/pages/Dashboard.jsx`)
```jsx
// Imports added
import { useEffect, useState } from 'react';
import { REHomePageSkeleton } from '../../../components/skeletons/PageSkeletons';

// Loading state added
const [isLoading, setIsLoading] = useState(true);

useEffect(() => {
  if (config) {
    setIsLoading(false);
  }
}, [config]);

// Loading check added
if (isLoading) {
  return (
    <AppLayout suppressPageHeader>
      <REHomePageSkeleton />
    </AppLayout>
  );
}
```
**Trigger:** Shows skeleton while `config` is loading

---

### 6. **LibraryPage** (`frontend/src/pages/LibraryPage.jsx`)
```jsx
// Import added
import { LibraryPageSkeleton } from '../components/skeletons/PageSkeletons';

// Loading check added (line ~516)
if (loadingCollections) {
  return (
    <AppLayout lockViewport pageHeader={pageHeader}>
      <LibraryPageSkeleton />
    </AppLayout>
  );
}
```
**Trigger:** Shows skeleton when `loadingCollections` is true

---

### 7. **ChatPage** (`frontend/src/pages/ChatPage.jsx`)
```jsx
// Import added
import { ChatPageSkeleton } from '../components/skeletons/PageSkeletons';

// Loading check added (line ~200)
if (isInitializing) {
  return (
    <AppLayout lockViewport suppressPageHeader>
      <ChatPageSkeleton />
    </AppLayout>
  );
}
```
**Trigger:** Shows skeleton during initial data fetch (`isInitializing`)

---

### 8. **TemplateFillRunPage** (`frontend/src/verticals/real_estate/pages/TemplateFillPage.jsx`)
```jsx
// Import added
import { TemplateFillRunPageSkeleton } from '../../../components/skeletons/PageSkeletons';

// Skeleton replaces error state (line ~567)
if (!fillRun) {
  return (
    <AppLayout>
      <div className="h-full">
        <TemplateFillRunPageSkeleton />
      </div>
    </AppLayout>
  );
}
```
**Trigger:** Shows skeleton when `fillRun` is null

---

### 9. **TemplatesPage** (`frontend/src/verticals/real_estate/pages/TemplatesPage.jsx`)
```jsx
// Import added
import { TemplatesPageSkeleton } from '../../../components/skeletons/PageSkeletons';

// Loading check added (line ~367)
if (loading) {
  return (
    <AppLayout headerLeft={breadcrumb} headerRight={uploadButton}>
      <TemplatesPageSkeleton />
    </AppLayout>
  );
}
```
**Trigger:** Shows skeleton when `loading` is true

---

## Design Principles

1. **Structure Mirroring** — Each skeleton uses the exact grid, gaps, and layout of its page
2. **No Extra Dependencies** — Uses only shadcn `<Skeleton>` component (already in project)
3. **Minimal Overhead** — Simple arrays and ternary rendering, no utility classes needed
4. **Maintainability** — Skeleton code lives in one place; changes auto-reflect in the page
5. **Visual Accuracy** — Skeleton heights/widths match real content placeholders

## Skeleton Component Specifications

### Sizing

| Component | Key Heights |
|-----------|-----------|
| Header title | `h-10 w-72` |
| Subtitle | `h-5 w-96` |
| Metric cards (4 col) | `h-32 rounded-3xl` |
| Metric cards (5 col) | `h-24 rounded-3xl` |
| Chart/panel | `h-80 rounded-3xl` |
| Form field | `h-10 w-full rounded-lg` |
| Form label | `h-4 w-32` |
| Table row | `h-4 flex-1` |

### Grid Layouts

- **Metric cards (4 col):** `grid-cols-2 xl:grid-cols-4`
- **Metric cards (5 col):** `grid-cols-2 xl:grid-cols-5`
- **Returns section:** `grid-cols-[1.7fr,1fr]`
- **Info cards:** `grid-cols-1 lg:grid-cols-2`
- **Quick actions:** `grid-cols-1 md:grid-cols-2 lg:grid-cols-3`

## Testing Checklist

- [x] No import errors (build passes)
- [x] All 9 pages have loading skeleton guards
- [x] Skeletons mirror actual page structure
- [x] No extra dependencies added
- [x] Single source of truth for all skeletons

## Future Enhancements

1. **Animation duration customization** — Currently uses shadcn defaults; could expose via `PageSkeletons` props
2. **Theme variants** — Could create light/dark skeleton color variants if needed
3. **Performance monitoring** — Track actual load times for each page to optimize skeleton timing
4. **A/B testing** — Test skeleton impact on perceived performance vs. blank screen

## File Metrics

- **New files:** 1 (`PageSkeletons.jsx` — ~550 lines, includes all 10 skeletons)
- **Modified files:** 9 (one import + one loading check per page)
- **Total lines added:** ~80 lines of logic across all pages
- **Bundle impact:** Negligible (only text/JSX, no new dependencies)
