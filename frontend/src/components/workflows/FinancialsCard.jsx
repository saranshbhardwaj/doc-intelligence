import { TrendingUp } from "lucide-react";
import { formatCurrency } from "../../utils/formatters";

export default function FinancialsCard({ financials, currency = "USD" }) {
  if (!financials) return null;

  return (
    <div className="bg-card rounded-xl shadow-md p-6 border-l-4 border-green-500">
      <div className="flex items-center gap-3 mb-4">
        <TrendingUp className="w-6 h-6 text-green-600" />
        <h2 className="text-xl font-bold text-foreground">
          Financial Performance
        </h2>
      </div>

      {financials.historical && financials.historical.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b dark:border-gray-700">
                <th className="text-left py-2 px-3 font-semibold">Year</th>
                <th className="text-right py-2 px-3 font-semibold">Revenue</th>
                <th className="text-right py-2 px-3 font-semibold">EBITDA</th>
                <th className="text-right py-2 px-3 font-semibold">Margin</th>
              </tr>
            </thead>
            <tbody>
              {financials.historical.map((row, idx) => (
                <tr
                  key={idx}
                  className="border-b dark:border-gray-700 last:border-0"
                >
                  <td className="py-2 px-3 font-medium">{row.year}</td>
                  <td className="py-2 px-3 text-right">
                    {row.revenue ? formatCurrency(row.revenue, currency) : "—"}
                  </td>
                  <td className="py-2 px-3 text-right">
                    {row.ebitda ? formatCurrency(row.ebitda, currency) : "—"}
                  </td>
                  <td className="py-2 px-3 text-right">
                    {row.margin ? `${(row.margin * 100).toFixed(1)}%` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {financials.metrics && (
        <div className="mt-4 grid grid-cols-2 gap-4">
          {financials.metrics.rev_cagr && (
            <div className="p-3 bg-blue-50 dark:bg-blue-900/30 rounded-lg">
              <div className="text-xs font-semibold text-muted-foreground dark:text-muted-foreground uppercase">
                Revenue CAGR
              </div>
              <div className="text-lg font-bold text-blue-900 dark:text-blue-100">
                {(financials.metrics.rev_cagr * 100).toFixed(1)}%
              </div>
            </div>
          )}
          {financials.metrics.ebitda_margin_latest && (
            <div className="p-3 bg-green-50 dark:bg-green-900/30 rounded-lg">
              <div className="text-xs font-semibold text-muted-foreground dark:text-muted-foreground uppercase">
                Latest EBITDA Margin
              </div>
              <div className="text-lg font-bold text-green-900 dark:text-green-100">
                {(financials.metrics.ebitda_margin_latest * 100).toFixed(1)}%
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
