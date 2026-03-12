/**
 * InvestigationDetail — Card-based claims list with PDF side panel.
 * Route: /app/pe/rooms/:roomId/investigations/:invId
 *
 * Evidence span click → opens PDF viewer on the right, scrolls to source page.
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft, RefreshCw, AlertCircle, X, ExternalLink,
} from "lucide-react";
import { useAppAuth } from "@/hooks/useAppAuth";
import PELayout from "./PELayout";
import PDFViewer from "@/components/pdf/PDFViewer";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import { getInvestigation, rerunInvestigation, overrideClaim } from "../../../api/pe-diligence";
import { getDocumentDownloadUrl } from "../../../api/documents";

// ─── Style maps ───────────────────────────────────────────────────────────────

const STANCE_STYLES = {
  supported:          "bg-green-100 text-green-700 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800",
  contradicted:       "bg-red-100 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800",
  partially_supported:"bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-800",
  unknown:            "bg-gray-100 text-gray-600 border-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700",
  inconclusive:       "bg-gray-100 text-gray-600 border-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700",
};

const SEVERITY_STYLES = {
  high:   "bg-red-100 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800",
  medium: "bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-800",
  low:    "bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800",
};

const VERIFICATION_STYLES = {
  verified:     "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  needs_review: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  dismissed:    "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500",
  pending:      "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
};

const COVERAGE_COLORS = {
  strong:   "text-green-600",
  moderate: "text-yellow-600",
  weak:     "text-red-600",
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function Badge({ label, style, className = "" }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-semibold capitalize border ${style} ${className}`}>
      {label?.replace(/_/g, " ")}
    </span>
  );
}

function EvidenceSpan({ span, docFilenames, onViewInDoc }) {
  const filename = docFilenames[span.source_document_id] || span.source_document_id || "Document";
  const hasDoc = Boolean(span.source_document_id);
  return (
    <div className="rounded-lg border border-border/70 p-3 bg-muted/30">
      <p className="text-sm italic text-foreground leading-relaxed">
        "{span.quote}"
      </p>
      <div className="flex items-center justify-between mt-2">
        <span className="text-xs text-muted-foreground truncate max-w-[60%]">
          {filename}
          {span.source_page_number && (
            <span className="ml-1 font-medium">· p.{span.source_page_number}</span>
          )}
        </span>
        {hasDoc && (
          <button
            onClick={() => onViewInDoc(span)}
            className="flex items-center gap-1 text-xs text-primary font-medium hover:underline shrink-0"
          >
            <ExternalLink className="w-3 h-3" />
            View in doc
          </button>
        )}
      </div>
    </div>
  );
}

function ClaimCard({ claim, roomId, invId, docFilenames, onUpdated, onViewInDoc }) {
  const { getToken } = useAppAuth();
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  async function handleOverride(newStatus) {
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await overrideClaim(getToken, roomId, invId, claim.id, {
        verification_status: newStatus,
        override_reason: newStatus === "needs_review" ? "reset" : "manual_review",
      });
      onUpdated(claim.id, updated.verification_status || newStatus);
    } catch (err) {
      setSaveError(err.response?.data?.detail || "Update failed");
    } finally {
      setSaving(false);
    }
  }

  const stanceStyle      = STANCE_STYLES[claim.stance] || STANCE_STYLES.unknown;
  const severityStyle    = SEVERITY_STYLES[claim.severity] || SEVERITY_STYLES.low;
  const verifyStyle      = VERIFICATION_STYLES[claim.verification_status] || VERIFICATION_STYLES.pending;

  return (
    <div className="pe-card p-4 hover:border-primary/30 hover:shadow-md transition-all">
      {/* Header row */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <Badge label={claim.stance || "unknown"} style={stanceStyle} />
        {claim.severity && <Badge label={claim.severity} style={severityStyle} />}
        {claim.confidence != null && (
          <span className="text-xs text-muted-foreground ml-auto">
            Conf: {Math.round(claim.confidence * 100)}%
          </span>
        )}
      </div>

      {/* Claim text */}
      <p className="text-sm leading-relaxed mb-3">{claim.claim_text}</p>

      {/* Evidence spans */}
      {claim.evidence_spans?.length > 0 && (
        <div className="mb-3">
          <p className="text-xs font-medium text-muted-foreground mb-1.5">
            Evidence ({claim.evidence_spans.length} source{claim.evidence_spans.length !== 1 ? "s" : ""})
          </p>
          <div className="space-y-2">
            {claim.evidence_spans.map((span) => (
              <EvidenceSpan
                key={span.id}
                span={span}
                docFilenames={docFilenames}
                onViewInDoc={onViewInDoc}
              />
            ))}
          </div>
        </div>
      )}

      {/* Reason codes */}
      {claim.reason_codes?.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {claim.reason_codes.map((code) => (
            <span
              key={code}
              className="text-xs bg-muted px-2 py-0.5 rounded text-muted-foreground border"
            >
              {code.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      )}

      {/* Verification */}
      <div className="border-t border-border/60 pt-3 mt-1 flex items-center gap-2 flex-wrap">
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${verifyStyle}`}>
          {(claim.verification_status || "pending").replace(/_/g, " ")}
        </span>
        {saveError && (
          <span className="text-xs text-destructive">{saveError}</span>
        )}
        <div className="flex gap-1.5 ml-auto">
          {claim.verification_status !== "verified" && (
            <button
              onClick={() => handleOverride("verified")}
              disabled={saving}
              className="text-xs px-2.5 py-1 rounded-lg bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 hover:brightness-95 font-medium disabled:opacity-50 transition-colors"
            >
              ✓ Verify
            </button>
          )}
          {claim.verification_status !== "dismissed" && (
            <button
              onClick={() => handleOverride("dismissed")}
              disabled={saving}
              className="text-xs px-2.5 py-1 rounded-lg bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400 hover:brightness-95 font-medium disabled:opacity-50 transition-colors"
            >
              ✕ Dismiss
            </button>
          )}
          {claim.verification_status !== "needs_review" && (
            <button
              onClick={() => handleOverride("needs_review")}
              disabled={saving}
              className="text-xs px-2.5 py-1 rounded-lg border hover:bg-muted font-medium disabled:opacity-50 transition-colors"
            >
              ↻ Review
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function InvestigationDetail() {
  const { roomId, invId } = useParams();
  const navigate = useNavigate();
  const { getToken } = useAppAuth();

  const [investigation, setInvestigation] = useState(null);
  const [claims, setClaims]               = useState([]);
  const [loading, setLoading]             = useState(true);
  const [error, setError]                 = useState(null);
  const [rerunning, setRerunning]         = useState(false);

  // PDF panel state
  const [showPdf, setShowPdf]             = useState(false);
  const [activePdfUrl, setActivePdfUrl]   = useState(null);
  const [highlightBbox, setHighlightBbox] = useState(null);
  const [pdfLoading, setPdfLoading]       = useState(false);
  const [activePdfLabel, setActivePdfLabel] = useState("");
  const urlCacheRef = useRef({});

  // Build doc filename lookup from evidence spans
  const [docFilenames, setDocFilenames]   = useState({});

  useEffect(() => {
    getInvestigation(getToken, roomId, invId)
      .then((data) => {
        setInvestigation(data);
        const claimsData = data.claims || [];
        setClaims(claimsData);
        // Extract unique doc IDs from all evidence spans to build filenames map
        // (filenames would need a separate call; use doc IDs as fallback for now)
        const docIds = new Set();
        claimsData.forEach((c) => c.evidence_spans?.forEach((s) => {
          if (s.source_document_id) docIds.add(s.source_document_id);
        }));
      })
      .catch((err) => setError(err.message || "Failed to load investigation"))
      .finally(() => setLoading(false));
  }, [roomId, invId]);

  const handleViewInDoc = useCallback(async (span) => {
    if (!span.source_document_id) return;
    const docId = span.source_document_id;
    setPdfLoading(true);
    setActivePdfLabel(span.source_document_id);

    try {
      // Check URL cache
      const cached = urlCacheRef.current[docId];
      let url = cached?.url;
      if (!url || (cached?.expiry && Date.now() > cached.expiry)) {
        const result = await getDocumentDownloadUrl(getToken, docId);
        url = result.url || result;
        urlCacheRef.current[docId] = { url, expiry: Date.now() + 10 * 60 * 1000 };
      }
      setActivePdfUrl(url);
      setHighlightBbox(
        span.source_page_number
          ? { page: span.source_page_number, x0: 0, y0: 0, x1: 0, y1: 0 }
          : null,
      );
      setShowPdf(true);
    } catch (err) {
      console.error("Failed to load PDF", err);
    } finally {
      setPdfLoading(false);
    }
  }, [getToken]);

  function handleClaimUpdated(claimId, newStatus) {
    setClaims((prev) =>
      prev.map((c) => (c.id === claimId ? { ...c, verification_status: newStatus } : c)),
    );
  }

  async function handleRerun() {
    setRerunning(true);
    try {
      await rerunInvestigation(getToken, roomId, invId);
      const data = await getInvestigation(getToken, roomId, invId);
      setInvestigation(data);
      setClaims(data.claims || []);
    } catch (err) {
      console.error("Rerun failed", err);
    } finally {
      setRerunning(false);
    }
  }

  const isRunning = ["running", "queued"].includes(investigation?.status);
  const coverageScore  = investigation?.coverage_score;
  const coverageStatus = investigation?.coverage_status;
  const typeLabel = investigation?.investigation_type?.replace(/_/g, " ") || "Investigation";

  return (
    <PELayout>
      <div className="flex flex-col h-full">
        {/* Page header — outside resizable panels */}
        <div className="px-6 pt-5 pb-4 border-b bg-card/70 shrink-0">
          <div className="flex items-center gap-2 mb-3">
            <button
              onClick={() => navigate(`/app/pe/rooms/${roomId}/investigations`)}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              Investigations
            </button>
          </div>

          <div className="pe-header">
            <div>
              <h1 className="text-xl font-semibold capitalize font-display">{typeLabel}</h1>
              {investigation?.question && (
                <p className="text-sm text-muted-foreground mt-0.5">{investigation.question}</p>
              )}
            </div>
            <div className="flex items-center gap-2">
              {showPdf && (
                <button
                  onClick={() => setShowPdf(false)}
                  className="pe-action-ghost text-xs px-2.5 py-1.5"
                >
                  <X className="w-3.5 h-3.5" />
                  Close PDF
                </button>
              )}
              <button
                onClick={handleRerun}
                disabled={rerunning || isRunning}
                className="pe-action-ghost text-sm px-3 py-1.5 disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${rerunning ? "animate-spin" : ""}`} />
                {rerunning ? "Rerunning…" : "Re-run"}
              </button>
            </div>
          </div>

          {/* Coverage bar */}
          {!loading && investigation && !isRunning && coverageScore != null && (
            <div className="flex items-center gap-3 mt-3">
              <span className="pe-chip font-semibold text-primary border-primary/30 bg-primary/10">
                {Math.round(coverageScore * 100)}%
                {coverageStatus && (
                  <span className="font-normal capitalize">{coverageStatus}</span>
                )}
              </span>
              <span className="text-xs text-muted-foreground">
                {claims.length} claim{claims.length !== 1 ? "s" : ""}
              </span>
            </div>
          )}
        </div>

        {/* Errors */}
        {error && (
          <div className="mx-6 mt-4 flex items-center gap-2 border border-destructive/30 bg-destructive/10 text-destructive rounded-lg p-3 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        {loading && (
          <p className="px-6 pt-4 text-sm text-muted-foreground">Loading investigation…</p>
        )}

        {/* Split-screen content */}
        {!loading && investigation && (
          <div className="flex-1 min-h-0">
            <ResizablePanelGroup direction="horizontal" className="h-full">
              {/* Left: claims list */}
              <ResizablePanel defaultSize={showPdf ? 55 : 100} minSize={30}>
                <div className="h-full overflow-y-auto px-6 py-4">
                  {isRunning && (
                    <div className="pe-muted-banner mb-4">
                      Investigation is {investigation.status}… refresh to check for updates.
                    </div>
                  )}

                  {/* Conclusion markdown */}
                  {investigation.conclusion_markdown && (
                    <div className="pe-card p-4 bg-primary/5 border-primary/20 mb-4">
                      <p className="text-[10px] font-bold uppercase tracking-widest text-primary mb-2">Conclusion</p>
                      <div
                        className="text-sm leading-relaxed prose prose-sm dark:prose-invert max-w-none border-l-4 border-primary pl-3"
                        dangerouslySetInnerHTML={{ __html: mdToHtml(investigation.conclusion_markdown) }}
                      />
                    </div>
                  )}

                  {claims.length === 0 && !isRunning && (
                    <div className="pe-card-muted p-8 text-center">
                      <p className="text-sm text-muted-foreground">No claims generated yet.</p>
                    </div>
                  )}

                  <div className="space-y-4">
                    {claims.map((claim) => (
                      <ClaimCard
                        key={claim.id}
                        claim={claim}
                        roomId={roomId}
                        invId={invId}
                        docFilenames={docFilenames}
                        onUpdated={handleClaimUpdated}
                        onViewInDoc={handleViewInDoc}
                      />
                    ))}
                  </div>
                </div>
              </ResizablePanel>

              {/* PDF panel */}
              {showPdf && (
                <>
                  <ResizableHandle withHandle />
                  <ResizablePanel defaultSize={45} minSize={25}>
                    <div className="h-full flex flex-col border-l">
                      <div className="px-4 py-2.5 border-b bg-muted/30 flex items-center justify-between shrink-0">
                        <p className="text-xs font-medium text-muted-foreground truncate">
                          {activePdfLabel || "Document"}
                        </p>
                        <button onClick={() => setShowPdf(false)}>
                          <X className="w-4 h-4 text-muted-foreground hover:text-foreground" />
                        </button>
                      </div>
                      <div className="flex-1 overflow-hidden">
                        {pdfLoading ? (
                          <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
                            Loading document…
                          </div>
                        ) : activePdfUrl ? (
                          <PDFViewer
                            pdfUrl={activePdfUrl}
                            highlightBbox={highlightBbox}
                          />
                        ) : null}
                      </div>
                    </div>
                  </ResizablePanel>
                </>
              )}
            </ResizablePanelGroup>
          </div>
        )}
      </div>
    </PELayout>
  );
}

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
