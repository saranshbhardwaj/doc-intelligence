// src/components/results/sections/DerivedMetrics.jsx
import { BarChart3 } from "lucide-react";
import Section from "../Section";
import DataField from "../DataField";
import { sortYearKeysDesc } from "../../../utils/formatters";

export default function DerivedMetrics({ data }) {
  const derived = data.derived_metrics || {};
  const currency = data.financials?.currency || "USD";

  if (!derived || Object.keys(derived).length === 0) {
    return null;
  }

  return (
    <Section title="Derived Metrics & Analysis" icon={BarChart3}>
      <div className="space-y-4">
        {Object.entries(derived).map(([key, value]) => {
          // Check if value is an object (nested metrics by year)
          if (
            typeof value === "object" &&
            value !== null &&
            !Array.isArray(value)
          ) {
            // Render as a year-based metric section
            return (
              <div key={key}>
                <h5 className="text-md font-semibold text-muted-foreground dark:text-gray-300 mb-2 flex items-center gap-2">
                  <div className="w-1 h-5 bg-blue-600 rounded"></div>
                  {key
                    .replace(/_/g, " ")
                    .replace(/\b\w/g, (l) => l.toUpperCase())}
                </h5>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                  {sortYearKeysDesc(Object.keys(value)).map((yearKey) => {
                    const isCurrency =
                      typeof value[yearKey] === "number" &&
                      Math.abs(value[yearKey]) > 1000;
                    return (
                      <DataField
                        key={yearKey}
                        label={yearKey}
                        value={value[yearKey]}
                        format={
                          isCurrency
                            ? "currency"
                            : typeof value[yearKey] === "number" &&
                              Math.abs(value[yearKey]) < 1
                            ? "percentage"
                            : "text"
                        }
                        {...(isCurrency && { currency })}
                      />
                    );
                  })}
                </div>
              </div>
            );
          } else {
            // Render as simple metric
            const isCurrency =
              typeof value === "number" && Math.abs(value) > 1000;
            return (
              <div
                key={key}
                className="inline-block"
                style={{ minWidth: "200px" }}
              >
                <DataField
                  label={key
                    .replace(/_/g, " ")
                    .replace(/\b\w/g, (l) => l.toUpperCase())}
                  value={value}
                  format={
                    isCurrency
                      ? "currency"
                      : typeof value === "number" && Math.abs(value) < 1
                      ? "percentage"
                      : "text"
                  }
                  {...(isCurrency && { currency })}
                />
              </div>
            );
          }
        })}
      </div>
    </Section>
  );
}
