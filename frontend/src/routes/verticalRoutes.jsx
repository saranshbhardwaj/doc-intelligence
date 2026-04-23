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
import { Navigate } from 'react-router-dom';
import {
  DealRoomsPage,
  RoomDashboard,
  RoomDocuments,
  RoomAnalysis,
  RoomInvestigations,
  InvestigationDetail,
} from '../verticals/private_equity/pages';
import {
  REDashboard,
  TemplateFillPage,
  TemplatesPage,
  UnderwritingDashboard,
  UnderwritingWizard,
  UnderwritingResult,
} from '../verticals/real_estate/pages';
import PDFPopoutPage from '../verticals/real_estate/pages/PDFPopoutPage';
import ExcelPopoutPage from '../verticals/real_estate/pages/ExcelPopoutPage';

// Routes for Private Equity vertical
export const peRoutes = [
  { path: '/pe',        element: <Navigate to="/app/pe/rooms" replace /> },
  { path: '/pe/rooms',  element: <DealRoomsPage /> },
  { path: '/pe/rooms/:roomId', element: <Navigate to="dashboard" replace /> },
  { path: '/pe/rooms/:roomId/dashboard',      element: <RoomDashboard /> },
  { path: '/pe/rooms/:roomId/documents',      element: <RoomDocuments /> },
  { path: '/pe/rooms/:roomId/analysis',       element: <RoomAnalysis /> },
  { path: '/pe/rooms/:roomId/investigations', element: <RoomInvestigations /> },
  { path: '/pe/rooms/:roomId/investigations/:invId', element: <InvestigationDetail /> },
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
  {
    path: '/re/underwriting',
    element: <UnderwritingDashboard />,
  },
  {
    path: '/re/underwriting/new',
    element: <UnderwritingWizard />,
  },
  {
    path: '/re/underwriting/:runId',
    element: <UnderwritingResult />,
  },
];

export const verticalRoutes = [...peRoutes, ...reRoutes];
