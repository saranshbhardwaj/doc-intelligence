export default function FieldPills({ fields = {} }) {
  const entries = Object.entries(fields || {}).filter(([, value]) => value !== null && value !== undefined && value !== "");

  if (!entries.length) {
    return <span className="text-xs text-muted-foreground italic">No structured fields extracted.</span>;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([key, value]) => (
        <span key={key} className="pe-chip text-[11px]">
          <span className="font-semibold">{key.replace(/_/g, " ")}:</span> {String(value)}
        </span>
      ))}
    </div>
  );
}
