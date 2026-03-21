import { useState } from "react";
import { ChevronRight } from "lucide-react";

import { mdToHtml, DOC_TYPE_COLORS } from "../../../constants";
import { humanizeLabel } from "../../../analysis/formatters";
import { SEVERITY_STYLES } from "../../../analysis/displayConstants";
import DealMetricCard from "./DealMetricCard";
import FinancialKPITable from "./FinancialKPITable";
import FindingCard from "../shared/FindingCard";

export default function DealSourcingTab({ clauses, findings, summary, docNameMap, onCitationClick, roomId, setFindings, financials }) {
  const [summaryExpanded, setSummaryExpanded] = useState(false);

  const spaClause = clauses.find((clause) => clause.playbook_id === "spa_core");
  const debtClause = clauses.find((clause) => clause.playbook_id === "debt_covenants");
  const concentrationClause = clauses.find((clause) => clause.playbook_id === "customer_concentration");
  const employmentClause = clauses.find((clause) => clause.playbook_id === "employment");

  const financialFindings = findings.filter((finding) =>
    finding.category === "financial" || finding.category === "commercial" || finding.category === "debt"
  );

  const summaryText = summary?.content_markdown || "";
  const summaryPreview = summaryText.length > 600 ? `${summaryText.slice(0, 600)}…` : summaryText;
  const missingKeyDocuments = summary?.missing_key_documents || [];
  const icMemoInputs = summary?.ic_memo_inputs || null;

  const spaEf = spaClause?.extracted_fields || {};
  const spaFields = {};
  if (spaEf.purchase_price_mechanism) spaFields.purchase_price_mechanism = spaEf.purchase_price_mechanism;
  if (spaEf.earnout_period_months) spaFields.earnout_period_months = spaEf.earnout_period_months;
  if (spaEf.earnout_metric) spaFields.earnout_metric = spaEf.earnout_metric;

  const indemFields = {};
  if (spaEf.cap_amount) indemFields.cap_amount = spaEf.cap_amount;
  if (spaEf.basket_amount) indemFields.basket_amount = spaEf.basket_amount;
  if (spaEf.survival_months) indemFields.survival_months = spaEf.survival_months;

  const debtEf = debtClause?.extracted_fields || {};
  const debtFields = {};
  if (debtEf.max_leverage_ratio) debtFields.max_leverage_ratio = debtEf.max_leverage_ratio;
  if (debtEf.interest_coverage_min) debtFields.interest_coverage_min = debtEf.interest_coverage_min;
  if (debtEf.covenant_holiday_months) debtFields.covenant_holiday_months = debtEf.covenant_holiday_months;

  const concEf = concentrationClause?.extracted_fields || {};
  const concFields = {};
  if (concEf.top_customer_pct) concFields.top_customer_pct = concEf.top_customer_pct;
  if (concEf.exclusivity) concFields.exclusivity = concEf.exclusivity;
  if (concEf.mfn_pricing) concFields.mfn_pricing = concEf.mfn_pricing;

  const hasClauseData = spaClause || debtClause || concentrationClause || employmentClause;

  return (
    <div className="space-y-5">
      {summaryText && (
        <div className="pe-card p-4">
          <h3 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">Diligence Narrative</h3>
          <div
            className={`text-sm leading-relaxed text-foreground prose prose-sm dark:prose-invert max-w-none ${summaryExpanded ? "" : "max-h-40 overflow-hidden"}`}
            dangerouslySetInnerHTML={{ __html: mdToHtml(summaryExpanded ? summaryText : summaryPreview) }}
          />
          {summaryText.length > 600 && (
            <button
              onClick={() => setSummaryExpanded((value) => !value)}
              className="text-xs text-primary hover:underline mt-2"
            >
              {summaryExpanded ? "Show less" : "Read more"}
            </button>
          )}
        </div>
      )}

      {icMemoInputs && (
        <div className="pe-card p-4">
          <div className="flex items-start justify-between gap-3 mb-3">
            <div>
              <h3 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">IC Memo Inputs</h3>
              <p className="text-xs text-muted-foreground mt-1">Baseline handoff only. Final memo should follow investigations and management follow-up.</p>
            </div>
            <span className="pe-chip text-[11px]">{humanizeLabel(icMemoInputs.status) || "draft inputs only"}</span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="border rounded-xl p-3">
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">Top Issues For Memo</p>
              <div className="space-y-2">
                {(icMemoInputs.top_issues_for_memo || []).slice(0, 4).map((item, idx) => (
                  <div key={`${item.title}-${idx}`} className="text-sm">
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 text-[10px] font-semibold border rounded-full ${SEVERITY_STYLES[item.severity] || SEVERITY_STYLES.low}`}>
                        {item.severity || "low"}
                      </span>
                      <span className="font-medium text-foreground">{item.title}</span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">{item.summary}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="border rounded-xl p-3">
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">Critical Gaps</p>
              <div className="space-y-2">
                {(icMemoInputs.critical_gaps || []).length > 0 ? (
                  icMemoInputs.critical_gaps.map((item, idx) => (
                    <div key={`${item}-${idx}`} className="text-sm text-foreground flex items-start gap-2">
                      <ChevronRight className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                      <span>{item}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-muted-foreground italic">No critical gaps highlighted.</p>
                )}
              </div>
            </div>

            <div className="border rounded-xl p-3">
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">Financial Snapshot</p>
              <div className="space-y-1.5 text-sm">
                {Object.entries(icMemoInputs.financial_snapshot || {}).length > 0 ? (
                  Object.entries(icMemoInputs.financial_snapshot || {}).map(([key, value]) => (
                    <div key={key} className="flex items-start justify-between gap-2">
                      <span className="text-muted-foreground">{key.replace(/_/g, " ")}</span>
                      <span className="font-medium text-foreground text-right">{String(value)}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-muted-foreground italic">No financial snapshot available.</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {missingKeyDocuments.length > 0 && (
        <div className="pe-card p-4">
          <h3 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">Missing Key Documents</h3>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {missingKeyDocuments.map((item) => (
              <div key={item.slug} className="border rounded-xl p-3">
                <p className="text-sm font-semibold text-foreground">{item.title}</p>
                <p className="text-xs text-muted-foreground mt-1">{item.reason}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {(item.expected_doc_types || []).map((docType) => (
                    <span key={docType.type} className={`text-[10px] px-2 py-0.5 rounded-full font-medium whitespace-nowrap ${DOC_TYPE_COLORS[docType.type] || DOC_TYPE_COLORS.other}`}>
                      {docType.label}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <FinancialKPITable llmFinancials={financials?.llm_financials} />

      <div>
        <h3 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">Deal Metrics</h3>
        {!hasClauseData && (
          <p className="text-xs text-muted-foreground mb-3">Structured deal terms are populated after analysis runs. Re-run analysis to extract.</p>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          <DealMetricCard title="Purchase Structure" fields={spaFields} emptyLabel="No purchase agreement found" />
          <DealMetricCard title="Indemnification" fields={indemFields} emptyLabel="No indemnification terms found" />
          <DealMetricCard title="Debt & Covenants" fields={debtFields} emptyLabel="No debt covenant terms found" />
          <DealMetricCard title="Revenue Concentration" fields={concFields} emptyLabel="No concentration data found" />
        </div>
      </div>

      {financialFindings.length > 0 && (
        <div>
          <h3 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-3">
            Financial & Commercial Findings ({financialFindings.length})
          </h3>
          <div className="space-y-3">
            {financialFindings
              .sort((a, b) => {
                const sev = { high: 0, medium: 1, low: 2 };
                return (sev[a.severity] ?? 2) - (sev[b.severity] ?? 2);
              })
              .map((finding) => (
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
      )}
    </div>
  );
}
