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
}) {
  let displayValue = value;

  if (format === "currency") {
    displayValue = formatCurrency(value);
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
          : "bg-gray-50 dark:bg-gray-700/50"
      }`}
    >
      <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
        {label}
      </div>
      <div
        className={`text-lg font-bold ${
          highlight
            ? "text-blue-900 dark:text-blue-100"
            : "text-gray-900 dark:text-white"
        }`}
      >
        {displayValue}
      </div>
    </div>
  );
}
