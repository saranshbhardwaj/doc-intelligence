/**
 * Simplified Workflow Page - Single Screen Experience
 *
 * Layout: 3-panel side-by-side (documents, workflow grid, results)
 * UX: Professional, clean, inspired by frearaAI mock-up
 */

import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAppAuth } from "@/hooks/useAppAuth";
import {
  FileText,
  FileSpreadsheet,
  File,
  Sparkles,
  Settings,
  Plus,
  X,
  Clock,
  AlertCircle,
  CheckCircle,
  Flag,
  TrendingUp,
  Calculator,
  Users,
  Timer,
  Play,
  ArrowLeft,
} from "lucide-react";
import { toast } from "sonner";

// Only these workflow names are fully functional. All others show as "Coming Soon".
const WORKING_WORKFLOWS = new Set(["Investment Memo"]);

const getDocFileIcon = (filename) => {
  const ext = filename?.toLowerCase().split(".").pop();
  if (ext === "pdf")
    return {
      Icon: FileText,
      bg: "bg-red-50 dark:bg-red-900/20",
      color: "text-red-500 dark:text-red-400",
    };
  if (["xlsx", "xls"].includes(ext))
    return {
      Icon: FileSpreadsheet,
      bg: "bg-green-50 dark:bg-green-900/20",
      color: "text-green-600 dark:text-green-400",
    };
  return {
    Icon: File,
    bg: "bg-blue-50 dark:bg-blue-900/20",
    color: "text-blue-500 dark:text-blue-400",
  };
};

const getWorkflowIcon = (name = "") => {
  if (name.includes("Investment Memo")) return { Icon: FileText };
  if (name.includes("Red Flag")) return { Icon: Flag };
  if (name.includes("Revenue")) return { Icon: TrendingUp };
  if (name.includes("Financial Model")) return { Icon: Calculator };
  if (name.includes("Management")) return { Icon: Users };
  return { Icon: Sparkles };
};

const getRelativeTime = (iso) => {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3600000);
  if (h < 1) return "Just now";
  if (h < 24) return `${h}h ago`;
  if (h < 48) return "Yesterday";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
};

/**
 * Renders a prompt string with {{variable}} placeholders as inline teal chips.
 */
const renderPromptWithVariables = (text = "") => {
  const parts = text.split(/(\{\{[^}]+\}\})/);
  return parts.map((part, i) => {
    const match = part.match(/^\{\{([^}]+)\}\}$/);
    if (match) {
      return (
        <span
          key={i}
          className="inline-flex items-center px-1.5 py-0.5 rounded-md bg-primary/10 text-primary text-xs font-mono font-semibold mx-0.5 whitespace-nowrap"
        >
          {match[1]}
        </span>
      );
    }
    return <span key={i}>{part}</span>;
  });
};

import AppLayout from "../components/layout/AppLayout";
import { Button } from "../components/ui/button";
import { Progress } from "../components/ui/progress";
import Spinner from "../components/common/Spinner";
import VariableConfigModal from "../components/workflows/VariableConfigModal";
import DocumentSelectorModal from "../components/workflows/DocumentSelectorModal";
import WorkflowResultSheet from "../components/workflows/WorkflowResultSheet";
import { useWorkflowDraft, useWorkflowDraftActions } from "../store";
import { streamWorkflowProgress } from "../api/workflows";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

/**
 * Format workflow error messages for user-friendly display
 */
function formatWorkflowError(error) {
  console.error("Full error object:", error);
  console.error("Error response data:", error.response?.data);
  console.error("Error response status:", error.response?.status);

  const errorData = error.response?.data || {};
  const status = error.response?.status;
  const errorType = errorData.error_type || errorData.error;

  switch (errorType) {
    case "workflow_limit_exceeded":
      return {
        title: "Workflow Limit Reached",
        message: `You've reached the workflow run limit (${errorData.used || "?"} of ${errorData.limit || "?"} runs used on this beta account). Contact your admin to increase the limit.`,
      };
    case "not_found":
      return {
        title: "Workflow Not Found",
        message: "The workflow you're trying to run no longer exists.",
      };
    case "unauthorized":
      return {
        title: "Access Denied",
        message: "You don't have permission to run this workflow.",
      };
    default:
      if (status === 403) {
        return {
          title: "Permission Denied",
          message:
            "You don't have permission to run workflows. Contact your admin to enable this feature.",
        };
      }
      if (status === 401) {
        return {
          title: "Authentication Required",
          message: "Your session has expired. Please refresh the page.",
        };
      }
      return {
        title: "Workflow Error",
        message: String(
          errorData.detail ||
            errorData.message ||
            error.message ||
            "Failed to start workflow"
        ),
      };
  }
}

