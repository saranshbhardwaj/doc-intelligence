// src/components/results/sections/GrowthAnalysis.jsx
import { TrendingUp } from "lucide-react";
import Section from "../Section";
import DataField from "../DataField";
import { safeText } from "../../../utils/formatters";

export default function GrowthAnalysis({ data }) {
  const growth = data.growth_analysis || {};
  if (!growth || !Object.values(growth).some((v) => v != null)) return null;

  const renderTextCard = (title, content, color) => (
    <div className={`bg-${color}-50 p-4 rounded-lg border border-${color}-200`}>
      <h4 className={`text-sm font-semibold text-${color}-800 mb-2`}>
        {title}
      </h4>
      <p className="text-sm text-muted-foreground">{safeText(content)}</p>
    </div>
  );

  return (
    <Section title="Growth Analysis" icon={TrendingUp} highlight={true}>
      {/* Numeric Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {growth.historical_cagr != null && (
          <DataField
            label="Historical CAGR"
            value={growth.historical_cagr}
            format="percentage"
            highlight={true}
          />
        )}
        {growth.projected_cagr != null && (
          <DataField
            label="Projected CAGR"
            value={growth.projected_cagr}
            format="percentage"
            highlight={true}
          />
        )}
        {growth.organic_pct != null && (
          <DataField
            label="Organic Growth %"
            value={growth.organic_pct}
            format="percentage"
          />
        )}
        {growth.m_and_a_pct != null && (
          <DataField
            label="M&A Growth %"
            value={growth.m_and_a_pct}
            format="percentage"
          />
        )}
      </div>

      {/* Text Descriptions */}
      <div className="space-y-4">
        {growth.organic_growth_estimate &&
          renderTextCard(
            "Organic Growth Drivers",
            growth.organic_growth_estimate,
            "green"
          )}
        {growth.m_and_a_summary &&
          renderTextCard("M&A Impact", growth.m_and_a_summary, "purple")}
        {growth.notes &&
          renderTextCard("Additional Notes", growth.notes, "blue")}
      </div>
    </Section>
  );
}
