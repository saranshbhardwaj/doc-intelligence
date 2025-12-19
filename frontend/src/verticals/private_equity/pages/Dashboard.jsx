/**
 * Private Equity Dashboard
 * Main entry point for PE vertical
 */
import { useEffect, useState } from 'react';
import { useAuth } from '@clerk/clerk-react';
import { Link } from 'react-router-dom';
import { useVertical } from '../../../core/hooks/useVertical';
import { peWorkflows, peExtraction } from '../../../api';
import AppLayout from '../../../components/layout/AppLayout';

export default function PEDashboard() {
  const { config } = useVertical();
  const { getToken } = useAuth();
  const [templates, setTemplates] = useState([]);
  const [recentRuns, setRecentRuns] = useState([]);
  const [recentExtractions, setRecentExtractions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchDashboardData() {
      try {
        setLoading(true);

        // Fetch workflow templates
        const templatesData = await peWorkflows.listPETemplates(getToken);
        setTemplates(templatesData || []);

        // Fetch recent workflow runs
        const runsData = await peWorkflows.listPERuns(getToken, { limit: 5 });
        setRecentRuns(runsData || []);

        // Fetch recent extractions
        const extractionsData = await peExtraction.listPEExtractions(getToken, { limit: 5 });
        setRecentExtractions(extractionsData?.items || []);
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
      } finally {
        setLoading(false);
      }
    }

    fetchDashboardData();
  }, [getToken]);

  return (
    <AppLayout>
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-semibold text-foreground">
            {config?.name} Dashboard
          </h1>
          <p className="text-muted-foreground mt-2">
            {config?.description}
          </p>
        </div>

        {loading ? (
          <div className="flex flex-col items-center justify-center py-16">
            <div className="animate-spin rounded-full h-10 w-10 border-2 border-primary border-t-transparent"></div>
            <p className="text-muted-foreground mt-4 text-sm">Loading dashboard...</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Workflow Templates */}
            <div className="bg-card rounded-lg border border-border p-6">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-lg font-semibold text-foreground">
                  Available Workflows
                </h2>
                <Link
                  to="/app/workflows"
                  className="text-sm text-primary hover:text-primary/80 transition-colors"
                >
                  View all →
                </Link>
              </div>
              <div className="space-y-3">
                {templates.length === 0 ? (
                  <p className="text-muted-foreground text-sm">
                    No workflow templates available
                  </p>
                ) : (
                  templates.slice(0, 3).map((template) => (
                    <Link
                      key={template.id}
                      to={`/app/workflows?template=${template.id}`}
                      className="block p-4 rounded-lg border border-border hover:border-primary/50 hover:bg-accent/5 transition-all"
                    >
                      <h3 className="font-medium text-foreground">
                        {template.name}
                      </h3>
                      <p className="text-sm text-muted-foreground mt-1.5 line-clamp-2">
                        {template.description}
                      </p>
                      <div className="flex items-center gap-2 mt-3 text-xs text-muted-foreground">
                        <span className="px-2.5 py-1 bg-muted rounded-md">
                          {template.category}
                        </span>
                        <span>
                          {template.min_documents}
                          {template.max_documents && `-${template.max_documents}`} docs
                        </span>
                      </div>
                    </Link>
                  ))
                )}
                {templates.length > 3 && (
                  <Link
                    to="/app/workflows"
                    className="block text-center py-3 text-sm text-primary hover:text-primary/80 transition-colors"
                  >
                    +{templates.length - 3} more workflows
                  </Link>
                )}
              </div>
            </div>

            {/* Recent Workflow Runs */}
            <div className="bg-card rounded-lg border border-border p-6">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-lg font-semibold text-foreground">
                  Recent Workflow Runs
                </h2>
                <Link
                  to="/app/workflows/history"
                  className="text-sm text-primary hover:text-primary/80 transition-colors"
                >
                  View all →
                </Link>
              </div>
              <div className="space-y-3">
                {recentRuns.length === 0 ? (
                  <p className="text-muted-foreground text-sm">
                    No workflow runs yet
                  </p>
                ) : (
                  recentRuns.map((run) => (
                    <Link
                      key={run.id}
                      to={`/app/workflows/runs/${run.id}`}
                      className="block p-4 rounded-lg border border-border hover:border-primary/50 hover:bg-accent/5 transition-all"
                    >
                      <div className="flex items-center justify-between">
                        <h3 className="font-medium text-foreground">
                          {run.workflow_name}
                        </h3>
                        <span
                          className={`text-xs px-2.5 py-1 rounded-md ${
                            run.status === 'completed'
                              ? 'bg-success/10 text-success-foreground'
                              : run.status === 'failed'
                              ? 'bg-destructive/10 text-destructive-foreground'
                              : 'bg-warning/10 text-warning-foreground'
                          }`}
                        >
                          {run.status}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground mt-1.5">
                        {new Date(run.created_at).toLocaleDateString()}
                      </p>
                    </Link>
                  ))
                )}
              </div>
            </div>

            {/* Recent Extractions */}
            <div className="bg-card rounded-lg border border-border p-6 lg:col-span-2">
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-lg font-semibold text-foreground">
                  Recent Extractions
                </h2>
                <Link
                  to="/app/extractions"
                  className="text-sm text-primary hover:text-primary/80 transition-colors"
                >
                  View all →
                </Link>
              </div>
              <div className="space-y-3">
                {recentExtractions.length === 0 ? (
                  <p className="text-muted-foreground text-sm">
                    No extractions yet
                  </p>
                ) : (
                  recentExtractions.map((extraction) => (
                    <Link
                      key={extraction.id}
                      to={`/app/extractions/${extraction.id}`}
                      className="block p-4 rounded-lg border border-border hover:border-primary/50 hover:bg-accent/5 transition-all"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex-1 min-w-0 mr-4">
                          <h3 className="font-medium text-foreground truncate">
                            {extraction.filename}
                          </h3>
                          <p className="text-xs text-muted-foreground mt-1.5">
                            {extraction.page_count} pages • {new Date(extraction.created_at).toLocaleDateString()}
                          </p>
                        </div>
                        <span
                          className={`text-xs px-2.5 py-1 rounded-md whitespace-nowrap ${
                            extraction.status === 'completed'
                              ? 'bg-success/10 text-success-foreground'
                              : extraction.status === 'failed'
                              ? 'bg-destructive/10 text-destructive-foreground'
                              : 'bg-warning/10 text-warning-foreground'
                          }`}
                        >
                          {extraction.status}
                        </span>
                      </div>
                    </Link>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  );
}
