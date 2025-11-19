/**
 * Simplified Workflow Page - Single Screen Experience
 *
 * Layout: 3-panel side-by-side (documents, workflow config, results)
 * UX: Professional, clean, deliverables.ai-inspired
 */

import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import { FileText, Sparkles, ArrowLeft, Settings, Plus, X } from "lucide-react";
import AppLayout from "../components/layout/AppLayout";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import Spinner from "../components/common/Spinner";
import VariableConfigModal from "../components/workflows/VariableConfigModal";
import DocumentSelectorModal from "../components/workflows/DocumentSelectorModal";
import WorkflowResultSheet from "../components/workflows/WorkflowResultSheet";
import { useWorkflowDraft, useWorkflowDraftActions } from "../store";
import { streamWorkflowProgress } from "../api/workflows";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export default function WorkflowSimplePage() {
  const navigate = useNavigate();
  const { getToken } = useAuth();

  // Zustand store for workflow draft (persisted in localStorage)
  const { selectedDocuments, selectedWorkflow, variables, execution } =
    useWorkflowDraft();
  const {
    setSelectedWorkflow,
    setWorkflowVariables,
    removeDocumentFromDraft,
    reconnectWorkflowExecution,
  } = useWorkflowDraftActions();

  // Local state (not persisted)
  const [templates, setTemplates] = useState([]);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [showDocSelector, setShowDocSelector] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [selectedRunId, setSelectedRunId] = useState(null);

  useEffect(() => {
    fetchInitialData();

    // Reconnect to active workflow execution if exists
    if (execution && execution.jobId && execution.runId) {
      console.log("🔄 Reconnecting to active workflow execution on mount");
      reconnectWorkflowExecution(getToken);
    }

    // Cleanup SSE on unmount
    return () => {
      if (execution && execution.cleanup) {
        execution.cleanup();
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch templates and recent runs (documents come from modal/store)
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

  // Select workflow template
  const handleSelectTemplate = async (template) => {
    setLoading(true);
    try {
      const token = await getToken();
      const res = await axios.get(
        `${API_BASE}/api/workflows/templates/${template.id}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      setSelectedWorkflow(res.data);

      // Initialize variables with defaults
      const initialVars = {};
      (res.data.variables_schema || []).forEach((v) => {
        if (v.default !== undefined && v.default !== null) {
          initialVars[v.name] = v.default;
        }
      });
      setWorkflowVariables(initialVars);
    } catch (error) {
      console.error("Failed to load template:", error);
    } finally {
      setLoading(false);
    }
  };

  // Go back to template selection
  const handleBack = () => {
    setSelectedWorkflow(null);
    setWorkflowVariables({});
  };

  // Generate workflow
  const handleGenerate = async () => {
    if (!selectedWorkflow || selectedDocuments.length === 0) {
      alert("Please select documents and configure the workflow");
      return;
    }

    // Prevent duplicate starts
    if (execution && execution.isProcessing) {
      console.warn("⚠️ Workflow already in progress");
      return;
    }
  };

  // Filter runs by selected workflow
  const filteredRuns = selectedWorkflow
    ? runs.filter((r) => r.workflow_id === selectedWorkflow.id)
    : runs;

  // Handle opening result sheet
  const handleOpenResult = (runId) => {
    setSelectedRunId(runId);
    setSheetOpen(true);
  };

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
      <div className="h-[calc(100vh-12rem)] flex gap-4">
        {/* LEFT PANEL: Selected Documents */}
        <div className="w-64 flex-shrink-0 bg-card rounded-lg border border-border dark:border-gray-700 p-4 overflow-y-auto flex flex-col">
          <h3 className="font-semibold text-sm text-foreground mb-3 flex items-center gap-2">
            <FileText className="w-4 h-4" />
            Selected Documents
          </h3>

          <div className="flex-1 overflow-y-auto">
            {selectedDocuments.length === 0 ? (
              <div className="text-center py-8">
                <FileText className="w-10 h-10 text-gray-300 dark:text-muted-foreground mx-auto mb-2" />
                <p className="text-sm text-muted-foreground dark:text-muted-foreground mb-1">
                  No documents selected
                </p>
                <p className="text-xs text-muted-foreground dark:text-muted-foreground">
                  Add documents to get started
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {selectedDocuments.map((doc) => (
                  <div
                    key={doc.id}
                    className="p-3 rounded-lg border border-border dark:border-gray-700 bg-background "
                  >
                    <div className="flex items-start gap-2">
                      <FileText className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">
                          {doc.filename}
                        </p>
                        <p className="text-xs text-muted-foreground dark:text-muted-foreground">
                          {doc.page_count} pages
                        </p>
                      </div>
                      <button
                        onClick={() => removeDocumentFromDraft(doc.id)}
                        className="flex-shrink-0 p-1 hover:bg-muted dark:hover:bg-gray-700 rounded transition-colors"
                        title="Remove from workflow"
                      >
                        <X className="w-3.5 h-3.5 text-muted-foreground hover:text-red-600" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="mt-4 pt-4 border-t border-border dark:border-gray-700 space-y-3">
            <div className="text-xs text-muted-foreground dark:text-muted-foreground">
              <p className="font-medium">
                {selectedDocuments.length}{" "}
                {selectedDocuments.length === 1 ? "document" : "documents"} •{" "}
                {selectedDocuments.reduce(
                  (sum, d) => sum + (d.page_count || 0),
                  0
                )}{" "}
                pages
              </p>
            </div>
            <Button
              onClick={() => setShowDocSelector(true)}
              variant="outline"
              size="sm"
              className="w-full"
            >
              <Plus className="w-4 h-4 mr-2" />
              Add Documents
            </Button>
          </div>
        </div>

        {/* MIDDLE PANEL: Workflow Selection or Config */}
        <div className="flex-1 bg-card rounded-lg border border-border dark:border-gray-700 p-6 overflow-y-auto">
          {!selectedWorkflow ? (
            /* Workflow Selection */
            <div>
              <h2 className="text-xl font-bold text-foreground mb-1">
                Select a Workflow
              </h2>
              <p className="text-sm text-muted-foreground dark:text-gray-300 mb-6">
                Choose a workflow template to generate insights from your
                documents
              </p>

              <div className="grid grid-cols-1 gap-4">
                {templates.map((template) => (
                  <Card
                    key={template.id}
                    className="p-5 hover:shadow-lg transition-shadow cursor-pointer border-2 hover:border-blue-500"
                    onClick={() => handleSelectTemplate(template)}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <Sparkles className="w-5 h-5 text-blue-600" />
                          <h3 className="text-lg font-semibold text-foreground">
                            {template.name}
                          </h3>
                        </div>
                        <p className="text-sm text-muted-foreground dark:text-gray-300 mb-3">
                          {template.description}
                        </p>
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="text-xs">
                            {template.category}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {template.min_documents}-
                            {template.max_documents || "∞"} docs
                          </span>
                        </div>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            </div>
          ) : (
            /* Workflow Config */
            <div>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleBack}
                className="mb-4"
              >
                <ArrowLeft className="w-4 h-4 mr-2" />
                Back to workflows
              </Button>

              <div className="flex items-start gap-3 mb-6">
                <Sparkles className="w-6 h-6 text-blue-600 flex-shrink-0 mt-1" />
                <div className="flex-1">
                  <h2 className="text-xl font-bold text-foreground mb-1">
                    {selectedWorkflow.name}
                  </h2>
                  <p className="text-sm text-muted-foreground dark:text-gray-300">
                    {selectedWorkflow.description}
                  </p>
                </div>
              </div>

              <div className="bg-background  rounded-lg p-4 mb-6">
                <p className="text-sm text-muted-foreground dark:text-gray-300 font-mono leading-relaxed">
                  {selectedWorkflow.user_prompt_template ||
                    selectedWorkflow.prompt_template?.slice(0, 200) + "..."}
                </p>
              </div>

              <Button
                onClick={() => setShowConfigModal(true)}
                variant="outline"
                className="w-full mb-4"
              >
                <Settings className="w-4 h-4 mr-2" />
                Configure Variables
              </Button>

              <Button
                onClick={handleGenerate}
                disabled={
                  (execution && execution.isProcessing) ||
                  selectedDocuments.length === 0
                }
                className="w-full bg-blue-600 hover:bg-blue-700 text-foreground"
              >
                {execution && execution.isProcessing ? (
                  <>
                    <Spinner size="sm" className="mr-2" />
                    Generating...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4 mr-2" />
                    Generate
                  </>
                )}
              </Button>

              {/* Elegant Progress Indicator */}
              {execution && execution.isProcessing && (
                <div className="mt-4 p-4 bg-blue-50 dark:bg-blue-950 rounded-lg border border-blue-200 dark:border-blue-800">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-blue-900 dark:text-blue-100">
                      {execution.message || "Processing..."}
                    </span>
                    <span className="text-xs text-blue-700 dark:text-blue-300">
                      {execution.progress}%
                    </span>
                  </div>
                  {/* Progress Bar */}
                  <div className="w-full bg-blue-100 dark:bg-blue-900 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-blue-600 dark:bg-blue-400 h-2 rounded-full transition-all duration-500 ease-out"
                      style={{ width: `${execution.progress}%` }}
                    />
                  </div>
                  {execution.stage === "failed" && (
                    <p className="mt-2 text-xs text-red-600 dark:text-red-400">
                      {execution.message}
                    </p>
                  )}
                </div>
              )}

              {selectedDocuments.length === 0 &&
                !(execution && execution.isProcessing) && (
                  <p className="mt-3 text-sm text-amber-600 dark:text-amber-400">
                    ⚠️ Please select at least one document
                  </p>
                )}
            </div>
          )}
        </div>

        {/* RIGHT PANEL: Results */}
        <div className="w-96 flex-shrink-0 bg-card rounded-lg border border-border dark:border-gray-700 p-4 overflow-y-auto">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-sm text-foreground">
              {selectedWorkflow
                ? `${selectedWorkflow.name} Results`
                : "Recent Results"}
            </h3>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate("/app/workflows/history?tab=runs")}
              className="text-xs"
            >
              View All
            </Button>
          </div>

          {filteredRuns.length === 0 ? (
            <div className="text-center py-12">
              <Sparkles className="w-12 h-12 text-gray-300 dark:text-muted-foreground mx-auto mb-3" />
              <p className="text-sm text-muted-foreground dark:text-muted-foreground">
                No results yet
              </p>
              <p className="text-xs text-muted-foreground dark:text-muted-foreground mt-1">
                Generate a workflow to see results here
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {filteredRuns.slice(0, 5).map((run) => (
                <ResultPreviewCard
                  key={run.id}
                  run={run}
                  onOpenSheet={handleOpenResult}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Variable Config Modal */}
      <VariableConfigModal
        open={showConfigModal}
        onOpenChange={setShowConfigModal}
        template={selectedWorkflow}
        variables={variables}
        onVariablesChange={setWorkflowVariables}
        onGenerate={handleGenerate}
      />

      {/* Document Selector Modal */}
      <DocumentSelectorModal
        open={showDocSelector}
        onOpenChange={setShowDocSelector}
      />

      {/* Workflow Result Sheet */}
      <WorkflowResultSheet
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        runId={selectedRunId}
      />
    </AppLayout>
  );
}

// Placeholder for ResultPreviewCard - will create separate component
function ResultPreviewCard({ run, onOpenSheet }) {
  const getStatusBadge = () => {
    switch (run.status) {
      case "completed":
        return (
          <Badge className="bg-green-600 text-foreground">✓ Completed</Badge>
        );
      case "running":
        return <Badge className="bg-blue-600 text-foreground">Running</Badge>;
      case "failed":
        return <Badge className="bg-red-600 text-foreground">Failed</Badge>;
      default:
        return <Badge variant="outline">{run.status}</Badge>;
    }
  };

  return (
    <Card
      className="p-4 hover:shadow-md transition-shadow cursor-pointer dark:bg-card dark:border-gray-700 dark:hover:shadow-lg"
      onClick={() => onOpenSheet(run.id)}
    >
      <div className="flex items-start justify-between mb-2">
        <p className="text-sm font-medium text-foreground flex-1">
          {run.workflow_name || "Workflow"}
        </p>
        {getStatusBadge()}
      </div>

      {run.status === "completed" && run.artifact_json?.sections?.[0] && (
        <div className="text-xs text-muted-foreground dark:text-gray-300 line-clamp-3">
          {run.artifact_json.sections[0].content?.slice(0, 150)}...
        </div>
      )}

      {run.status === "failed" && (
        <p className="text-xs text-red-600 dark:text-red-400">
          {run.error_message}
        </p>
      )}

      <Button variant="ghost" size="sm" className="mt-2 w-full text-xs">
        View Details →
      </Button>
    </Card>
  );
}
