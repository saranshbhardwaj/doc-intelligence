// src/components/results/sections/CapitalStructure.jsx
import { BarChart3 } from "lucide-react";
import Section from "../Section";
import DataField from "../DataField";

export default function CapitalStructure({ data }) {
  const capital = data.capital_structure;

  if (!capital || !Object.values(capital).some((v) => v != null)) {
    return null;
  }

  return (
    <Section title="Capital Structure" icon={BarChart3}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {capital.existing_debt != null && (
          <DataField
            label="Existing Debt"
            value={capital.existing_debt}
            format="currency"
            highlight={true}
          />
        )}
        {capital.debt_to_ebitda != null && (
          <DataField
            label="Debt / EBITDA"
            value={`${capital.debt_to_ebitda.toFixed(1)}x`}
            highlight={true}
          />
        )}
        {capital.proposed_leverage != null && (
          <DataField
            label="Proposed Leverage"
            value={`${capital.proposed_leverage.toFixed(1)}x`}
          />
        )}
        {capital.equity_contribution_estimate != null && (
          <DataField
            label="Est. Equity Contribution"
            value={capital.equity_contribution_estimate}
            format="currency"
          />
        )}
      </div>
    </Section>
  );
}
