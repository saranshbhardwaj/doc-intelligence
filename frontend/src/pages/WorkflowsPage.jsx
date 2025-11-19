/**
 * Workflows History Page
 *
 * Displays all workflow runs for the user (accessed via "View All" from main workflows page)
 */

import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import {
  ArrowLeft,
  FileText,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  DollarSign,
  Trash2,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import Spinner from "../components/common/Spinner";
import AppLayout from "../components/layout/AppLayout";
import { listRuns, deleteRun } from "../api";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../components/ui/alert-dialog";

export default function WorkflowsPage() {
  const navigate = useNavigate();
  const { getToken } = useAuth();

  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [runToDelete, setRunToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const runsData = await listRuns(getToken);
      setRuns(runsData || []);
    } catch (error) {
      console.error("Failed to fetch workflow runs:", error);
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const getStatusBadge = (status) => {
    const variants = {
      completed: {
        icon: CheckCircle,
        color:
          "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
      },
      failed: {
        icon: XCircle,
        color: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
      },
      running: {
        icon: Clock,
        color: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
      },
      queued: {
        icon: AlertCircle,
        color:
          "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
      },
    };
    const variant = variants[status] || variants.queued;
    const Icon = variant.icon;

    return (
      <span
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${variant.color}`}
      >
        <Icon className="w-3.5 h-3.5" />
        {status}
      </span>
    );
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  };

  const handleDeleteClick = (run, e) => {
    e.stopPropagation(); // Prevent card click
    setRunToDelete(run);
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!runToDelete) return;

    setDeleting(true);
    try {
      await deleteRun(getToken, runToDelete.id);
      // Refresh the runs list
      await fetchData();
      setDeleteDialogOpen(false);
      setRunToDelete(null);
    } catch (error) {
      console.error("Failed to delete run:", error);
      alert(
        "Failed to delete workflow run: " +
          (error.response?.data?.detail || error.message)
      );
    } finally {
      setDeleting(false);
    }
  };

  const breadcrumbs = [
    { label: "Workflows", href: "/app/workflows" },
    { label: "All Runs" },
  ];

  return (
    <AppLayout breadcrumbs={breadcrumbs}>
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Back Button */}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate("/app/workflows")}
          className="mb-4"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Workflows
        </Button>

        {/* Page Header */}
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-foreground">
            All Workflow Runs
          </h1>
          <p className="mt-2 text-muted-foreground dark:text-gray-300">
            View all your workflow run history
          </p>
        </div>

        {/* Content */}
        {loading ? (
          <div className="flex justify-center py-12">
            <Spinner size="lg" />
          </div>
        ) : runs.length === 0 ? (
          <Card className="p-12 text-center">
            <FileText className="w-16 h-16 text-gray-300 dark:text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground dark:text-muted-foreground mb-4">
              No workflow runs yet
            </p>
            <Button onClick={() => navigate("/app/workflows")}>
              Start Your First Workflow
            </Button>
          </Card>
        ) : (
          /* Runs List */
          <div className="space-y-4">
            {runs.map((run) => (
              <Card
                key={run.id}
                className="p-6 hover:shadow-md transition-shadow cursor-pointer"
                onClick={() => navigate(`/app/workflows/runs/${run.id}`)}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <h3 className="text-lg font-semibold text-foreground">
                        {run.workflow_name || "Workflow"}
                      </h3>
                      {getStatusBadge(run.status)}
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground dark:text-muted-foreground">
                      {run.mode} mode • Created {formatDate(run.created_at)}
                    </p>
                    {run.error_message && (
                      <p className="mt-2 text-sm text-red-600 dark:text-red-400">
                        Error: {run.error_message}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right text-sm text-muted-foreground dark:text-muted-foreground">
                      {run.completed_at && (
                        <div className="mb-1">
                          {((run.latency_ms || 0) / 1000).toFixed(1)}s
                        </div>
                      )}
                      {run.cost_usd && (
                        <div className="flex items-center gap-1 text-green-600 dark:text-green-400">
                          <DollarSign className="w-3.5 h-3.5" />
                          {run.cost_usd.toFixed(3)}
                        </div>
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => handleDeleteClick(run, e)}
                      className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-950"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Workflow Run?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this workflow run? This will
              permanently delete the run and all associated artifacts from
              storage. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              disabled={deleting}
              className="bg-red-600 hover:bg-red-700 focus:ring-red-600"
            >
              {deleting ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </AppLayout>
  );
}
