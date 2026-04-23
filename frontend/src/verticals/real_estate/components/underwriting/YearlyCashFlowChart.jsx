/**
 * YearlyCashFlowChart
 * 10-year NOI and cash flow projections
 */
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';

const abbreviate = (value) => {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
};

export default function YearlyCashFlowChart({ projections }) {
  if (!projections || projections.length === 0) {
    return (
      <div className="h-72 flex items-center justify-center text-muted-foreground">
        No projection data available
      </div>
    );
  }

  const data = projections.map((p) => ({
    year: p.year,
    noi: p.noi,
    cash_flow: p.cash_flow,
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart
        data={data}
        margin={{ top: 5, right: 30, left: 0, bottom: 5 }}
      >
        <CartesianGrid
          strokeDasharray="3 3"
          stroke="hsl(var(--border))"
        />
        <XAxis
          dataKey="year"
          stroke="hsl(var(--muted-foreground))"
          style={{ fontSize: '12px' }}
        />
        <YAxis
          tickFormatter={(v) => abbreviate(v)}
          stroke="hsl(var(--muted-foreground))"
          style={{ fontSize: '12px' }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
            borderRadius: '6px',
          }}
          formatter={(value) => abbreviate(value)}
          labelFormatter={(label) => `Year ${label}`}
        />
        <Legend />
        <Line
          name="NOI"
          dataKey="noi"
          stroke="hsl(var(--primary))"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
        <Line
          name="Cash Flow"
          dataKey="cash_flow"
          stroke="hsl(var(--accent))"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
