// src/components/results/sections/OperatingMetrics.jsx
import { Target } from "lucide-react";
import Section from "../Section";
import DataField from "../DataField";
import { safeText, sortYearKeysDesc } from "../../../utils/formatters";

export default function OperatingMetrics({ data }) {
  const metrics = data.operating_metrics;
  const currency = data.financials?.currency || "USD";

  if (!metrics || !Object.values(metrics).some((v) => v != null)) {
    return null;
  }

  return (
    <Section title="Operating Metrics" icon={Target}>
      <div className="space-y-6">
        {/* KPIs */}
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {metrics.working_capital_pct_revenue != null && (
            <DataField
              label="WC % of Revenue"
              value={metrics.working_capital_pct_revenue}
              format="percentage"
            />
          )}
          {metrics.pricing_power && (
            <DataField
              label="Pricing Power"
              value={metrics.pricing_power}
              highlight={metrics.pricing_power === "High"}
            />
          )}
        </div>

        {/* FCF by Year */}
        {metrics.fcf_by_year && Object.keys(metrics.fcf_by_year).length > 0 && (
          <div>
            <h4 className="text-lg font-bold text-muted-foreground dark:text-gray-200 mb-3 flex items-center gap-2">
              <div className="w-1 h-6 bg-green-600 rounded"></div>
              Free Cash Flow by Year
            </h4>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {sortYearKeysDesc(Object.keys(metrics.fcf_by_year)).map(
                (yearKey) => (
                  <DataField
                    key={yearKey}
                    label={yearKey}
                    value={metrics.fcf_by_year[yearKey]}
                    format="currency"
                    currency={currency}
                  />
                )
              )}
            </div>
          </div>
        )}

        {/* CapEx by Year */}
        {metrics.capex_by_year &&
          Object.keys(metrics.capex_by_year).length > 0 && (
            <div>
              <h4 className="text-lg font-bold text-muted-foreground dark:text-gray-200 mb-3 flex items-center gap-2">
                <div className="w-1 h-6 bg-orange-600 rounded"></div>
                CapEx by Year
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                {sortYearKeysDesc(Object.keys(metrics.capex_by_year)).map(
                  (yearKey) => (
                    <DataField
                      key={yearKey}
                      label={yearKey}
                      value={metrics.capex_by_year[yearKey]}
                      format="currency"
                      currency={currency}
                    />
                  )
                )}
              </div>
            </div>
          )}

        {/* Contract Structure */}
        {metrics.contract_structure && (
          <div className="bg-background dark:bg-card p-4 rounded-lg">
            <h4 className="text-sm font-semibold text-muted-foreground dark:text-gray-300 mb-2">
              Contract Structure
            </h4>
            <p className="text-sm text-muted-foreground dark:text-muted-foreground">
              {safeText(metrics.contract_structure)}
            </p>
          </div>
        )}
      </div>
    </Section>
  );
}
