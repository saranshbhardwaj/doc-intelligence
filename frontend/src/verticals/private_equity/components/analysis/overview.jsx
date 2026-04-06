import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronRight, FileText, Search } from "lucide-react";

import { mdToHtml } from "../../constants";
import {
  FINDINGS_PAGE_SIZE,
  SEVERITY_STYLES,
  WORKSTREAM_LABELS,
  WORKSTREAM_ORDER,
} from "../../analysis/displayConstants";
import {
  getAnalysisCategoryLabel,
  getCoverageStatusLabel,
  getCoverageWorkstreamLabel,
  getFindingWorkstream,
  humanizeLabel,
} from "../../analysis/formatters";
import { AnalysisTriggerButton } from "../AnalysisTriggerButton";
import { ChecklistRow, FilterPill, FindingCard } from "./shared.jsx";

function buildReviewSignalCounts(findings) {
  return findings.reduce((acc, finding) => {
    if (finding.status !== "open") return acc;

    const verification = finding.metadata?.verification || {};
    const workflow = finding.metadata?.workflow || {};
    const reasons = verification.reasons || [];

    if (verification.status === "needs_review") acc.needsReview += 1;
    if (verification.review_priority === "high" || workflow.bucket === "ic_blocker") acc.highPriority += 1;
    if (workflow.bucket === "specialist_review" || reasons.includes("specialist_review_required")) acc.specialist += 1;
    if (workflow.bucket === "underwriting_input" || reasons.includes("underwriting_needs_confirmation")) acc.underwriting += 1;
    if (
      workflow.bucket === "diligence_gap"
      || reasons.includes("missing_evidence")
      || reasons.includes("weak_cross_document_linkage")
    ) {
      acc.evidenceGap += 1;
    }

    return acc;
  }, {
    needsReview: 0,
    highPriority: 0,
    specialist: 0,
    underwriting: 0,
    evidenceGap: 0,
  });
}

