/**
 * Workflow Metrics Dashboard - Top-level KPI cards
 *
 * Displays key metrics at a glance with visual indicators
 * Similar to KeyMetricsDashboard from extraction results
 */

import { DollarSign, TrendingUp, BarChart3, Target, Building2, Users, AlertTriangle, Sparkles } from "lucide-react";
import { Card } from "../ui/card";
import { formatCurrency } from "../../utils/formatters";

function MetricCard({ label, value, format = "text", currency = "USD", icon: Icon, color = "blue", trend }) {
  const formatValue = () => {
    if (value === null || value === undefined) return "—";

    switch (format) {
      case "currency":
        return formatCurrency(value, currency);
      case "percentage":
        return `${(value * 100).toFixed(1)}%`;
      case "number":
        return value.toLocaleString();
      default:
        return value;
    }
  };

  const colorClasses = {
    blue: {
      bg: "bg-primary/5 dark:bg-primary/10",
      border: "border-primary/20",
      icon: "bg-primary/10 text-primary",
      text: "text-primary"
    },
    green: {
      bg: "bg-success/5 dark:bg-success/10",
      border: "border-success/20",
      icon: "bg-success/10 text-success",
      text: "text-success"
    },
    orange: {
      bg: "bg-warning/5 dark:bg-warning/10",
      border: "border-warning/20",
      icon: "bg-warning/10 text-warning",
      text: "text-warning"
    },
    purple: {
      bg: "bg-primary/5 dark:bg-primary/10",
      border: "border-primary/20",
      icon: "bg-primary/10 text-primary",
      text: "text-primary"
    }
  };

  const colors = colorClasses[color] || colorClasses.blue;

  return (
    <Card className={`${colors.bg} border ${colors.border} rounded-xl p-4 hover:shadow-md transition-shadow`}>
      <div className="flex items-center justify-between mb-3">
        <div className={`p-2 ${colors.icon} rounded-lg`}>
          <Icon className="w-5 h-5" />
        </div>
        {trend && (
          <span className={`text-xs font-semibold px-2 py-1 rounded ${
            trend > 0 ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
          }`}>
            {trend > 0 ? '+' : ''}{trend.toFixed(1)}%
          </span>
        )}
      </div>
      <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
        {label}
      </div>
      <div className={`text-2xl font-bold ${colors.text}`}>
        {formatValue()}
      </div>
    </Card>
  );
}

export default function WorkflowMetricsDashboard({ data, run }) {
  if (!data) return null;

  const financials = data.financials || {};
  const companyOverview = data.company_overview || {};
  const risks = data.risks || [];
  const opportunities = data.opportunities || [];

  // Get latest financial metrics
  const getLatestValue = (yearData) => {
    if (!yearData || !Array.isArray(yearData) || yearData.length === 0) return null;
    const sorted = [...yearData].sort((a, b) => b.year - a.year);
    return sorted[0];
  };

  const latest = getLatestValue(financials.historical);
  const currency = data.currency || run.currency || "USD";

  // Calculate some derived metrics
  const highRisks = risks.filter(r =>
    (r.severity || "").toLowerCase() === "high" ||
    (r.severity || "").toLowerCase() === "critical"
  ).length;

  const highOpportunities = opportunities.filter(o =>
    (o.impact || "").toLowerCase() === "high"
  ).length;

  const hasMetrics = latest || financials.metrics || companyOverview.industry || risks.length || opportunities.length;

  if (!hasMetrics) return null;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {/* Latest Revenue */}
      {latest && latest.revenue && (
        <MetricCard
          label="Latest Revenue"
          value={latest.revenue}
          format="currency"
          currency={currency}
          icon={DollarSign}
          color="blue"
          trend={financials.metrics?.rev_cagr ? financials.metrics.rev_cagr * 100 : null}
        />
      )}

      {/* Latest EBITDA */}
      {latest && latest.ebitda && (
        <MetricCard
          label="Latest EBITDA"
          value={latest.ebitda}
          format="currency"
          currency={currency}
          icon={TrendingUp}
          color="green"
        />
      )}

      {/* EBITDA Margin */}
      {(latest?.margin || financials.metrics?.ebitda_margin_latest) && (
        <MetricCard
          label="EBITDA Margin"
          value={latest?.margin || financials.metrics.ebitda_margin_latest}
          format="percentage"
          icon={Target}
          color="purple"
        />
      )}

      {/* Industry */}
      {companyOverview.industry && (
        <Card className="bg-gradient-to-br from-indigo-50 to-purple-50 dark:from-indigo-950/30 dark:to-purple-950/30 border border-indigo-200 dark:border-indigo-800 rounded-xl p-4 hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between mb-3">
            <div className="p-2 bg-indigo-600/10 dark:bg-indigo-600/20 text-indigo-600 dark:text-indigo-400 rounded-lg">
              <Building2 className="w-5 h-5" />
            </div>
          </div>
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
            Industry
          </div>
          <div className="text-lg font-bold text-indigo-900 dark:text-indigo-100 leading-tight">
            {companyOverview.industry}
          </div>
        </Card>
      )}

      {/* High Risks Count */}
      {risks.length > 0 && (
        <Card className="bg-gradient-to-br from-red-50 to-orange-50 dark:from-red-950/30 dark:to-orange-950/30 border border-red-200 dark:border-red-800 rounded-xl p-4 hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between mb-3">
            <div className="p-2 bg-red-600/10 dark:bg-red-600/20 text-red-600 dark:text-red-400 rounded-lg">
              <AlertTriangle className="w-5 h-5" />
            </div>
            {highRisks > 0 && (
              <span className="text-xs font-semibold px-2 py-1 rounded bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">
                {highRisks} High
              </span>
            )}
          </div>
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
            Total Risks
          </div>
          <div className="text-2xl font-bold text-red-900 dark:text-red-100">
            {risks.length}
          </div>
        </Card>
      )}

      {/* High Opportunities Count */}
      {opportunities.length > 0 && (
        <Card className="bg-gradient-to-br from-emerald-50 to-green-50 dark:from-emerald-950/30 dark:to-green-950/30 border border-emerald-200 dark:border-emerald-800 rounded-xl p-4 hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between mb-3">
            <div className="p-2 bg-emerald-600/10 dark:bg-emerald-600/20 text-emerald-600 dark:text-emerald-400 rounded-lg">
              <Sparkles className="w-5 h-5" />
            </div>
            {highOpportunities > 0 && (
              <span className="text-xs font-semibold px-2 py-1 rounded bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200">
                {highOpportunities} High
              </span>
            )}
          </div>
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
            Opportunities
          </div>
          <div className="text-2xl font-bold text-emerald-900 dark:text-emerald-100">
            {opportunities.length}
          </div>
        </Card>
      )}
    </div>
  );
}
