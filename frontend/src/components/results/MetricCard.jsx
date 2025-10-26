// src/components/results/MetricCard.jsx
import {
  formatCurrency,
  formatPercentage,
  safeText,
} from "../../utils/formatters";

export default function MetricCard({
  label,
  value,
  format = "text",
  icon: Icon,
  currency = "USD",
}) {
  let displayValue = value;

  if (format === "currency") {
    displayValue = formatCurrency(value, currency);
  } else if (format === "percentage") {
    displayValue = formatPercentage(value);
  } else {
    displayValue = safeText(value);
  }

  return (
    <div className="bg-gradient-to-br from-white to-gray-50 rounded-xl p-5 shadow-md border border-gray-200 hover:shadow-lg transition-shadow">
      <div className="flex items-start justify-between mb-2">
        <div className="text-sm font-medium text-gray-600">{label}</div>
        {Icon && <Icon className="w-5 h-5 text-blue-600" />}
      </div>
      <div className="text-2xl font-bold text-gray-900 mb-1">
        {displayValue}
      </div>
    </div>
  );
}
