/**
 * MetricTile
 * Compact metric display for key underwriting figures
 * Formats: percent, x (multiple), dollar (abbreviated), number
 */

export default function MetricTile({
  label,
  value,
  format = 'number',
  warn = false,
  className = '',
}) {
  const formatValue = () => {
    if (value === null || value === undefined) return '—';

    switch (format) {
      case 'percent':
        return `${(value * 100).toFixed(1)}%`;
      case 'x':
        return `${value.toFixed(2)}×`;
      case 'dollar':
        if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
        if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
        return `$${value.toFixed(0)}`;
      case 'number':
      default:
        return value.toLocaleString('en-US', { maximumFractionDigits: 1 });
    }
  };

  return (
    <div
      className={`bg-card border border-border rounded-lg p-4 ${
        warn ? 'ring-1 ring-warning' : ''
      } ${className}`}
    >
      <p className="text-xs text-muted-foreground uppercase tracking-wide">
        {label}
      </p>
      <p className="text-2xl font-bold font-display mt-2">
        {formatValue()}
      </p>
    </div>
  );
}
