export default function DealMetricCard({ title, fields, emptyLabel }) {
  const entries = Object.entries(fields || {}).filter(([, value]) => value !== null && value !== undefined && value !== "");

  return (
    <div className="pe-deal-stat">
      <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">{title}</p>
      {entries.length > 0 ? (
        <div className="space-y-1.5">
          {entries.map(([key, value]) => {
            const label = key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
            let display = value;
            if (typeof value === "number") {
              if (key.includes("amount") || key.includes("cap") || key.includes("basket") || key.endsWith("_usd")) display = `$${value.toLocaleString()}`;
              else if (key.includes("pct") || key.endsWith("_pct")) display = `${value}%`;
              else if (key.endsWith("_months")) display = `${value} mo`;
              else if (key.endsWith("_ratio")) display = `${value}x`;
            } else if (typeof value === "boolean") {
              display = value ? "Yes" : "No";
            } else if (Array.isArray(value)) {
              display = value.join(", ");
            }
            return (
              <div key={key} className="flex items-start justify-between gap-2">
                <span className="text-xs text-muted-foreground leading-tight">{label}</span>
                <span className="text-xs font-semibold text-foreground text-right">{String(display)}</span>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground italic">{emptyLabel || "Not extracted"}</p>
      )}
    </div>
  );
}
