// src/components/results/sections/FinancialRatios.jsx
import { Target } from "lucide-react";
import Section from "../Section";
import DataField from "../DataField";

export default function FinancialRatios({ data }) {
  const ratios = data.financial_ratios || {};
  if (!ratios || !Object.values(ratios).some((v) => v != null)) return null;

  const renderDataFields = (fields, highlightKeys = []) => {
    return fields.map(([label, value]) => {
      if (value == null) return null;
      const formattedValue =
        typeof value === "number" && !label.includes("%")
          ? Number(value).toFixed(2)
          : value;
      return (
        <DataField
          key={label}
          label={label}
          value={formattedValue}
          format={
            label.includes("%") ||
            label.includes("Margin") ||
            label.includes("Return")
              ? "percentage"
              : "text"
          }
          highlight={highlightKeys.includes(label)}
        />
      );
    });
  };

  return (
    <Section title="Financial Ratios & Metrics" icon={Target}>
      <div className="space-y-6">
        {/* Key PE Metrics */}
        <div>
          <h4 className="text-lg font-bold text-muted-foreground mb-3">
            Key PE Metrics
          </h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {renderDataFields(
              [
                ["EBITDA Margin", ratios.ebitda_margin],
                ["Net Debt / EBITDA", ratios.net_debt_to_ebitda],
                ["CapEx % of Revenue", ratios.capex_pct_revenue],
                ["Return on Equity", ratios.return_on_equity],
              ],
              [
                "EBITDA Margin",
                "Net Debt / EBITDA",
                "CapEx % of Revenue",
                "Return on Equity",
              ]
            )}
          </div>
        </div>

        {/* Liquidity Ratios */}
        <div>
          <h4 className="text-lg font-bold text-muted-foreground mb-3">
            Liquidity Ratios
          </h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {renderDataFields([
              ["Current Ratio", ratios.current_ratio],
              ["Quick Ratio", ratios.quick_ratio],
            ])}
          </div>
        </div>

        {/* Leverage & Profitability */}
        <div>
          <h4 className="text-lg font-bold text-muted-foreground mb-3">
            Leverage & Profitability
          </h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {renderDataFields([
              ["Debt to Equity", ratios.debt_to_equity],
              ["Return on Assets", ratios.return_on_assets],
            ])}
          </div>
        </div>

        {/* Efficiency Ratios */}
        <div>
          <h4 className="text-lg font-bold text-muted-foreground mb-3">
            Efficiency Ratios
          </h4>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {renderDataFields([
              ["Inventory Turnover", ratios.inventory_turnover],
              ["A/R Turnover", ratios.accounts_receivable_turnover],
            ])}
          </div>
        </div>
      </div>
    </Section>
  );
}
