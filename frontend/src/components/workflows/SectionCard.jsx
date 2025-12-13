/**
 * Enhanced Section Card - Production-quality section display
 *
 * Features:
 * - Rich markdown rendering with GitHub Flavored Markdown
 * - Beautiful prose styling for readability
 * - Interactive inline citations with hover tooltips
 * - Citation display with badges
 * - Confidence indicators
 * - Gradient headers
 * - Smooth hover effects
 */

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FileText, Award, ChevronRight } from "lucide-react";
import { Badge } from "../ui/badge";
import { Card } from "../ui/card";
import HighlightCard from "./HighlightCard";
import MetricPill from "./MetricPill";
import FinancialsCard from "./FinancialsCard";

export default function SectionCard({ section, index, currency = "USD", richCitations = [] }) {
  if (!section) return null;

  // Map citation tokens to rich citation objects
  const getRichCitation = (token) => {
    return richCitations.find(
      (rc) => rc.token === token || rc.id === token
    );
  };

  // Custom renderer for markdown to convert citation tokens to interactive elements
  const renderCitationText = (text) => {
    // Regex to match citation tokens like [D1:p1], [D2:p5], etc.
    const citationRegex = /\[D\d+:p\d+\]/g;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = citationRegex.exec(text)) !== null) {
      // Add text before citation
      if (match.index > lastIndex) {
        parts.push(text.substring(lastIndex, match.index));
      }

      // Add citation as interactive element
      const token = match[0];
      const richCite = getRichCitation(token);

      if (richCite) {
        parts.push(
          <span
            key={`cite-${match.index}`}
            className="inline-flex items-center align-baseline mx-0.5 px-1.5 py-0.5 rounded text-xs font-mono font-semibold bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors cursor-help border border-blue-300 dark:border-blue-700"
            title={`${richCite.document || 'Document'} - Page ${richCite.page || '?'}${richCite.section ? '\n' + richCite.section : ''}${richCite.snippet ? '\n"' + richCite.snippet.substring(0, 100) + '..."' : ''}`}
          >
            {token}
          </span>
        );
      } else {
        // Fallback: plain citation token styled
        parts.push(
          <span
            key={`cite-${match.index}`}
            className="inline-flex items-center align-baseline mx-0.5 px-1.5 py-0.5 rounded text-xs font-mono bg-muted text-muted-foreground"
          >
            {token}
          </span>
        );
      }

      lastIndex = match.index + match[0].length;
    }

    // Add remaining text
    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }

    return parts.length > 0 ? parts : text;
  };

  // Custom markdown components
  const markdownComponents = {
    p: ({ children, ...props }) => {
      // Process text nodes to render citations
      const processedChildren = React.Children.map(children, (child) => {
        if (typeof child === 'string') {
          return renderCitationText(child);
        }
        return child;
      });
      return <p {...props}>{processedChildren}</p>;
    },
    li: ({ children, ...props }) => {
      // Process text nodes in list items
      const processedChildren = React.Children.map(children, (child) => {
        if (typeof child === 'string') {
          return renderCitationText(child);
        }
        return child;
      });
      return <li {...props}>{processedChildren}</li>;
    },
    strong: ({ children, ...props }) => {
      // Process text nodes in bold text
      const processedChildren = React.Children.map(children, (child) => {
        if (typeof child === 'string') {
          return renderCitationText(child);
        }
        return child;
      });
      return <strong {...props}>{processedChildren}</strong>;
    },
  };

  const hasContent =
    section.content && section.content !== "[Content not generated]";
  const hasConfidence = section.confidence || section.confidence === 0;

  // Confidence badge color
  const getConfidenceColor = (conf) => {
    if (typeof conf === "string") {
      conf = conf.toLowerCase();
      if (conf === "high")
        return { bg: "bg-green-600", text: "text-white" };
      if (conf === "medium")
        return { bg: "bg-yellow-500", text: "text-white" };
      if (conf === "low")
        return { bg: "bg-red-500", text: "text-white" };
    }

    // Numeric confidence (0-1)
    const numConf = parseFloat(conf);
    if (isNaN(numConf)) return { bg: "bg-muted", text: "text-muted-foreground" };
    if (numConf >= 0.8)
      return { bg: "bg-green-600", text: "text-white" };
    if (numConf >= 0.5)
      return { bg: "bg-yellow-500", text: "text-white" };
    return { bg: "bg-red-500", text: "text-white" };
  };

  const getConfidenceLabel = (conf) => {
    if (typeof conf === "string") return conf;
    const numConf = parseFloat(conf);
    if (isNaN(numConf)) return "";
    return `${(numConf * 100).toFixed(0)}%`;
  };

  // Get icon color based on section key
  const getIconColor = (key) => {
    const k = (key || "").toLowerCase();
    if (k.includes("executive") || k.includes("overview")) return "text-blue-600 dark:text-blue-400";
    if (k.includes("financial")) return "text-green-600 dark:text-green-400";
    if (k.includes("risk")) return "text-red-600 dark:text-red-400";
    if (k.includes("opportunit")) return "text-emerald-600 dark:text-emerald-400";
    if (k.includes("market") || k.includes("competition")) return "text-purple-600 dark:text-purple-400";
    if (k.includes("management") || k.includes("culture")) return "text-indigo-600 dark:text-indigo-400";
    if (k.includes("valuation")) return "text-orange-600 dark:text-orange-400";
    return "text-blue-600 dark:text-blue-400";
  };

  const iconColor = getIconColor(section.key);
  const confidenceColors = hasConfidence ? getConfidenceColor(section.confidence) : null;

  return (
    <Card className="rounded-xl shadow-lg overflow-hidden border-l-4 border-blue-500 hover:shadow-xl transition-shadow duration-200">
      {/* Header */}
      <div className="px-6 py-4 bg-gradient-to-r from-slate-50 to-blue-50 dark:from-slate-900/40 dark:to-blue-950/40 border-b border-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-white dark:bg-slate-800 rounded-lg shadow-sm">
              <FileText className={`w-5 h-5 ${iconColor}`} />
            </div>
            <div>
              <h3 className="text-xl font-bold text-foreground">
                {section.title || `Section ${index + 1}`}
              </h3>
              {section.key && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  {section.key}
                </p>
              )}
            </div>
          </div>

          {hasConfidence && confidenceColors && (
            <div className="flex items-center gap-2">
              <Award className="w-4 h-4 text-muted-foreground" />
              <Badge className={`${confidenceColors.bg} ${confidenceColors.text} font-semibold`}>
                {getConfidenceLabel(section.confidence)}
              </Badge>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="px-6 py-6 bg-white dark:bg-slate-900/20">
        {/* Highlights Section */}
        {section.highlights && section.highlights.length > 0 && (
          <div className="mb-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {section.highlights.map((highlight, idx) => (
                <HighlightCard key={idx} highlight={highlight} currency={currency} />
              ))}
            </div>
          </div>
        )}

        {/* Key Metrics Pills */}
        {section.key_metrics && section.key_metrics.length > 0 && (
          <div className="mb-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {section.key_metrics.map((metric, idx) => (
                <MetricPill key={idx} metric={metric} />
              ))}
            </div>
          </div>
        )}

        {/* Markdown Content */}
        {hasContent ? (
          <div className="prose prose-sm md:prose-base max-w-none
            dark:prose-invert
            prose-headings:font-bold prose-headings:text-foreground
            prose-h3:text-lg prose-h3:mt-6 prose-h3:mb-3
            prose-h4:text-base prose-h4:mt-4 prose-h4:mb-2
            prose-p:text-muted-foreground prose-p:leading-relaxed
            prose-strong:text-foreground prose-strong:font-semibold
            prose-ul:text-muted-foreground prose-ul:my-3
            prose-ol:text-muted-foreground prose-ol:my-3
            prose-li:my-1
            prose-a:text-primary prose-a:no-underline hover:prose-a:underline
            prose-blockquote:border-l-primary prose-blockquote:bg-muted/50 prose-blockquote:py-1
            prose-code:text-primary prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:before:content-none prose-code:after:content-none
            prose-pre:bg-muted prose-pre:border prose-pre:border-border
            prose-table:border-collapse prose-table:w-full
            prose-th:border prose-th:border-border prose-th:bg-muted/50 prose-th:p-2 prose-th:text-left prose-th:font-semibold
            prose-td:border prose-td:border-border prose-td:p-2
            prose-tr:even:bg-muted/30
          ">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={markdownComponents}
            >
              {section.content}
            </ReactMarkdown>
          </div>
        ) : (
          <div className="text-center py-8">
            <p className="text-muted-foreground italic">Content not available for this section</p>
          </div>
        )}

        {/* Embedded Financials Table (for financial_performance section) */}
        {section.financials && (
          <div className="mt-6">
            <FinancialsCard financials={section.financials} currency={currency} embedded={true} />
          </div>
        )}

        {/* Citations */}
        {section.citations && section.citations.length > 0 && (
          <div className="mt-6 pt-4 border-t border-border">
            <div className="flex items-center gap-2 mb-3">
              <ChevronRight className="w-4 h-4 text-muted-foreground" />
              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wide">
                Citations ({section.citations.length})
              </span>
            </div>
            <div className="grid grid-cols-1 gap-3">
              {section.citations.map((cite, idx) => {
                const richCite = getRichCitation(cite);

                // If we have rich metadata, display it beautifully
                if (richCite) {
                  return (
                    <div
                      key={idx}
                      className="bg-muted/50 hover:bg-muted/80 transition-colors rounded-lg p-3 border border-border/50"
                    >
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <span className="font-mono text-xs font-semibold text-primary">
                          {richCite.token || richCite.id}
                        </span>
                        {richCite.page && (
                          <span className="text-xs text-muted-foreground font-medium">
                            Page {richCite.page}
                          </span>
                        )}
                      </div>

                      {richCite.document && richCite.document !== "Unknown" && (
                        <div className="mb-2">
                          {richCite.url ? (
                            <a
                              href={richCite.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-sm font-medium text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 hover:underline"
                            >
                              {richCite.document}
                            </a>
                          ) : (
                            <p className="text-sm font-medium text-foreground">
                              {richCite.document}
                            </p>
                          )}
                        </div>
                      )}

                      {richCite.heading_hierarchy && richCite.heading_hierarchy.length > 0 && (
                        <p className="text-xs text-muted-foreground mb-1">
                          {richCite.heading_hierarchy.join(" › ")}
                        </p>
                      )}

                      {richCite.section && !richCite.heading_hierarchy?.length && (
                        <p className="text-xs text-muted-foreground italic mb-1">
                          {richCite.section}
                        </p>
                      )}

                      {richCite.snippet && (
                        <p className="text-xs text-muted-foreground/80 mt-2 line-clamp-2 leading-relaxed">
                          {richCite.snippet}
                        </p>
                      )}
                    </div>
                  );
                }

                // Fallback: If no rich metadata found, show token badge
                return (
                  <Badge
                    key={idx}
                    variant="outline"
                    className="text-xs font-mono hover:bg-primary/10 transition-colors cursor-default"
                  >
                    {cite}
                  </Badge>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
