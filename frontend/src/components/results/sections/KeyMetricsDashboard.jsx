// src/components/results/sections/KeyMetricsDashboard.jsx
import { DollarSign, TrendingUp, BarChart3, Target } from "lucide-react";
import MetricCard from "../MetricCard";
import { sortYearKeysDesc } from "../../../utils/formatters";

export default function KeyMetricsDashboard({ data }) {
  const financials = data.financials || {};
  const tx = data.transaction_details || {};
  const ratios = data.financial_ratios || {};
  const currency = financials.currency || 'USD';

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {tx.asking_price && (
        <MetricCard
          label="Asking Price"
          value={tx.asking_price}
          format="currency"
          currency={currency}
          icon={DollarSign}
        />
      )}
      {Object.keys(financials.revenue_by_year || {}).length > 0 && (
        <MetricCard
          label="Latest Revenue"
          value={
            financials.revenue_by_year[
              sortYearKeysDesc(Object.keys(financials.revenue_by_year))[0]
            ]
          }
          format="currency"
          currency={currency}
          icon={TrendingUp}
        />
      )}
      {Object.keys(financials.adjusted_ebitda_by_year || {}).length > 0 && (
        <MetricCard
          label="Latest Adj. EBITDA"
          value={
            financials.adjusted_ebitda_by_year[
              sortYearKeysDesc(
                Object.keys(financials.adjusted_ebitda_by_year)
              )[0]
            ]
          }
          format="currency"
          currency={currency}
          icon={BarChart3}
        />
      )}
      {ratios.ebitda_margin != null && (
        <MetricCard
          label="EBITDA Margin"
          value={ratios.ebitda_margin}
          format="percentage"
          icon={Target}
        />
      )}
    </div>
  );
}
