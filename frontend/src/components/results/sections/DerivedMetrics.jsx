// src/components/results/sections/DerivedMetrics.jsx
import { BarChart3 } from "lucide-react";
import Section from "../Section";
import DataField from "../DataField";

export default function DerivedMetrics({ data }) {
  const derived = data.derived_metrics || {};

  if (!derived || Object.keys(derived).length === 0) {
    return null;
  }

  return (
    <Section title="Derived Metrics & Analysis" icon={BarChart3}>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {Object.entries(derived).map(([key, value]) => (
          <DataField
            key={key}
            label={key
              .replace(/_/g, " ")
              .replace(/\b\w/g, (l) => l.toUpperCase())}
            value={value}
            format={
              typeof value === "number" && Math.abs(value) > 1000
                ? "currency"
                : typeof value === "number" && Math.abs(value) < 1
                ? "percentage"
                : "text"
            }
          />
        ))}
      </div>
    </Section>
  );
}
