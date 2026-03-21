import { useEffect, useMemo, useState } from "react";
import { ChevronRight, FileText, Search } from "lucide-react";

import {
  FINDINGS_PAGE_SIZE,
  SEVERITY_STYLES,
  WORKSTREAM_LABELS,
  WORKSTREAM_ORDER,
} from "../../../analysis/displayConstants";
import {
  getAnalysisCategoryLabel,
  getCoverageStatusLabel,
  getCoverageWorkstreamLabel,
  getFindingWorkstream,
} from "../../../analysis/formatters";
import { mdToHtml } from "../../../constants";
import ChecklistRow from "../shared/ChecklistRow";
import FilterPill from "../shared/FilterPill";
import FindingCard from "../shared/FindingCard";

export default function RoomOverviewTab({ checklist, findings, summary, docNameMap, onCitationClick, roomId, setFindings, showPdf, onInvestigationLaunch }) {
  const [findingFilter, setFindingFilter] = useState({ severity: "all", status: "open", search: "" });
  const [findingsPage, setFindingsPage] = useState(1);
  const [checklistStatusFilter, setChecklistStatusFilter] = useState("all");

  useEffect(() => { setFindingsPage(1); }, [findingFilter]);

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

  const findingsByWorkstream = useMemo(() =>
    visibleFindings.reduce((acc, finding) => {
      const workstream = getFindingWorkstream(finding);
      if (!acc[workstream]) acc[workstream] = [];
      acc[workstream].push(finding);
      return acc;
    }, {}),
  [visibleFindings]);

  const groupedFindings = useMemo(() =>
    Object.entries(findingsByWorkstream).sort(
      (a, b) => WORKSTREAM_ORDER.indexOf(a[0]) - WORKSTREAM_ORDER.indexOf(b[0])
    ),
  [findingsByWorkstream]);

  const filteredChecklist = useMemo(() =>
    checklistStatusFilter === "all" ? checklist
      : checklistStatusFilter === "required" ? checklist.filter((item) => item.required)
      : checklist.filter((item) => item.status === checklistStatusFilter),
  [checklist, checklistStatusFilter]);

  const checklistByCategory = useMemo(() =>
    filteredChecklist.reduce((acc, item) => {
      const cat = item.category || "General";
      if (!acc[cat]) acc[cat] = [];
      acc[cat].push(item);
      return acc;
    }, {}),
  [filteredChecklist]);

  const triage = summary?.triage || null;
  const coverage = summary?.coverage || null;
  const topRisks = summary?.top_risks || [];
  const followUpRequests = summary?.follow_up_requests || [];
  const suggestedInvestigations = summary?.suggested_investigations || [];
  const workstreams = coverage?.workstreams || [];
  const missingRequiredItems = coverage?.missing_required_items || [];

  return (
    <div className="space-y-6">
      {(triage || coverage || topRisks.length > 0 || followUpRequests.length > 0 || suggestedInvestigations.length > 0) && (
        <div className={`grid grid-cols-1 ${showPdf ? "" : "xl:grid-cols-2"} gap-6`}>
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
                        {item.category && <span className="text-xs text-muted-foreground"> · {getAnalysisCategoryLabel(item.category)}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
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
                    {(risk.source_document_id && risk.source_page_number) && (
                      <button
                        onClick={() => onCitationClick({
                          documentId: risk.source_document_id,
                          page: risk.source_page_number,
                          filename: docNameMap[risk.source_document_id] || "Source document",
                        })}
                        className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline"
                      >
                        <FileText className="w-3 h-3" />
                        {(docNameMap[risk.source_document_id] || "Source").slice(0, 40)} · p.{risk.source_page_number}
                      </button>
                    )}
                  </div>
                ))}
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

          {suggestedInvestigations.length > 0 && (
            <div className="bg-card border rounded-xl p-4 shadow-sm">
              <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">Suggested Investigations</h2>
              <div className="space-y-3">
                {suggestedInvestigations.map((item) => (
                  <div key={item.slug} className="border rounded-lg p-3">
                    <p className="text-sm font-semibold text-foreground">{item.title}</p>
                    <p className="text-xs text-muted-foreground mt-1">{item.rationale}</p>
                    <div className="mt-3 flex items-center justify-between gap-3">
                      <span className="text-[11px] text-muted-foreground">Planning handoff only. This does not auto-run an investigation.</span>
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

        <div>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              Findings{findings.length > 0 ? ` (${filteredFindings.length}/${findings.length})` : ""}
            </h2>
          </div>

          <div className="pe-filter-bar mb-3">
            <div className="flex gap-1">
              {["all", "open", "resolved", "dismissed"].map((status) => (
                <FilterPill key={status} active={findingFilter.status === status} onClick={() => setFindingFilter((prev) => ({ ...prev, status }))}>
                  {status.charAt(0).toUpperCase() + status.slice(1)}
                </FilterPill>
              ))}
            </div>
            <div className="w-px h-4 bg-border/60 mx-1" />
            <div className="flex gap-1">
              {["all", "high", "medium", "low"].map((severity) => (
                <FilterPill key={severity} active={findingFilter.severity === severity} onClick={() => setFindingFilter((prev) => ({ ...prev, severity }))}>
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
                onChange={(e) => setFindingFilter((prev) => ({ ...prev, search: e.target.value }))}
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
                        onUpdated={(updated) => setFindings((prev) => prev.map((item) => (item.id === updated.id ? updated : item)))}
                      />
                    ))}
                  </div>
                </div>
              ))}
              {hasMore && (
                <button
                  onClick={() => setFindingsPage((value) => value + 1)}
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
