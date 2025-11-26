/**
 * DocumentUsageBadge Component
 *
 * Shows usage indicators for documents (chat sessions, extracts, workflows).
 * Displays on hover with tooltip showing details.
 *
 * Input:
 *   - documentId: string
 *   - getToken: () => Promise<string>
 *
 * Output:
 *   - Renders usage badges with hover tooltip
 */

import { useState } from "react";
import { MessageSquare, FileText, Workflow } from "lucide-react";
import { getDocumentUsage } from "../../api/chat";

export default function DocumentUsageBadge({ documentId, getToken }) {
  const [usageData, setUsageData] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const fetchUsage = async () => {
    if (usageData || isLoading) return; // Don't fetch if already loaded or loading

    setIsLoading(true);
    try {
      const data = await getDocumentUsage(getToken, documentId);
      setUsageData(data);
    } catch (error) {
      console.error("Failed to fetch document usage:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleMouseEnter = () => {
    setIsHovered(true);
    fetchUsage();
  };

  const handleMouseLeave = () => {
    setIsHovered(false);
  };

  // Don't show anything if no usage
  if (!usageData || usageData.total_usage_count === 0) {
    return null;
  }

  const chatCount = usageData.usage.chat_sessions?.length || 0;
  const extractCount = usageData.usage.extracts?.length || 0;
  const workflowCount = usageData.usage.workflows?.length || 0;

  return (
    <div
      className="relative inline-flex items-center gap-1"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* Usage Chips */}
      {chatCount > 0 && (
        <div className="flex items-center gap-0.5 px-1.5 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-xs font-medium">
          <MessageSquare className="w-3 h-3" />
          <span>{chatCount}</span>
        </div>
      )}

      {extractCount > 0 && (
        <div className="flex items-center gap-0.5 px-1.5 py-0.5 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded text-xs font-medium">
          <FileText className="w-3 h-3" />
          <span>{extractCount}</span>
        </div>
      )}

      {workflowCount > 0 && (
        <div className="flex items-center gap-0.5 px-1.5 py-0.5 bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 rounded text-xs font-medium">
          <Workflow className="w-3 h-3" />
          <span>{workflowCount}</span>
        </div>
      )}

      {/* Hover Tooltip */}
      {isHovered && (
        <div className="absolute z-50 bottom-full right-0 mb-2 p-3 bg-popover border border-border rounded-lg shadow-lg min-w-[250px]">
          <div className="text-xs font-semibold text-foreground mb-2">
            Document Usage
          </div>

          {/* Chat Sessions */}
          {chatCount > 0 && (
            <div className="mb-2">
              <div className="text-xs font-medium text-muted-foreground mb-1">
                💬 Chat Sessions ({chatCount})
              </div>
              <div className="space-y-0.5">
                {usageData.usage.chat_sessions.slice(0, 3).map((session) => (
                  <div
                    key={session.session_id}
                    className="text-xs text-foreground truncate pl-2"
                  >
                    • {session.title}
                  </div>
                ))}
                {chatCount > 3 && (
                  <div className="text-xs text-muted-foreground italic pl-2">
                    + {chatCount - 3} more
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Extracts */}
          {extractCount > 0 && (
            <div className="mb-2">
              <div className="text-xs font-medium text-muted-foreground mb-1">
                📝 Extractions ({extractCount})
              </div>
              <div className="text-xs text-foreground pl-2">
                {extractCount} extraction
                {extractCount !== 1 ? "s" : ""} performed
              </div>
            </div>
          )}

          {/* Workflows */}
          {workflowCount > 0 && (
            <div>
              <div className="text-xs font-medium text-muted-foreground mb-1">
                ⚙️ Workflows ({workflowCount})
              </div>
              <div className="space-y-0.5">
                {usageData.usage.workflows.slice(0, 3).map((workflow) => (
                  <div
                    key={workflow.run_id}
                    className="text-xs text-foreground truncate pl-2"
                  >
                    • {workflow.workflow_name}
                  </div>
                ))}
                {workflowCount > 3 && (
                  <div className="text-xs text-muted-foreground italic pl-2">
                    + {workflowCount - 3} more
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Triangle pointer */}
          <div className="absolute top-full right-4 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-border" />
          <div className="absolute top-full right-4 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-popover" style={{ marginTop: '-1px' }} />
        </div>
      )}
    </div>
  );
}
