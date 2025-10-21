// src/components/ResultsView.jsx
import React from 'react'
import DOMPurify from 'dompurify'
import DataField from './DataField'
import { Section } from './Section'
import { useState } from 'react'
import Modal from './Modal'
import FeedbackForm from './FeedbackForm'

/**
 * ResultsView
 * Renders the parsed `result` object returned from the backend.
 *
 * Expects `result` shaped similarly to the example in the app:
 * {
 *   metadata: { pages: number, ... },
 *   data: {
 *     company_info: { company_name, industry, founded_year, ... },
 *     financials: {
 *       currency,
 *       revenue_by_year: { "2023": 123, "2022": 100, "projected_2024": 150 },
 *       ebitda_by_year: { ... },
 *       growth_rates: { revenue_cagr, recent_growth },
 *       other_metrics: { ... }
 *     },
 *     customers: { total_count, retention_rate, notable_customers: [...] },
 *     market: { market_size, growth_rate, competitive_position },
 *     investment_thesis: string,
 *     key_risks: [ string | { risk, severity, description } ],
 *     management_team: [{ name, title, background }],
 *     balance_sheet: { total_assets, total_liabilities, ... },
 *     financial_ratios: { current_ratio, quick_ratio, debt_to_equity, return_on_assets, return_on_equity },
 *     transaction_details: { seller_motivation, auction_deadline, ... }
 *   }
 * }
 */

function safeText(value) {
  if (value === null || value === undefined) return ''
  // DOMPurify expects strings — convert non-strings first
  return DOMPurify.sanitize(String(value))
}

function sortYearKeysDesc(keys = []) {
  // keys may be like "2023", "projected_2025". We'll extract numeric year where possible.
  return keys.sort((a, b) => {
    const extract = (k) => {
      const m = k.match(/(\d{4})/)
      return m ? Number(m[1]) : -Infinity
    }
    return extract(b) - extract(a)
  })
}

