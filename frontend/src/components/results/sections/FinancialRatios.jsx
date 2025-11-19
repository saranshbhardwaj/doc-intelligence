// src/components/results/sections/FinancialRatios.jsx
import { Target } from "lucide-react";
import Section from "../Section";
import DataField from "../DataField";

export default function FinancialRatios({ data }) {
  const ratios = data.financial_ratios || {};

  if (!ratios || !Object.values(ratios).some((v) => v != null)) {
    return null;
  }

  return (
    <Section title="Financial Ratios & Metrics" icon={Target}>
      <div className="space-y-6">
        {/* Key PE Ratios - Highlighted */}
        <div>
          <h4 className="text-lg font-bold text-muted-foreground dark:text-gray-200 mb-3">
            Key PE Metrics
          </h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {ratios.ebitda_margin != null && (
              <DataField
                label="EBITDA Margin"
                value={ratios.ebitda_margin}
                format="percentage"
                highlight={true}
              />
            )}
            {ratios.net_debt_to_ebitda != null && (
              <DataField
                label="Net Debt / EBITDA"
                value={Number(ratios.net_debt_to_ebitda).toFixed(2)}
                highlight={true}
              />
            )}
            {ratios.capex_pct_revenue != null && (
              <DataField
                label="CapEx % of Revenue"
                value={ratios.capex_pct_revenue}
                format="percentage"
                highlight={true}
              />
            )}
            {ratios.return_on_equity != null && (
              <DataField
                label="Return on Equity"
                value={ratios.return_on_equity}
                format="percentage"
                highlight={true}
              />
            )}
          </div>
        </div>

        {/* Liquidity Ratios */}
        <div>
          <h4 className="text-lg font-bold text-muted-foreground dark:text-gray-200 mb-3">
            Liquidity Ratios
          </h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {ratios.current_ratio != null && (
              <DataField
                label="Current Ratio"
                value={Number(ratios.current_ratio).toFixed(2)}
              />
            )}
            {ratios.quick_ratio != null && (
              <DataField
                label="Quick Ratio"
                value={Number(ratios.quick_ratio).toFixed(2)}
              />
            )}
          </div>
        </div>

        {/* Leverage Ratios */}
        <div>
          <h4 className="text-lg font-bold text-muted-foreground dark:text-gray-200 mb-3">
            Leverage & Profitability
          </h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {ratios.debt_to_equity != null && (
              <DataField
                label="Debt to Equity"
                value={Number(ratios.debt_to_equity).toFixed(2)}
              />
            )}
            {ratios.return_on_assets != null && (
              <DataField
                label="Return on Assets"
                value={ratios.return_on_assets}
                format="percentage"
              />
            )}
          </div>
        </div>

        {/* Efficiency Ratios */}
        <div>
          <h4 className="text-lg font-bold text-muted-foreground dark:text-gray-200 mb-3">
            Efficiency Ratios
          </h4>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {ratios.inventory_turnover != null && (
              <DataField
                label="Inventory Turnover"
                value={Number(ratios.inventory_turnover).toFixed(2)}
              />
            )}
            {ratios.accounts_receivable_turnover != null && (
              <DataField
                label="A/R Turnover"
                value={Number(ratios.accounts_receivable_turnover).toFixed(2)}
              />
            )}
          </div>
        </div>
      </div>
    </Section>
  );
}
