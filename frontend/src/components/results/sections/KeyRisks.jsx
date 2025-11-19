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
                              ? "bg-red-600 text-foreground"
                              : risk.severity === "Medium"
                              ? "bg-yellow-500 text-foreground"
                              : "bg-accent text-foreground"
                          }`}
                        >
                          {safeText(risk.severity)}
                        </span>
                      )}
                      <span className="font-bold text-foreground text-lg">
                        {safeText(risk.risk || "Risk")}
                      </span>
                      {risk.inferred && (
                        <span className="text-xs bg-muted text-muted-foreground px-2 py-1 rounded">
                          Inferred
                        </span>
                      )}
                    </div>
                    {risk.description && (
                      <p className="text-sm text-muted-foreground mb-2">
                        {safeText(risk.description)}
                      </p>
                    )}
                    {risk.mitigation && (
                      <div className="mt-3 bg-background p-3 rounded border border-green-200">
                        <span className="text-xs font-semibold text-green-700 uppercase">
                          Mitigation:
                        </span>
                        <p className="text-sm text-muted-foreground mt-1">
                          {safeText(risk.mitigation)}
                        </p>
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-muted-foreground font-medium">
                    {safeText(risk)}
                  </p>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}
