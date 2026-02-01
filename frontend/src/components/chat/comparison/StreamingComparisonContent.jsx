/**
 * StreamingComparisonContent Component
 *
 * Renders streaming markdown with styled citations during streaming.
 * Citations are styled but not clickable to avoid race conditions during streaming.
 *
 * After streaming completes, citations become clickable in the final ComparisonMessage.
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import React from "react";

/**
 * Render citations as styled badges but not clickable during streaming
 */
function renderStreamingCitations(text) {
  if (!text) return text;

  const citationRegex = /\[D\d+:p\d+\]/g;
  const parts = [];
  let lastIndex = 0;
  let match;

  while ((match = citationRegex.exec(text)) !== null) {
    // Add text before citation
    if (match.index > lastIndex) {
      parts.push(text.substring(lastIndex, match.index));
    }
    // Add styled citation badge (non-clickable)
    parts.push(
      <span
        key={`cite-${match.index}`}
        className="inline-flex items-center mx-0.5 px-1.5 py-0.5 rounded text-xs font-mono font-semibold
          bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300
          border border-blue-300 dark:border-blue-700"
      >
        {match[0]}
      </span>
    );
    lastIndex = match.index + match[0].length;
  }

  // Add remaining text
  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex));
  }

  return parts.length > 0 ? parts : text;
}

/**
 * Custom markdown components for streaming content
 */
const streamingComponents = {
  p: ({ children, ...props }) => {
    const processed = React.Children.map(children, (child) =>
      typeof child === "string" ? renderStreamingCitations(child) : child
    );
    return <p {...props}>{processed}</p>;
  },
  td: ({ children, ...props }) => {
    const processed = React.Children.map(children, (child) =>
      typeof child === "string" ? renderStreamingCitations(child) : child
    );
    return <td {...props}>{processed}</td>;
  },
  th: ({ children, ...props }) => {
    const processed = React.Children.map(children, (child) =>
      typeof child === "string" ? renderStreamingCitations(child) : child
    );
    return <th {...props}>{processed}</th>;
  },
  li: ({ children, ...props }) => {
    const processed = React.Children.map(children, (child) =>
      typeof child === "string" ? renderStreamingCitations(child) : child
    );
    return <li {...props}>{processed}</li>;
  },
  strong: ({ children, ...props }) => {
    const processed = React.Children.map(children, (child) =>
      typeof child === "string" ? renderStreamingCitations(child) : child
    );
    return <strong {...props}>{processed}</strong>;
  },
};

export default function StreamingComparisonContent({ content }) {
  if (!content) return null;

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={streamingComponents}
    >
      {content}
    </ReactMarkdown>
  );
}
