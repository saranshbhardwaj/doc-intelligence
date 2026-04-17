/**
 * RoomDashboard — Room overview: KPI strip, circular score gauge, doc type bars,
 * findings severity breakdown, recent investigations, AI summary.
 * Route: /app/pe/rooms/:roomId/dashboard
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import {
  FileText, Flag, AlertTriangle, Layers,
  CheckSquare, AlertCircle, BarChart3, ChevronRight,
} from "lucide-react";
import { useAppAuth } from "@/hooks/useAppAuth";
import PELayout from "./PELayout";
import { getRoomSummary, listInvestigations, getRoomFindings } from "../../../api/pe-diligence";
import { mdToHtml } from "../constants";
import { usePeDiligence } from "../../../store";

// ─── Circular progress gauge ──────────────────────────────────────────────────

const CIRCUMFERENCE = 2 * Math.PI * 52; // r=52 → 326.7

function CircularGauge({ pct, label }) {
  const offset = CIRCUMFERENCE * (1 - (pct || 0) / 100);
  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative flex items-center justify-center">
        <svg className="w-36 h-36 -rotate-90" viewBox="0 0 120 120">
          <circle
            cx="60" cy="60" r="52" fill="none"
            stroke="hsl(var(--muted))" strokeWidth="10"
          />
          <circle
            cx="60" cy="60" r="52" fill="none"
            stroke="hsl(var(--primary))" strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={offset}
            style={{ transition: "stroke-dashoffset 0.6s ease" }}
          />
        </svg>
        <div className="absolute flex flex-col items-center">
          <span className="text-3xl font-black text-foreground">{pct}%</span>
          <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-0.5">
            {label}
          </span>
        </div>
      </div>
    </div>
  );
}

// ─── KPI item ─────────────────────────────────────────────────────────────────

// eslint-disable-next-line no-unused-vars
function KpiItem({ icon: Icon, iconBg, iconColor, label, value, sub, danger }) {
  return (
    <div className="pe-kpi-item">
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${iconBg}`}>
        <Icon className={`w-4.5 h-4.5 ${iconColor}`} />
      </div>
      <div className="mt-1">
        <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{label}</p>
        <p className={`font-display text-2xl font-black mt-0.5 ${danger ? "text-red-500" : "text-foreground"}`} style={{letterSpacing: '-0.02em'}}>{value}</p>
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

// ─── Doc type row with progress bar ──────────────────────────────────────────

function DocTypeRow({ label, count, total }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  const formatted = label.replace(/_/g, " ");
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs capitalize text-foreground">{formatted}</span>
        <span className="text-xs font-semibold text-muted-foreground">{count}</span>
      </div>
      <div className="w-full bg-muted rounded-full h-1.5">
        <div
          className="bg-primary h-1.5 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ─── Severity bar row ─────────────────────────────────────────────────────────

function SeverityRow({ label, count, total, colorClass, barColor }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className={`text-xs font-semibold ${colorClass}`}>{label}</span>
        <span className="text-xs font-bold text-foreground">{count}</span>
      </div>
      <div className="w-full bg-muted rounded-full h-1.5">
        <div className={`${barColor} h-1.5 rounded-full transition-all duration-500`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function RoomDashboard() {
  const { roomId } = useParams();
  const { getToken } = useAppAuth();

  const peDiligence = usePeDiligence();
  const room = peDiligence.room;

  const docTypeCounts = useMemo(() => {
    const counts = {};
    peDiligence.documents.forEach((d) => {
      const t = d.metadata?.document_classification?.document_type;
      if (t) counts[t] = (counts[t] || 0) + 1;
    });
    return counts;
  }, [peDiligence.documents]);

  const totalDocs = Object.values(docTypeCounts).reduce((a, b) => a + b, 0);

  const [summary, setSummary]             = useState(null);
  const [investigations, setInvestigations] = useState([]);
  const [findings, setFindings]           = useState([]);
  const [loading, setLoading]             = useState(true);
  const [error, setError]                 = useState(null);

  const loadData = useCallback(() => {
    setLoading(true);
    Promise.all([
      getRoomSummary(getToken, roomId).catch(() => null),
      listInvestigations(getToken, roomId).catch(() => []),
      getRoomFindings(getToken, roomId).catch(() => []),
    ])
      .then(([summaryData, invData, findingsData]) => {
        setSummary(summaryData);
        setInvestigations(invData || []);
        setFindings(findingsData || []);
      })
      .catch((err) => setError(err.message || "Failed to load room"))
      .finally(() => setLoading(false));
  }, [getToken, roomId]);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    if (peDiligence.analysisCompletedAt) loadData();
  }, [peDiligence.analysisCompletedAt]); // eslint-disable-line react-hooks/exhaustive-deps

  // Derived metrics
  const openFindings = findings.filter((f) => f.status === "open");
  const highCount   = openFindings.filter((f) => f.severity === "high").length;
  const medCount    = openFindings.filter((f) => f.severity === "medium").length;
  const lowCount    = openFindings.filter((f) => f.severity === "low").length;
  const totalOpen   = openFindings.length;

  const completionPct = Math.round(room?.checklist_completion_pct ?? 0);

  const bestInv = investigations
    .filter((i) => i.status === "completed" && i.coverage_score != null)
    .sort((a, b) => b.coverage_score - a.coverage_score)[0];

  const recentInvestigations = [...investigations]
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    .slice(0, 3);

  const uniqueDocTypes = Object.keys(docTypeCounts).length;

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
            <div className="pe-header mb-5">
              <div>
                <h1 className="pe-title font-display">{room.name}</h1>
                {room.target_company && (
                  <p className="pe-subtitle mt-0.5">Target: {room.target_company}</p>
                )}
              </div>
              <StatusBadge status={room.status} />
            </div>

            {/* KPI strip */}
            <div className="pe-kpi-row">
              <KpiItem
                icon={FileText}
                iconBg="bg-primary/10"
                iconColor="text-primary"
                label="Documents"
                value={room.documents_count ?? 0}
              />
              <KpiItem
                icon={Layers}
                iconBg="bg-primary/10"
                iconColor="text-primary"
                label="Doc Types"
                value={uniqueDocTypes || "—"}
                sub={uniqueDocTypes > 0 ? "classified" : "run analysis"}
              />
              <KpiItem
                icon={Flag}
                iconBg={room.open_flags_count > 0 ? "bg-red-500/10" : "bg-muted"}
                iconColor={room.open_flags_count > 0 ? "text-red-500" : "text-muted-foreground"}
                label="Open Flags"
                value={room.open_flags_count ?? 0}
                sub={room.open_flags_count > 0 ? "Requires review" : "All clear"}
                danger={room.open_flags_count > 0}
              />
              <KpiItem
                icon={CheckSquare}
                iconBg="bg-blue-500/10"
                iconColor="text-blue-500"
                label="Checklist"
                value={`${completionPct}%`}
                sub="items covered"
              />
              <KpiItem
                icon={AlertTriangle}
                iconBg={highCount > 0 ? "bg-red-500/10" : "bg-muted"}
                iconColor={highCount > 0 ? "text-red-500" : "text-muted-foreground"}
                label="High Findings"
                value={highCount}
                sub={highCount > 0 ? "Open, needs action" : "No high severity"}
                danger={highCount > 0}
              />
            </div>

            {/* Lower grid: left col (doc types + summary) | right col (gauge + investigations) */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Left col */}
              <div className="flex flex-col gap-4">
                {/* Document type breakdown */}
                <div className="pe-card p-4">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="font-display text-sm font-bold">Document Types</h2>
                    <Link
                      to={`/app/pe/rooms/${roomId}/documents`}
                      className="text-xs text-primary hover:underline"
                    >
                      View all →
                    </Link>
                  </div>
                  {Object.keys(docTypeCounts).length > 0 ? (
                    <div className="space-y-3">
                      {Object.entries(docTypeCounts)
                        .sort(([, a], [, b]) => b - a)
                        .map(([type, count]) => (
                          <DocTypeRow key={type} label={type} count={count} total={totalDocs} />
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
                      className="text-sm leading-relaxed text-foreground prose prose-sm dark:prose-invert max-w-none max-h-48 overflow-y-auto scrollbar-thin"
                      dangerouslySetInnerHTML={{ __html: mdToHtml(summary.content_markdown) }}
                    />
                  ) : (
                    <div className="text-center py-6">
                      <p className="text-sm text-muted-foreground">No summary yet.</p>
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

              {/* Right col */}
              <div className="flex flex-col gap-4">
                {/* Circular gauge + severity breakdown */}
                <div className="pe-card p-5 flex flex-col items-center gap-4">
                  <h2 className="text-sm font-bold self-start">Diligence Score</h2>
                  <CircularGauge pct={completionPct} label="Checklist" />

                  {/* Severity rows */}
                  {totalOpen > 0 ? (
                    <div className="w-full space-y-2.5 border-t pt-4 mt-1">
                      <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">
                        Open Findings by Severity
                      </p>
                      <SeverityRow label="High" count={highCount} total={totalOpen} colorClass="text-red-600 dark:text-red-400" barColor="bg-red-500" />
                      <SeverityRow label="Medium" count={medCount} total={totalOpen} colorClass="text-yellow-600 dark:text-yellow-400" barColor="bg-yellow-500" />
                      <SeverityRow label="Low" count={lowCount} total={totalOpen} colorClass="text-blue-600 dark:text-blue-400" barColor="bg-blue-500" />
                    </div>
                  ) : (
                    findings.length > 0 ? (
                      <p className="text-xs text-green-600 dark:text-green-400 font-medium">
                        All findings resolved ✓
                      </p>
                    ) : (
                      <p className="text-xs text-muted-foreground">No findings yet — run analysis.</p>
                    )
                  )}

                  {bestInv && (
                    <div className="w-full border-t pt-3 mt-1 flex items-center justify-between">
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                          Best Coverage
                        </p>
                        <p className="text-sm font-semibold mt-0.5">
                          {Math.round(bestInv.coverage_score * 100)}%
                          <span className="text-xs text-muted-foreground font-normal ml-1.5">
                            {bestInv.coverage_status}
                          </span>
                        </p>
                      </div>
                      <Link
                        to={`/app/pe/rooms/${roomId}/investigations`}
                        className="flex items-center gap-1 text-xs text-primary hover:underline"
                      >
                        <BarChart3 className="w-3 h-3" />
                        Investigations
                      </Link>
                    </div>
                  )}
                </div>

                {/* Recent investigations */}
                {recentInvestigations.length > 0 && (
                  <div className="pe-card p-4">
                    <div className="flex items-center justify-between mb-3">
                      <h2 className="font-display text-sm font-bold">Recent Investigations</h2>
                      <Link
                        to={`/app/pe/rooms/${roomId}/investigations`}
                        className="text-xs text-primary hover:underline"
                      >
                        All →
                      </Link>
                    </div>
                    <div className="space-y-2">
                      {recentInvestigations.map((inv) => (
                        <Link
                          key={inv.id}
                          to={`/app/pe/rooms/${roomId}/investigations/${inv.id}`}
                          className="flex items-center justify-between px-3 py-2.5 rounded-lg hover:bg-muted/40 transition-colors border border-border/50 group"
                        >
                          <div className="min-w-0">
                            <p className="text-xs font-semibold truncate text-foreground">
                              {inv.name || "Investigation"}
                            </p>
                            {inv.coverage_score != null && (
                              <p className="text-[10px] text-muted-foreground mt-0.5">
                                {Math.round(inv.coverage_score * 100)}% coverage
                              </p>
                            )}
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <StatusBadge status={inv.status} />
                            <ChevronRight className="w-3.5 h-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                          </div>
                        </Link>
                      ))}
                    </div>
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
