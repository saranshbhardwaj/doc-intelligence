/**
 * Section Card - Renders a workflow section with Markdown content
 *
 * Features:
 * - Markdown rendering with GitHub Flavored Markdown
 * - Citation display
 * - Confidence indicator
 * - Beautiful formatting
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FileText, Award } from "lucide-react";

export default function SectionCard({ section, index }) {
  if (!section) return null;

  const hasContent =
    section.content && section.content !== "[Content not generated]";
  const hasConfidence = section.confidence || section.confidence === 0;

  // Confidence badge color
  const getConfidenceColor = (conf) => {
    if (typeof conf === "string") {
      conf = conf.toLowerCase();
      if (conf === "high")
        return "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200";
      if (conf === "medium")
        return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200";
      if (conf === "low")
        return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
    }

    // Numeric confidence (0-1)
    const numConf = parseFloat(conf);
    if (isNaN(numConf)) return "bg-popover text-muted-foreground";
    if (numConf >= 0.8)
      return "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200";
    if (numConf >= 0.5)
      return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200";
    return "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
  };

  const getConfidenceLabel = (conf) => {
    if (typeof conf === "string") return conf;
    const numConf = parseFloat(conf);
    if (isNaN(numConf)) return "";
    return `${(numConf * 100).toFixed(0)}%`;
  };

  return (
    <div className="bg-card rounded-xl shadow-md overflow-hidden border-l-4 border-blue-500">
      {/* Header */}
      <div className="px-6 py-4 bg-gradient-to-r from-blue-50 to-white dark:from-blue-900/30 dark:to-gray-800 border-b border-border dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <FileText className="w-6 h-6 text-blue-600 dark:text-blue-400" />
            <h3 className="text-xl font-bold text-foreground">
              {section.title || `Section ${index + 1}`}
            </h3>
          </div>

          {hasConfidence && (
            <div className="flex items-center gap-2">
              <Award className="w-4 h-4 text-muted-foreground" />
              <span
                className={`text-xs font-semibold px-2 py-1 rounded-full ${getConfidenceColor(
                  section.confidence
                )}`}
              >
                {getConfidenceLabel(section.confidence)}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="px-6 py-5">
        {hasContent ? (
          <div className="prose prose-sm max-w-none dark:prose-invert prose-headings:text-foreground dark:prose-headings:text-foreground prose-p:text-muted-foreground dark:prose-p:text-gray-300 prose-strong:text-foreground dark:prose-strong:text-foreground prose-ul:text-muted-foreground dark:prose-ul:text-gray-300 prose-ol:text-muted-foreground dark:prose-ol:text-gray-300">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {section.content}
            </ReactMarkdown>
          </div>
        ) : (
          <p className="text-muted-foreground italic">Content not available</p>
        )}

        {/* Citations */}
        {section.citations && section.citations.length > 0 && (
          <div className="mt-6 pt-4 border-t border-border dark:border-gray-700">
            <div className="text-xs font-semibold text-muted-foreground dark:text-muted-foreground uppercase tracking-wide mb-2">
              Citations
            </div>
            <div className="flex flex-wrap gap-2">
              {section.citations.map((cite, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center px-2 py-1 rounded text-xs font-mono bg-popover text-muted-foreground dark:bg-gray-700 dark:text-gray-300"
                >
                  {cite}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