export function ExecutiveSummary({ checklist, findings, summary, analysisStatus, roomId, isRunning, onAnalysisStart }) {
  const covered = checklist.filter((item) => item.status === "covered").length;
  const partial = checklist.filter((item) => item.status === "partial").length;
  const missing = checklist.filter((item) => item.status === "missing").length;
  const openFindings = findings.filter((finding) => finding.status === "open").length;
  const highFindings = findings.filter((finding) => finding.severity === "high" && finding.status === "open").length;
  const mediumFindings = findings.filter((finding) => finding.severity === "medium" && finding.status === "open").length;
  const lowFindings = findings.filter((finding) => finding.severity === "low" && finding.status === "open").length;

  const completionPct = checklist.length > 0
    ? Math.round((covered / checklist.length) * 100)
    : 0;

  const workstreamStrip = useMemo(() => {
    return [...(summary?.coverage?.workstreams || [])]
      .sort((a, b) => {
        const order = { gap: 0, partial: 1, covered: 2 };
        return (order[a.status] ?? 3) - (order[b.status] ?? 3);
      })
      .slice(0, 6);
  }, [summary]);

  const reviewSignals = useMemo(() => buildReviewSignalCounts(findings), [findings]);
  const showReviewSignals = Object.values(reviewSignals).some((value) => value > 0);

  return (
    <div className="space-y-3 mb-6">
      <div className="flex items-center justify-between">
        <div>
          {analysisStatus?.has_delta && (
            <div className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400">
              <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
              <span>
                <strong>{analysisStatus?.added_doc_count || 0} new document{(analysisStatus?.added_doc_count || 0) !== 1 ? "s" : ""}</strong> haven't been analyzed yet
              </span>
            </div>
          )}
        </div>
        <AnalysisTriggerButton
          roomId={roomId}
          isRunning={isRunning}
          onStart={onAnalysisStart}
          status={analysisStatus}
          loading={analysisStatus?.loading}
        />
      </div>

      <div className="glass-card rounded-xl p-4">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="text-center">
            <p className="text-2xl font-black font-display text-primary">{completionPct}%</p>
            <div className="w-full bg-muted rounded-full h-1.5 mt-1.5 mx-auto max-w-[60px]">
              <div className="bg-primary h-1.5 rounded-full transition-all" style={{ width: `${completionPct}%` }} />
            </div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-1">Checklist</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-black font-display text-green-600">{covered}</p>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-0.5">Covered</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-black font-display text-yellow-600">{partial}</p>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-0.5">Partial</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-black font-display text-red-500">{missing}</p>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-0.5">Missing</p>
          </div>
          <div className="text-center">
            <div className="flex items-center justify-center gap-1.5">
              <p className={`text-2xl font-black font-display ${highFindings > 0 ? "text-red-500" : openFindings > 0 ? "text-yellow-600" : "text-green-600"}`}>
                {openFindings}
              </p>
            </div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-0.5">Open Findings</p>
          </div>
        </div>

        {openFindings > 0 && (
          <div className="flex items-center gap-3 mt-3 pt-3 border-t">
            <span className="text-xs text-muted-foreground font-medium">By severity:</span>
            <span className="pe-sev-high">{highFindings} High</span>
            <span className="pe-sev-medium">{mediumFindings} Medium</span>
            <span className="pe-sev-low">{lowFindings} Low</span>
          </div>
        )}

        {showReviewSignals && (
          <div className="mt-3 pt-3 border-t">
            <div className="flex items-center justify-between gap-3 mb-2">
              <span className="text-xs text-muted-foreground font-medium">Analyst review queue</span>
              <span className="text-[11px] text-muted-foreground">Open items that still need human routing</span>
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-2">
              <div className="glass-card rounded-lg px-3 py-2">
                <p className="text-lg font-bold font-display text-foreground">{reviewSignals.needsReview}</p>
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Needs review</p>
              </div>
              <div className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2">
                <p className="text-lg font-bold font-display text-destructive">{reviewSignals.highPriority}</p>
                <p className="text-[10px] uppercase tracking-widest text-destructive/70">High priority</p>
              </div>
              <div className="rounded-lg border border-purple-500/20 bg-purple-500/5 px-3 py-2">
                <p className="text-lg font-bold font-display text-purple-600 dark:text-purple-400">{reviewSignals.specialist}</p>
                <p className="text-[10px] uppercase tracking-widest text-purple-600/70 dark:text-purple-400/70">Specialist</p>
              </div>
              <div className="rounded-lg border border-primary/20 bg-primary/5 px-3 py-2">
                <p className="text-lg font-bold font-display text-primary">{reviewSignals.underwriting}</p>
                <p className="text-[10px] uppercase tracking-widest text-primary/70">Underwriting</p>
              </div>
              <div className="rounded-lg border border-warning/20 bg-warning/5 px-3 py-2">
                <p className="text-lg font-bold font-display text-warning">{reviewSignals.evidenceGap}</p>
                <p className="text-[10px] uppercase tracking-widest text-warning/70">Thin sourcing</p>
              </div>
            </div>
          </div>
        )}

        {workstreamStrip.length > 0 && (
          <div className="mt-3 pt-3 border-t">
            <div className="flex items-center justify-between gap-3 mb-2">
              <span className="text-xs text-muted-foreground font-medium">Missing by workstream</span>
              <span className="text-[11px] text-muted-foreground">Fast coverage signal</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {workstreamStrip.map((stream) => (
                <span
                  key={stream.category}
                  className={`pe-chip ${
                    stream.status === "gap"
                      ? "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400"
                      : stream.status === "partial"
                        ? "border-yellow-200 bg-yellow-50 text-yellow-700 dark:border-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400"
                        : "border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-400"
                  }`}
                >
                  <span className="font-semibold">{getCoverageWorkstreamLabel(stream.category)}</span>
                  <span className="opacity-80">· {getCoverageStatusLabel(stream.status)}</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function RoomOverviewTab({ checklist, findings, summary, docNameMap, onCitationClick, roomId, setFindings, showPdf, onInvestigationLaunch }) {
  const [findingFilter, setFindingFilter] = useState({ severity: "all", status: "open", search: "" });
  const [findingsPage, setFindingsPage] = useState(1);
  const [checklistStatusFilter, setChecklistStatusFilter] = useState("all");

  useEffect(() => {
    setFindingsPage(1);
  }, [findingFilter]);

  const filteredFindings = useMemo(() => {
    return findings.filter((finding) => {
      if (findingFilter.status !== "all" && finding.status !== findingFilter.status) return false;
      if (findingFilter.severity !== "all" && finding.severity !== findingFilter.severity) return false;
      if (findingFilter.search) {
        const q = findingFilter.search.toLowerCase();
        if (!finding.title?.toLowerCase().includes(q) && !finding.description?.toLowerCase().includes(q)) return false;
      }
      return true;
    }).sort((a, b) => {
      if (a.status === "open" && b.status !== "open") return -1;
      if (b.status === "open" && a.status !== "open") return 1;
      const sev = { high: 0, medium: 1, low: 2 };
      return (sev[a.severity] ?? 2) - (sev[b.severity] ?? 2);
    });
  }, [findings, findingFilter]);

  const visibleFindings = filteredFindings.slice(0, findingsPage * FINDINGS_PAGE_SIZE);
  const hasMore = visibleFindings.length < filteredFindings.length;

  const findingsByWorkstream = useMemo(() => {
    return visibleFindings.reduce((acc, finding) => {
      const workstream = getFindingWorkstream(finding);
      if (!acc[workstream]) acc[workstream] = [];
      acc[workstream].push(finding);
      return acc;
    }, {});
  }, [visibleFindings]);

  const groupedFindings = useMemo(() => {
    return Object.entries(findingsByWorkstream).sort(
      (a, b) => WORKSTREAM_ORDER.indexOf(a[0]) - WORKSTREAM_ORDER.indexOf(b[0])
    );
  }, [findingsByWorkstream]);

  const filteredChecklist = useMemo(() => {
    return checklistStatusFilter === "all"
      ? checklist
      : checklistStatusFilter === "required"
        ? checklist.filter((item) => item.required)
        : checklist.filter((item) => item.status === checklistStatusFilter);
  }, [checklist, checklistStatusFilter]);

  const checklistByCategory = useMemo(() => {
    return filteredChecklist.reduce((acc, item) => {
      const cat = item.category || "General";
      if (!acc[cat]) acc[cat] = [];
      acc[cat].push(item);
      return acc;
    }, {});
  }, [filteredChecklist]);

  const triage = summary?.triage || null;
  const coverage = summary?.coverage || null;
  const topRisks = summary?.top_risks || [];
  const contradictions = summary?.contradictions || [];
  const valuationSignals = summary?.valuation_signals || [];
  const dealBlockers = summary?.deal_blockers || [];
  const followUpRequests = summary?.follow_up_requests || [];
  const managementQuestions = summary?.management_questions || [];
  const suggestedInvestigations = summary?.suggested_investigations || [];
  const documentGapRegister = summary?.document_gap_register || [];
  const icReadiness = summary?.ic_readiness || null;
  const dataQualityAssessment = summary?.data_quality_assessment || null;
  const workstreams = coverage?.workstreams || [];
  const missingRequiredItems = coverage?.missing_required_items || [];

  return (
    <div className="space-y-6">
      {(triage || coverage || icReadiness || topRisks.length > 0 || dealBlockers.length > 0 || contradictions.length > 0 || valuationSignals.length > 0 || managementQuestions.length > 0 || followUpRequests.length > 0 || documentGapRegister.length > 0 || suggestedInvestigations.length > 0 || dataQualityAssessment) && (
        <div className={`grid grid-cols-1 ${showPdf ? "" : "xl:grid-cols-2"} gap-6`}>
          {icReadiness && (
            <div className="bg-card border rounded-xl p-4 shadow-sm">
              <div className="flex items-center justify-between gap-3 mb-3">
                <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">IC Readiness</h2>
                <span className={`px-2 py-1 text-[10px] font-semibold border rounded-full ${
                  icReadiness.status === "ready_for_draft"
                    ? "bg-green-100 text-green-700 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800"
                    : icReadiness.status === "caution"
                      ? "bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-800"
                      : "bg-red-100 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800"
                }`}>
                  {humanizeLabel(icReadiness.status)}
                </span>
              </div>
              <p className="text-sm font-semibold text-foreground">{icReadiness.headline}</p>
              <p className="text-xs text-muted-foreground mt-1">{icReadiness.recommended_next_step}</p>
              <div className="grid grid-cols-2 gap-3 mt-4">
                <div className="border rounded-lg p-2.5">
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Blockers</p>
                  <p className="text-lg font-bold text-foreground mt-1">{icReadiness.blocker_count || 0}</p>
                </div>
                <div className="border rounded-lg p-2.5">
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Required Gaps</p>
                  <p className="text-lg font-bold text-foreground mt-1">{icReadiness.required_gap_count || 0}</p>
                </div>
                <div className="border rounded-lg p-2.5">
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Review Queue</p>
                  <p className="text-lg font-bold text-foreground mt-1">{icReadiness.verification_review_count || 0}</p>
                </div>
                <div className="border rounded-lg p-2.5">
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Doc Review</p>
                  <p className="text-lg font-bold text-foreground mt-1">{icReadiness.classification_review_count || 0}</p>
                </div>
              </div>
            </div>
          )}

          {triage && (
            <div className="bg-card border rounded-xl p-4 shadow-sm">
              <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">Triage</h2>
              <p className="text-sm font-semibold text-foreground">{triage.headline}</p>
              {triage.next_actions?.length > 0 && (
                <div className="mt-3">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">Next Actions</p>
                  <div className="space-y-2">
                    {triage.next_actions.map((action, idx) => (
                      <div key={`${action}-${idx}`} className="flex items-start gap-2 text-sm">
                        <ChevronRight className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                        <span>{action}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {dealBlockers.length > 0 && (
            <div className="bg-card border rounded-xl p-4 shadow-sm">
              <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">Blockers Before IC</h2>
              <div className="space-y-3">
                {dealBlockers.slice(0, 5).map((item, idx) => (
                  <div key={`${item.title}-${idx}`} className="border rounded-lg p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-foreground">{item.title}</p>
                        <p className="text-xs text-muted-foreground mt-1">{item.detail}</p>
                      </div>
                      <span className={`px-2 py-1 text-[10px] font-semibold border rounded-full ${SEVERITY_STYLES[item.severity] || SEVERITY_STYLES.medium}`}>
                        {item.severity || "medium"}
                      </span>
                    </div>
                    {item.source_document_id && item.source_page_number && (
                      <button
                        onClick={() => onCitationClick({
                          documentId: item.source_document_id,
                          page: item.source_page_number,
                          filename: docNameMap[item.source_document_id] || "Source document",
                        })}
                        className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                      >
                        <FileText className="w-3 h-3" />
                        {(docNameMap[item.source_document_id] || "Source").slice(0, 40)}
                        {" · "}p.{item.source_page_number}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {coverage && (
            <div className="bg-card border rounded-xl p-4 shadow-sm">
              <div className="flex items-center justify-between gap-3 mb-3">
                <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Coverage</h2>
                <span className="text-xs text-muted-foreground">{coverage.classification_review_count || 0} docs need classification review</span>
              </div>
              <div className="space-y-2">
                {workstreams.slice(0, 6).map((stream) => (
                  <div key={stream.category} className="border rounded-lg p-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium capitalize">{getCoverageWorkstreamLabel(stream.category)}</span>
                      <span className={`text-[10px] font-bold uppercase tracking-wider ${
                        stream.status === "gap" ? "text-red-500" : stream.status === "partial" ? "text-yellow-600" : "text-green-600"
                      }`}>
                        {getCoverageStatusLabel(stream.status)}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {stream.covered} covered, {stream.partial} partial, {stream.missing} missing
                    </p>
                  </div>
                ))}
              </div>
              {missingRequiredItems.length > 0 && (
                <div className="mt-4 pt-4 border-t">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">Missing Required Items</p>
                  <div className="space-y-1.5">
                    {missingRequiredItems.slice(0, 5).map((item) => (
                      <div key={item.item_key} className="text-sm text-foreground">
                        {item.title}
                        {item.category && (
                          <span className="text-xs text-muted-foreground"> · {getAnalysisCategoryLabel(item.category)}</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {contradictions.length > 0 && (
            <div className="bg-card border rounded-xl p-4 shadow-sm">
              <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">Contradictions / Reconciliation</h2>
              <div className="space-y-3">
                {contradictions.slice(0, 5).map((item, idx) => (
                  <div key={`${item.title}-${idx}`} className="border rounded-lg p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-foreground">{item.title}</p>
                        <p className="text-xs text-muted-foreground mt-1">{item.summary}</p>
                        {item.metric && (
                          <p className="text-[11px] text-muted-foreground mt-1">Metric: {humanizeLabel(item.metric)}</p>
                        )}
                        {item.spread_ratio && (
                          <p className="text-[11px] text-muted-foreground">Spread ratio: {item.spread_ratio}x</p>
                        )}
                      </div>
                      <span className={`px-2 py-1 text-[10px] font-semibold border rounded-full ${SEVERITY_STYLES[item.severity] || SEVERITY_STYLES.medium}`}>
                        {item.severity || "medium"}
                      </span>
                    </div>
                    {item.source_document_id && item.source_page_number && (
                      <button
                        onClick={() => onCitationClick({
                          documentId: item.source_document_id,
                          page: item.source_page_number,
                          filename: docNameMap[item.source_document_id] || "Source document",
                        })}
                        className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                      >
                        <FileText className="w-3 h-3" />
                        {(docNameMap[item.source_document_id] || "Source").slice(0, 40)}
                        {" · "}p.{item.source_page_number}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {topRisks.length > 0 && (
            <div className="bg-card border rounded-xl p-4 shadow-sm">
              <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">Top Risks</h2>
              <div className="space-y-3">
                {topRisks.slice(0, 5).map((risk, idx) => (
                  <div key={`${risk.title}-${idx}`} className="border rounded-lg p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-foreground">{risk.title}</p>
                        <p className="text-xs text-muted-foreground mt-1">{risk.summary}</p>
                      </div>
                      <span className={`px-2 py-1 text-[10px] font-semibold border rounded-full ${SEVERITY_STYLES[risk.severity] || SEVERITY_STYLES.low}`}>
                        {risk.severity || "low"}
                      </span>
                    </div>
                    {risk.source_document_id && risk.source_page_number && (
                      <button
                        onClick={() => onCitationClick({
                          documentId: risk.source_document_id,
                          page: risk.source_page_number,
                          filename: docNameMap[risk.source_document_id] || "Source document",
                        })}
                        className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                      >
                        <FileText className="w-3 h-3" />
                        {(docNameMap[risk.source_document_id] || "Source").slice(0, 40)}
                        {" · "}p.{risk.source_page_number}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {(valuationSignals.length > 0 || dataQualityAssessment) && (
            <div className="bg-card border rounded-xl p-4 shadow-sm">
              <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">Valuation / Underwriting Signals</h2>
              <div className="space-y-3">
                {valuationSignals.slice(0, 6).map((item, idx) => (
                  <div key={`${item.title}-${idx}`} className="border rounded-lg p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-foreground">{item.title}</p>
                        <p className="text-xs text-muted-foreground mt-1">{item.detail}</p>
                      </div>
                      {item.severity && (
                        <span className={`px-2 py-1 text-[10px] font-semibold border rounded-full shrink-0 ${SEVERITY_STYLES[item.severity] || SEVERITY_STYLES.medium}`}>
                          {item.severity}
                        </span>
                      )}
                    </div>
                    {item.metrics?.length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-2">
                        {item.metrics.map((metric) => (
                          <span key={metric.metric} className="pe-chip text-xs">
                            {humanizeLabel(metric.metric)}: <strong className="ml-1">{metric.metric === "ebitda_margin" ? `${(metric.value * 100).toFixed(1)}%` : `${metric.currency === "EUR" ? "€" : metric.currency === "GBP" ? "£" : "$"}${Number(metric.value).toLocaleString()}`}</strong>
                          </span>
                        ))}
                      </div>
                    )}
                    {item.source_document_id && item.source_page_number && (
                      <button
                        onClick={() => onCitationClick({
                          documentId: item.source_document_id,
                          page: item.source_page_number,
                          filename: docNameMap[item.source_document_id] || "Source document",
                        })}
                        className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                      >
                        <FileText className="w-3 h-3" />
                        {(docNameMap[item.source_document_id] || "Source").slice(0, 40)}
                        {" · "}p.{item.source_page_number}
                      </button>
                    )}
                  </div>
                ))}
                {dataQualityAssessment && (
                  <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                    {dataQualityAssessment}
                  </div>
                )}
              </div>
            </div>
          )}

          {followUpRequests.length > 0 && (
            <div className="bg-card border rounded-xl p-4 shadow-sm">
              <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">Missing Materials / Follow-Up Requests</h2>
              <div className="space-y-3">
                {followUpRequests.map((item, idx) => (
                  <div key={`${item.title}-${idx}`} className="border rounded-lg p-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-foreground">{item.title}</p>
                      <span className={`px-2 py-1 text-[10px] font-semibold border rounded-full ${
                        item.priority === "high"
                          ? "bg-red-100 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800"
                          : "bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-800"
                      }`}>
                        {item.priority || "medium"}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">{item.reason}</p>
                    <p className="text-sm text-foreground mt-2">{item.request}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {managementQuestions.length > 0 && (
            <div className="bg-card border rounded-xl p-4 shadow-sm">
              <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">Management Agenda</h2>
              <div className="space-y-3">
                {managementQuestions.slice(0, 6).map((item, idx) => (
                  <div key={`${item.question}-${idx}`} className="border rounded-lg p-3">
                    <p className="text-sm font-semibold text-foreground">{item.question}</p>
                    {item.rationale && <p className="text-xs text-muted-foreground mt-1">{item.rationale}</p>}
                    {item.related_finding && <p className="text-[11px] text-muted-foreground mt-2">Linked issue: {humanizeLabel(item.related_finding)}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {documentGapRegister.length > 0 && (
            <div className="bg-card border rounded-xl p-4 shadow-sm">
              <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">Document Gap Register</h2>
              <div className="space-y-3">
                {documentGapRegister.slice(0, 8).map((item, idx) => (
                  <div key={`${item.title}-${idx}`} className="border rounded-lg p-3">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-foreground">{item.title}</p>
                      <span className={`px-2 py-1 text-[10px] font-semibold border rounded-full ${
                        item.priority === "high"
                          ? "bg-red-100 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800"
                          : "bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-800"
                      }`}>
                        {item.priority || "medium"}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">{item.detail}</p>
                    {item.expected_doc_types?.length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-2">
                        {item.expected_doc_types.map((docType) => (
                          <span key={docType.type || docType.label} className="pe-chip text-xs">{docType.label || docType.type}</span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {suggestedInvestigations.length > 0 && (
            <div className="bg-card border rounded-xl p-4 shadow-sm">
              <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">Suggested Investigations</h2>
              <div className="space-y-3">
                {suggestedInvestigations.map((item) => (
                  <div key={item.slug} className="border rounded-lg p-3">
                    <p className="text-sm font-semibold text-foreground">{item.title}</p>
                    <p className="text-xs text-muted-foreground mt-1">{item.rationale}</p>
                    <div className="mt-3 flex items-center justify-between gap-3">
                      <span className="text-[11px] text-muted-foreground">
                        Planning handoff only. This does not auto-run an investigation.
                      </span>
                      <button
                        onClick={() => onInvestigationLaunch?.(item)}
                        className="pe-action-ghost !px-3 !py-1.5 text-xs"
                      >
                        Launch Investigation
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {summary?.content_markdown && (
        <div className="bg-card border rounded-xl p-4 shadow-sm">
          <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">AI Summary</h2>
          <div
            className="text-sm leading-relaxed text-foreground prose prose-sm dark:prose-invert max-w-none max-h-64 overflow-y-auto scrollbar-thin"
            dangerouslySetInnerHTML={{ __html: mdToHtml(summary.content_markdown) }}
          />
        </div>
      )}

      <div className={`grid grid-cols-1 ${showPdf ? "" : "lg:grid-cols-2"} gap-6`}>
        <div>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              Diligence Checklist{checklist.length > 0 ? ` (${filteredChecklist.length}/${checklist.length})` : ""}
            </h2>
          </div>
          <div className="pe-filter-bar mb-3">
            {[
              { key: "all", label: "All" },
              { key: "required", label: "Required Only" },
              { key: "covered", label: "Covered" },
              { key: "partial", label: "Partial" },
              { key: "missing", label: "Missing" },
            ].map(({ key, label }) => (
              <FilterPill key={key} active={checklistStatusFilter === key} onClick={() => setChecklistStatusFilter(key)}>
                {label}
              </FilterPill>
            ))}
          </div>
          {filteredChecklist.length === 0 ? (
            <p className="text-sm text-muted-foreground">No checklist items match.</p>
          ) : (
            <div className="bg-card border rounded-xl overflow-hidden shadow-sm">
              {Object.entries(checklistByCategory).map(([cat, items]) => (
                <div key={cat}>
                  <div className="px-4 py-2 bg-muted/40 border-b">
                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider capitalize">
                      {getAnalysisCategoryLabel(cat)}
                    </p>
                  </div>
                  {items.map((item) => (
                    <ChecklistRow key={item.id} item={item} docNameMap={docNameMap} onCitationClick={onCitationClick} />
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              Findings{findings.length > 0 ? ` (${filteredFindings.length}/${findings.length})` : ""}
            </h2>
          </div>

          <div className="pe-filter-bar mb-3">
            <div className="flex gap-1">
              {["all", "open", "resolved", "dismissed"].map((status) => (
                <FilterPill key={status} active={findingFilter.status === status} onClick={() => setFindingFilter((value) => ({ ...value, status }))}>
                  {status.charAt(0).toUpperCase() + status.slice(1)}
                </FilterPill>
              ))}
            </div>
            <div className="w-px h-4 bg-border/60 mx-1" />
            <div className="flex gap-1">
              {["all", "high", "medium", "low"].map((severity) => (
                <FilterPill key={severity} active={findingFilter.severity === severity} onClick={() => setFindingFilter((value) => ({ ...value, severity }))}>
                  {severity.charAt(0).toUpperCase() + severity.slice(1)}
                </FilterPill>
              ))}
            </div>
            <div className="flex-1 min-w-0 flex items-center gap-1.5 bg-background border border-border/60 rounded-lg px-2 py-1">
              <Search className="w-3 h-3 text-muted-foreground shrink-0" />
              <input
                type="text"
                placeholder="Search findings…"
                value={findingFilter.search}
                onChange={(e) => setFindingFilter((value) => ({ ...value, search: e.target.value }))}
                className="text-xs bg-transparent border-0 outline-none w-full placeholder:text-muted-foreground"
              />
            </div>
          </div>
          {filteredFindings.length === 0 ? (
            <p className="text-sm text-muted-foreground">No findings match.</p>
          ) : (
            <div className="space-y-5">
              {groupedFindings.map(([workstream, entries]) => (
                <div key={workstream}>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">
                    {WORKSTREAM_LABELS[workstream] || workstream} ({entries.length})
                  </p>
                  <div className="space-y-3">
                    {entries.map((finding) => (
                      <FindingCard
                        key={finding.id}
                        finding={finding}
                        roomId={roomId}
                        docNameMap={docNameMap}
                        onCitationClick={onCitationClick}
                        onUpdated={(updated) =>
                          setFindings((prev) => prev.map((item) => (item.id === updated.id ? updated : item)))
                        }
                      />
                    ))}
                  </div>
                </div>
              ))}
              {hasMore && (
                <button
                  onClick={() => setFindingsPage((page) => page + 1)}
                  className="w-full text-xs text-muted-foreground hover:text-foreground border border-border/60 rounded-lg py-2.5 hover:bg-muted/30 transition-colors"
                >
                  Show {Math.min(FINDINGS_PAGE_SIZE, filteredFindings.length - visibleFindings.length)} more findings
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
