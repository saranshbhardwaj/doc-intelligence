import { AlertTriangle } from "lucide-react";

import { FINANCIAL_ROW_DEFS } from "../../../analysis/displayConstants";
import { fmtCurrency, fmtPct } from "../../../analysis/formatters";

export default function FinancialKPITable({ llmFinancials }) {
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

  const rowFormatters = {
    revenue: (value) => fmtCurrency(value, currency),
    ebitda: (value) => fmtCurrency(value, currency),
    ebitda_margin: (value) => fmtPct(value),
    gross_profit: (value) => fmtCurrency(value, currency),
    net_income: (value) => fmtCurrency(value, currency),
    free_cash_flow: (value) => fmtCurrency(value, currency),
    capex: (value) => fmtCurrency(value, currency),
  };

  const visibleRows = FINANCIAL_ROW_DEFS.filter(({ key }) => years.some((year) => yearMap[year]?.[key] != null));

  const growth = (key, idx) => {
    if (idx === 0) return null;
    const curr = yearMap[years[idx]]?.[key];
    const prev = yearMap[years[idx - 1]]?.[key];
    if (curr == null || prev == null || prev === 0) return null;
    return ((curr / prev) - 1) * 100;
  };

  const growthKeys = new Set(["revenue", "ebitda"]);

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
              const rows = [
                <tr key={key} className="border-b last:border-0 hover:bg-muted/10">
                  <td className="px-4 py-2 font-medium text-foreground">{label}</td>
                  {years.map((year) => {
                    const val = yearMap[year]?.[key];
                    return (
                      <td key={year} className="text-right px-4 py-2 text-muted-foreground tabular-nums">
                        {val != null ? rowFormatters[key](val) : "—"}
                      </td>
                    );
                  })}
                </tr>,
              ];

              if (growthKeys.has(key) && years.length > 1) {
                rows.push(
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
              }

              return rows;
            })}
          </tbody>
        </table>
      </div>

      {llmFinancials.ratios?.length > 0 && (
        <div className="px-4 py-3 border-t flex flex-wrap gap-2">
          {llmFinancials.ratios.map((ratio, index) => (
            <span key={index} className="pe-chip text-xs">
              {ratio.metric_name.replace(/_/g, " ")}: <strong className="ml-1">{ratio.value}{ratio.unit || ""}</strong>
              {ratio.period && <span className="text-muted-foreground/60 ml-1">({ratio.period})</span>}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
