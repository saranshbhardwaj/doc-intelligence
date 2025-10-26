// src/components/results/sections/CustomerMetrics.jsx
import { Users } from "lucide-react";
import Section from "../Section";
import DataField from "../DataField";
import { safeText } from "../../../utils/formatters";

export default function CustomerMetrics({ data }) {
  const customers = data.customers || {};

  if (!customers || !Object.values(customers).some((v) => v != null)) {
    return null;
  }

  return (
    <Section title="Customer Metrics" icon={Users}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {customers.total_count != null && (
          <DataField
            label="Total Customers"
            value={customers.total_count}
            format="number"
          />
        )}
        {customers.top_customer_concentration != null && (
          <DataField
            label="Top Customer Concentration"
            value={customers.top_customer_concentration}
          />
        )}
        {customers.top_customer_concentration_pct != null && (
          <DataField
            label="Top Customer %"
            value={customers.top_customer_concentration_pct}
            format="percentage"
            highlight={true}
          />
        )}
        {customers.customer_retention_rate != null && (
          <DataField
            label="Retention Rate"
            value={customers.customer_retention_rate}
          />
        )}
        {customers.recurring_revenue_pct != null && (
          <DataField
            label="Recurring Revenue %"
            value={customers.recurring_revenue_pct}
            format="percentage"
            highlight={true}
          />
        )}
      </div>

      {/* Revenue Mix */}
      {customers.revenue_mix_by_segment &&
        Object.keys(customers.revenue_mix_by_segment).length > 0 && (
          <div className="mb-6">
            <h4 className="text-md font-semibold text-gray-700 dark:text-gray-200 mb-3">
              Revenue Mix by Segment
            </h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Object.entries(customers.revenue_mix_by_segment).map(
                ([segment, pct]) => (
                  <DataField
                    key={segment}
                    label={segment}
                    value={pct}
                    format="percentage"
                  />
                )
              )}
            </div>
          </div>
        )}

      {/* Notable Customers */}
      {Array.isArray(customers.notable_customers) &&
        customers.notable_customers.length > 0 && (
          <div>
            <h4 className="text-md font-semibold text-gray-700 mb-3">
              Notable Customers
            </h4>
            <div className="flex flex-wrap gap-2">
              {customers.notable_customers.map((c, idx) => (
                <span
                  key={idx}
                  className="bg-blue-100 text-blue-800 px-4 py-2 rounded-full text-sm font-semibold"
                >
                  {safeText(c)}
                </span>
              ))}
            </div>
          </div>
        )}
    </Section>
  );
}
