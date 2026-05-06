import { ChevronDown } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Button } from '@/components/ui/button';
import { UnderwritingSection, UnderwritingStatusBadge } from './UnderwritingUI';
import KeyValueList from './KeyValueList';
import OccupancyBadge from './OccupancyBadge';
import SourceSupportActions from './SourceSupportActions';
import { formatCompactCurrency, formatCurrency, formatPercent, formatRatioPercent } from './formatters';

export default function ReturnsSection({
  show,
  onToggle,
  projections,
  proformaData,
  incomeBasisMonths,
  loanAmount,
  purchasePrice,
  equityInvested,
  equityPct,
  ltvPct,
  equityRaiseTone,
  equityRaiseLabel,
  currentRun,
  currentRentPerDoor,
  marketRentPerDoor,
  rentSpreadPerDoor,
  occupancy,
  impliedCapRate,
  breakEvenOccupancyPct,
  totalUnits,
  sourceCitations,
  omStatedNoi,
  noiBridge,
  modeledNoi,
  noiBridgeDelta,
  noiBridgeDeltaPct,
  noiBridgeAlert,
  expenseBasisSource,
  onOpenSource,
}) {
  const isOmNoiMode = expenseBasisSource === 'om_noi';
  const noiBridgeRows = Array.isArray(noiBridge?.rows) ? noiBridge.rows : [];

  return (
    <UnderwritingSection
      eyebrow="Returns"
      title="Returns and capital structure"
      className="underwriting-panel-strong"
      action={
        <Button variant="ghost" size="sm" onClick={onToggle} className="gap-1.5 h-7 px-3 text-xs text-muted-foreground">
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${show ? '' : '-rotate-90'}`} />
          {show ? 'Collapse' : 'Expand'}
        </Button>
      }
    >
      {show && (
        <div className="grid gap-4 xl:grid-cols-[1.7fr,1fr]">
          {/* First 5 years chart */}
          <div className="underwriting-panel p-4 sm:p-5">
            <div className="mb-4">
              <div className="flex items-center gap-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">First 5 years</p>
                {incomeBasisMonths != null && incomeBasisMonths < 12 ? (
                  <span className="rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide"
                    style={{ background: 'hsl(var(--uw-risk) / 0.12)', color: 'hsl(var(--uw-risk))' }}>
                    T-{incomeBasisMonths} annualized
                  </span>
                ) : null}
              </div>
              <p className="mt-1 text-sm text-muted-foreground">NOI and cash flow after debt service from the full hold-period projection.</p>
            </div>
            {proformaData.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={proformaData} barGap={6}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                  <XAxis dataKey="year" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                  <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}K`} tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                  <Tooltip formatter={(v) => formatCompactCurrency(v)} />
                  <Legend />
                  <Bar dataKey="NOI" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="CFADS" fill="hsl(var(--accent))" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="underwriting-empty py-16 text-sm text-muted-foreground">No projection data available.</div>
            )}
          </div>

          {/* Capital stack + sanity checks + NOI bridge */}
          <div className="space-y-4">
            <div className="underwriting-panel p-4 sm:p-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Capital stack</p>
              <div className="mt-4 space-y-3">
                <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Senior debt</p>
                  <p className="mt-2 font-display text-2xl font-semibold text-foreground">{formatCompactCurrency(loanAmount)}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{formatPercent(ltvPct)} LTV</p>
                </div>
                <div className={`rounded-2xl border p-4 ${equityPct > 0.4 ? 'border-warning/25 bg-warning/10' : 'border-border/60 bg-background/60'}`}>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Equity</p>
                  <p className="mt-2 font-display text-2xl font-semibold text-foreground">{formatCompactCurrency(equityInvested)}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{formatPercent(equityPct)} of purchase price</p>
                </div>
              </div>
              <div className={`mt-4 rounded-2xl border p-4 ${
                equityPct >= 0.5 ? 'border-warning/25 bg-warning/10'
                : equityPct >= 0.4 ? 'border-primary/20 bg-primary/5'
                : 'border-border/60 bg-background/60'
              }`}>
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Equity raise read</p>
                  <UnderwritingStatusBadge tone={equityRaiseTone}>{equityRaiseLabel}</UnderwritingStatusBadge>
                </div>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  {equityPct >= 0.5
                    ? 'This deal is funding more than half of the purchase basis with equity. That is a heavy raise and should be intentional.'
                    : equityPct >= 0.4
                      ? 'This deal needs a meaningful equity check. Make sure the basis and return profile justify the raise.'
                      : 'The equity requirement is within a more typical range for this model.'}
                </p>
              </div>
              <KeyValueList rows={[
                { label: 'Total purchase price', value: formatCompactCurrency(purchasePrice) },
                { label: 'NOI year 1', value: formatCompactCurrency(currentRun.noi_year_one) },
                { label: 'Cap rate year 1', value: formatPercent(currentRun.cap_rate_year_one) },
                { label: 'Equity raise', value: formatCompactCurrency(equityInvested) },
              ]} />
              <SourceSupportActions
                citations={[sourceCitations.purchase_price, sourceCitations.market_cap_rate_purchase, sourceCitations.interest_rate_pct]}
                onOpenSource={onOpenSource}
                title="Purchase basis"
              />
            </div>

            {/* Sanity checks */}
            <div className="underwriting-panel p-4 sm:p-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Sanity checks</p>
              <div className="mt-4 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-muted-foreground">Avg rent / door / month</span>
                  <span className="font-semibold text-foreground">{formatCurrency(currentRentPerDoor ? Math.round(currentRentPerDoor) : null)}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-muted-foreground">Avg market rent / door / month</span>
                  <span className="font-semibold text-foreground">{formatCurrency(marketRentPerDoor ? Math.round(marketRentPerDoor) : null)}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-muted-foreground">Rent spread / door / month</span>
                  <span className="font-semibold text-foreground">{formatCurrency(rentSpreadPerDoor ? Math.round(rentSpreadPerDoor) : null)}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-muted-foreground">Portfolio occupancy</span>
                  <OccupancyBadge pct={occupancy} />
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-muted-foreground">Implied cap rate</span>
                  <span className="font-semibold text-foreground">{formatPercent(impliedCapRate)}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm text-muted-foreground">Break-even occupancy</span>
                  <span className="font-semibold text-foreground">{formatRatioPercent(breakEvenOccupancyPct)}</span>
                </div>
                {totalUnits != null ? (
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm text-muted-foreground">Total units</span>
                    <span className="font-semibold text-foreground">{totalUnits}</span>
                  </div>
                ) : null}
              </div>
              <SourceSupportActions
                citations={[
                  sourceCitations.num_units,
                  sourceCitations.gross_potential_rent_annual,
                  sourceCitations.avg_in_place_rent_per_unit_monthly,
                  sourceCitations.avg_market_rent_per_unit_monthly,
                ]}
                onOpenSource={onOpenSource}
                title="Portfolio support"
              />

              {/* NOI build-up */}
              {projections[0] && !isOmNoiMode && (
                <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">NOI build-up — Year 1</p>
                  <p className="mt-1 text-sm text-muted-foreground">How modeled NOI is constructed from extracted components.</p>
                  <div className="mt-3 space-y-0">
                    <div className="flex items-center justify-between py-1.5">
                      <span className="text-sm text-muted-foreground">Gross Potential Rent</span>
                      <span className="font-mono text-sm font-medium text-foreground">{formatCompactCurrency(projections[0].gpr)}</span>
                    </div>
                    <div className="flex items-center justify-between py-1.5">
                      <span className="text-sm text-muted-foreground pl-3">− Vacancy &amp; Credit Loss</span>
                      <span className="font-mono text-sm text-muted-foreground">({formatCompactCurrency(projections[0].vacancy_loss)})</span>
                    </div>
                    {projections[0].other_income > 0 && (
                      <div className="flex items-center justify-between py-1.5">
                        <span className="text-sm text-muted-foreground pl-3">+ Other Income</span>
                        <span className="font-mono text-sm text-muted-foreground">{formatCompactCurrency(projections[0].other_income)}</span>
                      </div>
                    )}
                    <div className="flex items-center justify-between border-t border-border/60 py-1.5 mt-0.5">
                      <span className="text-sm font-semibold text-foreground">EGI (Effective Gross Income)</span>
                      <span className="font-mono text-sm font-semibold text-foreground">{formatCompactCurrency(projections[0].egi)}</span>
                    </div>
                    <div className="flex items-center justify-between py-1.5">
                      <span className="text-sm text-muted-foreground pl-3">− Operating Expenses</span>
                      <span className="font-mono text-sm text-muted-foreground">({formatCompactCurrency(projections[0].opex)})</span>
                    </div>
                    <div className="flex items-center justify-between border-t border-border/60 py-1.5 mt-0.5">
                      <span className="text-sm font-semibold text-foreground">NOI</span>
                      <span className="font-mono text-sm font-semibold text-foreground">{formatCompactCurrency(projections[0].noi)}</span>
                    </div>
                  </div>
                </div>
              )}
              {projections[0] && isOmNoiMode && (
                <div className="rounded-2xl border border-warning/25 bg-warning/10 p-4">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">NOI — Year 1</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Quick-screen basis from OM-stated NOI. Revenue and expense components are not backsolved.
                  </p>
                  <div className="mt-3 flex items-center justify-between py-1.5">
                    <span className="text-sm text-muted-foreground">OM-stated NOI</span>
                    <span className="font-mono text-sm font-semibold text-foreground">{formatCompactCurrency(projections[0].noi)}</span>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Upload a T-12 to replace this with line-item income and expense support.
                  </p>
                </div>
              )}

              {/* NOI bridge */}
              {noiBridgeRows.length > 0 ? (
                <div className={`rounded-2xl border p-4 ${noiBridgeRows.some((row) => Math.abs(row.delta_to_prior?.pct || 0) > 0.10) ? 'border-amber-500/30 bg-amber-500/5' : 'border-border/60 bg-background/60'}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">NOI bridge</p>
                      <p className="mt-1 text-sm text-muted-foreground">
                        OM is broker context, T-12 is actuals support when available, and model NOI drives returns.
                      </p>
                    </div>
                    {noiBridge.has_t12 ? (
                      <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.12em] text-emerald-700 dark:text-emerald-300">
                        T-12 present
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-3 space-y-2">
                    {noiBridgeRows.map((row) => {
                      const citation = sourceCitations?.[row.source_field];
                      const pct = row.delta_to_prior?.pct;
                      const amount = row.delta_to_prior?.amount;
                      const basisLabel = row.delta_to_prior?.basis_label;
                      const signedAmount = amount == null
                        ? null
                        : amount >= 0
                          ? `+${formatCompactCurrency(amount)}`
                          : `-${formatCompactCurrency(Math.abs(amount))}`;
                      return (
                        <div key={`${row.source_type}-${row.source_field}`} className="rounded-2xl border border-border/60 bg-background/70 px-3 py-3">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div>
                              <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{row.label}</p>
                              <p className="mt-1 font-semibold text-foreground">{formatCompactCurrency(row.value)}</p>
                            </div>
                            <div className="flex items-center gap-2">
                              {pct != null ? (
                                <span className={`text-sm font-semibold ${Math.abs(pct) > 0.10 ? 'text-amber-700 dark:text-amber-300' : 'text-muted-foreground'}`}>
                                  {signedAmount} · {pct >= 0 ? '+' : ''}{(pct * 100).toFixed(0)}%{basisLabel ? ` vs ${basisLabel}` : ''}
                                </span>
                              ) : null}
                              {citation ? (
                                <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-[10px] font-bold uppercase tracking-wide text-uw-citation" onClick={() => onOpenSource?.(citation)}>
                                  Source
                                </Button>
                              ) : null}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : omStatedNoi != null && modeledNoi != null ? (
                <div className={`rounded-2xl border p-4 ${noiBridgeAlert ? 'border-amber-500/30 bg-amber-500/5' : 'border-border/60 bg-background/60'}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">NOI bridge</p>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {isOmNoiMode
                          ? 'OM-stated NOI drives valuation in quick-screen mode.'
                          : 'OM NOI is a reference check; modeled NOI is what drives valuation and returns.'}
                      </p>
                    </div>
                    <span className={`text-sm font-semibold ${noiBridgeAlert ? 'text-amber-700 dark:text-amber-300' : 'text-foreground'}`}>
                      {formatPercent(noiBridgeDeltaPct)}
                    </span>
                  </div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-3">
                    <div className="rounded-2xl border border-border/60 bg-background/70 px-3 py-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">OM stated NOI</p>
                      <p className="mt-1 font-semibold text-foreground">{formatCompactCurrency(omStatedNoi)}</p>
                      <p className="mt-1 text-[11px] font-medium text-muted-foreground">
                        {isOmNoiMode ? 'Quick-screen basis' : 'Reference only'}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-border/60 bg-background/70 px-3 py-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Modeled NOI</p>
                      <p className="mt-1 font-semibold text-foreground">{formatCompactCurrency(modeledNoi)}</p>
                      <p className="mt-1 text-[11px] font-medium text-uw-success">
                        {isOmNoiMode ? 'Same NOI basis' : 'Used in valuation'}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-border/60 bg-background/70 px-3 py-3">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Delta</p>
                      <p className={`mt-1 font-semibold ${noiBridgeAlert ? 'text-amber-700 dark:text-amber-300' : 'text-foreground'}`}>
                        {noiBridgeDelta == null ? '—' : `${noiBridgeDelta >= 0 ? '+' : ''}${formatCompactCurrency(noiBridgeDelta)}`}
                      </p>
                    </div>
                  </div>
                  {noiBridgeDeltaPct != null && Math.abs(noiBridgeDeltaPct) > 0.10 && (
                    <p className="mt-3 text-xs text-amber-600 dark:text-amber-400">
                      Gap &gt;10% — modeled NOI uses extracted or saved revenue, vacancy, other income, and expense basis.
                      Re-run or upload a T-12 for higher confidence.
                    </p>
                  )}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </UnderwritingSection>
  );
}
