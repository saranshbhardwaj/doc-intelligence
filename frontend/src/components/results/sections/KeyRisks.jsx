// src/components/results/sections/KeyRisks.jsx
import { AlertTriangle } from "lucide-react";
import Section from "../Section";
import { safeText } from "../../../utils/formatters";

export default function KeyRisks({ data }) {
  if (!Array.isArray(data.key_risks) || data.key_risks.length === 0) {
    return null;
  }

  return (
    <Section title="Key Risks" icon={AlertTriangle}>
      <div className="space-y-3">
        {data.key_risks.map((risk, index) => (
          <div
            key={index}
            className="border-l-4 border-red-500 bg-gradient-to-r from-red-50 to-white p-5 rounded-r-lg shadow-sm hover:shadow-md transition-shadow"
          >
            <div className="flex items-start">
              <div className="flex-1">
                {typeof risk === "object" ? (
                  <>
                    <div className="flex items-center gap-3 mb-2">
                      {risk.severity && (
                        <span
                          className={`text-xs font-bold px-3 py-1 rounded-full ${
                            risk.severity === "High"
                              ? "bg-red-600 text-white"
                              : risk.severity === "Medium"
                              ? "bg-yellow-500 text-white"
                              : "bg-green-500 text-white"
                          }`}
                        >
                          {safeText(risk.severity)}
                        </span>
                      )}
                      <span className="font-bold text-gray-900 text-lg">
                        {safeText(risk.risk || "Risk")}
                      </span>
                      {risk.inferred && (
                        <span className="text-xs bg-gray-200 text-gray-700 px-2 py-1 rounded">
                          Inferred
                        </span>
                      )}
                    </div>
                    {risk.description && (
                      <p className="text-sm text-gray-700 mb-2">
                        {safeText(risk.description)}
                      </p>
                    )}
                    {risk.mitigation && (
                      <div className="mt-3 bg-white p-3 rounded border border-green-200">
                        <span className="text-xs font-semibold text-green-700 uppercase">
                          Mitigation:
                        </span>
                        <p className="text-sm text-gray-700 mt-1">
                          {safeText(risk.mitigation)}
                        </p>
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-gray-800 font-medium">{safeText(risk)}</p>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}
