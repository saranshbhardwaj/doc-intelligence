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
import { REDashboard, TemplateFillPage, TemplatesPage } from '../verticals/real_estate/pages';
import PDFPopoutPage from '../verticals/real_estate/pages/PDFPopoutPage';
import ExcelPopoutPage from '../verticals/real_estate/pages/ExcelPopoutPage';

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
  {
    path: '/re/templates',
    element: <TemplatesPage />,
  },
  {
    path: '/re/fills/:fillRunId',
    element: <TemplateFillPage />,
  },
  {
    path: '/re/fills/:fillRunId/pdf-popout',
    element: <PDFPopoutPage />,
  },
  {
    path: '/re/fills/:fillRunId/excel-popout',
    element: <ExcelPopoutPage />,
  },
];

export const verticalRoutes = [...peRoutes, ...reRoutes];
