/**
 * Enhanced Financials Card - Production-quality financial data display
 *
 * Features:
 * - Beautiful table with zebra striping
 * - Visual metrics cards with icons
 * - Growth indicators
 * - Responsive design
 * - Professional formatting
 * - Embedded mode: No card wrapper (for use inside sections)
 */

import { TrendingUp, DollarSign, BarChart3, Target, TrendingDown } from "lucide-react";
import { Card } from "../ui/card";
import { Badge } from "../ui/badge";
import { formatCurrency } from "../../utils/formatters";

export default function FinancialsCard({ financials, currency = "USD", embedded = false }) {
  if (!financials) return null;

  const hasHistorical = financials.historical && financials.historical.length > 0;
  const hasMetrics = financials.metrics && Object.keys(financials.metrics).length > 0;

  if (!hasHistorical && !hasMetrics) return null;

  // Calculate growth from historical data
  const calculateGrowth = () => {
    if (!hasHistorical || financials.historical.length < 2) return null;
    const sorted = [...financials.historical].sort((a, b) => a.year - b.year);
    const first = sorted[0];
    const last = sorted[sorted.length - 1];

    if (first.revenue && last.revenue) {
      const growth = ((last.revenue - first.revenue) / first.revenue) * 100;
      return {
        percentage: growth,
        isPositive: growth > 0,
        years: `${first.year}-${last.year}`
      };
    }
    return null;
  };

  const growth = calculateGrowth();

  // Content to render (same for both embedded and standalone)
  const renderContent = () => (
    <>
      {/* Key Metrics Dashboard */}
      {hasMetrics && (
        <div className="grid grid-cols-2 gap-4">
          {financials.metrics.rev_cagr !== undefined && (
            <div className="p-4 bg-gradient-to-br from-primary/5 to-primary/10 dark:from-primary/10 dark:to-primary/20 rounded-lg border border-primary/20">
              <div className="flex items-center justify-between mb-2">
                <div className="p-2 bg-primary/20 rounded-lg">
                  <TrendingUp className="w-4 h-4 text-primary" />
                </div>
                <span className={`text-xs font-semibold px-2 py-1 rounded ${
                  financials.metrics.rev_cagr > 0 ? 'bg-success/20 text-success' : 'bg-destructive/20 text-destructive'
                }`}>
                  {financials.metrics.rev_cagr > 0 ? 'Growth' : 'Decline'}
                </span>
              </div>
              <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
                Revenue CAGR
              </div>
              <div className="text-2xl font-bold text-primary">
                {(financials.metrics.rev_cagr * 100).toFixed(1)}%
              </div>
            </div>
          )}

          {financials.metrics.ebitda_margin_latest !== undefined && (
            <div className="p-4 bg-gradient-to-br from-success/5 to-success/10 dark:from-success/10 dark:to-success/20 rounded-lg border border-success/20">
              <div className="flex items-center justify-between mb-2">
                <div className="p-2 bg-success/20 rounded-lg">
                  <Target className="w-4 h-4 text-success" />
                </div>
                <span className={`text-xs font-semibold px-2 py-1 rounded ${
                  financials.metrics.ebitda_margin_latest > 0.15 ? 'bg-success/20 text-success' : 'bg-warning/20 text-warning'
                }`}>
                  {financials.metrics.ebitda_margin_latest > 0.15 ? 'Strong' : 'Moderate'}
                </span>
              </div>
              <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
                EBITDA Margin
              </div>
              <div className="text-2xl font-bold text-success">
                {(financials.metrics.ebitda_margin_latest * 100).toFixed(1)}%
              </div>
            </div>
          )}
        </div>
      )}

      {/* Historical Data Table */}
      {hasHistorical && (
        <div>
          <h3 className="text-sm font-bold text-muted-foreground uppercase mb-3 flex items-center gap-2">
            <DollarSign className="w-4 h-4" />
            Historical Performance
          </h3>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="text-left py-3 px-4 font-bold text-foreground">Year</th>
                  <th className="text-right py-3 px-4 font-bold text-foreground">Revenue</th>
                  <th className="text-right py-3 px-4 font-bold text-foreground">EBITDA</th>
                  <th className="text-right py-3 px-4 font-bold text-foreground">Margin</th>
                </tr>
              </thead>
              <tbody>
                {financials.historical.map((row, idx) => (
                  <tr
                    key={idx}
                    className={`border-t border-border hover:bg-muted/30 transition-colors ${
                      idx % 2 === 0 ? 'bg-background' : 'bg-muted/10'
                    }`}
                  >
                    <td className="py-3 px-4 font-semibold text-foreground">
                      <div className="flex items-center gap-2">
                        {row.year}
                        {idx === financials.historical.length - 1 && (
                          <Badge variant="secondary" className="text-xs">Latest</Badge>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-foreground">
                      {row.revenue ? formatCurrency(row.revenue, currency) : "—"}
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-foreground">
                      {row.ebitda ? formatCurrency(row.ebitda, currency) : "—"}
                    </td>
                    <td className="py-3 px-4 text-right">
                      {row.margin ? (
                        <span className={`font-semibold ${
                          row.margin > 0.2 ? 'text-success' :
                          row.margin > 0.1 ? 'text-primary' :
                          'text-muted-foreground'
                        }`}>
                          {(row.margin * 100).toFixed(1)}%
                        </span>
                      ) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Fiscal Year Info */}
      {financials.fiscal_year_end && (
        <div className="text-xs text-muted-foreground flex items-center gap-2">
          <span className="font-semibold">Fiscal Year End:</span>
          <span>{financials.fiscal_year_end}</span>
        </div>
      )}
    </>
  );

  // If embedded, return content without Card wrapper
  if (embedded) {
    return (
      <div className="space-y-6">
        {renderContent()}
      </div>
    );
  }

  // Standalone mode: render with Card and header
  return (
    <Card className="rounded-xl shadow-lg overflow-hidden border-l-4 border-primary">
      {/* Header */}
      <div className="px-6 py-4 bg-gradient-to-r from-primary/5 to-primary/10 dark:from-primary/10 dark:to-primary/20 border-b border-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-lg">
              <BarChart3 className="w-6 h-6 text-primary" />
            </div>
            <h2 className="text-xl font-bold text-foreground">Financial Performance</h2>
          </div>
          {growth && (
            <Badge className={growth.isPositive ? "bg-success text-success-foreground" : "bg-destructive text-destructive-foreground"}>
              {growth.isPositive ? <TrendingUp className="w-3 h-3 mr-1" /> : <TrendingDown className="w-3 h-3 mr-1" />}
              {Math.abs(growth.percentage).toFixed(1)}% ({growth.years})
            </Badge>
          )}
        </div>
      </div>

      <div className="p-6 space-y-6">
        {renderContent()}
      </div>
    </Card>
  );
}
