import { useState } from 'react';
import { AlertTriangle, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { UnderwritingSection, UnderwritingStatusBadge } from './UnderwritingUI';
import { StressTestTable, RolloverRiskPanel } from './index';
import KeyValueList from './KeyValueList';
import OccupancyBadge from './OccupancyBadge';
import SourceSupportActions from './SourceSupportActions';
import { formatCompactCurrency, formatCurrency, formatPercent } from './formatters';

function getExpenseBasisTone(source) {
  if (source === 'line_items' || source === 'expense_ratio_current') return 'success';
  if (source === 'expense_ratio_pro_forma' || source === 'om_noi') return 'warning';
  return 'danger';
}

function getUnitTypeBadge(row) {
  const label = `${row.section || ''} ${row.unit_type || ''}`.toLowerCase();
  if (label.includes('parking')) return <UnderwritingStatusBadge tone="warning">Parking</UnderwritingStatusBadge>;
  if (label.includes('residential')) return <UnderwritingStatusBadge tone="neutral">Residential</UnderwritingStatusBadge>;
  if (label.includes('non-climate') || label.includes('non climate')) {
    return <UnderwritingStatusBadge tone="neutral">NC</UnderwritingStatusBadge>;
  }
  if (label.includes('climate')) return <UnderwritingStatusBadge tone="active">CC</UnderwritingStatusBadge>;
  return <UnderwritingStatusBadge tone="neutral">NC</UnderwritingStatusBadge>;
}

function UnitMixStat({ label, value, detail }) {
  return (
    <div className="rounded-xl border border-border/60 bg-background/60 px-3 py-2.5">
      <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <p className="mt-1 font-display text-xl font-semibold text-foreground">{value}</p>
      {detail ? <p className="mt-0.5 text-xs text-muted-foreground">{detail}</p> : null}
    </div>
  );
}

export default function OperationsSection({
  show,
  onToggle,
  unitMix,
  unitMixSummary,
  unitMixIsPartial = false,
  propertyUnits = null,
  extractedUnits = 0,
  unitMixCoveragePct = null,
  occupancy,
  currentExpenseRatio,
  proFormaExpenseRatio,
  propertyTaxAnnual,
  propertyTaxGrowthPct,
  milRate,
  badDebtAnnual,
  correctionsCollectionsAnnual,
  purchasePrice,
  totalUnits,
  rentableSqft,
  operational,
  expenseBasis,
  expenseBasisFormula,
  sourceCitations,
  stressTests,
  rolloverRisk,
  missingExpenseFields,
  onOpenSource,
}) {
  const [showOtherOpex, setShowOtherOpex] = useState(false);

  const otherOpexItems = [
    { label: 'Office & Admin', value: operational?.expense_office_admin_annual },
    { label: 'Bank Fees', value: operational?.expense_bank_fees_annual },
    { label: 'Contract Services', value: operational?.expense_contract_services_annual },
    { label: 'Miscellaneous', value: operational?.expense_miscellaneous_annual },
    { label: 'Telephone', value: operational?.expense_telephone_annual },
  ];
  const hasOtherOpex = otherOpexItems.some((item) => item.value != null);

  return (
    <UnderwritingSection
      eyebrow="Operations"
      title="Operating evidence and model support"
      className="underwriting-panel-strong"
      action={
        <Button variant="ghost" size="sm" onClick={onToggle} className="gap-1.5 h-7 px-3 text-xs text-muted-foreground">
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${show ? '' : '-rotate-90'}`} />
          {show ? 'Collapse' : 'Expand'}
        </Button>
      }
    >
      {show && (
        <div className="grid gap-4 xl:grid-cols-[1.35fr,1fr]">
          {/* Unit mix table */}
          <div className="underwriting-panel p-4 sm:p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Unit mix</p>
                  {unitMixIsPartial ? (
                    <UnderwritingStatusBadge tone="warning">Partial OM unit schedule</UnderwritingStatusBadge>
                  ) : null}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">Occupancy and rent by unit type.</p>
                {unitMixIsPartial && propertyUnits > 0 ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {extractedUnits} of {propertyUnits} property units represented
                    {unitMixCoveragePct != null ? ` (${Math.round(unitMixCoveragePct * 100)}% coverage)` : ''}
                  </p>
                ) : null}
              </div>
              <OccupancyBadge pct={occupancy} />
            </div>
            {unitMix.length > 0 ? (
              <div className="space-y-4">
                <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
                  <UnitMixStat label="Total units" value={unitMixSummary?.totalUnits || '—'} detail={`${unitMixSummary?.totalRows || unitMix.length} rows`} />
                  <UnitMixStat label="Climate" value={unitMixSummary?.climateUnits || 0} detail="CC storage" />
                  <UnitMixStat label="Non-climate" value={unitMixSummary?.nonClimateUnits || 0} detail="NC storage" />
                  <UnitMixStat label="Parking / other" value={unitMixSummary?.parkingOtherUnits || 0} detail="Non-storage" />
                  <UnitMixStat
                    label="Occupancy"
                    value={unitMixSummary?.hasOccupancy ? `${unitMixSummary.rowsWithOccupancy}/${unitMixSummary.totalRows}` : 'Missing'}
                    detail="Rows with support"
                  />
                </div>
                {!unitMixSummary?.hasOccupancy ? (
                  <div className="rounded-2xl border border-warning/25 bg-warning/10 p-3 text-sm leading-6 text-muted-foreground">
                    <span className="font-medium text-foreground">Review occupancy:</span> unit rows were found, but row-level occupancy was not available.
                    Validate occupied units or occupancy before relying on rent-position and break-even reads.
                  </div>
                ) : null}
                <div className="overflow-x-auto">
                  <table className="underwriting-table min-w-[620px]">
                    <thead>
                      <tr className="border-b border-border/70 text-left text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                        <th className="pb-3">Type</th>
                        <th className="pb-3">Size</th>
                        <th className="pb-3 text-right">Units</th>
                        <th className="pb-3 text-right">Occupancy</th>
                        <th className="pb-3 text-right">Current rent</th>
                        <th className="pb-3 text-right">Market rent</th>
                      </tr>
                    </thead>
                    <tbody>
                      {unitMix.map((row, index) => (
                        <tr key={index} className="border-b border-border/50 last:border-b-0">
                          <td className="py-3">{getUnitTypeBadge(row)}</td>
                          <td className="py-3 font-medium text-foreground">{row.size || '—'}</td>
                          <td className="py-3 text-right">{row.num_units ?? '—'}</td>
                          <td className="py-3 text-right">{formatPercent(row.occupancy_pct)}</td>
                          <td className="py-3 text-right">{formatCurrency(row.current_rent)}</td>
                          <td className="py-3 text-right">{formatCurrency(row.market_rent)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="rounded-2xl border border-warning/30 bg-warning/10 p-5">
                <div className="flex items-start gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-warning/15 text-uw-risk">
                    <AlertTriangle className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="font-display text-lg font-semibold text-foreground">Unit mix needs review</p>
                    <p className="mt-2 text-sm leading-6 text-muted-foreground">
                      Missing unit mix. Add a rent roll or OM unit schedule before relying on per-door, occupancy, and rent-position metrics.
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Right column */}
          <div className="space-y-4">
            {/* Expense detail */}
            <div className="underwriting-panel p-4 sm:p-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Expense detail</p>
              <div className="mt-4">
                {expenseBasis ? (
                  <div className="mb-4 rounded-2xl border border-border/60 bg-background/60 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Modeled OpEx basis</p>
                        <p className="mt-1 text-sm leading-6 text-muted-foreground">{expenseBasis.reason}</p>
                      </div>
                      <UnderwritingStatusBadge tone={getExpenseBasisTone(expenseBasis.source)}>
                        {expenseBasis.label}
                      </UnderwritingStatusBadge>
                    </div>
                    {expenseBasis.source !== 'om_noi' ? (
                      <div className="mt-3 grid gap-3 sm:grid-cols-3">
                        <div>
                          <p className="text-xs text-muted-foreground">Line-item OpEx</p>
                          <p className="mt-1 font-semibold text-foreground">{formatCompactCurrency(expenseBasis.year1_line_item_opex)}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Ratio-implied OpEx</p>
                          <p className="mt-1 font-semibold text-foreground">{formatCompactCurrency(expenseBasis.year1_ratio_opex)}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Expense ratio used</p>
                          <p className="mt-1 font-semibold text-foreground">{formatPercent(expenseBasis.ratio)}</p>
                        </div>
                      </div>
                    ) : null}
                    {expenseBasisFormula ? (
                      <p className="mt-3 whitespace-pre-line rounded-xl bg-muted/40 px-3 py-2 font-mono text-xs leading-5 text-muted-foreground">
                        {expenseBasisFormula}
                      </p>
                    ) : null}
                  </div>
                ) : null}
                <KeyValueList rows={[
                  { label: 'Expense ratio (T-12 actual)', value: formatPercent(currentExpenseRatio) },
                  { label: 'Expense ratio (OM pro forma)', value: formatPercent(proFormaExpenseRatio) },
                  {
                    label: 'Expense ratio delta',
                    value: currentExpenseRatio != null && proFormaExpenseRatio != null
                      ? `${((currentExpenseRatio - proFormaExpenseRatio) * 100).toFixed(1)} pp`
                      : '—',
                  },
                  { label: 'Property tax (year 1)', value: formatCurrency(propertyTaxAnnual) },
                  { label: 'Property tax growth', value: formatPercent(propertyTaxGrowthPct) },
                  { label: 'Mil rate', value: milRate != null ? `${milRate.toFixed(5)} mills` : '—' },
                  { label: 'Bad debt', value: formatCurrency(badDebtAnnual) },
                  { label: 'Corrections / collections', value: formatCurrency(correctionsCollectionsAnnual) },
                  {
                    label: 'Price / unit',
                    value: purchasePrice && totalUnits ? formatCurrency(Math.round(purchasePrice / totalUnits)) : '—',
                  },
                  {
                    label: 'Price / rentable sqft',
                    value: purchasePrice && rentableSqft ? `$${(purchasePrice / rentableSqft).toFixed(2)}` : '—',
                  },
                ]} />

                {hasOtherOpex && (
                  <div className="mt-3">
                    <button
                      type="button"
                      onClick={() => setShowOtherOpex((v) => !v)}
                      className="flex w-full items-center justify-between gap-2 rounded-xl border border-border/60 bg-background/60 px-3 py-2 text-sm text-muted-foreground hover:bg-muted/40"
                    >
                      <span>Other OpEx breakdown</span>
                      <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${showOtherOpex ? 'rotate-180' : ''}`} />
                    </button>
                    {showOtherOpex && (
                      <div className="mt-2 space-y-2 rounded-xl border border-border/60 bg-background/40 px-3 py-3">
                        {otherOpexItems.map(({ label, value }) => (
                          <div key={label} className="flex items-center justify-between gap-3 text-sm">
                            <span className="text-muted-foreground">{label}</span>
                            <span className="font-medium text-foreground">{formatCurrency(value)}</span>
                          </div>
                        ))}
                        <div className="mt-2 flex items-center justify-between gap-3 border-t border-border/60 pt-2 text-sm">
                          <span className="font-medium text-muted-foreground">Total other OpEx</span>
                          <span className="font-semibold text-foreground">
                            {formatCurrency(otherOpexItems.reduce((s, item) => s + (item.value || 0), 0))}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {missingExpenseFields.length > 0 && (
                  <div className="mt-4 rounded-2xl border border-warning/25 bg-warning/10 p-3 text-sm text-muted-foreground">
                    <span className="font-medium text-foreground">Missing from extracted expense table:</span> {missingExpenseFields.join(', ')}
                  </div>
                )}
                <SourceSupportActions
                  citations={[
                    sourceCitations.expense_ratio_current,
                    sourceCitations.expense_ratio_pro_forma,
                    sourceCitations.property_tax_annual,
                    sourceCitations.property_tax_growth_pct,
                    sourceCitations.mil_rate,
                    sourceCitations.bad_debt_annual,
                    sourceCitations.corrections_collections_annual,
                  ]}
                  onOpenSource={onOpenSource}
                  title="Expense support"
                />
              </div>
            </div>

            {/* Revenue quality */}
            <div className="underwriting-panel p-4 sm:p-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Revenue quality</p>
              <div className="mt-4">
                <KeyValueList rows={[
                  { label: 'Vacancy & credit loss', value: formatPercent(operational?.vacancy_credit_loss_pct) },
                  { label: 'Bad debt', value: formatCurrency(badDebtAnnual), help: 'Historical charge-offs or delinquent losses from the T-12.' },
                  { label: 'Corrections / collections', value: formatCurrency(correctionsCollectionsAnnual), help: 'Adjustments, write-downs, or collection-related offsets.' },
                ]} />
                <SourceSupportActions
                  citations={[
                    sourceCitations.vacancy_credit_loss_pct,
                    sourceCitations.bad_debt_annual,
                    sourceCitations.corrections_collections_annual,
                  ]}
                  onOpenSource={onOpenSource}
                  title="Revenue support"
                />
                {operational?.income_basis_months === 6 && (
                  <div className="mt-4 rounded-2xl border border-warning/25 bg-warning/10 p-3 text-sm text-muted-foreground">
                    <span className="font-medium text-foreground">Income basis: </span>
                    Current EGI is based on trailing 6-month revenue, annualized by the broker.
                    This may mask seasonal low periods and should be validated against a full T-12.
                  </div>
                )}
              </div>
            </div>

            {stressTests.length > 0 && (
              <div className="underwriting-panel p-4 sm:p-5">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Stress tests</p>
                <div className="mt-4">
                  <StressTestTable stressTests={stressTests} />
                </div>
              </div>
            )}

            {rolloverRisk && (
              <div className="underwriting-panel p-4 sm:p-5">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Rollover risk</p>
                <div className="mt-4">
                  <RolloverRiskPanel rolloverRisk={rolloverRisk} />
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </UnderwritingSection>
  );
}