export default function ResultsView({ result }) {
  const [showFeedback, setShowFeedback] = useState(false)
  if (!result || !result.data) {
    return null
  }

  const data = result.data
  const financials = data.financials || {}
  const customers = data.customers || {}
  const market = data.market || {}
  const ratios = data.financial_ratios || {}
  const balance = data.balance_sheet || {}
  const tx = data.transaction_details || {}

  return (
    <div className="bg-white rounded-lg shadow-md p-8 mt-6">
        <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Extracted Data</h2>
          <p className="text-sm text-gray-500 mt-1">
            {result.metadata.pages} pages
          </p>
        </div>
        
        <button
          onClick={() => setShowFeedback(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-50 text-blue-700 rounded-lg
            hover:bg-blue-100 transition-colors font-medium"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
              d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
          </svg>
          Give Feedback
        </button>
      </div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Extracted Data</h2>
        <span className="text-sm text-gray-500">
          {result.metadata?.pages ?? '—'} pages processed
        </span>
      </div>

      <div className="space-y-8">
        {/* Company Information */}
        {data.company_info && (
          <Section title="Company Information">
            <div className="grid grid-cols-2 gap-4">
              {data.company_info.company_name && (
                <DataField label="Company Name" value={safeText(data.company_info.company_name)} />
              )}
              {data.company_info.industry && (
                <DataField label="Industry" value={safeText(data.company_info.industry)} />
              )}
              {data.company_info.founded_year && (
                <DataField label="Founded" value={data.company_info.founded_year} />
              )}
              {data.company_info.employees && (
                <DataField label="Employees" value={data.company_info.employees} />
              )}
              {data.company_info.headquarters && (
                <DataField label="Headquarters" value={safeText(data.company_info.headquarters)} />
              )}
              {data.company_info.website && (
                <DataField label="Website" value={safeText(data.company_info.website)} />
              )}
            </div>
          </Section>
        )}

        {/* Financial Summary */}
        {financials && Object.keys(financials).length > 0 && (
          <Section title="Financial Summary">
            {financials.currency && (
              <p className="text-sm text-gray-600 mb-4">Currency: {safeText(financials.currency)}</p>
            )}

            {/* Revenue by Year */}
            {financials.revenue_by_year &&
              Object.keys(financials.revenue_by_year).length > 0 && (
                <div className="mb-6">
                  <h4 className="text-md font-semibold text-gray-700 mb-3">Revenue by Year</h4>
                  <div className="grid grid-cols-3 gap-4">
                    {sortYearKeysDesc(Object.keys(financials.revenue_by_year)).map((yearKey) => {
                      const label = yearKey.startsWith('projected_')
                        ? `${yearKey.replace('projected_', '')} (Proj)`
                        : yearKey
                      const value = financials.revenue_by_year[yearKey]
                      return (
                        <DataField
                          key={yearKey}
                          label={label}
                          value={value}
                          format="currency"
                        />
                      )
                    })}
                  </div>
                </div>
              )}

            {/* EBITDA by Year */}
            {financials.ebitda_by_year &&
              Object.keys(financials.ebitda_by_year).length > 0 && (
                <div className="mb-6">
                  <h4 className="text-md font-semibold text-gray-700 mb-3">EBITDA by Year</h4>
                  <div className="grid grid-cols-3 gap-4">
                    {sortYearKeysDesc(Object.keys(financials.ebitda_by_year)).map((yearKey) => (
                      <DataField
                        key={yearKey}
                        label={yearKey.startsWith('projected_') ? `${yearKey.replace('projected_', '')} (Proj)` : yearKey}
                        value={financials.ebitda_by_year[yearKey]}
                        format="currency"
                      />
                    ))}
                  </div>
                </div>
              )}

            {/* Growth Rates */}
            {financials.growth_rates && (
              <div className="grid grid-cols-2 gap-4 bg-blue-50 p-4 rounded">
                {financials.growth_rates.revenue_cagr != null && (
                  <DataField
                    label="Revenue CAGR"
                    value={String(financials.growth_rates.revenue_cagr)}
                  />
                )}
                {financials.growth_rates.recent_growth != null && (
                  <DataField
                    label="Recent Growth"
                    value={String(financials.growth_rates.recent_growth)}
                  />
                )}
              </div>
            )}

            {/* Other Metrics */}
            {financials.other_metrics && Object.keys(financials.other_metrics).length > 0 && (
              <div className="mt-4">
                <h4 className="text-md font-semibold text-gray-700 mb-3">Other Financial Metrics</h4>
                <div className="grid grid-cols-2 gap-4">
                  {Object.entries(financials.other_metrics).map(([key, value]) => (
                    <DataField
                      key={key}
                      label={key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
                      value={value}
                      format={typeof value === 'number' && Math.abs(value) > 1000 ? 'currency' : 'text'}
                    />
                  ))}
                </div>
              </div>
            )}
          </Section>
        )}

        {/* Customer Metrics */}
        {customers && Object.values(customers).some((v) => v != null) && (
          <Section title="Customer Metrics">
            <div className="grid grid-cols-2 gap-4">
              {customers.total_count != null && (
                <DataField label="Total Customers" value={customers.total_count} />
              )}
              {customers.top_customer_concentration != null && (
                <DataField label="Top Customer Concentration" value={customers.top_customer_concentration} />
              )}
              {customers.retention_rate != null && (
                <DataField label="Retention Rate" value={customers.retention_rate} />
              )}
            </div>

            {Array.isArray(customers.notable_customers) && customers.notable_customers.length > 0 && (
              <div className="mt-4">
                <h4 className="text-sm font-medium text-gray-700 mb-2">Notable Customers:</h4>
                <div className="flex flex-wrap gap-2">
                  {customers.notable_customers.map((c, idx) => (
                    <span key={idx} className="bg-gray-100 px-3 py-1 rounded-full text-sm">
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
          <Section title="Market Analysis">
            <div className="grid grid-cols-2 gap-4">
              {market.market_size != null && (
                <DataField label="Market Size" value={market.market_size} />
              )}
              {market.growth_rate != null && (
                <DataField label="Market Growth Rate" value={market.growth_rate} />
              )}
              {market.competitive_position != null && (
                <DataField label="Competitive Position" value={safeText(market.competitive_position)} />
              )}
            </div>
          </Section>
        )}

        {/* Investment Thesis */}
        {data.investment_thesis && (
          <Section title="Investment Thesis">
            <div className="bg-blue-50 p-4 rounded-lg">
              <p className="text-gray-700 leading-relaxed whitespace-pre-line">
                {safeText(data.investment_thesis)}
              </p>
            </div>
          </Section>
        )}

        {/* Key Risks */}
        {Array.isArray(data.key_risks) && data.key_risks.length > 0 && (
          <Section title="Key Risks">
            <div className="space-y-3">
              {data.key_risks.map((risk, index) => (
                <div key={index} className="border-l-4 border-red-400 bg-red-50 p-4 rounded-r">
                  <div className="flex items-start">
                    <div className="flex-1">
                      {typeof risk === 'object' ? (
                        <>
                          <div className="flex items-center mb-1">
                            <span
                              className={`text-xs font-semibold px-2 py-1 rounded mr-2 ${
                                risk.severity === 'High' ? 'bg-red-200 text-red-800' :
                                risk.severity === 'Medium' ? 'bg-yellow-200 text-yellow-800' :
                                'bg-green-200 text-green-800'
                              }`}
                            >
                              {safeText(risk.severity || '')}
                            </span>
                            <span className="font-semibold text-gray-800">{safeText(risk.risk || 'Risk')}</span>
                          </div>
                          {risk.description && (
                            <p className="text-sm text-gray-700 ml-0">{safeText(risk.description)}</p>
                          )}
                        </>
                      ) : (
                        <p className="text-gray-700">{safeText(risk)}</p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Management Team */}
        {Array.isArray(data.management_team) && data.management_team.length > 0 && (
          <Section title="Management Team">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {data.management_team.map((member, index) => (
                <div key={index} className="bg-gray-50 p-4 rounded-lg">
                  <h4 className="font-semibold text-gray-900">{safeText(member.name)}</h4>
                  <p className="text-sm text-blue-600">{safeText(member.title)}</p>
                  {member.background && (
                    <p className="text-sm text-gray-600 mt-2">{safeText(member.background)}</p>
                  )}
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Balance Sheet */}
        {balance && Object.keys(balance).length > 0 && (
          <Section title="Balance Sheet Summary">
            <div className="grid grid-cols-2 gap-4">
              {balance.total_assets != null && (
                <DataField label="Total Assets" value={balance.total_assets} format="currency" />
              )}
              {balance.total_liabilities != null && (
                <DataField label="Total Liabilities" value={balance.total_liabilities} format="currency" />
              )}
              {balance.stockholders_equity != null && (
                <DataField label="Stockholders Equity" value={balance.stockholders_equity} format="currency" />
              )}
              {balance.working_capital != null && (
                <DataField label="Working Capital" value={balance.working_capital} format="currency" />
              )}
            </div>
          </Section>
        )}

        {/* Financial Ratios */}
        {ratios && Object.values(ratios).some((v) => v != null) && (
          <Section title="Financial Ratios">
            <div className="grid grid-cols-3 gap-4">
              {ratios.current_ratio != null && (
                <DataField label="Current Ratio" value={Number(ratios.current_ratio).toFixed(2)} />
              )}
              {ratios.quick_ratio != null && (
                <DataField label="Quick Ratio" value={Number(ratios.quick_ratio).toFixed(2)} />
              )}
              {ratios.debt_to_equity != null && (
                <DataField label="Debt to Equity" value={Number(ratios.debt_to_equity).toFixed(2)} />
              )}
              {ratios.return_on_assets != null && (
                <DataField label="Return on Assets" value={`${(Number(ratios.return_on_assets) * 100).toFixed(1)}%`} />
              )}
              {ratios.return_on_equity != null && (
                <DataField label="Return on Equity" value={`${(Number(ratios.return_on_equity) * 100).toFixed(1)}%`} />
              )}
            </div>
          </Section>
        )}

        {/* Transaction Details */}
        {tx && Object.values(tx).some((v) => v != null) && (
          <Section title="Transaction Details">
            <div className="space-y-3">
              {tx.seller_motivation && (
                <div>
                  <h4 className="text-sm font-medium text-gray-700">Seller Motivation:</h4>
                  <p className="text-gray-600">{safeText(tx.seller_motivation)}</p>
                </div>
              )}
              {tx.post_sale_involvement && (
                <div>
                  <h4 className="text-sm font-medium text-gray-700">Post-Sale Involvement:</h4>
                  <p className="text-gray-600">{safeText(tx.post_sale_involvement)}</p>
                </div>
              )}
              {tx.auction_deadline && (
                <div>
                  <h4 className="text-sm font-medium text-gray-700">Auction Deadline:</h4>
                  <p className="text-gray-600">{safeText(tx.auction_deadline)}</p>
                </div>
              )}
            </div>
          </Section>
        )}
      </div>

      {/* Footer */}
      <div className="mt-12 text-center text-sm text-gray-500">
        <p>Built for PE/VC professionals</p>
      </div>
      <div className="mt-8 pt-6 border-t border-gray-200">
  <div className="bg-blue-50 rounded-lg p-6 flex items-start gap-4">
    <div className="flex-shrink-0">
      <svg className="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
          d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
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
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
      </button>
    </div>
  </div>
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
  )
}
