/**
 * VerdictCard
 * Pass/fail verdict with failure metrics and rationale
 */
import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';

export default function VerdictCard({ verdict }) {
  if (!verdict) return null;

  const tone = verdict.status === 'worth_pursuing' ? 'success' : verdict.status === 'needs_review' ? 'warning' : 'danger';
  const verdictLabel = verdict.status === 'worth_pursuing' ? 'Worth Pursuing' : verdict.status === 'needs_review' ? 'Needs Review' : 'Below Standards';

  const formatMetric = (metric) => {
    switch (metric) {
      case 'irr':
        return 'IRR';
      case 'cash_on_cash':
        return 'Cash-on-Cash';
      case 'equity_multiple':
        return 'Equity Multiple';
      case 'dscr_year_one':
        return 'DSCR (Year 1)';
      case 'ltv':
        return 'LTV';
      case 'stress_dscr_floor':
        return 'Stress Test Floor';
      default:
        return metric;
    }
  };

  const formatValue = (metric, value) => {
    if (value == null) return '—';
    switch (metric) {
      case 'irr':
      case 'cash_on_cash':
      case 'ltv':
        return `${(value * 100).toFixed(1)}%`;
      case 'equity_multiple':
      case 'dscr_year_one':
      case 'stress_dscr_floor':
        return `${value.toFixed(2)}×`;
      default:
        return value.toFixed(2);
    }
  };

  return (
    <div
      className={`rounded-lg border p-6 ${
        tone === 'success'
          ? 'bg-green-500/10 border-green-500/30'
          : tone === 'warning'
            ? 'bg-amber-500/10 border-amber-500/30'
          : 'bg-destructive/10 border-destructive/30'
      }`}
    >
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        {tone === 'success' ? (
          <CheckCircle2 className="w-8 h-8 text-green-600" />
        ) : tone === 'warning' ? (
          <AlertTriangle className="w-8 h-8 text-amber-600" />
        ) : (
          <XCircle className="w-8 h-8 text-destructive" />
        )}
        <h2
          className={`text-xl font-bold ${
            tone === 'success' ? 'text-green-700' : tone === 'warning' ? 'text-amber-700 dark:text-amber-300' : 'text-destructive'
          }`}
        >
          {verdictLabel}
        </h2>
      </div>

      {/* Failures */}
      {verdict.failures && verdict.failures.length > 0 && (
        <div className="mb-4 space-y-2">
          {verdict.failures.map((failure, idx) => (
            <p key={idx} className="text-sm text-muted-foreground">
              <span className="font-medium">
                {formatMetric(failure.metric)}:
              </span>{' '}
              {formatValue(failure.metric, failure.actual)} vs target{' '}
              {formatValue(failure.metric, failure.target)}
            </p>
          ))}
        </div>
      )}

      {/* Rationale */}
      {verdict.rationale && (
        <p className="text-sm text-muted-foreground">
          {verdict.rationale}
        </p>
      )}
    </div>
  );
}
