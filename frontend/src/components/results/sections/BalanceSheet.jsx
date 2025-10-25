// src/components/results/sections/BalanceSheet.jsx
import { BarChart3 } from "lucide-react";
import Section from "../Section";
import DataField from "../DataField";

export default function BalanceSheet({ data }) {
  const balance = data.balance_sheet || {};

  if (!balance || Object.keys(balance).length === 0) {
    return null;
  }

  return (
    <Section title="Balance Sheet" icon={BarChart3}>
      {balance.most_recent_year && (
        <div className="mb-4 pb-4 border-b border-gray-200">
          <span className="text-sm font-semibold text-gray-600">
            Most Recent Year:{" "}
            <span className="text-gray-900 text-lg">
              {balance.most_recent_year}
            </span>
          </span>
        </div>
      )}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {balance.total_assets != null && (
          <DataField
            label="Total Assets"
            value={balance.total_assets}
            format="currency"
            highlight={true}
          />
        )}
        {balance.current_assets != null && (
          <DataField
            label="Current Assets"
            value={balance.current_assets}
            format="currency"
          />
        )}
        {balance.fixed_assets != null && (
          <DataField
            label="Fixed Assets"
            value={balance.fixed_assets}
            format="currency"
          />
        )}
        {balance.total_liabilities != null && (
          <DataField
            label="Total Liabilities"
            value={balance.total_liabilities}
            format="currency"
            highlight={true}
          />
        )}
        {balance.current_liabilities != null && (
          <DataField
            label="Current Liabilities"
            value={balance.current_liabilities}
            format="currency"
          />
        )}
        {balance.long_term_debt != null && (
          <DataField
            label="Long-Term Debt"
            value={balance.long_term_debt}
            format="currency"
            highlight={true}
          />
        )}
        {balance.stockholders_equity != null && (
          <DataField
            label="Stockholders Equity"
            value={balance.stockholders_equity}
            format="currency"
            highlight={true}
          />
        )}
        {balance.working_capital != null && (
          <DataField
            label="Working Capital"
            value={balance.working_capital}
            format="currency"
          />
        )}
      </div>
    </Section>
  );
}
