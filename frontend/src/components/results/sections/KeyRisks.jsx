// src/components/results/sections/KeyRisks.jsx
import { AlertTriangle } from "lucide-react";
import Section from "../Section";
import { safeText } from "../../../utils/formatters";

export default function KeyRisks({ data }) {
  if (!Array.isArray(data.key_risks) || data.key_risks.length === 0)
    return null;

  return (
    <Section title="Key Risks" icon={AlertTriangle}>
      <div className="space-y-3">
        {data.key_risks.map((risk, idx) => (
          <div
            key={idx}
            className={`p-5 rounded-lg shadow-sm hover:shadow-md transition-shadow border-l-4 ${
              risk.severity === "High"
                ? "border-destructive bg-destructive/10 dark:bg-destructive/20"
                : risk.severity === "Medium"
                ? "border-warning bg-warning/10 dark:bg-warning/20"
                : "border-accent bg-accent/10 dark:bg-accent/20"
            }`}
          >
            {typeof risk === "object" ? (
              <div className="space-y-2">
                {/* Risk Header */}
                <div className="flex items-center gap-3 flex-wrap">
                  {risk.severity && (
                    <span
                      className={`text-xs font-bold px-3 py-1 rounded-full ${
                        risk.severity === "High"
                          ? "bg-destructive text-foreground"
                          : risk.severity === "Medium"
                          ? "bg-warning text-foreground"
                          : "bg-accent text-foreground"
                      }`}
                    >
                      {safeText(risk.severity)}
                    </span>
                  )}
                  <span className="text-lg font-bold text-foreground">
                    {safeText(risk.risk || "Risk")}
                  </span>
                  {risk.inferred && (
                    <span className="text-xs bg-muted text-foreground px-2 py-1 rounded">
                      Inferred
                    </span>
                  )}
                </div>

                {/* Description */}
                {risk.description && (
                  <p className="text-sm text-foreground">
                    {safeText(risk.description)}
                  </p>
                )}

                {/* Mitigation */}
                {risk.mitigation && (
                  <div className="mt-2 p-3 rounded-lg border border-success/30 bg-background dark:bg-card">
                    <span className="text-xs font-semibold text-success uppercase">
                      Mitigation:
                    </span>
                    <p className="text-sm text-foreground mt-1">
                      {safeText(risk.mitigation)}
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-foreground font-medium">{safeText(risk)}</p>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
}
