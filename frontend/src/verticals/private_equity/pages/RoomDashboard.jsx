/**
 * RoomDashboard — Room overview: metric cards, doc type breakdown, AI summary.
 * Route: /app/pe/rooms/:roomId/dashboard
 */

import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { FileText, Flag, CheckSquare, BarChart3, AlertCircle } from "lucide-react";
import { useAppAuth } from "@/hooks/useAppAuth";
import PELayout from "./PELayout";
import { getRoom, getRoomSummary, listInvestigations, listRoomDocuments } from "../../../api/pe-diligence";

// ─── Metric card ─────────────────────────────────────────────────────────────

function MetricCard({ icon: Icon, iconBg, label, value, sub }) {
  return (
    <div className="pe-metric-card">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${iconBg}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</p>
        <p className="text-2xl font-black mt-0.5">{value}</p>
        {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

// ─── Status badge ─────────────────────────────────────────────────────────────

const STATUS_STYLES = {
  completed: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  running:   "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  failed:    "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  draft:     "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
};

function StatusBadge({ status }) {
  const style = STATUS_STYLES[status] || STATUS_STYLES.draft;
  return (
    <span className={`text-xs px-2.5 py-1 rounded-full font-semibold capitalize ${style}`}>
      {status || "draft"}
    </span>
  );
}

// ─── Doc type pill ────────────────────────────────────────────────────────────

function DocTypePill({ label, count }) {
  const formatted = label.replace(/_/g, " ");
  return (
    <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-muted/50 border">
      <span className="text-sm capitalize text-foreground">{formatted}</span>
      <span className="text-sm font-semibold">{count}</span>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function RoomDashboard() {
  const { roomId } = useParams();
  const { getToken } = useAppAuth();

  const [room, setRoom]                   = useState(null);
  const [summary, setSummary]             = useState(null);
  const [investigations, setInvestigations] = useState([]);
  const [docTypeCounts, setDocTypeCounts] = useState({});
  const [loading, setLoading]             = useState(true);
  const [error, setError]                 = useState(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      getRoom(getToken, roomId),
      getRoomSummary(getToken, roomId).catch(() => null),
      listInvestigations(getToken, roomId).catch(() => []),
      listRoomDocuments(getToken, roomId).catch(() => []),
    ])
      .then(([roomData, summaryData, invData, docsData]) => {
        setRoom(roomData);
        setSummary(summaryData);
        setInvestigations(invData);
        // Derive doc type breakdown from classified documents
        const counts = {};
        docsData.forEach((d) => {
          if (d.document_type) counts[d.document_type] = (counts[d.document_type] || 0) + 1;
        });
        setDocTypeCounts(counts);
      })
      .catch((err) => setError(err.message || "Failed to load room"))
      .finally(() => setLoading(false));
  }, [roomId]);

  // Best coverage score from completed investigations
  const bestInv = investigations
    .filter((i) => i.status === "completed" && i.coverage_score != null)
    .sort((a, b) => b.coverage_score - a.coverage_score)[0];

  return (
    <PELayout>
      <div className="pe-page min-h-full">
        {loading && <p className="text-sm text-muted-foreground">Loading…</p>}

        {error && (
          <div className="flex items-center gap-2 border border-destructive/30 bg-destructive/10 text-destructive rounded-lg p-3 text-sm mb-4">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        {!loading && room && (
          <>
            {/* Header */}
            <div className="pe-header mb-4">
              <div>
                <h1 className="pe-title font-display">{room.name}</h1>
                {room.target_company && (
                  <p className="pe-subtitle mt-0.5">Target: {room.target_company}</p>
                )}
              </div>
              <StatusBadge status={room.status} />
            </div>

            {/* Metric cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
              <MetricCard
                icon={FileText}
                iconBg="bg-primary/10 text-primary"
                label="Documents"
                value={room.documents_count ?? 0}
              />
              <MetricCard
                icon={Flag}
                iconBg="bg-red-500/10 text-red-500"
                label="Open Flags"
                value={room.open_flags_count ?? 0}
                sub={room.open_flags_count > 0 ? "Requires review" : "All clear"}
              />
              <MetricCard
                icon={CheckSquare}
                iconBg="bg-blue-500/10 text-blue-500"
                label="Checklist"
                value={`${Math.round(room.checklist_completion_pct ?? 0)}%`}
                sub="items covered"
              />
              <MetricCard
                icon={BarChart3}
                iconBg="bg-green-500/10 text-green-500"
                label="Coverage"
                value={bestInv ? `${Math.round(bestInv.coverage_score * 100)}%` : "—"}
                sub={bestInv ? `${bestInv.coverage_status} (best investigation)` : "No investigations yet"}
              />
            </div>

            {/* Lower grid: doc types + summary */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Document type breakdown */}
              <div className="pe-card p-4">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-sm font-bold">Document Types</h2>
                  <Link
                    to={`/app/pe/rooms/${roomId}/documents`}
                    className="text-xs text-primary hover:underline"
                  >
                    View all →
                  </Link>
                </div>
                {Object.keys(docTypeCounts).length > 0 ? (
                  <div className="space-y-2">
                    {Object.entries(docTypeCounts)
                      .sort(([, a], [, b]) => b - a)
                      .map(([type, count]) => (
                        <DocTypePill key={type} label={type} count={count} />
                      ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground text-center py-6">
                    Run analysis to see document breakdown.
                  </p>
                )}
              </div>

              {/* AI Summary */}
              <div className="pe-card p-4">
                <h2 className="text-sm font-bold mb-3">AI Summary</h2>
                {summary?.content_markdown ? (
                  <div
                    className="text-sm leading-relaxed text-foreground prose prose-sm dark:prose-invert max-w-none"
                    dangerouslySetInnerHTML={{ __html: mdToHtml(summary.content_markdown) }}
                  />
                ) : (
                  <div className="text-center py-6">
                    <p className="text-sm text-muted-foreground">
                      No summary yet.
                    </p>
                    <Link
                      to={`/app/pe/rooms/${roomId}/documents`}
                      className="text-xs text-primary hover:underline mt-1 inline-block"
                    >
                      Run analysis from the Documents page →
                    </Link>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </PELayout>
  );
}

/**
 * Minimal markdown-to-HTML converter for summary display.
 * Only handles: **bold**, *italic*, # headings, - lists, line breaks.
 * Safe — no XSS vectors since content comes from our own API.
 */
function mdToHtml(md) {
  return md
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/^### (.+)$/gm, "<h3 class='font-bold mt-3 mb-1'>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2 class='font-bold text-base mt-4 mb-1'>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1 class='font-bold text-lg mt-4 mb-2'>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/^- (.+)$/gm, "<li class='ml-4 list-disc'>$1</li>")
    .replace(/\n\n/g, "<br/><br/>")
    .replace(/\n/g, "<br/>");
}
