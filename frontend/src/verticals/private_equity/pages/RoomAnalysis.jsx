/**
 * RoomAnalysis — Executive summary, Room Overview + By Document tabs,
 * clickable citations with PDF side panel.
 * Route: /app/pe/rooms/:roomId/analysis
 */

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import {
  CheckCircle2, AlertTriangle, XCircle, AlertCircle, Shield,
  ChevronDown, ChevronUp, FileText, X, BarChart3, Flag,
  CheckSquare, RefreshCw, ChevronRight, Link2, Play, Sparkles,
} from "lucide-react";
import { useAppAuth } from "@/hooks/useAppAuth";
import PELayout from "./PELayout";
import PDFViewer from "../../../components/pdf/PDFViewer";
import {
  getRoomChecklist, getRoomFindings, getRoomSummary,
  updateFinding, listRoomDocuments, startAnalysis, getRoom,
  generateICMemo, listRoomClauses,
} from "../../../api/pe-diligence";
import { getDocumentDownloadUrl } from "../../../api/documents";

// ─── Constants ───────────────────────────────────────────────────────────────

const CHECKLIST_STATUS = {
  covered: { icon: CheckCircle2, color: "text-green-500", label: "Covered" },
  partial: { icon: AlertTriangle, color: "text-yellow-500", label: "Partial" },
  missing: { icon: XCircle, color: "text-red-500", label: "Missing" },
};

const SEVERITY_STYLES = {
  high:   "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 border-red-200 dark:border-red-800",
  medium: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400 border-yellow-200 dark:border-yellow-800",
  low:    "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 border-blue-200 dark:border-blue-800",
};

const FINDING_STATUS_STYLES = {
  open:      "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
  resolved:  "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  dismissed: "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500",
};

const DOC_TYPE_LABELS = {
  offering_memorandum: "CIM / OM",
  financial_statement: "Financials",
  purchase_agreement: "SPA",
  qoe_report: "QoE Report",
  legal_contract: "Contract",
  amendment: "Amendment",
  other: "Other",
};

const DOC_TYPE_COLORS = {
  offering_memorandum: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  financial_statement: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  purchase_agreement: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  qoe_report: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400",
  legal_contract: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  amendment: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400",
  other: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
};

// ─── Minimal markdown renderer ──────────────────────────────────────────────

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

// ─── Citation badge ──────────────────────────────────────────────────────────

function CitationBadge({ span, docName, onCitationClick }) {
  if (!span?.source_document_id || !span?.source_page_number) return null;
  const name = docName || "Source";
  const shortName = name.length > 20 ? name.slice(0, 18) + "\u2026" : name;
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onCitationClick({ documentId: span.source_document_id, page: span.source_page_number, filename: name });
      }}
      className="inline-flex items-center gap-1 text-xs text-primary hover:text-primary/80 hover:underline font-medium transition-colors"
      title={`Open ${name} at page ${span.source_page_number}`}
    >
      <FileText className="w-3 h-3" />
      {shortName} &middot; p.{span.source_page_number}
    </button>
  );
}

// ─── Checklist row ───────────────────────────────────────────────────────────

