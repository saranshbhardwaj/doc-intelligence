// src/components/results/sections/FinancialPerformance.jsx
import { DollarSign } from "lucide-react";
import Section from "../Section";
import DataField from "../DataField";
import { safeText, sortYearKeysDesc } from "../../../utils/formatters";

export default function FinancialPerformance({ data }) {
  const financials = data.financials || {};
  const currency = financials.currency || "USD";

  if (!financials || Object.keys(financials).length === 0) return null;

  const yearGridClasses =
    "grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3";

  const renderYearMetrics = (metrics, highlightPrefix, accent = "primary") =>
    sortYearKeysDesc(Object.keys(metrics)).map((yearKey) => {
      const isProjected = yearKey.startsWith(highlightPrefix);
      const label = isProjected
        ? `${yearKey.replace(highlightPrefix, "")} (Proj)`
        : yearKey;
      return (
        <DataField
          key={yearKey}
          label={label}
          value={metrics[yearKey]}
          format="currency"
          currency={currency}
          highlight={isProjected}
        />
      );
    });

  return (
    <Section title="Financial Performance" icon={DollarSign}>
      <div className="space-y-6">
        {/* Header Info */}
        <div className="flex gap-4 items-center pb-4 border-b border-border">
          {financials.currency && (
            <span className="text-sm font-semibold text-muted-foreground">
              Currency:{" "}
              <span className="text-foreground">{safeText(currency)}</span>
            </span>
          )}
          {financials.fiscal_year_end && (
            <span className="text-sm font-semibold text-muted-foreground">
              Fiscal Year End:{" "}
              <span className="text-foreground">
                {safeText(financials.fiscal_year_end)}
              </span>
            </span>
          )}
        </div>

        {/* Revenue */}
        {financials.revenue_by_year && (
          <div>
            <h4 className="text-lg font-bold text-muted-foreground mb-3 flex items-center gap-2">
              <div className="w-1 h-6 bg-primary rounded"></div>
              Revenue by Year
            </h4>
            <div className={yearGridClasses}>
              {renderYearMetrics(financials.revenue_by_year, "projected_")}
            </div>
          </div>
        )}

        {/* EBITDA */}
        {financials.ebitda_by_year && (
          <div>
            <h4 className="text-lg font-bold text-muted-foreground mb-3 flex items-center gap-2">
              <div className="w-1 h-6 bg-success rounded"></div>
              EBITDA by Year
            </h4>
            <div className={yearGridClasses}>
              {renderYearMetrics(financials.ebitda_by_year, "projected_")}
            </div>
          </div>
        )}

        {/* Adjusted EBITDA */}
        {financials.adjusted_ebitda_by_year && (
          <div>
            <h4 className="text-lg font-bold text-muted-foreground mb-3 flex items-center gap-2">
              <div className="w-1 h-6 bg-accent rounded"></div>
              Adjusted EBITDA by Year
            </h4>
            <div className={yearGridClasses}>
              {renderYearMetrics(
                financials.adjusted_ebitda_by_year,
                "projected_"
              )}
            </div>
          </div>
        )}

        {/* Net Income */}
        {financials.net_income_by_year && (
          <div>
            <h4 className="text-lg font-bold text-muted-foreground mb-3 flex items-center gap-2">
              <div className="w-1 h-6 bg-secondary rounded"></div>
              Net Income by Year
            </h4>
            <div className={yearGridClasses}>
              {renderYearMetrics(financials.net_income_by_year, "projected_")}
            </div>
          </div>
        )}

        {/* Gross Margin */}
        {financials.gross_margin_by_year && (
          <div>
            <h4 className="text-lg font-bold text-muted-foreground mb-3 flex items-center gap-2">
              <div className="w-1 h-6 bg-warning rounded"></div>
              Gross Margin by Year
            </h4>
            <div className={yearGridClasses}>
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
        {financials.other_metrics && (
          <div>
            <h4 className="text-lg font-bold text-muted-foreground mb-3">
              Other Financial Metrics
            </h4>
            <div className="space-y-4">
              {Object.entries(financials.other_metrics).map(([key, value]) => {
                if (
                  typeof value === "object" &&
                  value !== null &&
                  !Array.isArray(value)
                ) {
                  return (
                    <div key={key}>
                      <h5 className="text-md font-semibold text-muted-foreground mb-2 flex items-center gap-2">
                        <div className="w-1 h-5 bg-accent rounded"></div>
                        {key
                          .replace(/_/g, " ")
                          .replace(/\b\w/g, (l) => l.toUpperCase())}
                      </h5>
                      <div className={yearGridClasses}>
                        {renderYearMetrics(value, "")}
                      </div>
                    </div>
                  );
                } else {
                  const isCurrency =
                    typeof value === "number" && Math.abs(value) > 1000;
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
              })}
            </div>
          </div>
        )}
      </div>
    </Section>
  );
}