export default function WorkflowSimplePage() {
  const navigate = useNavigate();
  const { getToken } = useAppAuth();

  const { selectedDocuments, selectedWorkflow, variables, execution } =
    useWorkflowDraft();
  const {
    setSelectedWorkflow,
    setWorkflowVariables,
    removeDocumentFromDraft,
    reconnectWorkflowExecution,
    startWorkflowExecution,
    updateWorkflowProgress,
    completeWorkflowExecution,
    failWorkflowExecution,
  } = useWorkflowDraftActions();

  const [templates, setTemplates] = useState([]);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [showDocSelector, setShowDocSelector] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [mobilePanel, setMobilePanel] = useState("workflow");
  const [showConfigView, setShowConfigView] = useState(false);

  useEffect(() => {
    fetchInitialData();

    if (execution && execution.jobId && execution.runId) {
      reconnectWorkflowExecution(getToken);
    }

    return () => {
      if (execution && execution.cleanup) {
        execution.cleanup();
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const prevProcessingRef = useRef(execution?.isProcessing);
  useEffect(() => {
    if (
      prevProcessingRef.current === true &&
      execution?.isProcessing === false
    ) {
      fetchInitialData();
    }
    prevProcessingRef.current = execution?.isProcessing;
  }, [execution?.isProcessing]); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchInitialData = async () => {
    setLoading(true);
    try {
      const token = await getToken();
      const [templatesRes, runsRes] = await Promise.all([
        axios.get(`${API_BASE}/api/workflows/templates`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        axios.get(`${API_BASE}/api/workflows/runs?limit=10`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);

      setTemplates(templatesRes.data);
      setRuns(runsRes.data || []);
    } catch (error) {
      console.error("Failed to fetch initial data:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectTemplate = async (template) => {
    setLoading(true);
    try {
      const token = await getToken();
      const res = await axios.get(
        `${API_BASE}/api/workflows/templates/${template.id}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      setSelectedWorkflow(res.data);

      const initialVars = {};
      (res.data.variables_schema || []).forEach((v) => {
        if (v.default !== undefined && v.default !== null) {
          initialVars[v.name] = v.default;
        }
      });
      setWorkflowVariables(initialVars);
      setShowConfigView(true);
    } catch (error) {
      console.error("Failed to load template:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async () => {
    if (!selectedWorkflow || selectedDocuments.length === 0) return;

    if (execution && execution.isProcessing === true) {
      console.warn("⚠️ Workflow already in progress");
      return;
    }

    startWorkflowExecution(null, null, null);

    try {
      const token = await getToken();

      const payload = {
        workflow_id: selectedWorkflow.id,
        document_ids: selectedDocuments.map((doc) => doc.id),
        variables: variables || {},
      };

      const response = await axios.post(
        `${API_BASE}/api/workflows/runs`,
        payload,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      const { id: runId, job_id: jobId } = response.data;

      const cleanup = await streamWorkflowProgress(jobId, getToken, {
        onProgress: (progressData) => {
          updateWorkflowProgress(progressData);
        },
        onComplete: () => {
          completeWorkflowExecution();
          fetchInitialData();
        },
        onError: (errorData) => {
          console.error("❌ Workflow error:", errorData);
          const errorMsg =
            typeof errorData === "string"
              ? errorData
              : errorData?.message || "Workflow failed";
          failWorkflowExecution(errorMsg);
          fetchInitialData();
        },
        onEnd: () => {},
      });

      startWorkflowExecution(jobId, runId, cleanup);
    } catch (error) {
      console.error("Failed to start workflow:", error);
      const { title, message } = formatWorkflowError(error);
      failWorkflowExecution(message);
      toast.error(message, { description: title, duration: 6000 });
    }
  };

  const filteredRuns = selectedWorkflow
    ? runs.filter((r) => r.workflow_id === selectedWorkflow.id)
    : runs.filter((r) => r.workflow_id !== null);

  const orphanedRuns = runs.filter((r) => r.workflow_id === null);

  const handleOpenResult = (runId) => {
    setSelectedRunId(runId);
    setSheetOpen(true);
  };

  const totalPages = selectedDocuments.reduce(
    (s, d) => s + (d.page_count || 0),
    0
  );

  const breadcrumbs = [{ label: "Workflows" }];

  if (loading) {
    return (
      <AppLayout breadcrumbs={breadcrumbs}>
        <div className="flex items-center justify-center h-96">
          <Spinner size="lg" />
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout breadcrumbs={breadcrumbs}>
      <div className="h-[calc(100vh-64px)] flex flex-col md:flex-row gap-3 md:gap-4 min-h-0">
        {/* Mobile panel switcher */}
        <div className="md:hidden grid grid-cols-3 gap-2 px-1">
          {["documents", "workflow", "results"].map((panel) => (
            <button
              key={panel}
              onClick={() => setMobilePanel(panel)}
              className={`py-2 text-sm font-medium rounded-lg capitalize transition-colors ${
                mobilePanel === panel
                  ? "bg-primary text-secondary"
                  : "bg-card border border-border text-foreground"
              }`}
            >
              {panel}
            </button>
          ))}
        </div>

        {/* ── LEFT PANEL: Selected Documents ── */}
        <div
          className={`${
            mobilePanel === "documents" ? "flex" : "hidden"
          } md:flex w-full md:w-72 flex-shrink-0 bg-card rounded-xl border border-border flex-col overflow-hidden min-h-0`}
        >
          {/* Header */}
          <div className="p-4 border-b border-border flex-shrink-0">
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-lg font-bold text-foreground">
                Selected Docs
              </h3>
              {selectedDocuments.length > 0 && (
                <span className="bg-primary/20 text-primary text-xs font-bold px-2 py-1 rounded-full">
                  {selectedDocuments.length}
                </span>
              )}
            </div>
            <p className="text-sm text-muted-foreground">
              Review files before processing
            </p>
          </div>

          {/* Doc list */}
          <div className="flex-1 overflow-y-auto p-4 space-y-2">
            {selectedDocuments.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full py-4 text-center">
                <FileText className="w-10 h-10 text-muted-foreground mx-auto mb-2 opacity-40" />
                <p className="text-sm text-muted-foreground mb-1">
                  No documents selected
                </p>
                <p className="text-xs text-muted-foreground">
                  Add documents to get started
                </p>
              </div>
            ) : (
              selectedDocuments.map((doc) => {
                const { Icon, bg, color } = getDocFileIcon(doc.filename);
                return (
                  <div
                    key={doc.id}
                    className="group flex items-start gap-3 p-3 bg-background rounded-xl border border-transparent hover:border-primary/30 transition-all shadow-sm"
                  >
                    <div
                      className={`shrink-0 w-10 h-10 rounded-lg flex items-center justify-center ${bg}`}
                    >
                      <Icon className={`w-5 h-5 ${color}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-foreground truncate">
                        {doc.filename}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {doc.page_count || 0} pages
                      </p>
                    </div>
                    <button
                      onClick={() => removeDocumentFromDraft(doc.id)}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-destructive/10 hover:text-destructive text-muted-foreground transition-opacity"
                      title="Remove from workflow"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                );
              })
            )}

            {/* Dashed add button */}
            <button
              onClick={() => setShowDocSelector(true)}
              className="w-full py-3 border-2 border-dashed border-border rounded-xl flex items-center justify-center gap-2 text-muted-foreground hover:border-primary hover:text-primary hover:bg-primary/5 transition-all group mt-1"
            >
              <Plus className="w-4 h-4 group-hover:scale-110 transition-transform" />
              <span className="text-sm font-medium">Add from Library</span>
            </button>
          </div>

          {/* Footer: pages used */}
          <div className="p-4 bg-card border-t border-border flex-shrink-0">
            <div className="flex justify-between text-xs text-muted-foreground mb-2">
              <span>Pages Used</span>
              <span className="font-medium text-foreground">
                {totalPages} / 700
              </span>
            </div>
            <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-primary h-full rounded-full transition-all"
                style={{
                  width: `${Math.min((totalPages / 700) * 100, 100)}%`,
                }}
              />
            </div>
          </div>
        </div>

        {/* ── CENTER PANEL: Workflow Grid ── */}
        <div
          className={`${
            mobilePanel === "workflow" ? "flex" : "hidden"
          } md:flex flex-1 bg-card rounded-xl border border-border flex-col overflow-hidden min-h-0 relative`}
        >
          {showConfigView && selectedWorkflow ? (
            /* ── CONFIG VIEW ── */
            <div className="flex-1 overflow-y-auto p-6 md:p-8">
              {/* Back link */}
              <button
                onClick={() => setShowConfigView(false)}
                className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors"
              >
                <ArrowLeft className="w-4 h-4" />
                Back to workflows
              </button>

              {/* Analysis Prompt Card */}
              {selectedWorkflow.user_prompt_template && (
                <div className="bg-background rounded-xl border border-border shadow-sm p-6 mb-6">
                  <div className="flex items-start justify-between gap-4 mb-4">
                    <div>
                      <h3 className="text-sm font-semibold text-foreground">
                        {selectedWorkflow.name}
                      </h3>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {(selectedWorkflow.variables_schema || []).length > 0
                          ? `${(selectedWorkflow.variables_schema || []).length} configurable parameter${(selectedWorkflow.variables_schema || []).length !== 1 ? "s" : ""}`
                          : "Ready to run"}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {(selectedWorkflow.variables_schema || []).length > 0 && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setShowConfigModal(true)}
                          className="gap-1.5"
                        >
                          <Settings className="w-3.5 h-3.5" />
                          Configure
                        </Button>
                      )}
                      <Button
                        size="sm"
                        onClick={handleGenerate}
                        disabled={
                          selectedDocuments.length === 0 || execution?.isProcessing
                        }
                        className="gap-2"
                      >
                        {execution?.isProcessing ? (
                          <>
                            <Spinner size="sm" />
                            Running
                          </>
                        ) : (
                          <>
                            <Play className="w-4 h-4" />
                            Run
                          </>
                        )}
                      </Button>
                    </div>
                  </div>

                  {/* Prompt body with inline variable chips */}
                  <div className="bg-muted/30 border border-border rounded-xl p-4 text-sm text-foreground leading-7 font-mono">
                    {renderPromptWithVariables(
                      selectedWorkflow.user_prompt_template
                    )}
                  </div>
                </div>
              )}

              {/* Progress indicator */}
              {execution?.isProcessing && (
                <div className="p-4 bg-primary/5 rounded-xl border border-primary/20 mb-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-foreground">
                      {execution.message}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {execution.progress}%
                    </span>
                  </div>
                  <Progress
                    value={execution.progress || 0}
                    variant="primary"
                    className="h-1.5"
                    showShimmer
                  />
                </div>
              )}

              {/* Error state */}
              {!execution?.isProcessing && execution?.stage === "failed" && (
                <div className="p-4 bg-destructive/10 rounded-xl border border-destructive/30 mb-4">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 text-destructive mt-0.5 shrink-0" />
                    <div>
                      <p className="text-sm font-medium text-destructive">
                        Workflow failed
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {execution.message || "An unexpected error occurred."}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <>
              {/* ── GRID VIEW ── */}
              <div className="flex-1 overflow-y-auto p-6 md:p-8 pb-32">
                {/* Header */}
                <div className="mb-8">
                  <h1 className="text-3xl font-extrabold text-foreground tracking-tight mb-2">
                    Select a Workflow
                  </h1>
                  <p className="text-muted-foreground text-sm">
                    Choose the type of analysis you want to generate from your
                    documents.
                  </p>
                </div>

                {/* Workflow grid */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
                  {templates.map((template) => {
                    const isActive = selectedWorkflow?.id === template.id;
                    const isAvailable = WORKING_WORKFLOWS.has(template.name);
                    const { Icon } = getWorkflowIcon(template.name);

                    return (
                      <div
                        key={template.id}
                        onClick={() =>
                          isAvailable && handleSelectTemplate(template)
                        }
                        className={`relative p-5 rounded-2xl border-2 bg-card transition-all select-none
                          ${
                            isActive
                              ? "border-primary shadow-[0_4px_20px_-4px_rgba(19,236,218,0.15)] cursor-pointer"
                              : isAvailable
                              ? "border-border hover:border-primary/40 hover:shadow-md cursor-pointer hover:scale-[1.01]"
                              : "border-border opacity-70 cursor-not-allowed"
                          }`}
                      >
                        {/* Top-right badge */}
                        {isActive && (
                          <CheckCircle className="absolute top-4 right-4 w-5 h-5 text-primary" />
                        )}
                        {!isAvailable && (
                          <span className="absolute top-4 right-4 px-2 py-0.5 bg-muted text-muted-foreground rounded text-[10px] font-bold uppercase tracking-wide">
                            Coming Soon
                          </span>
                        )}

                        {/* Icon */}
                        <div
                          className={`w-12 h-12 rounded-xl flex items-center justify-center mb-4 ${
                            isAvailable
                              ? "bg-primary/10 text-primary"
                              : "bg-muted text-muted-foreground"
                          }`}
                        >
                          <Icon className="w-7 h-7" />
                        </div>

                        {/* Name + description */}
                        <h3
                          className={`text-lg font-bold mb-1 ${
                            isAvailable
                              ? "text-foreground"
                              : "text-muted-foreground"
                          }`}
                        >
                          {template.name}
                        </h3>
                        <p
                          className={`text-sm mb-4 line-clamp-2 ${
                            isAvailable
                              ? "text-muted-foreground"
                              : "text-muted-foreground/70"
                          }`}
                        >
                          {template.description}
                        </p>

                        {/* Tags */}
                        <div className="flex flex-wrap gap-2">
                          <span
                            className={`px-2.5 py-1 rounded-md text-xs font-semibold ${
                              isAvailable
                                ? "bg-muted text-muted-foreground"
                                : "bg-muted/50 text-muted-foreground/70"
                            }`}
                          >
                            {template.category}
                          </span>
                          <span
                            className={`px-2.5 py-1 rounded-md text-xs font-semibold ${
                              isAvailable
                                ? "bg-muted text-muted-foreground"
                                : "bg-muted/50 text-muted-foreground/70"
                            }`}
                          >
                            {template.min_documents}–
                            {template.max_documents || "∞"} docs
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Progress indicator */}
                {execution?.isProcessing && (
                  <div className="p-4 bg-primary/5 rounded-xl border border-primary/20 mb-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-foreground">
                        {execution.message}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {execution.progress}%
                      </span>
                    </div>
                    <Progress
                      value={execution.progress || 0}
                      variant="primary"
                      className="h-1.5"
                      showShimmer
                    />
                  </div>
                )}

                {/* Error state */}
                {!execution?.isProcessing &&
                  execution?.stage === "failed" && (
                    <div className="p-4 bg-destructive/10 rounded-xl border border-destructive/30 mb-4">
                      <div className="flex items-start gap-2">
                        <AlertCircle className="w-4 h-4 text-destructive mt-0.5 shrink-0" />
                        <div>
                          <p className="text-sm font-medium text-destructive">
                            Workflow failed
                          </p>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {execution.message || "An unexpected error occurred."}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}

                {/* No docs warning */}
                {selectedWorkflow &&
                  selectedDocuments.length === 0 &&
                  !execution?.isProcessing && (
                    <p className="text-sm text-warning flex items-center gap-1.5">
                      <Clock className="w-4 h-4" />
                      Add at least one document to run this workflow
                    </p>
                  )}
              </div>
            </>
          )}
        </div>

        {/* ── RIGHT PANEL: Recent Results ── */}
        <div
          className={`${
            mobilePanel === "results" ? "block" : "hidden"
          } md:block w-full md:w-80 flex-shrink-0 bg-card rounded-xl border border-border flex-col overflow-hidden min-h-0 flex`}
        >
          {/* Header */}
          <div className="p-5 border-b border-border flex items-center justify-between flex-shrink-0">
            <h3 className="text-lg font-bold text-foreground">
              {selectedWorkflow
                ? `${selectedWorkflow.name} Results`
                : "Recent Results"}
            </h3>
            <button
              onClick={() => navigate("/app/workflows/history?tab=runs")}
              className="text-xs text-muted-foreground hover:text-primary transition-colors font-medium"
            >
              View All
            </button>
          </div>

          {/* Results list */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {filteredRuns.length === 0 && orphanedRuns.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center py-12">
                <Sparkles className="w-12 h-12 text-muted-foreground mx-auto mb-3 opacity-40" />
                <p className="text-sm text-muted-foreground">No results yet</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Generate a workflow to see results here
                </p>
              </div>
            ) : (
              <>
                {filteredRuns.slice(0, 5).map((run) => (
                  <ResultPreviewCard
                    key={run.id}
                    run={run}
                    onOpenSheet={handleOpenResult}
                  />
                ))}

                {orphanedRuns.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-border">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-[10px] font-bold px-2 py-0.5 bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800 rounded-full">
                        ⚠️ Previous Runs
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mb-3">
                      These runs reference workflows that were deleted
                    </p>
                    <div className="space-y-3">
                      {orphanedRuns.slice(0, 3).map((run) => (
                        <ResultPreviewCard
                          key={run.id}
                          run={run}
                          onOpenSheet={handleOpenResult}
                          isOrphaned
                        />
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Modals */}
      <VariableConfigModal
        open={showConfigModal}
        onOpenChange={setShowConfigModal}
        template={selectedWorkflow}
        variables={variables}
        onVariablesChange={setWorkflowVariables}
        onGenerate={handleGenerate}
        isProcessing={execution && execution.isProcessing}
      />

      <DocumentSelectorModal
        open={showDocSelector}
        onOpenChange={setShowDocSelector}
      />

      <WorkflowResultSheet
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        runId={selectedRunId}
      />
    </AppLayout>
  );
}

function ResultPreviewCard({ run, onOpenSheet, isOrphaned = false }) {
  const workflowName = isOrphaned
    ? run.workflow_snapshot?.name || "Unknown Workflow"
    : run.workflow_name || "Workflow";

  const companyName =
    run.artifact_json?.parsed?.company_overview?.company_name ||
    run.artifact_json?.company_overview?.company_name;

  const displayTitle = companyName || workflowName;
  const docCount = run.document_ids?.length || 0;

  const statusConfig = {
    completed: {
      classes:
        "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400",
      label: "✓ Completed",
    },
    running: {
      classes: "bg-primary/10 text-primary",
      label: "Running",
    },
    failed: {
      classes:
        "bg-red-100 dark:bg-red-900/30 text-destructive",
      label: "Failed",
    },
  };
  const status = statusConfig[run.status] || {
    classes: "bg-muted text-muted-foreground",
    label: run.status,
  };

  return (
    <div
      onClick={() => onOpenSheet(run.id)}
      className={`group p-4 rounded-xl border border-border bg-muted/30 hover:shadow-md transition-shadow cursor-pointer ${
        isOrphaned ? "border-warning/50 bg-warning/5" : ""
      }`}
    >
      {/* Top row: status + relative time */}
      <div className="flex justify-between items-start mb-2">
        <span
          className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${status.classes}`}
        >
          {status.label}
        </span>
        <span className="text-[10px] text-muted-foreground">
          {getRelativeTime(run.created_at)}
        </span>
      </div>

      {/* Title + workflow name */}
      <h4 className="font-bold text-foreground text-sm mb-1 group-hover:text-primary transition-colors truncate">
        {displayTitle}
      </h4>
      {companyName && (
        <p className="text-xs text-muted-foreground mb-3">{workflowName}</p>
      )}
      {isOrphaned && (
        <p className="text-xs text-warning mb-3">⚠️ Workflow deleted</p>
      )}

      {/* Metadata row */}
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        {run.latency_ms && run.status === "completed" && (
          <div className="flex items-center gap-1">
            <Timer className="w-3 h-3" />
            {(run.latency_ms / 1000).toFixed(1)}s
          </div>
        )}
        {docCount > 0 && (
          <div className="flex items-center gap-1">
            <FileText className="w-3 h-3" />
            {docCount} {docCount === 1 ? "doc" : "docs"}
          </div>
        )}
      </div>

      {run.status === "failed" && run.error_message && (
        <p className="text-xs text-destructive mt-2 line-clamp-2">
          {run.error_message}
        </p>
      )}
    </div>
  );
}
