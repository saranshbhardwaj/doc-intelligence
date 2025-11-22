// src/components/results/sections/ExtractionNotes.jsx
import { FileText } from "lucide-react";
import Section from "../Section";
import { safeText } from "../../../utils/formatters";

export default function ExtractionNotes({ data }) {
  if (!data?.extraction_notes) return null;

  return (
    <Section title="Extraction Notes" icon={FileText}>
      <div className="bg-accent/10 dark:bg-accent/20 p-4 rounded-lg border border-border">
        <p className="text-foreground text-sm whitespace-pre-line">
          {safeText(data.extraction_notes)}
        </p>
      </div>
    </Section>
  );
}
