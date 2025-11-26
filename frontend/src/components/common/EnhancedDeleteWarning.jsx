/**
 * EnhancedDeleteWarning Component
 *
 * Advanced delete confirmation dialog that shows document usage.
 * Requires typing "DELETE" for documents that are in use.
 *
 * Input:
 *   - documentId: string
 *   - documentName: string
 *   - getToken: () => Promise<string>
 *   - onConfirmDelete: () => void
 *   - trigger: React.ReactNode (the button/element that triggers the dialog)
 *
 * Output:
 *   - Renders AlertDialog with usage information
 *   - Handles deletion confirmation with safety check
 */

import { useState, useEffect } from "react";
import { AlertTriangle, MessageSquare, FileText, Workflow } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "../ui/alert-dialog";
import { Input } from "../ui/input";
import { getDocumentUsage } from "../../api/chat";
import Spinner from "./Spinner";

export default function EnhancedDeleteWarning({
  documentId,
  documentName,
  getToken,
  onConfirmDelete,
  trigger,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [usageData, setUsageData] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [confirmText, setConfirmText] = useState("");

  // Fetch usage data when dialog opens
  useEffect(() => {
    if (isOpen && !usageData && !isLoading) {
      fetchUsageData();
    }
  }, [isOpen]);

  const fetchUsageData = async () => {
    setIsLoading(true);
    try {
      const data = await getDocumentUsage(getToken, documentId);
      setUsageData(data);
    } catch (error) {
      console.error("Failed to fetch document usage:", error);
      setUsageData({ total_usage_count: 0, usage: {} }); // Allow deletion on error
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirm = () => {
    // If document is in use, require "DELETE" confirmation
    if (usageData && usageData.total_usage_count > 0) {
      if (confirmText !== "DELETE") {
        return; // Don't proceed if confirmation text doesn't match
      }
    }

    onConfirmDelete?.();
    setIsOpen(false);
    setConfirmText("");
    setUsageData(null); // Reset for next time
  };

  const handleCancel = () => {
    setIsOpen(false);
    setConfirmText("");
    setUsageData(null); // Reset for next time
  };

  const isInUse = usageData && usageData.total_usage_count > 0;
  const canDelete = !isInUse || confirmText === "DELETE";

  const chatCount = usageData?.usage?.chat_sessions?.length || 0;
  const extractCount = usageData?.usage?.extracts?.length || 0;
  const workflowCount = usageData?.usage?.workflows?.length || 0;

  return (
    <AlertDialog open={isOpen} onOpenChange={setIsOpen}>
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>

      <AlertDialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-destructive" />
            Delete Document?
          </AlertDialogTitle>

          {isLoading ? (
            <div className="py-6 flex items-center justify-center">
              <Spinner />
            </div>
          ) : (
            <>
              {isInUse ? (
                <AlertDialogDescription className="space-y-4">
                  <p className="text-base">
                    <strong className="text-foreground">{documentName}</strong> is currently being used in{" "}
                    <strong className="text-destructive">{usageData.total_usage_count}</strong>{" "}
                    {usageData.total_usage_count === 1 ? "place" : "places"}:
                  </p>

                  {/* Usage Breakdown */}
                  <div className="space-y-3 bg-muted/50 p-4 rounded-lg">
                    {/* Chat Sessions */}
                    {chatCount > 0 && (
                      <div>
                        <div className="flex items-center gap-2 font-medium text-sm text-foreground mb-2">
                          <MessageSquare className="w-4 h-4 text-blue-600" />
                          <span>Chat Sessions ({chatCount})</span>
                        </div>
                        <ul className="space-y-1 pl-6">
                          {usageData.usage.chat_sessions.slice(0, 5).map((session) => (
                            <li
                              key={session.session_id}
                              className="text-sm text-muted-foreground"
                            >
                              • {session.title}
                            </li>
                          ))}
                          {chatCount > 5 && (
                            <li className="text-sm text-muted-foreground italic">
                              • ... and {chatCount - 5} more
                            </li>
                          )}
                        </ul>
                      </div>
                    )}

                    {/* Extractions */}
                    {extractCount > 0 && (
                      <div>
                        <div className="flex items-center gap-2 font-medium text-sm text-foreground mb-2">
                          <FileText className="w-4 h-4 text-green-600" />
                          <span>Extractions ({extractCount})</span>
                        </div>
                        <p className="text-sm text-muted-foreground pl-6">
                          {extractCount} extraction{extractCount !== 1 ? "s" : ""} will lose reference to this document
                        </p>
                      </div>
                    )}

                    {/* Workflows */}
                    {workflowCount > 0 && (
                      <div>
                        <div className="flex items-center gap-2 font-medium text-sm text-foreground mb-2">
                          <Workflow className="w-4 h-4 text-purple-600" />
                          <span>Workflow Runs ({workflowCount})</span>
                        </div>
                        <ul className="space-y-1 pl-6">
                          {usageData.usage.workflows.slice(0, 5).map((workflow) => (
                            <li
                              key={workflow.run_id}
                              className="text-sm text-muted-foreground"
                            >
                              • {workflow.workflow_name}
                            </li>
                          ))}
                          {workflowCount > 5 && (
                            <li className="text-sm text-muted-foreground italic">
                              • ... and {workflowCount - 5} more
                            </li>
                          )}
                        </ul>
                      </div>
                    )}
                  </div>

                  {/* Impact Warning */}
                  <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4">
                    <p className="text-sm text-foreground font-medium mb-2">
                      ⚠️ Impact of Deletion:
                    </p>
                    <ul className="space-y-1 text-sm text-muted-foreground">
                      <li>• Document will be removed from all chat sessions</li>
                      <li>• All document chunks and embeddings will be deleted</li>
                      <li>• Extraction and workflow history will remain, but won't reference this document</li>
                      <li>• This action cannot be undone</li>
                    </ul>
                  </div>

                  {/* Confirmation Input */}
                  <div>
                    <p className="text-sm text-foreground font-medium mb-2">
                      Type <code className="px-1.5 py-0.5 bg-muted rounded text-destructive font-mono">DELETE</code> to confirm:
                    </p>
                    <Input
                      value={confirmText}
                      onChange={(e) => setConfirmText(e.target.value)}
                      placeholder="Type DELETE to confirm"
                      className="font-mono"
                    />
                  </div>
                </AlertDialogDescription>
              ) : (
                <AlertDialogDescription>
                  <p className="mb-3">
                    This will permanently delete{" "}
                    <strong className="text-foreground">{documentName}</strong>.
                  </p>
                  <p className="text-sm text-muted-foreground">
                    The document is not currently used in any chat sessions, extractions, or workflows.
                    This action cannot be undone.
                  </p>
                </AlertDialogDescription>
              )}
            </>
          )}
        </AlertDialogHeader>

        <AlertDialogFooter>
          <AlertDialogCancel onClick={handleCancel}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={!canDelete || isLoading}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {isLoading ? "Loading..." : "Delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
