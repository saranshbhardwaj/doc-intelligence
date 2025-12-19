/**
 * Vertical Routes
 *
 * Architecture:
 * - Vertical dashboards (/pe, /re) are OVERVIEW pages that show vertical-filtered data
 * - They link to existing main routes (/app/library, /app/chat, /app/workflows, etc.)
 * - Only vertical-specific features get dedicated routes (e.g., /re/templates for Excel)
 *
 * DO NOT duplicate existing functionality - use links to main routes instead.
 */
import { PEDashboard } from '../verticals/private_equity/pages';
import { REDashboard } from '../verticals/real_estate/pages';

// Routes for Private Equity vertical
export const peRoutes = [
  {
    path: '/pe',
    element: <PEDashboard />,
  },
  // Note: PE uses existing main routes for library, chat, workflows, and extractions
  // The PE dashboard links to these with vertical-specific data filtering
];

// Routes for Real Estate vertical
export const reRoutes = [
  {
    path: '/re',
    element: <REDashboard />,
  },
  // TODO: Add RE-specific routes when implemented:
  // {
  //   path: '/re/templates',
  //   element: <RETemplatesPage />,
  // },
  // {
  //   path: '/re/fills',
  //   element: <RETemplateFillsPage />,
  // },
];

export const verticalRoutes = [...peRoutes, ...reRoutes];
