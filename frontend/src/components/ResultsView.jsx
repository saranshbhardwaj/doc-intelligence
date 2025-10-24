// src/components/ResultsView.jsx
import React, { useState } from "react";
import DOMPurify from "dompurify";
import {
  Download,
  Share2,
  Printer,
  Building2,
  DollarSign,
  TrendingUp,
  BarChart3,
  Target,
  Users,
  Award,
  AlertTriangle,
  FileText,
} from "lucide-react";
import DataField from "./DataField";
import Section from "./Section";
import Modal from "./Modal";
import FeedbackForm from "./FeedbackForm";
import {
  safeText,
  formatCurrency,
  formatPercentage,
  sortYearKeysDesc,
} from "../utils/formatters";
import { exportToExcel } from "../utils/excelExport";

/**
 * MetricCard component for key metrics dashboard
 */
function MetricCard({ label, value, format = "text", icon: Icon }) {
  let displayValue = value;

  if (format === "currency") {
    displayValue = formatCurrency(value);
  } else if (format === "percentage") {
    displayValue = formatPercentage(value);
  } else {
    displayValue = safeText(value);
  }

  return (
    <div className="bg-gradient-to-br from-white to-gray-50 rounded-xl p-5 shadow-md border border-gray-200 hover:shadow-lg transition-shadow">
      <div className="flex items-start justify-between mb-2">
        <div className="text-sm font-medium text-gray-600">{label}</div>
        {Icon && <Icon className="w-5 h-5 text-blue-600" />}
      </div>
      <div className="text-2xl font-bold text-gray-900 mb-1">
        {displayValue}
      </div>
    </div>
  );
}

