// src/components/results/sections/InvestmentThesis.jsx
import { Target } from "lucide-react";
import Section from "../Section";
import { safeText } from "../../../utils/formatters";

export default function InvestmentThesis({ data }) {
  if (!data.investment_thesis) {
    return null;
  }

  return (
    <Section title="Investment Thesis" icon={Target} highlight={true}>
      <div className="bg-gradient-to-br from-blue-50 to-indigo-50 p-6 rounded-xl border-2 border-blue-200">
        <p className="text-muted-foreground leading-relaxed whitespace-pre-line text-base">
          {safeText(data.investment_thesis)}
        </p>
      </div>
    </Section>
  );
}
