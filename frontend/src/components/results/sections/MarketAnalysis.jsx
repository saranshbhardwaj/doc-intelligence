// src/components/results/sections/MarketAnalysis.jsx
import { Award } from "lucide-react";
import Section from "../Section";
import DataField from "../DataField";

export default function MarketAnalysis({ data }) {
  const market = data.market || {};
  const currency = data.financials?.currency || 'USD';

  if (!market || !Object.values(market).some((v) => v != null)) {
    return null;
  }

  return (
    <Section title="Market Analysis" icon={Award}>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {market.market_size != null && (
          <DataField label="Market Size" value={market.market_size} />
        )}
        {market.market_size_estimate != null && (
          <DataField
            label="Market Size (Est.)"
            value={market.market_size_estimate}
            format="currency"
            currency={currency}
          />
        )}
        {market.market_growth_rate != null && (
          <DataField
            label="Market Growth Rate"
            value={market.market_growth_rate}
          />
        )}
        {market.competitive_position != null && (
          <DataField
            label="Competitive Position"
            value={market.competitive_position}
          />
        )}
        {market.market_share != null && (
          <DataField label="Market Share" value={market.market_share} />
        )}
      </div>
    </Section>
  );
}