export default function ResultsView({ result }) {
  const [showFeedback, setShowFeedback] = useState(false);
  if (!result || !result.data) {
    return null;
  }

  const data = result.data;
  const financials = data.financials || {};
  const customers = data.customers || {};
  const market = data.market || {};
  const ratios = data.financial_ratios || {};
  const balance = data.balance_sheet || {};
  const tx = data.transaction_details || {};
  const growth = data.growth_analysis || {};
  const derived = data.derived_metrics || {};

  console.log("Result is:", result);
  console.log("Extracted Data:", data);

  console.log("Keys:", Object.keys(data || {}));

  // Action handlers
  const handleExportExcel = () => {
    try {
      exportToExcel(data, result.metadata);
      // Optional: Show success toast/notification
      console.log("Excel exported successfully!");
    } catch (error) {
      console.error("Error exporting to Excel:", error);
      alert("Failed to export Excel. Please try again.");
    }
  };

  // eslint-disable-next-line no-unused-vars
  const handleShare = () => {
    // TODO: Implement share functionality
    console.log("Sharing report...");
  };

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 py-8 px-4">
      <div className="max-w-7xl mx-auto space-y-6">
        <div className="bg-white rounded-xl shadow-md p-4 flex flex-wrap justify-between items-center gap-3">
          <div className="flex flex-wrap gap-3">
            <button
              onClick={handleExportExcel}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors font-semibold shadow-sm"
            >
              <Download className="w-4 h-4" />
              Export to Excel
            </button>
            <button
              onClick={handlePrint}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-semibold shadow-sm"
            >
              <Printer className="w-4 h-4" />
              Print Report
            </button>
            {/* <button
              onClick={handleShare}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors font-semibold shadow-sm"
            >
              <Share2 className="w-4 h-4" />
              Share
            </button> */}
          </div>
          <button
            onClick={() => setShowFeedback(true)}
            className="flex items-center gap-2 px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors font-semibold shadow-sm"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"
              />
            </svg>
            Give Feedback
          </button>
        </div>

        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 to-blue-800 rounded-xl shadow-xl p-8 text-white">
          <div className="flex items-center gap-4 mb-4">
            <Building2 className="w-12 h-12" />
            <div>
              <h1 className="text-4xl font-bold">
                {safeText(data.company_info?.company_name || "Company Report")}
              </h1>
              <p className="text-blue-100 text-lg mt-1">
                Confidential Information Memorandum
              </p>
            </div>
          </div>
          {data.company_info?.industry && (
            <div className="flex gap-2 mt-4">
              <span className="bg-blue-500 px-4 py-2 rounded-full text-sm font-semibold">
                {safeText(data.company_info.industry)}
              </span>
              {data.company_info.secondary_industry && (
                <span className="bg-blue-500 px-4 py-2 rounded-full text-sm font-semibold">
                  {safeText(data.company_info.secondary_industry)}
                </span>
              )}
            </div>
          )}
          <div className="mt-4 text-sm text-blue-100">
            {result.metadata?.pages &&
              `${result.metadata.pages} pages processed`}
          </div>
        </div>
      </div>

      {/* Key Metrics Dashboard */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {tx.asking_price && (
          <MetricCard
            label="Asking Price"
            value={tx.asking_price}
            format="currency"
            icon={DollarSign}
          />
        )}
        {Object.keys(financials.revenue_by_year || {}).length > 0 && (
          <MetricCard
            label="Latest Revenue"
            value={
              financials.revenue_by_year[
                sortYearKeysDesc(Object.keys(financials.revenue_by_year))[0]
              ]
            }
            format="currency"
            icon={TrendingUp}
          />
        )}
        {Object.keys(financials.adjusted_ebitda_by_year || {}).length > 0 && (
          <MetricCard
            label="Latest Adj. EBITDA"
            value={
              financials.adjusted_ebitda_by_year[
                sortYearKeysDesc(
                  Object.keys(financials.adjusted_ebitda_by_year)
                )[0]
              ]
            }
            format="currency"
            icon={BarChart3}
          />
        )}
        {ratios.ebitda_margin != null && (
          <MetricCard
            label="EBITDA Margin"
            value={ratios.ebitda_margin}
            format="percentage"
            icon={Target}
          />
        )}
      </div>

      {/* Transaction Details - Highlighted */}
      {tx && Object.values(tx).some((v) => v != null) && (
        <Section title="Transaction Overview" icon={FileText} highlight={true}>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-4">
            {tx.asking_price && (
              <DataField
                label="Asking Price"
                value={tx.asking_price}
                format="currency"
                highlight={true}
              />
            )}
            {tx.deal_type && (
              <DataField
                label="Deal Type"
                value={tx.deal_type}
                highlight={true}
              />
            )}
            {tx.implied_valuation_hint && (
              <DataField
                label="Valuation Hint"
                value={tx.implied_valuation_hint}
                highlight={true}
              />
            )}
          </div>
          <div className="space-y-4">
            {tx.seller_motivation && (
              <div className="bg-white p-4 rounded-lg border border-gray-200">
                <h4 className="text-sm font-semibold text-gray-700 mb-2">
                  Seller Motivation
                </h4>
                <p className="text-gray-600">
                  {safeText(tx.seller_motivation)}
                </p>
              </div>
            )}
            {tx.assets_for_sale && (
              <div className="bg-white p-4 rounded-lg border border-gray-200">
                <h4 className="text-sm font-semibold text-gray-700 mb-2">
                  Assets for Sale
                </h4>
                <p className="text-gray-600">{safeText(tx.assets_for_sale)}</p>
              </div>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {tx.post_sale_involvement && (
                <div className="bg-white p-4 rounded-lg border border-gray-200">
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">
                    Post-Sale Involvement
                  </h4>
                  <p className="text-gray-600">
                    {safeText(tx.post_sale_involvement)}
                  </p>
                </div>
              )}
              {tx.auction_deadline && (
                <div className="bg-white p-4 rounded-lg border border-gray-200">
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">
                    Auction Deadline
                  </h4>
                  <p className="text-gray-600">
                    {safeText(tx.auction_deadline)}
                  </p>
                </div>
              )}
            </div>
          </div>
        </Section>
      )}

      {/* Company Information */}
      {data.company_info && (
        <Section title="Company Information" icon={Building2}>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {data.company_info.company_name && (
              <DataField
                label="Company Name"
                value={data.company_info.company_name}
              />
            )}
            {data.company_info.company_id && (
              <DataField
                label="Company ID"
                value={data.company_info.company_id}
              />
            )}
            {data.company_info.industry && (
              <DataField label="Industry" value={data.company_info.industry} />
            )}
            {data.company_info.secondary_industry && (
              <DataField
                label="Secondary Industry"
                value={data.company_info.secondary_industry}
              />
            )}
            {data.company_info.founded_year && (
              <DataField
                label="Founded"
                value={data.company_info.founded_year}
                format="number"
              />
            )}
            {data.company_info.employees && (
              <DataField
                label="Employees"
                value={data.company_info.employees}
                format="number"
              />
            )}
            {data.company_info.headquarters && (
              <DataField
                label="Headquarters"
                value={data.company_info.headquarters}
              />
            )}
            {data.company_info.website && (
              <DataField label="Website" value={data.company_info.website} />
            )}
            {data.company_info.business_structure && (
              <DataField
                label="Business Structure"
                value={data.company_info.business_structure}
              />
            )}
          </div>
        </Section>
      )}

      {/* Growth Analysis */}
      {growth && Object.values(growth).some((v) => v != null) && (
        <Section title="Growth Analysis" icon={TrendingUp} highlight={true}>
          {/* Numeric Metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            {growth.historical_cagr != null && (
              <DataField
                label="Historical CAGR"
                value={growth.historical_cagr}
                format="percentage"
                highlight={true}
              />
            )}
            {growth.projected_cagr != null && (
              <DataField
                label="Projected CAGR"
                value={growth.projected_cagr}
                format="percentage"
                highlight={true}
              />
            )}
            {growth.organic_pct != null && (
              <DataField
                label="Organic Growth %"
                value={growth.organic_pct}
                format="percentage"
              />
            )}
            {growth.m_and_a_pct != null && (
              <DataField
                label="M&A Growth %"
                value={growth.m_and_a_pct}
                format="percentage"
              />
            )}
          </div>

          {/* Text Descriptions */}
          <div className="space-y-4">
            {growth.organic_growth_estimate && (
              <div className="bg-green-50 p-4 rounded-lg border border-green-200">
                <h4 className="text-sm font-semibold text-green-800 mb-2">
                  Organic Growth Drivers
                </h4>
                <p className="text-sm text-gray-700">
                  {safeText(growth.organic_growth_estimate)}
                </p>
              </div>
            )}
            {growth.m_and_a_summary && (
              <div className="bg-purple-50 p-4 rounded-lg border border-purple-200">
                <h4 className="text-sm font-semibold text-purple-800 mb-2">
                  M&A Impact
                </h4>
                <p className="text-sm text-gray-700">
                  {safeText(growth.m_and_a_summary)}
                </p>
              </div>
            )}
            {growth.notes && (
              <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
                <h4 className="text-sm font-semibold text-blue-800 mb-2">
                  Additional Notes
                </h4>
                <p className="text-sm text-gray-700">
                  {safeText(growth.notes)}
                </p>
              </div>
            )}
          </div>
        </Section>
      )}

      {/* Valuation Multiples */}
      {data.valuation_multiples &&
        Object.values(data.valuation_multiples).some((v) => v != null) && (
          <Section
            title="Valuation Multiples"
            icon={DollarSign}
            highlight={true}
          >
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {data.valuation_multiples.asking_ev_ebitda != null && (
                <DataField
                  label="Asking EV / EBITDA"
                  value={`${data.valuation_multiples.asking_ev_ebitda.toFixed(
                    1
                  )}x`}
                  highlight={true}
                />
              )}
              {data.valuation_multiples.asking_ev_revenue != null && (
                <DataField
                  label="Asking EV / Revenue"
                  value={`${data.valuation_multiples.asking_ev_revenue.toFixed(
                    1
                  )}x`}
                  highlight={true}
                />
              )}
              {data.valuation_multiples.exit_ev_ebitda_estimate != null && (
                <DataField
                  label="Est. Exit EV / EBITDA"
                  value={`${data.valuation_multiples.exit_ev_ebitda_estimate.toFixed(
                    1
                  )}x`}
                />
              )}
              {data.valuation_multiples.comparable_multiples_range && (
                <DataField
                  label="Comparable Range"
                  value={data.valuation_multiples.comparable_multiples_range}
                />
              )}
            </div>
          </Section>
        )}

      {/* Capital Structure */}
      {data.capital_structure &&
        Object.values(data.capital_structure).some((v) => v != null) && (
          <Section title="Capital Structure" icon={BarChart3}>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {data.capital_structure.existing_debt != null && (
                <DataField
                  label="Existing Debt"
                  value={data.capital_structure.existing_debt}
                  format="currency"
                  highlight={true}
                />
              )}
              {data.capital_structure.debt_to_ebitda != null && (
                <DataField
                  label="Debt / EBITDA"
                  value={`${data.capital_structure.debt_to_ebitda.toFixed(1)}x`}
                  highlight={true}
                />
              )}
              {data.capital_structure.proposed_leverage != null && (
                <DataField
                  label="Proposed Leverage"
                  value={`${data.capital_structure.proposed_leverage.toFixed(
                    1
                  )}x`}
                />
              )}
              {data.capital_structure.equity_contribution_estimate != null && (
                <DataField
                  label="Est. Equity Contribution"
                  value={data.capital_structure.equity_contribution_estimate}
                  format="currency"
                />
              )}
            </div>
          </Section>
        )}

      {/* Operating Metrics */}
      {data.operating_metrics &&
        Object.values(data.operating_metrics).some((v) => v != null) && (
          <Section title="Operating Metrics" icon={Target}>
            <div className="space-y-6">
              {/* KPIs */}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                {data.operating_metrics.working_capital_pct_revenue != null && (
                  <DataField
                    label="WC % of Revenue"
                    value={data.operating_metrics.working_capital_pct_revenue}
                    format="percentage"
                  />
                )}
                {data.operating_metrics.pricing_power && (
                  <DataField
                    label="Pricing Power"
                    value={data.operating_metrics.pricing_power}
                    highlight={data.operating_metrics.pricing_power === "High"}
                  />
                )}
              </div>

              {/* FCF by Year */}
              {data.operating_metrics.fcf_by_year &&
                Object.keys(data.operating_metrics.fcf_by_year).length > 0 && (
                  <div>
                    <h4 className="text-lg font-bold text-gray-800 mb-3 flex items-center gap-2">
                      <div className="w-1 h-6 bg-green-600 rounded"></div>
                      Free Cash Flow by Year
                    </h4>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                      {sortYearKeysDesc(
                        Object.keys(data.operating_metrics.fcf_by_year)
                      ).map((yearKey) => (
                        <DataField
                          key={yearKey}
                          label={yearKey}
                          value={data.operating_metrics.fcf_by_year[yearKey]}
                          format="currency"
                        />
                      ))}
                    </div>
                  </div>
                )}

              {/* CapEx by Year */}
              {data.operating_metrics.capex_by_year &&
                Object.keys(data.operating_metrics.capex_by_year).length >
                  0 && (
                  <div>
                    <h4 className="text-lg font-bold text-gray-800 mb-3 flex items-center gap-2">
                      <div className="w-1 h-6 bg-orange-600 rounded"></div>
                      CapEx by Year
                    </h4>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                      {sortYearKeysDesc(
                        Object.keys(data.operating_metrics.capex_by_year)
                      ).map((yearKey) => (
                        <DataField
                          key={yearKey}
                          label={yearKey}
                          value={data.operating_metrics.capex_by_year[yearKey]}
                          format="currency"
                        />
                      ))}
                    </div>
                  </div>
                )}

              {/* Contract Structure */}
              {data.operating_metrics.contract_structure && (
                <div className="bg-gray-50 p-4 rounded-lg">
                  <h4 className="text-sm font-semibold text-gray-700 mb-2">
                    Contract Structure
                  </h4>
                  <p className="text-sm text-gray-600">
                    {safeText(data.operating_metrics.contract_structure)}
                  </p>
                </div>
              )}
            </div>
          </Section>
        )}

      {/* Strategic Rationale */}
      {data.strategic_rationale &&
        Object.values(data.strategic_rationale).some((v) => v != null) && (
          <Section
            title="Strategic Rationale & Deal Thesis"
            icon={Target}
            highlight={true}
          >
            <div className="space-y-4">
              {data.strategic_rationale.deal_thesis && (
                <div className="bg-gradient-to-br from-blue-50 to-indigo-50 p-6 rounded-xl border-2 border-blue-200">
                  <h4 className="text-lg font-bold text-blue-900 mb-3">
                    Deal Thesis
                  </h4>
                  <p className="text-gray-800 leading-relaxed whitespace-pre-line">
                    {safeText(data.strategic_rationale.deal_thesis)}
                  </p>
                </div>
              )}

              {data.strategic_rationale.value_creation_plan && (
                <div className="bg-green-50 p-4 rounded-lg border border-green-200">
                  <h4 className="text-sm font-semibold text-green-800 mb-2">
                    Value Creation Plan
                  </h4>
                  <p className="text-sm text-gray-700 whitespace-pre-line">
                    {safeText(data.strategic_rationale.value_creation_plan)}
                  </p>
                </div>
              )}

              {data.strategic_rationale.add_on_opportunities && (
                <div className="bg-purple-50 p-4 rounded-lg border border-purple-200">
                  <h4 className="text-sm font-semibold text-purple-800 mb-2">
                    Add-on / Roll-up Opportunities
                  </h4>
                  <p className="text-sm text-gray-700 whitespace-pre-line">
                    {safeText(data.strategic_rationale.add_on_opportunities)}
                  </p>
                </div>
              )}

              {Array.isArray(data.strategic_rationale.competitive_advantages) &&
                data.strategic_rationale.competitive_advantages.length > 0 && (
                  <div>
                    <h4 className="text-md font-semibold text-gray-700 mb-3">
                      Competitive Advantages (USPs)
                    </h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {data.strategic_rationale.competitive_advantages.map(
                        (advantage, idx) => (
                          <div
                            key={idx}
                            className="bg-white p-3 rounded-lg border border-gray-200 flex items-start gap-2"
                          >
                            <svg
                              className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M5 13l4 4L19 7"
                              />
                            </svg>
                            <span className="text-sm text-gray-700">
                              {safeText(advantage)}
                            </span>
                          </div>
                        )
                      )}
                    </div>
                  </div>
                )}
            </div>
          </Section>
        )}

      {/* Financial Performance */}
      {financials && Object.keys(financials).length > 0 && (
        <Section title="Financial Performance" icon={DollarSign}>
          <div className="space-y-6">
            {/* Header Info */}
            <div className="flex gap-4 items-center pb-4 border-b border-gray-200">
              {financials.currency && (
                <span className="text-sm font-semibold text-gray-600">
                  Currency:{" "}
                  <span className="text-gray-900">
                    {safeText(financials.currency)}
                  </span>
                </span>
              )}
              {financials.fiscal_year_end && (
                <span className="text-sm font-semibold text-gray-600">
                  Fiscal Year End:{" "}
                  <span className="text-gray-900">
                    {safeText(financials.fiscal_year_end)}
                  </span>
                </span>
              )}
            </div>

            {/* Revenue by Year */}
            {financials.revenue_by_year &&
              Object.keys(financials.revenue_by_year).length > 0 && (
                <div>
                  <h4 className="text-lg font-bold text-gray-800 mb-3 flex items-center gap-2">
                    <div className="w-1 h-6 bg-blue-600 rounded"></div>
                    Revenue by Year
                  </h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
                    {sortYearKeysDesc(
                      Object.keys(financials.revenue_by_year)
                    ).map((yearKey) => {
                      const isProjected = yearKey.startsWith("projected_");
                      const label = isProjected
                        ? `${yearKey.replace("projected_", "")} (Proj)`
                        : yearKey;
                      return (
                        <DataField
                          key={yearKey}
                          label={label}
                          value={financials.revenue_by_year[yearKey]}
                          format="currency"
                          highlight={isProjected}
                        />
                      );
                    })}
                  </div>
                </div>
              )}

            {/* EBITDA by Year */}
            {financials.ebitda_by_year &&
              Object.keys(financials.ebitda_by_year).length > 0 && (
                <div>
                  <h4 className="text-lg font-bold text-gray-800 mb-3 flex items-center gap-2">
                    <div className="w-1 h-6 bg-green-600 rounded"></div>
                    EBITDA by Year
                  </h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
                    {sortYearKeysDesc(
                      Object.keys(financials.ebitda_by_year)
                    ).map((yearKey) => {
                      const isProjected = yearKey.startsWith("projected_");
                      const label = isProjected
                        ? `${yearKey.replace("projected_", "")} (Proj)`
                        : yearKey;
                      return (
                        <DataField
                          key={yearKey}
                          label={label}
                          value={financials.ebitda_by_year[yearKey]}
                          format="currency"
                          highlight={isProjected}
                        />
                      );
                    })}
                  </div>
                </div>
              )}

            {/* Adjusted EBITDA by Year */}
            {financials.adjusted_ebitda_by_year &&
              Object.keys(financials.adjusted_ebitda_by_year).length > 0 && (
                <div>
                  <h4 className="text-lg font-bold text-gray-800 mb-3 flex items-center gap-2">
                    <div className="w-1 h-6 bg-purple-600 rounded"></div>
                    Adjusted EBITDA by Year
                  </h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
                    {sortYearKeysDesc(
                      Object.keys(financials.adjusted_ebitda_by_year)
                    ).map((yearKey) => {
                      const isProjected = yearKey.startsWith("projected_");
                      const label = isProjected
                        ? `${yearKey.replace("projected_", "")} (Proj)`
                        : yearKey;
                      return (
                        <DataField
                          key={yearKey}
                          label={label}
                          value={financials.adjusted_ebitda_by_year[yearKey]}
                          format="currency"
                          highlight={isProjected}
                        />
                      );
                    })}
                  </div>
                </div>
              )}

            {/* Net Income by Year */}
            {financials.net_income_by_year &&
              Object.keys(financials.net_income_by_year).length > 0 && (
                <div>
                  <h4 className="text-lg font-bold text-gray-800 mb-3 flex items-center gap-2">
                    <div className="w-1 h-6 bg-indigo-600 rounded"></div>
                    Net Income by Year
                  </h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
                    {sortYearKeysDesc(
                      Object.keys(financials.net_income_by_year)
                    ).map((yearKey) => (
                      <DataField
                        key={yearKey}
                        label={
                          yearKey.startsWith("projected_")
                            ? `${yearKey.replace("projected_", "")} (Proj)`
                            : yearKey
                        }
                        value={financials.net_income_by_year[yearKey]}
                        format="currency"
                      />
                    ))}
                  </div>
                </div>
              )}

            {/* Gross Margin by Year */}
            {financials.gross_margin_by_year &&
              Object.keys(financials.gross_margin_by_year).length > 0 && (
                <div>
                  <h4 className="text-lg font-bold text-gray-800 mb-3 flex items-center gap-2">
                    <div className="w-1 h-6 bg-amber-600 rounded"></div>
                    Gross Margin by Year
                  </h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
                    {sortYearKeysDesc(
                      Object.keys(financials.gross_margin_by_year)
                    ).map((yearKey) => (
                      <DataField
                        key={yearKey}
                        label={
                          yearKey.startsWith("projected_")
                            ? `${yearKey.replace("projected_", "")} (Proj)`
                            : yearKey
                        }
                        value={financials.gross_margin_by_year[yearKey]}
                        format="percentage"
                      />
                    ))}
                  </div>
                </div>
              )}

            {/* Other Metrics */}
            {financials.other_metrics &&
              Object.keys(financials.other_metrics).length > 0 && (
                <div>
                  <h4 className="text-lg font-bold text-gray-800 mb-3">
                    Other Financial Metrics
                  </h4>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    {Object.entries(financials.other_metrics).map(
                      ([key, value]) => (
                        <DataField
                          key={key}
                          label={key
                            .replace(/_/g, " ")
                            .replace(/\b\w/g, (l) => l.toUpperCase())}
                          value={value}
                          format={
                            typeof value === "number" && Math.abs(value) > 1000
                              ? "currency"
                              : "text"
                          }
                        />
                      )
                    )}
                  </div>
                </div>
              )}
          </div>
        </Section>
      )}

      {/* Balance Sheet */}
      {balance && Object.keys(balance).length > 0 && (
        <Section title="Balance Sheet" icon={BarChart3}>
          {balance.most_recent_year && (
            <div className="mb-4 pb-4 border-b border-gray-200">
              <span className="text-sm font-semibold text-gray-600">
                Most Recent Year:{" "}
                <span className="text-gray-900 text-lg">
                  {balance.most_recent_year}
                </span>
              </span>
            </div>
          )}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {balance.total_assets != null && (
              <DataField
                label="Total Assets"
                value={balance.total_assets}
                format="currency"
                highlight={true}
              />
            )}
            {balance.current_assets != null && (
              <DataField
                label="Current Assets"
                value={balance.current_assets}
                format="currency"
              />
            )}
            {balance.fixed_assets != null && (
              <DataField
                label="Fixed Assets"
                value={balance.fixed_assets}
                format="currency"
              />
            )}
            {balance.total_liabilities != null && (
              <DataField
                label="Total Liabilities"
                value={balance.total_liabilities}
                format="currency"
                highlight={true}
              />
            )}
            {balance.current_liabilities != null && (
              <DataField
                label="Current Liabilities"
                value={balance.current_liabilities}
                format="currency"
              />
            )}
            {balance.long_term_debt != null && (
              <DataField
                label="Long-Term Debt"
                value={balance.long_term_debt}
                format="currency"
                highlight={true}
              />
            )}
            {balance.stockholders_equity != null && (
              <DataField
                label="Stockholders Equity"
                value={balance.stockholders_equity}
                format="currency"
                highlight={true}
              />
            )}
            {balance.working_capital != null && (
              <DataField
                label="Working Capital"
                value={balance.working_capital}
                format="currency"
              />
            )}
          </div>
        </Section>
      )}

      {/* Financial Ratios */}
      {ratios && Object.values(ratios).some((v) => v != null) && (
        <Section title="Financial Ratios & Metrics" icon={Target}>
          <div className="space-y-6">
            {/* Key PE Ratios - Highlighted */}
            <div>
              <h4 className="text-lg font-bold text-gray-800 mb-3">
                Key PE Metrics
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {ratios.ebitda_margin != null && (
                  <DataField
                    label="EBITDA Margin"
                    value={ratios.ebitda_margin}
                    format="percentage"
                    highlight={true}
                  />
                )}
                {ratios.net_debt_to_ebitda != null && (
                  <DataField
                    label="Net Debt / EBITDA"
                    value={Number(ratios.net_debt_to_ebitda).toFixed(2)}
                    highlight={true}
                  />
                )}
                {ratios.capex_pct_revenue != null && (
                  <DataField
                    label="CapEx % of Revenue"
                    value={ratios.capex_pct_revenue}
                    format="percentage"
                    highlight={true}
                  />
                )}
                {ratios.return_on_equity != null && (
                  <DataField
                    label="Return on Equity"
                    value={ratios.return_on_equity}
                    format="percentage"
                    highlight={true}
                  />
                )}
              </div>
            </div>

            {/* Liquidity Ratios */}
            <div>
              <h4 className="text-lg font-bold text-gray-800 mb-3">
                Liquidity Ratios
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {ratios.current_ratio != null && (
                  <DataField
                    label="Current Ratio"
                    value={Number(ratios.current_ratio).toFixed(2)}
                  />
                )}
                {ratios.quick_ratio != null && (
                  <DataField
                    label="Quick Ratio"
                    value={Number(ratios.quick_ratio).toFixed(2)}
                  />
                )}
              </div>
            </div>

            {/* Leverage Ratios */}
            <div>
              <h4 className="text-lg font-bold text-gray-800 mb-3">
                Leverage & Profitability
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {ratios.debt_to_equity != null && (
                  <DataField
                    label="Debt to Equity"
                    value={Number(ratios.debt_to_equity).toFixed(2)}
                  />
                )}
                {ratios.return_on_assets != null && (
                  <DataField
                    label="Return on Assets"
                    value={ratios.return_on_assets}
                    format="percentage"
                  />
                )}
              </div>
            </div>

            {/* Efficiency Ratios */}
            <div>
              <h4 className="text-lg font-bold text-gray-800 mb-3">
                Efficiency Ratios
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                {ratios.inventory_turnover != null && (
                  <DataField
                    label="Inventory Turnover"
                    value={Number(ratios.inventory_turnover).toFixed(2)}
                  />
                )}
                {ratios.accounts_receivable_turnover != null && (
                  <DataField
                    label="A/R Turnover"
                    value={Number(ratios.accounts_receivable_turnover).toFixed(
                      2
                    )}
                  />
                )}
              </div>
            </div>
          </div>
        </Section>
      )}

      {/* Customer Metrics */}
      {customers && Object.values(customers).some((v) => v != null) && (
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
                <h4 className="text-md font-semibold text-gray-700 mb-3">
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
      )}

      {/* Market Analysis */}
      {market && Object.values(market).some((v) => v != null) && (
        <Section title="Market Analysis" icon={Award}>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {market.market_size != null && (
              <DataField label="Market Size" value={market.market_size} />
            )}
            {market.market_size_estimate != null && (
              <DataField
                label="Market Size (Est.)"
                value={market.market_size_estimate}
                format="currency"
              />
            )}
            {market.market_growth_rate != null && (
              <DataField
                label="Market Growth Rate"
                value={market.market_growth_rate}
              />
            )}
            {market.competitive_position != null && (
              <DataField
                label="Competitive Position"
                value={market.competitive_position}
              />
            )}
            {market.market_share != null && (
              <DataField label="Market Share" value={market.market_share} />
            )}
          </div>
        </Section>
      )}

      {/* Investment Thesis */}
      {data.investment_thesis && (
        <Section title="Investment Thesis" icon={Target} highlight={true}>
          <div className="bg-gradient-to-br from-blue-50 to-indigo-50 p-6 rounded-xl border-2 border-blue-200">
            <p className="text-gray-800 leading-relaxed whitespace-pre-line text-base">
              {safeText(data.investment_thesis)}
            </p>
          </div>
        </Section>
      )}

      {/* Derived Metrics */}
      {derived && Object.keys(derived).length > 0 && (
        <Section title="Derived Metrics & Analysis" icon={BarChart3}>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {Object.entries(derived).map(([key, value]) => (
              <DataField
                key={key}
                label={key
                  .replace(/_/g, " ")
                  .replace(/\b\w/g, (l) => l.toUpperCase())}
                value={value}
                format={
                  typeof value === "number" && Math.abs(value) > 1000
                    ? "currency"
                    : typeof value === "number" && Math.abs(value) < 1
                    ? "percentage"
                    : "text"
                }
              />
            ))}
          </div>
        </Section>
      )}

      {/* Key Risks */}
      {Array.isArray(data.key_risks) && data.key_risks.length > 0 && (
        <Section title="Key Risks" icon={AlertTriangle}>
          <div className="space-y-3">
            {data.key_risks.map((risk, index) => (
              <div
                key={index}
                className="border-l-4 border-red-500 bg-gradient-to-r from-red-50 to-white p-5 rounded-r-lg shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="flex items-start">
                  <div className="flex-1">
                    {typeof risk === "object" ? (
                      <>
                        <div className="flex items-center gap-3 mb-2">
                          {risk.severity && (
                            <span
                              className={`text-xs font-bold px-3 py-1 rounded-full ${
                                risk.severity === "High"
                                  ? "bg-red-600 text-white"
                                  : risk.severity === "Medium"
                                  ? "bg-yellow-500 text-white"
                                  : "bg-green-500 text-white"
                              }`}
                            >
                              {safeText(risk.severity)}
                            </span>
                          )}
                          <span className="font-bold text-gray-900 text-lg">
                            {safeText(risk.risk || "Risk")}
                          </span>
                          {risk.inferred && (
                            <span className="text-xs bg-gray-200 text-gray-700 px-2 py-1 rounded">
                              Inferred
                            </span>
                          )}
                        </div>
                        {risk.description && (
                          <p className="text-sm text-gray-700 mb-2">
                            {safeText(risk.description)}
                          </p>
                        )}
                        {risk.mitigation && (
                          <div className="mt-3 bg-white p-3 rounded border border-green-200">
                            <span className="text-xs font-semibold text-green-700 uppercase">
                              Mitigation:
                            </span>
                            <p className="text-sm text-gray-700 mt-1">
                              {safeText(risk.mitigation)}
                            </p>
                          </div>
                        )}
                      </>
                    ) : (
                      <p className="text-gray-800 font-medium">
                        {safeText(risk)}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Management Team */}
      {Array.isArray(data.management_team) &&
        data.management_team.length > 0 && (
          <Section title="Management Team" icon={Users}>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {data.management_team.map((member, index) => (
                <div
                  key={index}
                  className="bg-gradient-to-br from-gray-50 to-white p-5 rounded-xl border border-gray-200 hover:shadow-lg transition-shadow"
                >
                  <div className="flex items-start gap-3">
                    <div className="w-12 h-12 bg-blue-600 rounded-full flex items-center justify-center text-white font-bold text-xl flex-shrink-0">
                      {safeText(member.name).charAt(0)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <h4 className="font-bold text-gray-900 text-lg truncate">
                        {safeText(member.name)}
                      </h4>
                      <p className="text-sm text-blue-600 font-semibold">
                        {safeText(member.title)}
                      </p>
                      {member.background && (
                        <p className="text-sm text-gray-600 mt-2 line-clamp-3">
                          {safeText(member.background)}
                        </p>
                      )}
                      {member.linkedin && (
                        <a
                          href={member.linkedin}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-blue-500 hover:text-blue-700 mt-2 inline-block"
                        >
                          LinkedIn Profile →
                        </a>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )}

      {/* Extraction Notes */}
      {data.extraction_notes && (
        <Section title="Extraction Notes" icon={FileText}>
          <div className="bg-yellow-50 p-4 rounded-lg border border-yellow-200">
            <p className="text-sm text-gray-700 whitespace-pre-line">
              {safeText(data.extraction_notes)}
            </p>
          </div>
        </Section>
      )}

      {/* Feedback CTA Banner */}
      <div className="bg-white rounded-xl shadow-md overflow-hidden">
        <div className="bg-gradient-to-r from-blue-50 to-indigo-50 p-6 flex items-start gap-4">
          <div className="flex-shrink-0">
            <svg
              className="w-8 h-8 text-blue-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
              />
            </svg>
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-gray-900 mb-1">
              Was this extraction helpful?
            </h3>
            <p className="text-sm text-gray-600 mb-3">
              Your feedback helps us improve accuracy and add features you need.
            </p>
            <button
              onClick={() => setShowFeedback(true)}
              className="text-sm font-medium text-blue-600 hover:text-blue-700 flex items-center gap-1"
            >
              Share your thoughts
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 5l7 7-7 7"
                />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="bg-white rounded-xl shadow-md p-6 text-center text-sm text-gray-600">
        <p>
          This is a confidential document prepared for private equity evaluation
          purposes.
        </p>
        <p className="mt-2">
          Generated using AI-powered extraction from CIM documents.
        </p>
      </div>
      {/* Feedback Modal */}
      <Modal
        isOpen={showFeedback}
        onClose={() => setShowFeedback(false)}
        title="📝 Help Us Improve"
      >
        <FeedbackForm
          requestId={result.metadata.request_id}
          onClose={() => setShowFeedback(false)}
        />
      </Modal>
    </div>
  );
}
