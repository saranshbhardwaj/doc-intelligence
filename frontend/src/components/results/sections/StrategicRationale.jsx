// src/components/results/sections/StrategicRationale.jsx
import { Target } from "lucide-react";
import Section from "../Section";
import { safeText } from "../../../utils/formatters";

export default function StrategicRationale({ data }) {
  const rationale = data.strategic_rationale;

  if (!rationale || !Object.values(rationale).some((v) => v != null))
    return null;

  return (
    <Section
      title="Strategic Rationale & Deal Thesis"
      icon={Target}
      highlight={true}
    >
      <div className="space-y-4">
        {rationale.deal_thesis && (
          <div className="bg-card p-6 rounded-xl border-2 border-primary">
            <h4 className="text-lg font-bold text-primary-foreground mb-3">
              Deal Thesis
            </h4>
            <p className="text-muted-foreground leading-relaxed whitespace-pre-line">
              {safeText(rationale.deal_thesis)}
            </p>
          </div>
        )}

        {rationale.value_creation_plan && (
          <div className="bg-success p-4 rounded-lg border border-success-foreground/20">
            <h4 className="text-sm font-semibold text-success-foreground mb-2">
              Value Creation Plan
            </h4>
            <p className="text-sm text-muted-foreground whitespace-pre-line">
              {safeText(rationale.value_creation_plan)}
            </p>
          </div>
        )}

        {rationale.add_on_opportunities && (
          <div className="bg-accent p-4 rounded-lg border border-accent-foreground/20">
            <h4 className="text-sm font-semibold text-accent-foreground mb-2">
              Add-on / Roll-up Opportunities
            </h4>
            <p className="text-sm text-muted-foreground whitespace-pre-line">
              {safeText(rationale.add_on_opportunities)}
            </p>
          </div>
        )}

        {Array.isArray(rationale.competitive_advantages) &&
          rationale.competitive_advantages.length > 0 && (
            <div>
              <h4 className="text-md font-semibold text-muted-foreground mb-3">
                Competitive Advantages (USPs)
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {rationale.competitive_advantages.map((advantage, idx) => (
                  <div
                    key={idx}
                    className="bg-card p-3 rounded-lg border border-border flex items-start gap-2"
                  >
                    <svg
                      className="w-5 h-5 text-success flex-shrink-0 mt-0.5"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                    <span className="text-sm text-muted-foreground">
                      {safeText(advantage)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
      </div>
    </Section>
  );
}
