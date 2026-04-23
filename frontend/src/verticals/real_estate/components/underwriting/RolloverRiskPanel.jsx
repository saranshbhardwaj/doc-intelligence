/**
 * RolloverRiskPanel
 * Lease rollover and concentration risk visualization
 */
import { Progress } from '@/components/ui/progress';

export default function RolloverRiskPanel({ rolloverRisk }) {
  if (!rolloverRisk) return null;

  const formatPercent = (value) => {
    if (value === null || value === undefined) return '0%';
    return `${(value * 100).toFixed(1)}%`;
  };

  const hasHighRisk =
    rolloverRisk.pct_rent_expiring_12mo > 0.40;

  return (
    <div className="space-y-6">
      {/* Expiration buckets */}
      <div className="space-y-4">
        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-medium text-foreground">
              Expiring within 12 months
            </p>
            <p className="text-sm font-semibold text-foreground">
              {formatPercent(rolloverRisk.pct_rent_expiring_12mo)}
            </p>
          </div>
          <Progress
            value={
              Math.min(rolloverRisk.pct_rent_expiring_12mo, 1) * 100
            }
            className="h-2"
          />
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-medium text-foreground">
              Expiring within 24 months
            </p>
            <p className="text-sm font-semibold text-foreground">
              {formatPercent(rolloverRisk.pct_rent_expiring_24mo)}
            </p>
          </div>
          <Progress
            value={
              Math.min(rolloverRisk.pct_rent_expiring_24mo, 1) * 100
            }
            className="h-2"
          />
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-medium text-foreground">
              Expiring within 36 months
            </p>
            <p className="text-sm font-semibold text-foreground">
              {formatPercent(rolloverRisk.pct_rent_expiring_36mo)}
            </p>
          </div>
          <Progress
            value={
              Math.min(rolloverRisk.pct_rent_expiring_36mo, 1) * 100
            }
            className="h-2"
          />
        </div>
      </div>

      {/* Avg remaining term */}
      {rolloverRisk.avg_remaining_term_months && (
        <p className="text-sm text-muted-foreground">
          Average remaining lease term:{' '}
          <span className="font-semibold text-foreground">
            {rolloverRisk.avg_remaining_term_months.toFixed(1)} months
          </span>
        </p>
      )}

      {/* Top 5 tenants */}
      {rolloverRisk.top_5_tenants_pct && (
        <p className="text-sm text-muted-foreground">
          Top 5 tenants represent{' '}
          <span className="font-semibold text-foreground">
            {formatPercent(rolloverRisk.top_5_tenants_pct)}
          </span>{' '}
          of rent
        </p>
      )}

      {/* High risk warning */}
      {hasHighRisk && (
        <div className="p-3 bg-warning/10 border border-warning/30 rounded-md">
          <p className="text-xs text-warning font-semibold">⚠ Warning:</p>
          <p className="text-xs text-muted-foreground mt-1">
            More than 40% of rent expiring in 12 months poses
            significant concentration risk.
          </p>
        </div>
      )}
    </div>
  );
}
