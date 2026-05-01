import { useEffect, useMemo, useState } from 'react';
import { Building2, ChevronDown, MapPin, TrendingUp } from 'lucide-react';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Button } from '@/components/ui/button';
import { UnderwritingSection, UnderwritingStatusBadge } from './UnderwritingUI';
import KeyValueList from './KeyValueList';
import { formatCompactCurrency, formatCurrency, formatCurrencyPrecise, formatPercent, formatRatioPercent } from './formatters';

const BUCKET_ORDER = ['locker', 'small', 'medium', 'large', 'xlarge'];
const CLIMATE_ORDER = ['CC', 'NC'];
const CLIMATE_LABEL = { CC: 'Climate-Controlled', NC: 'Non-Climate' };

function deltaTone(ratio) {
  if (ratio == null) return null;
  if (ratio > 1.10) return 'danger';
  if (ratio > 1.05) return 'warning';
  return 'success';
}

export default function MarketSection({
  show,
  onToggle,
  address,
  mapUrl,
  nearbyStorageCount1Mi,
  nearbyStorageCount3Mi,
  nearbyStorageCount5Mi,
  demographics,
  impliedCapRate,
  purchasePrice,
  capRateSubmarket,
  capRatePurchase,
  capRateSale,
  bpsDelta,
  rentPositionAnalysis,
  rentComps,
  rentCompCoverage,
  unknownClimateCompCount,
  getToken,
  runId,
  runSensitivityAnalysis,
  basePurchasePrice,
}) {
  const minPrice = Math.round(basePurchasePrice * 0.7);
  const maxPrice = Math.round(basePurchasePrice * 1.3);

  const [sensitivityPrice, setSensitivityPrice] = useState(null);
  const [sensitivityPoints, setSensitivityPoints] = useState([]);
  const [isSensitivityLoading, setIsSensitivityLoading] = useState(false);

  const { hasBuckets, matrixBuckets, matrixClimates } = useMemo(() => {
    const bucketSet = new Set(rentPositionAnalysis.map(r => r.bucket).filter(Boolean));
    const climateSet = new Set(rentPositionAnalysis.map(r => r.climate_type).filter(Boolean));
    return {
      hasBuckets: bucketSet.size > 0,
      matrixBuckets: BUCKET_ORDER.filter(b => bucketSet.has(b)),
      matrixClimates: CLIMATE_ORDER.filter(c => climateSet.has(c)),
    };
  }, [rentPositionAnalysis]);

  useEffect(() => {
    if (!sensitivityPrice || !runId) return;
    const timer = setTimeout(async () => {
      setIsSensitivityLoading(true);
      try {
        const prices = [minPrice, sensitivityPrice, maxPrice].sort((a, b) => a - b);
        const result = await runSensitivityAnalysis(getToken, runId, prices);
        setSensitivityPoints(result.sensitivity_points || []);
      } catch (err) {
        console.error('Sensitivity error:', err);
      } finally {
        setIsSensitivityLoading(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [getToken, maxPrice, minPrice, runId, runSensitivityAnalysis, sensitivityPrice]);

  return (
    <UnderwritingSection
      eyebrow="Market context"
      title="Location, comps, and pricing sensitivity"
      className="underwriting-panel-strong"
      action={
        <Button variant="ghost" size="sm" onClick={onToggle} className="gap-1.5 h-7 px-3 text-xs text-muted-foreground">
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${show ? '' : '-rotate-90'}`} />
          {show ? 'Collapse' : 'Expand'}
        </Button>
      }
    >
      {show && (
        <div className="grid gap-4 xl:grid-cols-[1fr,1fr]">
          {/* Left: location + demographics */}
          <div className="space-y-4">
            <div className="underwriting-panel p-4 sm:p-5">
              <div className="mb-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Location</p>
                <p className="mt-1 text-sm text-muted-foreground">{address || 'Add an address to see the map context.'}</p>
              </div>
              {mapUrl ? (
                <div className="overflow-hidden rounded-2xl border border-border/60">
                  <img src={mapUrl} alt="Property location map" className="h-[240px] w-full object-cover" />
                </div>
              ) : (
                <div className="underwriting-empty py-12">
                  <MapPin className="h-6 w-6 text-primary" />
                  <p className="mt-3 text-sm text-muted-foreground">
                    {!address ? 'No address provided yet.' : 'Map unavailable because the Google Maps key is not configured.'}
                  </p>
                </div>
              )}
              {(nearbyStorageCount1Mi != null || nearbyStorageCount3Mi != null || nearbyStorageCount5Mi != null) && (
                <div className="mt-4 rounded-2xl border border-border/60 bg-background/60 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Nearby storage overview</p>
                  <div className="mt-3 grid gap-3 sm:grid-cols-3">
                    <div>
                      <p className="text-xs text-muted-foreground">1 mile</p>
                      <p className="mt-1 font-display text-xl font-semibold text-foreground">{nearbyStorageCount1Mi ?? '—'}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">3 miles</p>
                      <p className="mt-1 font-display text-xl font-semibold text-foreground">{nearbyStorageCount3Mi ?? '—'}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">5 miles</p>
                      <p className="mt-1 font-display text-xl font-semibold text-foreground">{nearbyStorageCount5Mi ?? '—'}</p>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div className="underwriting-panel p-4 sm:p-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Market demographics</p>
              <div className="mt-4">
                {demographics ? (
                  <KeyValueList rows={[
                    { label: 'Population (3-mile radius)', value: demographics.population?.toLocaleString() ?? '—' },
                    { label: 'Avg household income', value: formatCurrency(demographics.avg_household_income) },
                    { label: 'Storage sqft / capita', value: demographics.sqft_per_capita != null ? `${demographics.sqft_per_capita.toFixed(1)} sqft` : '—' },
                    { label: 'Median age', value: demographics.median_age ?? '—' },
                  ]} />
                ) : (
                  <div className="underwriting-empty py-12">
                    <TrendingUp className="h-6 w-6 text-primary" />
                    <p className="mt-3 text-sm text-muted-foreground">Demographics were not extracted from the source package.</p>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Right: cap rate + rent position + sensitivity */}
          <div className="space-y-4">
            <div className="underwriting-panel p-4 sm:p-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Cap rate context</p>
              <div className="mt-4 space-y-3">
                <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Subject implied</p>
                  <p className="mt-2 font-display text-2xl font-semibold text-primary">{formatPercent(impliedCapRate)}</p>
                  <p className="mt-1 text-sm text-muted-foreground">Based on {formatCompactCurrency(purchasePrice)} purchase price.</p>
                </div>
                <KeyValueList rows={[
                  { label: 'Submarket average cap rate', value: formatPercent(capRateSubmarket) },
                  { label: 'Purchase cap rate basis', value: formatPercent(capRatePurchase) },
                  { label: 'Sale cap rate assumption', value: formatPercent(capRateSale) },
                  {
                    label: 'Spread vs submarket',
                    value: bpsDelta != null ? `${Math.abs(bpsDelta)} bps ${bpsDelta > 0 ? 'premium' : 'discount'}` : '—',
                  },
                ]} />
              </div>
            </div>

            <div className="underwriting-panel p-4 sm:p-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Rent position</p>
              <div className="mt-4">
                {rentCompCoverage ? (
                  <div className={`mb-4 rounded-2xl border p-4 ${
                    rentCompCoverage.tone === 'danger' ? 'border-destructive/25 bg-destructive/10'
                    : rentCompCoverage.tone === 'warning' ? 'border-warning/25 bg-warning/10'
                    : 'border-border/60 bg-background/60'
                  }`}>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Comp matching read</p>
                        <p className="mt-1 text-sm leading-6 text-muted-foreground">{rentCompCoverage.detail}</p>
                      </div>
                      <UnderwritingStatusBadge tone={rentCompCoverage.tone}>
                        {rentCompCoverage.label}
                      </UnderwritingStatusBadge>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs font-medium text-muted-foreground">
                      <span>{rentCompCoverage.compRows} comp rows reviewed</span>
                      <span>·</span>
                      <span>{rentCompCoverage.unmatchedCount} unmatched subject sizes</span>
                    </div>
                    {rentCompCoverage.unmatchedLabels?.length > 0 ? (
                      <p className="mt-2 text-xs leading-5 text-muted-foreground">
                        Unmatched: {rentCompCoverage.unmatchedLabels.join(', ')}
                        {rentCompCoverage.unmatchedCount > rentCompCoverage.unmatchedLabels.length ? ', and more' : ''}
                      </p>
                    ) : null}
                  </div>
                ) : null}
                {rentPositionAnalysis.length > 0 ? (
                  <div>
                    {/* Matrix table */}
                    {!hasBuckets ? (
                      <div className="overflow-x-auto">
                        <table className="underwriting-table min-w-[760px]">
                          <thead>
                            <tr className="border-b border-border/70 text-left text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                              <th className="pb-3">Size</th>
                              <th className="pb-3">Type</th>
                              <th className="pb-3 text-right">Subject current</th>
                              <th className="pb-3 text-right">Subject market</th>
                              <th className="pb-3 text-right">Comp avg</th>
                              <th className="pb-3 text-right">Current vs comp</th>
                              <th className="pb-3 text-right">Market vs comp</th>
                            </tr>
                          </thead>
                          <tbody>
                            {rentPositionAnalysis.map((row, index) => (
                              <tr key={index} className="border-b border-border/50 last:border-b-0">
                                <td className="py-3 font-medium text-foreground">{row.size || '—'}</td>
                                <td className="py-3 text-muted-foreground">{row.climate_type}</td>
                                <td className="py-3 text-right">{formatCurrency(row.subject_current_rent)}</td>
                                <td className="py-3 text-right">{formatCurrency(row.subject_market_rent)}</td>
                                <td className="py-3 text-right">{formatCurrency(row.comp_average_rent)}</td>
                                <td className="py-3 text-right font-medium text-foreground">{formatRatioPercent(row.current_vs_comp_ratio)}</td>
                                <td className="py-3 text-right font-medium text-foreground">{formatRatioPercent(row.market_vs_comp_ratio)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="underwriting-table min-w-[480px]">
                          <thead>
                            <tr className="border-b border-border/70 text-left text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                              <th className="pb-3 pr-4">Bucket</th>
                              {matrixClimates.map(c => (
                                <th key={c} className="pb-3 px-3 text-left">
                                  <div>{CLIMATE_LABEL[c] ?? c}</div>
                                  <div className="text-[9px] font-normal normal-case tracking-normal text-muted-foreground/70 mt-0.5">asking avg</div>
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {matrixBuckets.map(bucket => (
                              <tr key={bucket} className="border-b border-border/50 last:border-b-0">
                                <td className="py-3 pr-4 font-medium text-foreground capitalize">{bucket}</td>
                                {matrixClimates.map(climate => {
                                  const cell = rentPositionAnalysis.find(r => r.bucket === bucket && r.climate_type === climate);
                                  if (!cell) {
                                    return <td key={climate} className="py-3 px-3 text-muted-foreground">—</td>;
                                  }
                                  const ratio = cell.current_vs_comp_ratio ?? cell.market_vs_comp_ratio;
                                  const tone = deltaTone(ratio);
                                  const pct = ratio != null ? `${ratio > 1 ? '+' : ''}${((ratio - 1) * 100).toFixed(0)}%` : null;
                                  return (
                                    <td key={climate} className="py-3 px-3">
                                      <div className="flex flex-col gap-0.5">
                                        <span className="text-xs font-medium text-foreground tabular-nums">
                                          {formatCurrency(cell.comp_average_rent)}
                                          {cell.comp_count != null && (
                                            <span className="ml-1 text-muted-foreground font-normal">
                                              ({cell.comp_count} {cell.comp_count === 1 ? 'comp' : 'comps'})
                                            </span>
                                          )}
                                        </span>
                                        {cell.subject_current_rent != null && (
                                          <span className="text-xs text-muted-foreground tabular-nums">
                                            Subject: {formatCurrency(cell.subject_current_rent)}
                                            {pct && tone && cell.comp_count > 1 && (
                                              <UnderwritingStatusBadge tone={tone} className="ml-1 px-1.5 py-0 text-[9px]">
                                                {pct}
                                              </UnderwritingStatusBadge>
                                            )}
                                            {pct && cell.comp_count === 1 && (
                                              <span className="ml-1 text-muted-foreground/70 text-[9px]">{pct}*</span>
                                            )}
                                          </span>
                                        )}
                                      </div>
                                    </td>
                                  );
                                })}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {unknownClimateCompCount > 0 && (
                      <p className="mt-2 text-[11px] text-muted-foreground/70">
                        {unknownClimateCompCount} comp{unknownClimateCompCount !== 1 ? 's' : ''} not matched — climate type unclear
                      </p>
                    )}

                    {/* Collapsible raw comp list */}
                    {rentComps.length > 0 && (
                      <details className="mt-3">
                        <summary className="cursor-pointer select-none text-xs font-medium text-primary hover:text-primary/80">
                          Show all comps ({rentComps.length})
                        </summary>
                        <div className="mt-2 overflow-x-auto">
                          <table className="underwriting-table min-w-[560px]">
                            <thead>
                              <tr className="border-b border-border/70 text-left text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                                <th className="pb-3">Facility</th>
                                <th className="pb-3">Size</th>
                                <th className="pb-3">Climate</th>
                                <th className="pb-3 text-right">Rent/mo</th>
                                <th className="pb-3 text-right">Rent/sqft</th>
                                <th className="pb-3 text-right">Distance</th>
                              </tr>
                            </thead>
                            <tbody>
                              {rentComps.map((c, i) => (
                                <tr key={i} className="border-b border-border/50 last:border-b-0">
                                  <td className="py-2 text-muted-foreground">{c.facility ?? '—'}</td>
                                  <td className="py-2 tabular-nums text-muted-foreground">{c.size ?? '—'}</td>
                                  <td className="py-2">
                                    {c.climate_type ? (
                                      <UnderwritingStatusBadge
                                        tone={c.climate_type === 'CC' ? 'success' : c.climate_type === 'NC' ? 'active' : 'neutral'}
                                        className="px-1.5 py-0 text-[9px]"
                                      >
                                        {c.climate_type}
                                      </UnderwritingStatusBadge>
                                    ) : <span className="text-muted-foreground">—</span>}
                                  </td>
                                  <td className="py-2 text-right tabular-nums text-foreground">
                                    {c.asking_rent != null ? formatCurrency(c.asking_rent) : '—'}
                                  </td>
                                  <td className="py-2 text-right tabular-nums text-muted-foreground">
                                    {c.rent_per_sqft != null ? formatCurrencyPrecise(c.rent_per_sqft) : '—'}
                                  </td>
                                  <td className="py-2 text-right tabular-nums text-muted-foreground">
                                    {c.distance_mi != null ? `${c.distance_mi} mi` : '—'}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </details>
                    )}
                  </div>
                ) : rentComps.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="underwriting-table min-w-[560px]">
                      <thead>
                        <tr className="border-b border-border/70 text-left text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                          <th className="pb-3">Size</th>
                          <th className="pb-3">Facility</th>
                          <th className="pb-3 text-right">Rent/Unit</th>
                          <th className="pb-3 text-right">Rent/Sq Ft</th>
                          <th className="pb-3 text-right">Distance</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rentComps.map((row, index) => (
                          <tr key={index} className="border-b border-border/50 last:border-b-0">
                            <td className="py-3 font-medium text-foreground">{row.size || '—'}</td>
                            <td className="py-3 text-muted-foreground">{row.facility || '—'}</td>
                            <td className="py-3 text-right">{row.asking_rent != null ? formatCurrency(row.asking_rent) : '—'}</td>
                            <td className="py-3 text-right">{row.rent_per_sqft != null ? formatCurrencyPrecise(row.rent_per_sqft) : '—'}</td>
                            <td className="py-3 text-right text-muted-foreground">{row.distance_mi ? `${row.distance_mi} mi` : '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <p className="mt-3 text-sm text-muted-foreground">Comp rows exist, but the subject unit mix did not line up cleanly enough to compute a rent-position view yet.</p>
                  </div>
                ) : (
                  <div className="underwriting-empty py-12">
                    <Building2 className="h-6 w-6 text-primary" />
                    <p className="mt-3 text-sm text-muted-foreground">No rent comps have been entered yet. This screen still avoids third-party market data, but you can add a tight comp set manually or extract one from an OM competitive-set table.</p>
                  </div>
                )}
              </div>
            </div>

            <div className="underwriting-panel p-4 sm:p-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Sensitivity</p>
                  <p className="mt-1 text-sm text-muted-foreground">IRR and cash-on-cash versus purchase price.</p>
                </div>
                {isSensitivityLoading ? <UnderwritingStatusBadge tone="active">Updating</UnderwritingStatusBadge> : null}
              </div>
              <div className="mt-4">
                <div className="flex items-center justify-between text-sm text-muted-foreground">
                  <span>{formatCompactCurrency(minPrice)}</span>
                  <span className="font-semibold text-foreground">{formatCompactCurrency(sensitivityPrice || basePurchasePrice)}</span>
                  <span>{formatCompactCurrency(maxPrice)}</span>
                </div>
                <input
                  type="range"
                  min={minPrice}
                  max={maxPrice}
                  step={50000}
                  value={sensitivityPrice || basePurchasePrice}
                  onChange={(e) => setSensitivityPrice(parseFloat(e.target.value))}
                  className="underwriting-range mt-4"
                />
                {sensitivityPoints.length > 0 && (
                  <div className="mt-4">
                    <ResponsiveContainer width="100%" height={240}>
                      <LineChart data={sensitivityPoints}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                        <XAxis dataKey="purchase_price" tickFormatter={(v) => `$${(v / 1_000_000).toFixed(1)}M`} tick={{ fontSize: 11 }} />
                        <YAxis tickFormatter={(v) => `${(v * 100).toFixed(1)}%`} tick={{ fontSize: 11 }} />
                        <Tooltip
                          labelFormatter={(v) => formatCompactCurrency(v)}
                          formatter={(v, name) => [`${(v * 100).toFixed(1)}%`, name]}
                        />
                        <Legend />
                        <Line type="monotone" dataKey="irr" stroke="hsl(var(--primary))" name="IRR" dot={false} strokeWidth={2.4} />
                        <Line type="monotone" dataKey="cash_on_cash" stroke="hsl(var(--accent))" name="Cash-on-Cash" dot={false} strokeWidth={2.4} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </UnderwritingSection>
  );
}
