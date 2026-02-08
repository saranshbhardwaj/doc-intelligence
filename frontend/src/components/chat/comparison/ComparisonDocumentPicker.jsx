/**
 * In-chat document picker for comparison selection.
 * Appears when >3 documents and comparison detected.
 */
import { useState } from "react";
import { FileText, Scale, Check } from "lucide-react";
import { Button } from "../../ui/button";
import { Checkbox } from "../../ui/checkbox";
import { cn } from "../../../lib/utils";

export default function ComparisonDocumentPicker({
  documents = [],
  preSelected = [],
  message = "Select 2-3 documents to compare:",
  onConfirm,
  onSkip,
}) {
  const [selected, setSelected] = useState(preSelected.slice(0, 3));
  const maxDocs = 3;

  const toggleDocument = (docId) => {
    if (selected.includes(docId)) {
      setSelected(selected.filter((id) => id !== docId));
    } else if (selected.length < maxDocs) {
      setSelected([...selected, docId]);
    }
  };

  return (
    <div className="bg-muted/50 rounded-xl border p-4 my-3 animate-fade-in">
      <div className="flex items-center gap-2 mb-3">
        <Scale className="h-4 w-4 text-primary" />
        <span className="text-sm font-medium">Comparison detected</span>
      </div>

      <p className="text-sm text-muted-foreground mb-3">{message}</p>

      <div className="space-y-2 mb-4 max-h-60 overflow-y-auto scrollbar-thin">
        {documents.map((doc) => (
          <label
            key={doc.id}
            className={cn(
              "flex items-center gap-3 p-2 rounded-lg border cursor-pointer transition-colors",
              selected.includes(doc.id)
                ? "bg-primary/10 border-primary"
                : "bg-background hover:bg-muted/50",
              !selected.includes(doc.id) &&
                selected.length >= maxDocs &&
                "opacity-50 cursor-not-allowed"
            )}
          >
            <Checkbox
              checked={selected.includes(doc.id)}
              onCheckedChange={() => toggleDocument(doc.id)}
              disabled={
                !selected.includes(doc.id) && selected.length >= maxDocs
              }
            />
            <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            <span className="text-sm truncate flex-1">{doc.name}</span>
            {selected.includes(doc.id) && (
              <Check className="h-4 w-4 text-primary flex-shrink-0" />
            )}
          </label>
        ))}
      </div>

      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={() => onConfirm(selected)}
          disabled={selected.length < 2}
          className="flex-1"
        >
          <Scale className="h-3.5 w-3.5 mr-2" />
          Compare ({selected.length}/{maxDocs})
        </Button>
        <Button size="sm" variant="ghost" onClick={onSkip} className="flex-1">
          Not comparing
        </Button>
      </div>

      {selected.length === 1 && (
        <p className="text-xs text-muted-foreground mt-2 text-center">
          Select at least 2 documents to compare
        </p>
      )}
    </div>
  );
}
