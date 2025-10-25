// src/components/results/sections/ValuationMultiples.jsx
import { DollarSign } from "lucide-react";
import Section from "../Section";
import DataField from "../DataField";

export default function ValuationMultiples({ data }) {
  const multiples = data.valuation_multiples;

  if (!multiples || !Object.values(multiples).some((v) => v != null)) {
    return null;
  }

  return (
    <Section title="Valuation Multiples" icon={DollarSign} highlight={true}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {multiples.asking_ev_ebitda != null && (
          <DataField
            label="Asking EV / EBITDA"
            value={`${multiples.asking_ev_ebitda.toFixed(1)}x`}
            highlight={true}
          />
        )}
        {multiples.asking_ev_revenue != null && (
          <DataField
            label="Asking EV / Revenue"
            value={`${multiples.asking_ev_revenue.toFixed(1)}x`}
            highlight={true}
          />
        )}
        {multiples.exit_ev_ebitda_estimate != null && (
          <DataField
            label="Est. Exit EV / EBITDA"
            value={`${multiples.exit_ev_ebitda_estimate.toFixed(1)}x`}
          />
        )}
        {multiples.comparable_multiples_range && (
          <DataField
            label="Comparable Range"
            value={multiples.comparable_multiples_range}
          />
        )}
      </div>
    </Section>
  );
}
