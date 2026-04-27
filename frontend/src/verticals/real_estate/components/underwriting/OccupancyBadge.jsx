import { UnderwritingStatusBadge } from './UnderwritingUI';

export default function OccupancyBadge({ pct }) {
  if (pct == null) return <span className="text-sm text-muted-foreground">—</span>;
  const pctValue = pct > 1 ? pct : pct * 100;
  const tone = pctValue >= 85 ? 'success' : pctValue >= 70 ? 'warning' : 'danger';
  return <UnderwritingStatusBadge tone={tone}>{pctValue.toFixed(0)}% occupied</UnderwritingStatusBadge>;
}
