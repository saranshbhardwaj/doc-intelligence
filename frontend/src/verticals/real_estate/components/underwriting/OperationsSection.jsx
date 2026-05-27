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
  if (source === 't12_line_items' || source === 't12_expense_ratio' || source === 'om_year1_line_items') return 'success';
  if (source?.includes?.('expense_ratio') || source === 'om_noi') return 'warning';
  return 'danger';
}

const periodLabel = {
  t12: 'T-12',
  current: 'Current',
  year1: 'Year 1',
  pro_forma: 'Pro Forma',
  mixed: 'Mixed period',
  unknown: 'Unknown',
};

const methodLabel = {
  line_items: 'Line items',
  expense_ratio: 'Expense ratio',
  noi: 'OM NOI',
  missing: 'Missing',
};

function getUnitTypeBadge(row) {
  const label = `${row.unit_category || ''}`.toLowerCase();
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

function unitMixCategory(row) {
  const label = `${row?.unit_category || ''}`.toLowerCase();
  if (label.includes('residential') || label.includes('apartment')) return 'residential';
  if (label.includes('parking')) return 'parking';
  if (label.includes('office') || label.includes('commercial')) return 'other';
  return 'storage';
}

function scheduledRent(row) {
  const units = Number(row?.num_units) || 0;
  const rent = Number(row?.current_rent ?? row?.market_rent) || 0;
  return units > 0 && rent > 0 ? units * rent * 12 : 0;
}

function getRevenueMix(unitMix = []) {
  const buckets = {
    storage: { label: 'Storage', rent: 0, tone: 'success' },
    parking: { label: 'Parking / other', rent: 0, tone: 'warning' },
    residential: { label: 'Residential', rent: 0, tone: 'neutral' },
    other: { label: 'Other', rent: 0, tone: 'neutral' },
  };
  (Array.isArray(unitMix) ? unitMix : []).forEach((row) => {
    const rent = scheduledRent(row);
    if (rent <= 0) return;
    buckets[unitMixCategory(row)].rent += rent;
  });
  const total = Object.values(buckets).reduce((sum, bucket) => sum + bucket.rent, 0);
  if (total <= 0) return [];
  return Object.values(buckets)
    .filter((bucket) => bucket.rent > 0)
    .map((bucket) => ({ ...bucket, share: bucket.rent / total }));
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
  proFormaExpenseRatio,
  propertyTaxAnnual,
  propertyTaxGrowthPct,
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
  stressBaseAssumptions,
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
  const revenueMix = getRevenueMix(unitMix);
  const hasCitation = (field) => Boolean(sourceCitations?.[field]);
  const hasSupportValue = (value) => value != null && value !== '—';
  const modeledExpenseRatio = expenseBasis?.expense_ratio ?? expenseBasis?.ratio ?? null;
  const isLineItemExpenseBasis = expenseBasis?.method === 'line_items'
    || String(expenseBasis?.source || '').endsWith('_line_items');
  const isExpenseRatioBasis = expenseBasis?.method === 'expense_ratio'
    || String(expenseBasis?.source || '').includes('expense_ratio');
  const expenseBasisReason = expenseBasis
    ? isLineItemExpenseBasis
      ? 'Operating expenses are modeled from selected line-item OpEx. The ratio shown below is an implied benchmark, not the driver.'
      : isExpenseRatioBasis
        ? 'Operating expenses are modeled from the selected expense ratio because coherent line-item support was unavailable.'
        : expenseBasis.reason
    : null;
  const modeledRatioLabel = isLineItemExpenseBasis
    ? 'Implied model ratio'
    : isExpenseRatioBasis
      ? 'Model ratio used'
      : 'Model expense ratio';
  const expenseRatioLabel = isLineItemExpenseBasis ? 'Implied ratio' : 'Expense ratio';
  const t12ExpenseRatio = operational?.expense_ratio_t12;
  const omCurrentExpenseRatio = operational?.expense_ratio_current;
  const omYear1ExpenseRatio = operational?.expense_ratio_year1;
  const omProFormaExpenseRatio = operational?.expense_ratio_pro_forma ?? proFormaExpenseRatio;
  const expenseSupportRows = [
    { label: modeledRatioLabel, value: formatPercent(modeledExpenseRatio) },
    { label: 'T-12 expense ratio', value: formatPercent(t12ExpenseRatio) },
    { label: 'OM current expense ratio', value: formatPercent(omCurrentExpenseRatio) },
    { label: 'OM Year 1 expense ratio', value: formatPercent(omYear1ExpenseRatio) },
    { label: 'OM pro forma expense ratio', value: formatPercent(omProFormaExpenseRatio) },
    {
      label: 'Delta vs broker pro forma',
      value: modeledExpenseRatio != null && omProFormaExpenseRatio != null
        ? `${((modeledExpenseRatio - omProFormaExpenseRatio) * 100).toFixed(1)} pp`
        : '—',
    },
  ].filter((row, index) => index === 0 || hasSupportValue(row.value));
  const taxSupportRows = [
    { label: 'Property tax (year 1)', value: formatCurrency(propertyTaxAnnual) },
    { label: 'Tax value basis', value: formatCurrency(operational?.property_tax_value_basis_amount) },
    { label: 'Tax assessed value', value: formatCurrency(operational?.property_tax_assessed_value) },
    { label: 'Tax assessment ratio', value: formatPercent(operational?.property_tax_assessment_ratio) },
    {
      label: 'Tax millage rate',
      value: operational?.property_tax_millage_rate != null
        ? `${operational.property_tax_millage_rate.toFixed(2)} mills`
        : '—',
    },
    {
      label: 'Tax rate / assessed $',
      value: operational?.property_tax_rate_per_assessed_dollar != null
        ? operational.property_tax_rate_per_assessed_dollar.toFixed(5)
        : '—',
    },
  ].filter((row) => hasSupportValue(row.value));
  const growthAssumptionRows = [
    { label: 'Property tax growth', value: formatPercent(propertyTaxGrowthPct) },
  ].filter((row) => hasSupportValue(row.value));
  const pricingContextRows = [
    {
      label: 'Price / unit',
      value: purchasePrice && totalUnits ? formatCurrency(Math.round(purchasePrice / totalUnits)) : '—',
    },
    {
      label: 'Price / rentable sqft',
      value: purchasePrice && rentableSqft ? `$${(purchasePrice / rentableSqft).toFixed(2)}` : '—',
    },
  ].filter((row) => row && hasSupportValue(row.value));
  const revenueQualityRows = [
    { label: 'Vacancy & credit loss', value: formatPercent(operational?.vacancy_credit_loss_pct) },
    hasCitation('bad_debt_annual') || Number(badDebtAnnual) !== 0
      ? { label: 'Bad debt', value: formatCurrency(badDebtAnnual), help: 'Historical charge-offs or delinquent losses from the T-12.' }
      : null,
    hasCitation('corrections_collections_annual') || Number(correctionsCollectionsAnnual) !== 0
      ? { label: 'Corrections / collections', value: formatCurrency(correctionsCollectionsAnnual), help: 'Adjustments, write-downs, or collection-related offsets.' }
      : null,
  ].filter((row) => row && hasSupportValue(row.value));

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
                {revenueMix.length > 0 ? (
                  <div className="rounded-2xl border border-border/60 bg-background/60 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Revenue mix by scheduled rent</p>
                      <span className="text-xs text-muted-foreground">Current rent × units × 12</span>
                    </div>
                    <div className="mt-3 grid gap-2 sm:grid-cols-3">
                      {revenueMix.map((bucket) => (
                        <div key={bucket.label} className="rounded-xl border border-border/50 bg-background/70 px-3 py-2">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-medium text-muted-foreground">{bucket.label}</span>
                            <UnderwritingStatusBadge tone={bucket.tone}>{formatPercent(bucket.share)}</UnderwritingStatusBadge>
                          </div>
                          <p className="mt-1 font-semibold text-foreground">{formatCompactCurrency(bucket.rent)}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
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
                        <p className="mt-1 text-sm leading-6 text-muted-foreground">{expenseBasisReason}</p>
                      </div>
                      <UnderwritingStatusBadge tone={getExpenseBasisTone(expenseBasis.source)}>
                        {expenseBasis.label}
                      </UnderwritingStatusBadge>
                    </div>
                    {expenseBasis.source !== 'om_noi' ? (
                      <div className="mt-3 grid gap-3 sm:grid-cols-3">
                        <div>
                          <p className="text-xs text-muted-foreground">Period</p>
                          <p className="mt-1 font-semibold text-foreground">{periodLabel[expenseBasis.period] ?? 'Unknown'}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Method</p>
                          <p className="mt-1 font-semibold text-foreground">{methodLabel[expenseBasis.method] ?? expenseBasis.method ?? '—'}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">{expenseRatioLabel}</p>
                          <p className="mt-1 font-semibold text-foreground">{formatPercent(expenseBasis.expense_ratio ?? expenseBasis.ratio)}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Modeled EGI</p>
                          <p className="mt-1 font-semibold text-foreground">{formatCompactCurrency(expenseBasis.modeled_egi)}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Modeled OpEx</p>
                          <p className="mt-1 font-semibold text-foreground">{formatCompactCurrency(expenseBasis.modeled_total_expenses ?? expenseBasis.year1_line_item_opex)}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Modeled NOI</p>
                          <p className="mt-1 font-semibold text-foreground">{formatCompactCurrency(expenseBasis.modeled_noi)}</p>
                        </div>
                      </div>
                    ) : null}
                    {Array.isArray(expenseBasis.warnings) && expenseBasis.warnings.length ? (
                      <div className="mt-3 rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-sm leading-6 text-muted-foreground">
                        {expenseBasis.warnings.join(' ')}
                      </div>
                    ) : null}
                    {expenseBasisFormula ? (
                      <p className="mt-3 whitespace-pre-line rounded-xl bg-muted/40 px-3 py-2 font-mono text-xs leading-5 text-muted-foreground">
                        {expenseBasisFormula}
                      </p>
                    ) : null}
                  </div>
                ) : null}
                <KeyValueList rows={expenseSupportRows} />

                {taxSupportRows.length > 0 ? (
                  <div className="mt-5 border-t border-border/60 pt-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Property tax support</p>
                    <div className="mt-3">
                      <KeyValueList rows={taxSupportRows} />
                    </div>
                  </div>
                ) : null}

                {growthAssumptionRows.length > 0 ? (
                  <div className="mt-5 border-t border-border/60 pt-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Growth assumptions</p>
                    <div className="mt-3">
                      <KeyValueList rows={growthAssumptionRows} />
                    </div>
                  </div>
                ) : null}

                {pricingContextRows.length > 0 ? (
                  <div className="mt-5 border-t border-border/60 pt-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Pricing context</p>
                    <div className="mt-3">
                      <KeyValueList rows={pricingContextRows} />
                    </div>
                  </div>
                ) : null}

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
                    sourceCitations.expense_ratio_t12,
                    sourceCitations.expense_ratio_current,
                    sourceCitations.expense_ratio_year1,
                    sourceCitations.expense_ratio_pro_forma,
                    sourceCitations.property_tax_annual,
                    sourceCitations.property_tax_growth_pct,
                    sourceCitations.property_tax_value_basis_amount,
                    sourceCitations.property_tax_assessed_value,
                    sourceCitations.property_tax_assessment_ratio,
                    sourceCitations.property_tax_millage_rate,
                    sourceCitations.property_tax_rate_per_assessed_dollar,
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
                <KeyValueList rows={revenueQualityRows} />
                {!hasCitation('bad_debt_annual') && !hasCitation('corrections_collections_annual')
                  && Number(badDebtAnnual) === 0 && Number(correctionsCollectionsAnnual) === 0 ? (
                    <p className="mt-3 rounded-xl border border-border/60 bg-background/60 px-3 py-2 text-xs leading-5 text-muted-foreground">
                      No T-12 bad debt or collection adjustments available.
                    </p>
                ) : null}
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
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Operating sensitivity</p>
                <div className="mt-4">
                  <StressTestTable stressTests={stressTests} baseAssumptions={stressBaseAssumptions} />
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
