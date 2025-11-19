// src/components/DataField.jsx
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
      className={`p-3 rounded-lg transition-colors duration-200 ${
        highlight
          ? "bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-700"
          : "bg-background dark:bg-gray-700/50"
      }`}
    >
      <div className="text-xs font-semibold text-muted-foreground dark:text-muted-foreground uppercase tracking-wide mb-1">
        {label}
      </div>
      <div
        className={`text-lg font-bold ${
          highlight ? "text-blue-900 dark:text-blue-100" : "text-foreground"
        }`}
      >
        {displayValue}
      </div>
    </div>
  );
}
