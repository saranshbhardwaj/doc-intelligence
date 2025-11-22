import {
  safeText,
  formatCurrency,
  formatPercentage,
} from "../../utils/formatters";

export default function DataField({
  label,
  value,
  format = "text",
  highlight = false,
  currency = "USD",
}) {
  let displayValue = value;

  if (format === "currency") {
    displayValue = formatCurrency(value, currency);
  } else if (format === "percentage") {
    displayValue = formatPercentage(value);
  } else if (format === "number") {
    displayValue = typeof value === "number" ? value.toLocaleString() : value;
  } else {
    displayValue = safeText(value);
  }

  return (
    <div
      className={`p-3 rounded-lg transition-colors duration-200 border ${
        highlight ? "bg-accent text-accent-foreground" : "bg-background"
      } border-border`}
    >
      <div className="text-xs font-semibold text-foreground uppercase tracking-wide mb-1">
        {label}
      </div>

      <div
        className={`text-lg font-bold ${
          highlight ? "text-accent-foreground" : "text-foreground"
        }`}
      >
        {displayValue}
      </div>
    </div>
  );
}