function ChecklistRow({ item, docNameMap, onCitationClick }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = CHECKLIST_STATUS[item.status] || CHECKLIST_STATUS.missing;
  const Icon = cfg.icon;
  const span = item.evidence_spans?.[0];
  const evidence = span?.quote || item.evidence_quote;

  return (
    <div className="border-b last:border-0">
      <div
        className="flex items-start gap-3 px-4 py-3 hover:bg-muted/20 cursor-pointer"
        onClick={() => evidence && setExpanded((v) => !v)}
      >
        <Icon className={`w-4 h-4 shrink-0 mt-0.5 ${cfg.color}`} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium leading-tight">{item.title}</p>
          {item.category && (
            <p className="text-xs text-muted-foreground mt-0.5 capitalize">
              {item.category.replace(/_/g, " ")}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {item.confidence != null && (
            <span className="text-xs text-muted-foreground">
              {Math.round(item.confidence * 100)}%
            </span>
          )}
          <span className={`text-xs font-medium ${cfg.color}`}>{cfg.label}</span>
          {evidence && (
            <span className="text-muted-foreground">
              {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </span>
          )}
        </div>
      </div>
      {expanded && evidence && (
        <div className="px-4 pb-3 pl-11 space-y-1.5">
          <blockquote className="border-l-2 border-muted pl-3 text-xs text-muted-foreground italic">
            &ldquo;{evidence}&rdquo;
          </blockquote>
          <CitationBadge
            span={span || { source_document_id: item.matched_document_id, source_page_number: item.matched_page_number }}
            docName={docNameMap[span?.source_document_id || item.matched_document_id]}
            onCitationClick={onCitationClick}
          />
        </div>
      )}
    </div>
  );
}

// ─── Finding card ────────────────────────────────────────────────────────────

function FindingCard({ finding, roomId, docNameMap, onCitationClick, onUpdated, compact }) {
  const { getToken } = useAppAuth();
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  async function updateStatus(newStatus) {
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await updateFinding(getToken, roomId, finding.id, { status: newStatus });
      onUpdated(updated);
    } catch (err) {
      setSaveError(err.response?.data?.detail || "Update failed");
    } finally {
      setSaving(false);
    }
  }

  const severityStyle = SEVERITY_STYLES[finding.severity] || SEVERITY_STYLES.low;
  const statusStyle = FINDING_STATUS_STYLES[finding.status] || FINDING_STATUS_STYLES.open;
  const isDimmed = finding.status !== "open";
  const span = finding.evidence_spans?.[0];

  return (
    <div className={`bg-card border rounded-xl ${compact ? "p-3" : "p-4"} shadow-sm transition-opacity ${isDimmed ? "opacity-60" : ""}`}>
      <div className="flex items-start gap-3 mb-2">
        <span className={`text-xs px-2 py-0.5 rounded-full font-bold capitalize border shrink-0 mt-0.5 ${severityStyle}`}>
          {finding.severity}
        </span>
        <div className="flex-1 min-w-0">
          <p className={`${compact ? "text-xs" : "text-sm"} font-semibold leading-tight`}>{finding.title}</p>
          {finding.category && (
            <p className="text-xs text-muted-foreground mt-0.5 capitalize">
              {finding.category.replace(/_/g, " ")}
            </p>
          )}
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize shrink-0 ${statusStyle}`}>
          {finding.status}
        </span>
      </div>

      {!compact && <p className="text-sm text-foreground leading-relaxed mb-2">{finding.description}</p>}
      {compact && finding.description && (
        <p className="text-xs text-muted-foreground leading-relaxed mb-2 line-clamp-2">{finding.description}</p>
      )}

      {finding.evidence_quote && (
        <div className="mb-2 space-y-1.5">
          <blockquote className="border-l-2 border-muted pl-3 text-xs text-muted-foreground italic">
            &ldquo;{finding.evidence_quote}&rdquo;
          </blockquote>
          <CitationBadge
            span={span || { source_document_id: finding.source_document_id, source_page_number: finding.source_page_number }}
            docName={docNameMap[span?.source_document_id || finding.source_document_id]}
            onCitationClick={onCitationClick}
          />
        </div>
      )}

      {!compact && finding.recommendation && (
        <p className="text-xs text-muted-foreground bg-muted/40 rounded p-2 mb-3">
          <span className="font-medium">Recommendation:</span> {finding.recommendation}
        </p>
      )}

      {saveError && <p className="text-xs text-destructive mb-2">{saveError}</p>}

      {finding.status === "open" && (
        <div className="flex gap-2">
          <button onClick={() => updateStatus("resolved")} disabled={saving}
            className="text-xs px-2.5 py-1.5 rounded-lg bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 hover:brightness-95 font-medium disabled:opacity-50 transition-colors">
            Resolve
          </button>
          <button onClick={() => updateStatus("dismissed")} disabled={saving}
            className="text-xs px-2.5 py-1.5 rounded-lg bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400 hover:brightness-95 font-medium disabled:opacity-50 transition-colors">
            Dismiss
          </button>
        </div>
      )}
      {finding.status !== "open" && (
        <button onClick={() => updateStatus("open")} disabled={saving}
          className="text-xs px-2.5 py-1.5 rounded-lg border hover:bg-muted font-medium disabled:opacity-50 transition-colors">
          Reopen
        </button>
      )}
    </div>
  );
}

// ─── By Document — Document Analysis Card ────────────────────────────────────

function DocumentAnalysisCard({
  doc, checklist, findings, docNameMap, onCitationClick, roomId, onFindingUpdated,
}) {
  const [expanded, setExpanded] = useState(false);

  // Gather analysis data for this document
  const docId = doc.document_id;
  const classification = doc.metadata?.document_classification;
  const docType = classification?.document_type;
  const amendmentLink = doc.metadata?.amendment_link;
  const amendmentParent = amendmentLink?.parent_document_id;
  const parentDoc = amendmentParent ? docNameMap[amendmentParent] : null;

  // Items where this document is the matched doc
  const docChecklist = useMemo(() =>
    checklist.filter((item) => {
      if (item.matched_document_id === docId) return true;
      return item.evidence_spans?.some((s) => s.source_document_id === docId);
    }),
    [checklist, docId]
  );

  // Findings sourced from this document
  const docFindings = useMemo(() =>
    findings.filter((f) => {
      if (f.source_document_id === docId) return true;
      return f.evidence_spans?.some((s) => s.source_document_id === docId);
    }),
    [findings, docId]
  );

  // Get amendments pointing to this doc
  const amendments = useMemo(() => {
    if (!docNameMap) return [];
    // We only have the docs list via docNameMap keys — would need full docs array
    return [];
  }, [docNameMap]);

  const checklistCovered = docChecklist.filter((i) => i.status === "covered").length;
  const checklistTotal = docChecklist.length;
  const openFindings = docFindings.filter((f) => f.status === "open").length;
  const highFindings = docFindings.filter((f) => f.severity === "high" && f.status === "open").length;

  const hasAnalysisData = docChecklist.length > 0 || docFindings.length > 0 || docType;

  return (
    <div className="bg-card border rounded-xl overflow-hidden shadow-sm">
      {/* Header — always visible */}
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-muted/20 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="w-8 h-8 rounded-lg bg-muted/50 flex items-center justify-center shrink-0">
          <FileText className="w-4 h-4 text-muted-foreground" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold truncate">{doc.filename}</span>
            {docType && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium whitespace-nowrap ${DOC_TYPE_COLORS[docType] || DOC_TYPE_COLORS.other}`}>
                {DOC_TYPE_LABELS[docType] || docType}
              </span>
            )}
          </div>
          {/* Amendment link */}
          {amendmentParent && (
            <div className="flex items-center gap-1 text-xs text-blue-500 mt-0.5">
              <Link2 className="w-3 h-3" />
              <span className="truncate max-w-[200px]">
                Amends: {parentDoc || "Parent document"}
              </span>
              {amendmentLink?.confidence && (
                <span className="text-muted-foreground">
                  ({Math.round(amendmentLink.confidence * 100)}%)
                </span>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {hasAnalysisData && (
            <>
              {checklistTotal > 0 && (
                <span className="text-xs text-muted-foreground">
                  {checklistCovered}/{checklistTotal} checklist
                </span>
              )}
              {openFindings > 0 && (
                <span className={`text-xs font-medium ${highFindings > 0 ? "text-red-500" : "text-yellow-600"}`}>
                  {openFindings} finding{openFindings !== 1 ? "s" : ""}
                </span>
              )}
            </>
          )}
          {!hasAnalysisData && (
            <span className="text-xs text-muted-foreground">No analysis data</span>
          )}
          <ChevronRight className={`w-4 h-4 text-muted-foreground transition-transform ${expanded ? "rotate-90" : ""}`} />
        </div>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t px-4 py-3 space-y-4">
          {/* Amendment chain tree */}
          {amendmentParent && (
            <AmendmentChainTree
              docId={docId}
              docNameMap={docNameMap}
              amendmentLink={amendmentLink}
              parentDoc={parentDoc}
              onCitationClick={onCitationClick}
            />
          )}

          {/* Checklist items for this doc */}
          {docChecklist.length > 0 && (
            <div>
              <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">
                Checklist Items ({docChecklist.length})
              </h4>
              <div className="bg-background border rounded-lg overflow-hidden">
                {docChecklist.map((item) => (
                  <ChecklistRow
                    key={item.id}
                    item={item}
                    docNameMap={docNameMap}
                    onCitationClick={onCitationClick}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Findings for this doc */}
          {docFindings.length > 0 && (
            <div>
              <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">
                Findings ({docFindings.length})
              </h4>
              <div className="space-y-2">
                {[...docFindings]
                  .sort((a, b) => {
                    if (a.status === "open" && b.status !== "open") return -1;
                    if (b.status === "open" && a.status !== "open") return 1;
                    const sev = { high: 0, medium: 1, low: 2 };
                    return (sev[a.severity] ?? 2) - (sev[b.severity] ?? 2);
                  })
                  .map((f) => (
                    <FindingCard
                      key={f.id}
                      finding={f}
                      roomId={roomId}
                      docNameMap={docNameMap}
                      onCitationClick={onCitationClick}
                      onUpdated={onFindingUpdated}
                      compact
                    />
                  ))}
              </div>
            </div>
          )}

          {!hasAnalysisData && (
            <p className="text-sm text-muted-foreground text-center py-4">
              No analysis data extracted from this document yet.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Amendment Chain Tree ────────────────────────────────────────────────────

function AmendmentChainTree({ docId, docNameMap, amendmentLink, parentDoc }) {
  return (
    <div className="bg-muted/30 rounded-lg p-3">
      <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">
        Amendment Chain
      </h4>
      <div className="text-xs space-y-1">
        {/* Parent */}
        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground">└─</span>
          <FileText className="w-3 h-3 text-muted-foreground" />
          <span className="font-medium">{parentDoc || "Parent document"}</span>
          <span className="text-muted-foreground">(Original)</span>
        </div>
        {/* This doc as child */}
        <div className="flex items-center gap-1.5 pl-5">
          <span className="text-muted-foreground">├─</span>
          <FileText className="w-3 h-3 text-primary" />
          <span className="font-medium text-primary">{docNameMap[docId] || "This document"}</span>
          <span className="text-muted-foreground">
            ({amendmentLink?.amendment_type || "modifies"}, {Math.round((amendmentLink?.confidence || 0) * 100)}%)
          </span>
        </div>
      </div>
    </div>
  );
}

// ─── Executive Summary Banner ────────────────────────────────────────────────

function ExecutiveSummary({ checklist, findings, room, docsCount, analysisDocsCount, onRerun, rerunning, onGenerateICMemo, generatingMemo }) {
  const covered = checklist.filter((i) => i.status === "covered").length;
  const partial = checklist.filter((i) => i.status === "partial").length;
  const missing = checklist.filter((i) => i.status === "missing").length;
  const openFindings = findings.filter((f) => f.status === "open").length;
  const highFindings = findings.filter((f) => f.severity === "high" && f.status === "open").length;

  // Check for unanalyzed docs — docs uploaded after last analysis
  const newDocsCount = docsCount > analysisDocsCount ? docsCount - analysisDocsCount : 0;

  const completionPct = checklist.length > 0
    ? Math.round((covered / checklist.length) * 100)
    : 0;

  return (
    <div className="space-y-3 mb-6">
      {/* New docs warning */}
      {newDocsCount > 0 && (
        <div className="flex items-center justify-between bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-xl px-4 py-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
            <span className="text-sm text-amber-700 dark:text-amber-400">
              <strong>{newDocsCount} new document{newDocsCount !== 1 ? "s" : ""}</strong> haven't been analyzed yet
            </span>
          </div>
          <button
            onClick={onRerun}
            disabled={rerunning}
            className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-full bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`w-3 h-3 ${rerunning ? "animate-spin" : ""}`} />
            Re-run Analysis
          </button>
        </div>
      )}

      {/* Stats banner */}
      <div className="bg-card border rounded-xl p-4 shadow-sm">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {/* Completion */}
          <div className="text-center">
            <p className="text-2xl font-black text-primary">{completionPct}%</p>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-0.5">Checklist</p>
          </div>
          {/* Covered */}
          <div className="text-center">
            <p className="text-2xl font-black text-green-600">{covered}</p>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-0.5">Covered</p>
          </div>
          {/* Partial */}
          <div className="text-center">
            <p className="text-2xl font-black text-yellow-600">{partial}</p>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-0.5">Partial</p>
          </div>
          {/* Missing */}
          <div className="text-center">
            <p className="text-2xl font-black text-red-500">{missing}</p>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-0.5">Missing</p>
          </div>
          {/* Open Findings */}
          <div className="text-center">
            <div className="flex items-center justify-center gap-1.5">
              <p className={`text-2xl font-black ${highFindings > 0 ? "text-red-500" : openFindings > 0 ? "text-yellow-600" : "text-green-600"}`}>
                {openFindings}
              </p>
              {highFindings > 0 && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400 font-bold">
                  {highFindings} HIGH
                </span>
              )}
            </div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-0.5">Open Findings</p>
          </div>
        </div>
        {/* Generate IC Memo */}
        <div className="mt-3 pt-3 border-t flex justify-end">
          <button
            onClick={onGenerateICMemo}
            disabled={generatingMemo}
            className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-full bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            <Sparkles className={`w-3 h-3 ${generatingMemo ? "animate-pulse" : ""}`} />
            {generatingMemo ? "Generating…" : "Generate IC Memo"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Tab Button ──────────────────────────────────────────────────────────────

function TabButton({ active, children, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
        active
          ? "bg-primary text-primary-foreground shadow-sm"
          : "text-muted-foreground hover:bg-muted hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

// ─── Room Overview Tab ───────────────────────────────────────────────────────

function RoomOverviewTab({ checklist, findings, summary, docNameMap, onCitationClick, roomId, setFindings, showPdf }) {
  const checklistByCategory = useMemo(() =>
    checklist.reduce((acc, item) => {
      const cat = item.category || "General";
      if (!acc[cat]) acc[cat] = [];
      acc[cat].push(item);
      return acc;
    }, {}),
    [checklist]
  );

  return (
    <div className="space-y-6">
      {/* AI Summary */}
      {summary?.content_markdown && (
        <div className="bg-card border rounded-xl p-4 shadow-sm">
          <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">
            AI Summary
          </h2>
          <div
            className="text-sm leading-relaxed text-foreground prose prose-sm dark:prose-invert max-w-none"
            dangerouslySetInnerHTML={{ __html: mdToHtml(summary.content_markdown) }}
          />
        </div>
      )}

      <div className={`grid grid-cols-1 ${showPdf ? "" : "lg:grid-cols-2"} gap-6`}>
        {/* Checklist */}
        <div>
          <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">
            Diligence Checklist{checklist.length > 0 ? ` (${checklist.length})` : ""}
          </h2>
          {checklist.length === 0 ? (
            <p className="text-sm text-muted-foreground">No checklist items.</p>
          ) : (
            <div className="bg-card border rounded-xl overflow-hidden shadow-sm">
              {Object.entries(checklistByCategory).map(([cat, items]) => (
                <div key={cat}>
                  <div className="px-4 py-2 bg-muted/40 border-b">
                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider capitalize">
                      {cat.replace(/_/g, " ")}
                    </p>
                  </div>
                  {items.map((item) => (
                    <ChecklistRow
                      key={item.id}
                      item={item}
                      docNameMap={docNameMap}
                      onCitationClick={onCitationClick}
                    />
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Findings */}
        <div>
          <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">
            Findings{findings.length > 0 ? ` (${findings.length})` : ""}
          </h2>
          {findings.length === 0 ? (
            <p className="text-sm text-muted-foreground">No findings.</p>
          ) : (
            <div className="space-y-3">
              {[...findings]
                .sort((a, b) => {
                  if (a.status === "open" && b.status !== "open") return -1;
                  if (b.status === "open" && a.status !== "open") return 1;
                  const sev = { high: 0, medium: 1, low: 2 };
                  return (sev[a.severity] ?? 2) - (sev[b.severity] ?? 2);
                })
                .map((f) => (
                  <FindingCard
                    key={f.id}
                    finding={f}
                    roomId={roomId}
                    docNameMap={docNameMap}
                    onCitationClick={onCitationClick}
                    onUpdated={(updated) =>
                      setFindings((prev) => prev.map((x) => (x.id === updated.id ? updated : x)))
                    }
                  />
                ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── By Document Tab ─────────────────────────────────────────────────────────

function ByDocumentTab({ docs, checklist, findings, docNameMap, onCitationClick, roomId, setFindings }) {
  // Sort: docs with findings first, then by filename
  const sortedDocs = useMemo(() => {
    return [...docs].sort((a, b) => {
      const aFindings = findings.filter((f) =>
        f.source_document_id === a.document_id ||
        f.evidence_spans?.some((s) => s.source_document_id === a.document_id)
      ).length;
      const bFindings = findings.filter((f) =>
        f.source_document_id === b.document_id ||
        f.evidence_spans?.some((s) => s.source_document_id === b.document_id)
      ).length;
      if (aFindings !== bFindings) return bFindings - aFindings;
      return (a.filename || "").localeCompare(b.filename || "");
    });
  }, [docs, findings]);

  return (
    <div className="space-y-2">
      {sortedDocs.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-8">No documents in this room.</p>
      ) : (
        sortedDocs.map((doc) => (
          <DocumentAnalysisCard
            key={doc.id}
            doc={doc}
            checklist={checklist}
            findings={findings}
            docNameMap={docNameMap}
            onCitationClick={onCitationClick}
            roomId={roomId}
            onFindingUpdated={(updated) =>
              setFindings((prev) => prev.map((x) => (x.id === updated.id ? updated : x)))
            }
          />
        ))
      )}
    </div>
  );
}

// ─── Playbook labels and colors for Clauses tab ──────────────────────────────

const PLAYBOOK_LABELS = {
  spa_core: "SPA Core Terms",
  change_of_control: "Change of Control & Assignment",
  customer_concentration: "Customer Concentration & Revenue",
  debt_covenants: "Debt & Covenant Analysis",
  ip_ownership: "IP & Technology Ownership",
  employment: "Key Employee & Compensation",
};

const CATEGORY_COLORS = {
  spa: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
  contract: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  debt: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  ip: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300",
  people: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
  commercial: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300",
};

// ─── FieldPills: smart formatting of extracted_fields ────────────────────────

function FieldPills({ fields }) {
  if (!fields || typeof fields !== "object") return null;

  const pills = [];
  const consumedKeys = new Set();

  // Helper: format number with currency or percentage
  const formatNumber = (val, key) => {
    if (typeof val !== "number") return null;
    if (key.includes("amount") || key.includes("cap") || key.includes("basket")) {
      if (!key.includes("pct")) return `$${val.toLocaleString()}`;
    }
    if (key.includes("pct") || key.endsWith("_pct")) return `${val}%`;
    if (key.endsWith("_months")) return `${val} months`;
    if (key.endsWith("_days")) return `${val} days`;
    return val;
  };

  Object.entries(fields).forEach(([key, value]) => {
    if (consumedKeys.has(key) || value === null || value === undefined || value === "") return;

    // Handle threshold_value + threshold_unit pair
    if (key === "threshold_value" && fields.threshold_unit) {
      const formatted = `${value}${fields.threshold_unit}`;
      pills.push(
        <span key={key} className="inline-flex items-center gap-1 text-xs bg-muted px-2 py-1 rounded">
          <span className="text-muted-foreground">Threshold</span>
          <span className="font-semibold text-foreground">{formatted}</span>
        </span>
      );
      consumedKeys.add(key);
      consumedKeys.add("threshold_unit");
      return;
    }
    if (key === "threshold_unit") return; // Already handled

    // Handle earnout pair: earnout_period_months + earnout_metric
    if (key === "earnout_period_months" && fields.earnout_metric) {
      const formatted = `${value}mo on ${fields.earnout_metric}`;
      pills.push(
        <span key={key} className="inline-flex items-center gap-1 text-xs bg-muted px-2 py-1 rounded">
          <span className="text-muted-foreground">Earnout</span>
          <span className="font-semibold text-foreground">{formatted}</span>
        </span>
      );
      consumedKeys.add(key);
      consumedKeys.add("earnout_metric");
      return;
    }
    if (key === "earnout_metric") return; // Already handled

    // Format different value types
    let displayValue = null;
    let label = key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());

    if (typeof value === "number") {
      displayValue = formatNumber(value, key);
    } else if (typeof value === "boolean") {
      displayValue = value ? "Yes" : "No";
    } else if (Array.isArray(value)) {
      if (value.length === 0) return;
      const truncated = value.slice(0, 3);
      displayValue = truncated.join(", ");
      if (value.length > 3) displayValue += ` +${value.length - 3} more`;
    } else if (typeof value === "string") {
      if (value.length === 0) return;
      displayValue = value;
    }

    if (displayValue) {
      consumedKeys.add(key);
      const bgColor = typeof value === "boolean"
        ? value ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300"
                : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300"
        : "bg-muted";
      pills.push(
        <span key={key} className={`inline-flex items-center gap-1 text-xs ${bgColor} px-2 py-1 rounded`}>
          <span className="text-muted-foreground">{label}</span>
          <span className="font-semibold text-foreground">{displayValue}</span>
        </span>
      );
    }
  });

  return pills.length > 0 ? <div className="flex flex-wrap gap-2 mt-2">{pills}</div> : null;
}

// ─── ClauseCard: individual clause display ───────────────────────────────────

function ClauseCard({ clause, docNameMap, onCitationClick }) {
  const [expanded, setExpanded] = useState(false);
  const docName = docNameMap?.[clause.source_document_id] || "Source";
  const categoryColor = CATEGORY_COLORS[clause.category] || CATEGORY_COLORS.contract;

  return (
    <div className="border border-border rounded-lg p-4 bg-card">
      {/* Header: badge + doc + page + confidence */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold px-2 py-1 rounded ${categoryColor}`}>
            {clause.clause_type}
          </span>
          <button
            onClick={() => onCitationClick({ documentId: clause.source_document_id, page: clause.source_page_number, filename: docName })}
            className="text-xs text-primary hover:text-primary/80 hover:underline font-medium transition-colors"
            title={`Open ${docName} at page ${clause.source_page_number}`}
          >
            <FileText className="w-3 h-3 inline mr-1" />
            {docName.length > 30 ? docName.slice(0, 28) + "…" : docName} • p.{clause.source_page_number}
          </button>
        </div>
        {clause.confidence && (
          <span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">
            {Math.round(clause.confidence * 100)}%
          </span>
        )}
      </div>

      {/* Interpretation (always visible, bold) */}
      {clause.interpretation && (
        <p className="text-sm font-semibold text-foreground mb-2">{clause.interpretation}</p>
      )}

      {/* Extracted fields */}
      <FieldPills fields={clause.extracted_fields} />

      {/* Raw quote (collapsible) */}
      {clause.raw_quote && (
        <div className="mt-3 border-t border-border pt-3">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            Raw Quote
          </button>
          {expanded && (
            <p className="text-xs text-muted-foreground bg-muted/50 p-2 rounded mt-2 font-mono">
              {clause.raw_quote}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── ClausesTab: main clauses display with grouping by playbook ───────────────

function ClausesTab({ clauses, docNameMap, onCitationClick }) {
  // Group clauses by playbook_id
  const grouped = useMemo(() => {
    const groups = {};
    clauses.forEach((c) => {
      const pid = c.playbook_id || "other";
      if (!groups[pid]) groups[pid] = [];
      groups[pid].push(c);
    });
    // Sort by group size descending
    return Object.entries(groups)
      .sort(([, a], [, b]) => b.length - a.length)
      .reduce((acc, [k, v]) => ({ ...acc, [k]: v }), {});
  }, [clauses]);

  if (clauses.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Shield className="w-8 h-8 mx-auto mb-2 opacity-50" />
        <p className="text-sm">No structured clauses extracted yet.</p>
        <p className="text-xs text-muted-foreground mt-1">Run analysis with LLM clause extraction enabled.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {Object.entries(grouped).map(([playbookId, clauseList]) => (
        <div key={playbookId} className="border border-border rounded-lg overflow-hidden">
          <div className="bg-muted/50 px-4 py-3 border-b border-border">
            <h3 className="font-semibold text-foreground">
              {PLAYBOOK_LABELS[playbookId] || playbookId}
              <span className="ml-2 text-sm text-muted-foreground font-normal">({clauseList.length})</span>
            </h3>
          </div>
          <div className="p-4 space-y-3">
            {clauseList.map((clause) => (
              <ClauseCard
                key={clause.id}
                clause={clause}
                docNameMap={docNameMap}
                onCitationClick={onCitationClick}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function RoomAnalysis() {
  const { roomId } = useParams();
  const { getToken } = useAppAuth();

  const [room, setRoom]               = useState(null);
  const [checklist, setChecklist]     = useState([]);
  const [findings, setFindings]       = useState([]);
  const [summary, setSummary]         = useState(null);
  const [docs, setDocs]               = useState([]);
  const [clauses, setClauses]         = useState([]);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState(null);
  const [docNameMap, setDocNameMap]   = useState({});
  const [activeTab, setActiveTab]     = useState("overview");
  const [rerunning, setRerunning]     = useState(false);
  const [generatingMemo, setGeneratingMemo] = useState(false);
  const navigate = useNavigate();
  const clausesLoaded = useRef(false);

  // PDF side panel
  const [pdfPanel, setPdfPanel]       = useState(null);
  const [pdfLoading, setPdfLoading]   = useState(false);
  const urlCache = useRef({});

  useEffect(() => {
    setLoading(true);
    Promise.all([
      getRoom(getToken, roomId).catch(() => null),
      getRoomChecklist(getToken, roomId).catch(() => []),
      getRoomFindings(getToken, roomId).catch(() => []),
      getRoomSummary(getToken, roomId).catch(() => null),
      listRoomDocuments(getToken, roomId).catch(() => []),
    ])
      .then(([roomData, cl, fi, sum, docsData]) => {
        setRoom(roomData);
        setChecklist(cl);
        setFindings(fi);
        setSummary(sum);
        setDocs(docsData);
        const nameMap = {};
        docsData.forEach((d) => {
          if (d.document_id) nameMap[d.document_id] = d.filename;
        });
        setDocNameMap(nameMap);
      })
      .catch((err) => setError(err.message || "Failed to load analysis"))
      .finally(() => setLoading(false));
  }, [roomId]);

  // Lazy-load clauses when "clauses" tab is first activated
  useEffect(() => {
    if (activeTab === "clauses" && !clausesLoaded.current && roomId) {
      clausesLoaded.current = true;
      listRoomClauses(getToken, roomId)
        .then(setClauses)
        .catch(() => { /* silently handle */ });
    }
  }, [activeTab, roomId, getToken]);

  const handleCitationClick = useCallback(async ({ documentId, page, filename }) => {
    if (!documentId) return;
    if (pdfPanel?.documentId === documentId) {
      setPdfPanel((prev) => ({ ...prev, page }));
      return;
    }
    setPdfLoading(true);
    setPdfPanel({ documentId, page, filename, url: null });
    try {
      let url = urlCache.current[documentId];
      if (!url) {
        const data = await getDocumentDownloadUrl(getToken, documentId);
        url = data.url;
        urlCache.current[documentId] = url;
      }
      setPdfPanel({ documentId, page, filename, url });
    } catch {
      setPdfPanel(null);
    } finally {
      setPdfLoading(false);
    }
  }, [getToken, pdfPanel?.documentId]);

  const closePdfPanel = useCallback(() => setPdfPanel(null), []);

  async function handleRerun() {
    setRerunning(true);
    try {
      await startAnalysis(getToken, roomId, true);
    } catch {
      // silently handle — user can see status on documents page
    } finally {
      setRerunning(false);
    }
  }

  async function handleGenerateICMemo() {
    setGeneratingMemo(true);
    try {
      const result = await generateICMemo(getToken, roomId);
      if (result?.workflow_run_id) {
        navigate(`/app/pe/workflows/${result.workflow_run_id}`);
      }
    } catch {
      // silently handle — API errors surface via normal error boundaries
    } finally {
      setGeneratingMemo(false);
    }
  }

  const showPdf = pdfPanel != null;

  // Count of docs that have been analyzed (have classification data)
  const analysisDocsCount = useMemo(() =>
    docs.filter((d) => d.metadata?.document_classification || d.document_type).length,
    [docs]
  );

  const hasData = checklist.length > 0 || findings.length > 0;

  return (
    <PELayout>
      <div className="flex h-full">
        {/* Left: Analysis content */}
        <div className={`${showPdf ? "w-[60%]" : "w-full"} overflow-y-auto transition-all duration-300`}>
          <div className="pe-page min-h-full max-w-6xl">
            {/* Header */}
            <div className="flex items-center justify-between mb-5">
              <div>
                <h1 className="pe-title font-display">Analysis</h1>
                {room?.target_company && (
                  <p className="text-sm text-muted-foreground mt-0.5">{room.target_company}</p>
                )}
              </div>
              {hasData && (
                <button
                  onClick={handleRerun}
                  disabled={rerunning}
                  className="pe-action-ghost text-sm disabled:opacity-50"
                >
                  <RefreshCw className={`w-4 h-4 ${rerunning ? "animate-spin" : ""}`} />
                  Re-run Analysis
                </button>
              )}
            </div>

            {loading && <p className="text-sm text-muted-foreground">Loading analysis…</p>}

            {error && (
              <div className="flex items-center gap-2 border border-destructive/30 bg-destructive/10 text-destructive rounded-lg p-3 text-sm mb-4">
                <AlertCircle className="w-4 h-4 shrink-0" />
                {error}
              </div>
            )}

            {/* Empty state */}
            {!loading && !hasData && (
              <div className="pe-card-muted p-16 text-center">
                <div className="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center mx-auto mb-4">
                  <Shield className="w-8 h-8 text-primary opacity-60" />
                </div>
                <p className="text-sm font-semibold">No analysis results yet</p>
                <p className="text-xs text-muted-foreground mt-1 mb-4">
                  Upload documents and run analysis to see diligence results here.
                </p>
                <Link
                  to={`/app/pe/rooms/${roomId}/documents`}
                  className="pe-action-primary"
                >
                  <Play className="w-4 h-4" />
                  Go to Documents
                </Link>
              </div>
            )}

            {/* Analysis content */}
            {!loading && hasData && (
              <>
                {/* Executive Summary */}
                <ExecutiveSummary
                  checklist={checklist}
                  findings={findings}
                  room={room}
                  docsCount={docs.length}
                  analysisDocsCount={analysisDocsCount}
                  onRerun={handleRerun}
                  rerunning={rerunning}
                  onGenerateICMemo={handleGenerateICMemo}
                  generatingMemo={generatingMemo}
                />

                {/* Tab switcher */}
                <div className="flex items-center gap-1 bg-muted/50 rounded-lg p-1 mb-6 w-fit">
                  <TabButton active={activeTab === "overview"} onClick={() => setActiveTab("overview")}>
                    Room Overview
                  </TabButton>
                  <TabButton active={activeTab === "by-document"} onClick={() => setActiveTab("by-document")}>
                    By Document ({docs.length})
                  </TabButton>
                  <TabButton active={activeTab === "clauses"} onClick={() => setActiveTab("clauses")}>
                    Clauses {clauses.length > 0 ? `(${clauses.length})` : ""}
                  </TabButton>
                </div>

                {/* Tab content */}
                {activeTab === "overview" && (
                  <RoomOverviewTab
                    checklist={checklist}
                    findings={findings}
                    summary={summary}
                    docNameMap={docNameMap}
                    onCitationClick={handleCitationClick}
                    roomId={roomId}
                    setFindings={setFindings}
                    showPdf={showPdf}
                  />
                )}

                {activeTab === "by-document" && (
                  <ByDocumentTab
                    docs={docs}
                    checklist={checklist}
                    findings={findings}
                    docNameMap={docNameMap}
                    onCitationClick={handleCitationClick}
                    roomId={roomId}
                    setFindings={setFindings}
                  />
                )}

                {activeTab === "clauses" && (
                  <ClausesTab
                    clauses={clauses}
                    docNameMap={docNameMap}
                    onCitationClick={handleCitationClick}
                  />
                )}
              </>
            )}
          </div>
        </div>

        {/* Right: PDF side panel */}
        {showPdf && (
          <div className="w-[40%] border-l border-border flex flex-col bg-background">
            <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/30 shrink-0">
              <div className="flex items-center gap-2 min-w-0">
                <FileText className="w-4 h-4 text-primary shrink-0" />
                <span className="text-sm font-medium truncate">
                  {pdfPanel.filename || "Document"}
                </span>
                {pdfPanel.page && (
                  <span className="text-xs text-muted-foreground shrink-0">
                    p.{pdfPanel.page}
                  </span>
                )}
              </div>
              <button
                onClick={closePdfPanel}
                className="p-1 hover:bg-muted rounded transition-colors shrink-0"
                title="Close panel"
              >
                <X className="w-4 h-4 text-muted-foreground" />
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              {pdfLoading && !pdfPanel.url && (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-muted-foreground">Loading document…</p>
                </div>
              )}
              {pdfPanel.url && (
                <PDFViewer
                  pdfUrl={pdfPanel.url}
                  defaultPage={pdfPanel.page || 1}
                  highlightBbox={pdfPanel.page ? { page: pdfPanel.page, x0: 0.5, y0: 0.2, x1: 7.5, y1: 0.8 } : null}
                />
              )}
            </div>
          </div>
        )}
      </div>
    </PELayout>
  );
}
