export default function KeyValueList({ rows }) {
  return (
    <div className="space-y-3">
      {rows.map((row) => (
        <div key={row.label} className="underwriting-kv-row">
          <div className="min-w-0">
            <p className="underwriting-kv-label">{row.label}</p>
            {row.help ? <p className="mt-1 text-xs leading-5 text-muted-foreground">{row.help}</p> : null}
          </div>
          <div className="underwriting-kv-value">{row.value}</div>
        </div>
      ))}
    </div>
  );
}
