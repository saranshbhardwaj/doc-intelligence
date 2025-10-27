// src/components/results/sections/RedFlags.jsx
import { ShieldAlert, TrendingDown, AlertCircle } from "lucide-react";
import Section from "../Section";
import { safeText } from "../../../utils/formatters";

export default function RedFlags({ data }) {
  if (!Array.isArray(data.red_flags) || data.red_flags.length === 0) {
    return null;
  }

  // Count by severity
  const counts = data.red_flags.reduce(
    (acc, flag) => {
      if (flag.severity === "High") acc.high++;
      else if (flag.severity === "Medium") acc.medium++;
      else acc.low++;
      return acc;
    },
    { high: 0, medium: 0, low: 0 }
  );

  // Group by category
  const byCategory = data.red_flags.reduce((acc, flag) => {
    const cat = flag.category || "Other";
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(flag);
    return acc;
  }, {});

  return (
    <Section title="🚩 Automated Red Flags" icon={ShieldAlert}>
      {/* Summary Banner */}
      <div className="mb-6 p-4 bg-gradient-to-r from-red-50 to-orange-50 border-l-4 border-red-500 rounded-r-lg">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-600 mt-0.5 flex-shrink-0" />
          <div className="flex-1">
            <h3 className="font-bold text-red-900 mb-1">
              {data.red_flags.length} Quantitative Red Flag{data.red_flags.length !== 1 ? 's' : ''} Detected
            </h3>
            <p className="text-sm text-red-800 mb-2">
              These flags are automatically detected based on financial metrics and industry benchmarks.
            </p>
            <div className="flex gap-3 text-sm">
              {counts.high > 0 && (
                <span className="bg-red-600 text-white px-2 py-1 rounded font-semibold">
                  {counts.high} High
                </span>
              )}
              {counts.medium > 0 && (
                <span className="bg-yellow-500 text-white px-2 py-1 rounded font-semibold">
                  {counts.medium} Medium
                </span>
              )}
              {counts.low > 0 && (
                <span className="bg-green-500 text-white px-2 py-1 rounded font-semibold">
                  {counts.low} Low
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Flags by Category */}
      {Object.entries(byCategory).map(([category, flags]) => (
        <div key={category} className="mb-6">
          <h4 className="text-sm font-bold text-gray-700 uppercase mb-3 flex items-center gap-2">
            <TrendingDown className="w-4 h-4" />
            {category} Risks
          </h4>
          <div className="space-y-3">
            {flags.map((flag, index) => (
              <div
                key={index}
                className={`border-l-4 p-4 rounded-r-lg shadow-sm hover:shadow-md transition-shadow ${
                  flag.severity === "High"
                    ? "border-red-500 bg-gradient-to-r from-red-50 to-white"
                    : flag.severity === "Medium"
                    ? "border-yellow-500 bg-gradient-to-r from-yellow-50 to-white"
                    : "border-green-500 bg-gradient-to-r from-green-50 to-white"
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className="flex-1">
                    {/* Header with severity and flag name */}
                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                      <span
                        className={`text-xs font-bold px-2 py-1 rounded-full ${
                          flag.severity === "High"
                            ? "bg-red-600 text-white"
                            : flag.severity === "Medium"
                            ? "bg-yellow-500 text-white"
                            : "bg-green-500 text-white"
                        }`}
                      >
                        {safeText(flag.severity)}
                      </span>
                      <span className="font-bold text-gray-900">
                        {safeText(flag.flag)}
                      </span>
                      <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded">
                        Auto-detected
                      </span>
                    </div>

                    {/* Description */}
                    {flag.description && (
                      <p className="text-sm text-gray-700 mb-3">
                        {safeText(flag.description)}
                      </p>
                    )}

                    {/* Metrics */}
                    {flag.metrics && Object.keys(flag.metrics).length > 0 && (
                      <div className="bg-white p-3 rounded border border-gray-200">
                        <span className="text-xs font-semibold text-gray-600 uppercase mb-2 block">
                          Supporting Data:
                        </span>
                        <div className="grid grid-cols-2 gap-2 text-xs">
                          {Object.entries(flag.metrics).map(([key, value]) => (
                            <div key={key} className="flex justify-between">
                              <span className="text-gray-600 capitalize">
                                {key.replace(/_/g, " ")}:
                              </span>
                              <span className="font-mono text-gray-900">
                                {typeof value === "number"
                                  ? value.toLocaleString(undefined, {
                                      maximumFractionDigits: 2,
                                    })
                                  : Array.isArray(value)
                                  ? value.join(", ")
                                  : String(value)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Rule info */}
                    {flag.rule_triggered && (
                      <div className="mt-2 text-xs text-gray-500">
                        Rule: <code className="bg-gray-100 px-1 py-0.5 rounded">{flag.rule_triggered}</code>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </Section>
  );
}
