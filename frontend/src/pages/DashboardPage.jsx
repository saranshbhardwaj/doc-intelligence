// src/pages/DashboardPage.jsx
/**
 * Dashboard page - User-facing analytics overview
 *
 * Shows organization-scoped metrics: documents, chat, template fills,
 * extractions, workflows, activity charts, and usage stats.
 */

import AppLayout from "../components/layout/AppLayout";
import DashboardOverview from "../components/dashboard/DashboardOverview";

export default function DashboardPage() {
  return (
    <AppLayout suppressPageHeader>
      <DashboardOverview />
    </AppLayout>
  );
}
