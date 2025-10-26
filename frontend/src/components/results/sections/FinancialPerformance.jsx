// src/components/results/sections/FinancialPerformance.jsx
import { DollarSign } from "lucide-react";
import Section from "../Section";
import DataField from "../DataField";
import { safeText, sortYearKeysDesc } from "../../../utils/formatters";

export default function FinancialPerformance({ data }) {
  const financials = data.financials || {};
  const currency = financials.currency || 'USD';

  if (!financials || Object.keys(financials).length === 0) {
    return null;
  }

  return (
    <Section title="Financial Performance" icon={DollarSign}>
      <div className="space-y-6">
        {/* Header Info */}
        <div className="flex gap-4 items-center pb-4 border-b border-gray-200 dark:border-gray-700">
          {financials.currency && (
            <span className="text-sm font-semibold text-gray-600 dark:text-gray-400">
              Currency:{" "}
              <span className="text-gray-900 dark:text-gray-100">
                {safeText(financials.currency)}
              </span>
            </span>
          )}
          {financials.fiscal_year_end && (
            <span className="text-sm font-semibold text-gray-600 dark:text-gray-400">
              Fiscal Year End:{" "}
              <span className="text-gray-900 dark:text-gray-100">
                {safeText(financials.fiscal_year_end)}
              </span>
            </span>
          )}
        </div>

        {/* Revenue */}
        {financials.revenue_by_year &&
          Object.keys(financials.revenue_by_year).length > 0 && (
            <div>
              <h4 className="text-lg font-bold text-gray-800 dark:text-gray-200 mb-3 flex items-center gap-2">
                <div className="w-1 h-6 bg-blue-600 rounded"></div>
                Revenue by Year
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
                {sortYearKeysDesc(Object.keys(financials.revenue_by_year)).map(
                  (yearKey) => {
                    const isProjected = yearKey.startsWith("projected_");
                    const label = isProjected
                      ? `${yearKey.replace("projected_", "")} (Proj)`
                      : yearKey;
                    return (
                      <DataField
                        key={yearKey}
                        label={label}
                        value={financials.revenue_by_year[yearKey]}
                        format="currency"
                        currency={currency}
                        highlight={isProjected}
                      />
                    );
                  }
                )}
              </div>
            </div>
          )}

        {/* EBITDA */}
        {financials.ebitda_by_year &&
          Object.keys(financials.ebitda_by_year).length > 0 && (
            <div>
              <h4 className="text-lg font-bold text-gray-800 dark:text-gray-200 mb-3 flex items-center gap-2">
                <div className="w-1 h-6 bg-green-600 rounded"></div>
                EBITDA by Year
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
                {sortYearKeysDesc(Object.keys(financials.ebitda_by_year)).map(
                  (yearKey) => {
                    const isProjected = yearKey.startsWith("projected_");
                    const label = isProjected
                      ? `${yearKey.replace("projected_", "")} (Proj)`
                      : yearKey;
                    return (
                      <DataField
                        key={yearKey}
                        label={label}
                        value={financials.ebitda_by_year[yearKey]}
                        format="currency"
                        currency={currency}
                        highlight={isProjected}
                      />
                    );
                  }
                )}
              </div>
            </div>
          )}

        {/* Adjusted EBITDA */}
        {financials.adjusted_ebitda_by_year &&
          Object.keys(financials.adjusted_ebitda_by_year).length > 0 && (
            <div>
              <h4 className="text-lg font-bold text-gray-800 dark:text-gray-200 mb-3 flex items-center gap-2">
                <div className="w-1 h-6 bg-purple-600 rounded"></div>
                Adjusted EBITDA by Year
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
                {sortYearKeysDesc(
                  Object.keys(financials.adjusted_ebitda_by_year)
                ).map((yearKey) => {
                  const isProjected = yearKey.startsWith("projected_");
                  const label = isProjected
                    ? `${yearKey.replace("projected_", "")} (Proj)`
                    : yearKey;
                  return (
                    <DataField
                      key={yearKey}
                      label={label}
                      value={financials.adjusted_ebitda_by_year[yearKey]}
                      format="currency"
                      currency={currency}
                      highlight={isProjected}
                    />
                  );
                })}
              </div>
            </div>
          )}

        {/* Net Income */}
        {financials.net_income_by_year &&
          Object.keys(financials.net_income_by_year).length > 0 && (
            <div>
              <h4 className="text-lg font-bold text-gray-800 dark:text-gray-200 mb-3 flex items-center gap-2">
                <div className="w-1 h-6 bg-indigo-600 rounded"></div>
                Net Income by Year
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
                {sortYearKeysDesc(
                  Object.keys(financials.net_income_by_year)
                ).map((yearKey) => (
                  <DataField
                    key={yearKey}
                    label={
                      yearKey.startsWith("projected_")
                        ? `${yearKey.replace("projected_", "")} (Proj)`
                        : yearKey
                    }
                    value={financials.net_income_by_year[yearKey]}
                    format="currency"
                    currency={currency}
                  />
                ))}
              </div>
            </div>
          )}

        {/* Gross Margin */}
        {financials.gross_margin_by_year &&
          Object.keys(financials.gross_margin_by_year).length > 0 && (
            <div>
              <h4 className="text-lg font-bold text-gray-800 dark:text-gray-200 mb-3 flex items-center gap-2">
                <div className="w-1 h-6 bg-amber-600 rounded"></div>
                Gross Margin by Year
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
                {sortYearKeysDesc(
                  Object.keys(financials.gross_margin_by_year)
                ).map((yearKey) => (
                  <DataField
                    key={yearKey}
                    label={
                      yearKey.startsWith("projected_")
                        ? `${yearKey.replace("projected_", "")} (Proj)`
                        : yearKey
                    }
                    value={financials.gross_margin_by_year[yearKey]}
                    format="percentage"
                  />
                ))}
              </div>
            </div>
          )}

        {/* Other Metrics */}
        {financials.other_metrics &&
          Object.keys(financials.other_metrics).length > 0 && (
            <div>
              <h4 className="text-lg font-bold text-gray-800 dark:text-gray-200 mb-3">
                Other Financial Metrics
              </h4>
              <div className="space-y-4">
                {Object.entries(financials.other_metrics).map(
                  ([key, value]) => {
                    // Check if value is an object (like cogs_by_year)
                    if (
                      typeof value === "object" &&
                      value !== null &&
                      !Array.isArray(value)
                    ) {
                      // Render as a year-based metric
                      return (
                        <div key={key}>
                          <h5 className="text-md font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                            <div className="w-1 h-5 bg-orange-600 rounded"></div>
                            {key
                              .replace(/_/g, " ")
                              .replace(/\b\w/g, (l) => l.toUpperCase())}
                          </h5>
                          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
                            {sortYearKeysDesc(Object.keys(value)).map(
                              (yearKey) => (
                                <DataField
                                  key={yearKey}
                                  label={yearKey}
                                  value={value[yearKey]}
                                  format="currency"
                                  currency={currency}
                                />
                              )
                            )}
                          </div>
                        </div>
                      );
                    } else {
                      // Render as simple text field
                      const isCurrency = typeof value === "number" && Math.abs(value) > 1000;
                      return (
                        <DataField
                          key={key}
                          label={key
                            .replace(/_/g, " ")
                            .replace(/\b\w/g, (l) => l.toUpperCase())}
                          value={value}
                          format={isCurrency ? "currency" : "text"}
                          {...(isCurrency && { currency })}
                        />
                      );
                    }
                  }
                )}
              </div>
            </div>
          )}
      </div>
    </Section>
  );
}
