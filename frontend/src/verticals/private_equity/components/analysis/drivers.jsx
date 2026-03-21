import { useState } from "react";
import { AlertTriangle, ChevronRight } from "lucide-react";

import { DOC_TYPE_COLORS, mdToHtml } from "../../constants";
import { FINANCIAL_ROW_DEFS, SEVERITY_STYLES } from "../../analysis/displayConstants";
import { fmtCurrency, fmtPct, humanizeLabel } from "../../analysis/formatters";
import { FindingCard } from "./shared.jsx";

export function DealMetricCard({ title, fields, emptyLabel }) {
  const entries = Object.entries(fields || {}).filter(([, value]) => value !== null && value !== undefined && value !== "");

  return (
    <div className="pe-deal-stat">
      <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">{title}</p>
      {entries.length > 0 ? (
        <div className="space-y-1.5">
          {entries.map(([key, value]) => {
            const label = key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
            let display = value;

            if (typeof value === "number") {
              if (key.includes("amount") || key.includes("cap") || key.includes("basket") || key.endsWith("_usd")) {
                display = `$${value.toLocaleString()}`;
              } else if (key.includes("pct") || key.endsWith("_pct")) {
                display = `${value}%`;
              } else if (key.endsWith("_months")) {
                display = `${value} mo`;
              } else if (key.endsWith("_ratio")) {
                display = `${value}x`;
              }
            } else if (typeof value === "boolean") {
              display = value ? "Yes" : "No";
            } else if (Array.isArray(value)) {
              display = value.join(", ");
            }

            return (
              <div key={key} className="flex items-start justify-between gap-2">
                <span className="text-xs text-muted-foreground leading-tight">{label}</span>
                <span className="text-xs font-semibold text-foreground text-right">{String(display)}</span>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground italic">{emptyLabel || "Not extracted"}</p>
      )}
    </div>
  );
}

export function FinancialKPITable({ llmFinancials }) {
  if (!llmFinancials?.historical?.length) {
    return (
      <div className="pe-card p-4 text-center">
        <p className="text-xs text-muted-foreground">
          No financial data available. Financial metrics are extracted from CIMs and financial statements when present.
        </p>
      </div>
    );
  }

  const currency = llmFinancials.currency || "USD";
  const historical = [...llmFinancials.historical].sort((a, b) => String(a.year).localeCompare(String(b.year)));
  const years = historical.map((item) => String(item.year));
  const yearMap = Object.fromEntries(historical.map((item) => [String(item.year), item]));
  const visibleRows = FINANCIAL_ROW_DEFS.filter(({ key }) => years.some((year) => yearMap[year]?.[key] != null));

  const growth = (key, idx) => {
    if (idx === 0) return null;
    const curr = yearMap[years[idx]]?.[key];
    const prev = yearMap[years[idx - 1]]?.[key];
    if (curr == null || prev == null || prev === 0) return null;
    return ((curr / prev) - 1) * 100;
  };

  const GROWTH_KEYS = new Set(["revenue", "ebitda"]);

  return (
    <div className="pe-card overflow-hidden">
      <div className="px-4 py-2.5 bg-muted/30 border-b flex items-center justify-between">
        <h3 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Financial Performance ({currency})</h3>
        <span className="text-[10px] text-muted-foreground/60">AI-extracted</span>
      </div>

      {llmFinancials.data_quality_notes && (
        <div className="flex items-start gap-2 px-4 py-2 bg-amber-50 dark:bg-amber-900/20 border-b border-amber-200 dark:border-amber-800">
          <AlertTriangle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
          <p className="text-[11px] text-amber-700 dark:text-amber-400 leading-snug">
            Verify against source documents. {llmFinancials.data_quality_notes}
          </p>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b bg-muted/20">
              <th className="text-left px-4 py-2 text-muted-foreground font-semibold w-40">Metric</th>
              {years.map((year) => (
                <th key={year} className="text-right px-4 py-2 text-muted-foreground font-semibold">{year}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.flatMap(({ key, label }) => {
              const valueRow = (
                <tr key={key} className="border-b last:border-0 hover:bg-muted/10">
                  <td className="px-4 py-2 font-medium text-foreground">{label}</td>
                  {years.map((year) => {
                    const val = yearMap[year]?.[key];
                    const formatter = key.endsWith("_margin") ? fmtPct : (value) => fmtCurrency(value, currency);
                    return (
                      <td key={year} className="text-right px-4 py-2 text-muted-foreground tabular-nums">
                        {val != null ? formatter(val) : "—"}
                      </td>
                    );
                  })}
                </tr>
              );

              if (!GROWTH_KEYS.has(key) || years.length <= 1) return [valueRow];

              const growthRow = (
                <tr key={`${key}-growth`} className="border-b last:border-0">
                  <td className="px-4 py-1 text-[10px] text-muted-foreground/60 pl-7">YoY growth</td>
                  {years.map((year, idx) => {
                    const g = growth(key, idx);
                    return (
                      <td key={year} className="text-right px-4 py-1 text-[10px] tabular-nums">
                        {g == null ? (
                          <span className="text-muted-foreground/40">—</span>
                        ) : (
                          <span className={g >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}>
                            {g >= 0 ? "↑" : "↓"} {Math.abs(g).toFixed(1)}%
                          </span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );

              return [valueRow, growthRow];
            })}
          </tbody>
        </table>
      </div>

      {llmFinancials.ratios?.length > 0 && (
        <div className="px-4 py-3 border-t flex flex-wrap gap-2">
          {llmFinancials.ratios.map((ratio, idx) => (
            <span key={idx} className="pe-chip text-xs">
              {ratio.metric_name.replace(/_/g, " ")}: <strong className="ml-1">{ratio.value}{ratio.unit ? ratio.unit : ""}</strong>
              {ratio.period && <span className="text-muted-foreground/60 ml-1">({ratio.period})</span>}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function DealSourcingTab({ clauses, findings, summary, docNameMap, onCitationClick, roomId, setFindings, financials }) {
  const [summaryExpanded, setSummaryExpanded] = useState(false);

  const spaClause = clauses.find((clause) => clause.playbook_id === "spa_core");
  const debtClause = clauses.find((clause) => clause.playbook_id === "debt_covenants");
  const concentrationClause = clauses.find((clause) => clause.playbook_id === "customer_concentration");
  const employmentClause = clauses.find((clause) => clause.playbook_id === "employment");

  const financialFindings = findings.filter((finding) => (
    finding.category === "financial" || finding.category === "commercial" || finding.category === "debt"
  ));

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
            <button onClick={() => setSummaryExpanded((value) => !value)} className="text-xs text-primary hover:underline mt-2">
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
              <p className="text-xs text-muted-foreground mt-1">
                Baseline handoff only. Final memo should follow investigations and management follow-up.
              </p>
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
                    <span
                      key={docType.type}
                      className={`text-[10px] px-2 py-0.5 rounded-full font-medium whitespace-nowrap ${DOC_TYPE_COLORS[docType.type] || DOC_TYPE_COLORS.other}`}
                    >
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
          <p className="text-xs text-muted-foreground mb-3">
            Structured deal terms are populated after analysis runs. Re-run analysis to extract.
          </p>
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
                  onUpdated={(updated) =>
                    setFindings((prev) => prev.map((item) => (item.id === updated.id ? updated : item)))
                  }
                />
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
