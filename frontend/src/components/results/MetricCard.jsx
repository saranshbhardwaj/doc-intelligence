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
    <div className="bg-card rounded-xl p-5 shadow-md border border-border hover:shadow-lg transition-shadow">
      <div className="flex items-start justify-between mb-2">
        <div className="text-sm font-medium text-muted-foreground">{label}</div>
        {Icon && <Icon className="w-5 h-5 text-primary" />}
      </div>
      <div className="text-2xl font-bold text-foreground mb-1">
        {displayValue}
      </div>
    </div>
  );
}
