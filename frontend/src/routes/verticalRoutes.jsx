/**
 * Vertical Routes
 * Routes for PE and RE verticals
 * To be integrated into main App routing
 */
import { PEDashboard } from '../verticals/private_equity/pages';
import { REDashboard } from '../verticals/real_estate/pages';

// Routes for Private Equity vertical
export const peRoutes = [
  {
    path: '/pe',
    element: <PEDashboard />,
  },
  {
    path: '/pe/library',
    element: <div>PE Library - To be implemented</div>,
    // element: <DocumentLibrary />,
  },
  {
    path: '/pe/chat',
    element: <div>PE Chat - To be implemented</div>,
    // element: <ChatInterface />,
  },
  {
    path: '/pe/workflows',
    element: <div>PE Workflows - To be implemented</div>,
    // element: <WorkflowsPage />,
  },
  {
    path: '/pe/extraction',
    element: <div>PE Extraction - To be implemented</div>,
    // element: <ExtractionPage />,
  },
  {
    path: '/pe/comparison',
    element: <div>PE Comparison - Coming Soon</div>,
    // element: <ComparisonPage />,
  },
];

// Routes for Real Estate vertical
export const reRoutes = [
  {
    path: '/re',
    element: <REDashboard />,
  },
  {
    path: '/re/library',
    element: <div>RE Library - To be implemented</div>,
    // element: <DocumentLibrary />,
  },
  {
    path: '/re/chat',
    element: <div>RE Chat - To be implemented</div>,
    // element: <ChatInterface />,
  },
  {
    path: '/re/templates',
    element: <div>RE Templates - To be implemented</div>,
    // element: <TemplatesPage />,
  },
  {
    path: '/re/fills',
    element: <div>RE Template Fills - To be implemented</div>,
    // element: <TemplateFillsPage />,
  },
];

export const verticalRoutes = [...peRoutes, ...reRoutes];
