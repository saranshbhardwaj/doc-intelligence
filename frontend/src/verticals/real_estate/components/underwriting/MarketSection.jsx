import { useMemo, useState } from 'react';
import { Building2, ChevronDown, MapPin, TrendingUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { UnderwritingSection, UnderwritingStatusBadge } from './UnderwritingUI';
import KeyValueList from './KeyValueList';
import { formatCompactCurrency, formatCurrency, formatCurrencyPrecise, formatPercent, formatRatioPercent } from './formatters';

const BUCKET_ORDER = ['locker', 'small', 'medium', 'large', 'xlarge'];
const CLIMATE_ORDER = ['CC', 'NC'];
const CLIMATE_LABEL = { CC: 'Climate-Controlled', NC: 'Non-Climate' };

function parseStandardSqft(size) {
  if (!size) return null;
  const text = String(size).trim().toLowerCase().replace('×', 'x');
  const dimension = text.match(/^(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)/);
  if (dimension) return Number(dimension[1]) * Number(dimension[2]);
  const scalar = text.match(/^(\d+(?:\.\d+)?)/);
  return scalar ? Number(scalar[1]) : null;
}

function sizeBucket(sqft) {
  if (!sqft || sqft <= 0) return null;
  if (sqft < 25) return 'locker';
  if (sqft < 75) return 'small';
  if (sqft < 150) return 'medium';
  if (sqft < 300) return 'large';
  return 'xlarge';
}

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
  capRateSpreadBps,
  rentPositionAnalysis,
  rentComps,
  rentCompCoverage,
  unknownClimateCompCount,
}) {
  const [showAllRentComps, setShowAllRentComps] = useState(false);

  const { hasBuckets, matrixBuckets, matrixClimates, allSizeOnly } = useMemo(() => {
    const bucketSet = new Set(rentPositionAnalysis.map(r => r.bucket).filter(Boolean));
    const climateSet = new Set(rentPositionAnalysis.map(r => r.climate_type).filter(Boolean));
    const sizeOnly = rentPositionAnalysis.length > 0
      && rentPositionAnalysis.every(r => r.match_basis === 'size_only' || r.climate_type === 'Mixed');
    return {
      hasBuckets: bucketSet.size > 0,
      matrixBuckets: BUCKET_ORDER.filter(b => bucketSet.has(b)),
      matrixClimates: CLIMATE_ORDER.filter(c => climateSet.has(c)),
      allSizeOnly: sizeOnly,
    };
  }, [rentPositionAnalysis]);

  const brokerBenchmarksByBucket = useMemo(() => {
    const grouped = new Map();
    rentComps
      .filter((row) => row?.is_broker_market_average)
      .forEach((row) => {
        const sqft = row.standard_sqft || parseStandardSqft(row.size);
        const bucket = sizeBucket(sqft);
        if (!bucket) return;
        const rent = row.asking_rent ?? (row.rent_per_sqft != null && sqft ? row.rent_per_sqft * sqft : null);
        if (rent == null || rent <= 0) return;
        const current = grouped.get(bucket) || { total: 0, count: 0 };
        grouped.set(bucket, { total: current.total + rent, count: current.count + 1 });
      });
    return grouped;
  }, [rentComps]);

  const capRateRows = [
    { label: 'Submarket average cap rate', value: formatPercent(capRateSubmarket) },
    { label: 'Purchase cap rate basis', value: formatPercent(capRatePurchase) },
    { label: 'Sale cap rate assumption', value: formatPercent(capRateSale) },
    {
      label: 'Spread vs submarket',
      value: bpsDelta != null ? `${Math.abs(bpsDelta)} bps ${bpsDelta > 0 ? 'premium' : 'discount'}` : '—',
    },
  ].filter((row) => row.value !== '—');
  const displayedRentComps = showAllRentComps ? rentComps : rentComps.slice(0, 12);

  return (
    <UnderwritingSection
      eyebrow="Market context"
      title="Location, supply, and rent comps"
      className="underwriting-panel-strong"
      action={
        <Button variant="ghost" size="sm" onClick={onToggle} className="gap-1.5 h-7 px-3 text-xs text-muted-foreground">
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${show ? '' : '-rotate-90'}`} />
          {show ? 'Collapse' : 'Expand'}
        </Button>
      }
    >
      {show && (
        <div className="space-y-4">
          <div className="grid gap-4 xl:grid-cols-[1.1fr,0.9fr]">
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

            <div className="space-y-4">
              <div className="underwriting-panel p-4 sm:p-5">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Cap rate context</p>
                <div className="mt-4 space-y-3">
                  <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Subject implied</p>
                    <p className="mt-2 font-display text-2xl font-semibold text-primary">{formatPercent(impliedCapRate)}</p>
                    <p className="mt-1 text-sm text-muted-foreground">Based on {formatCompactCurrency(purchasePrice)} purchase price.</p>
                  </div>
                  {capRateRows.length > 0 ? (
                    <KeyValueList rows={capRateRows} />
                  ) : (
                    <p className="mt-3 rounded-xl border border-border/60 bg-background/60 px-3 py-2 text-xs leading-5 text-muted-foreground">
                      No submarket cap-rate benchmark is available yet.
                    </p>
                  )}
                  {capRateSpreadBps != null && Math.abs(capRateSpreadBps) >= 10 && (
                    <div className={`mt-3 rounded-md border px-3 py-2 text-sm ${
                      capRateSpreadBps > 0
                        ? 'bg-uw-risk/10 border-uw-risk/30 text-uw-risk'
                        : 'bg-uw-success/10 border-uw-success/30 text-uw-success'
                    }`}>
                      <span className="font-medium">
                        {capRateSpreadBps > 0 ? 'Cap rate expansion: ' : 'Cap rate compression: '}
                      </span>
                      {Math.abs(capRateSpreadBps)} bps {capRateSpreadBps > 0 ? '(exit headwind)' : '(exit tailwind)'}
                    </div>
                  )}
                </div>
              </div>
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
                      <span>{rentCompCoverage.compRows} facility comp rows reviewed</span>
                      {rentCompCoverage.brokerBenchmarkRows > 0 ? (
                        <>
                          <span>·</span>
                          <span>{rentCompCoverage.brokerBenchmarkRows} broker benchmark{rentCompCoverage.brokerBenchmarkRows === 1 ? '' : 's'}</span>
                        </>
                      ) : null}
                      {rentCompCoverage.supportMode === 'bucket' ? (
                        <>
                          <span>·</span>
                          <span>{rentCompCoverage.exactLabel}</span>
                        </>
                      ) : (
                        <>
                          <span>·</span>
                          <span>{rentCompCoverage.unmatchedCount} unmatched subject sizes</span>
                        </>
                      )}
                    </div>
                    {rentCompCoverage.unmatchedLabels?.length > 0 ? (
                      <p className="mt-2 text-xs leading-5 text-muted-foreground">
                        {rentCompCoverage.supportMode === 'bucket' ? 'Unsupported buckets' : 'Unmatched'}: {rentCompCoverage.unmatchedLabels.join(', ')}
                        {rentCompCoverage.unmatchedCount > rentCompCoverage.unmatchedLabels.length ? ', and more' : ''}
                      </p>
                    ) : null}
                    {rentCompCoverage.supportMode === 'bucket' && rentCompCoverage.exactUnmatchedLabels?.length > 0 ? (
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        Exact sizes without direct facility comps: {rentCompCoverage.exactUnmatchedLabels.join(', ')}
                        {rentCompCoverage.exactUnmatchedCount > rentCompCoverage.exactUnmatchedLabels.length ? ', and more' : ''}
                      </p>
                    ) : null}
                  </div>
                ) : null}
                {rentPositionAnalysis.length > 0 ? (
                  <div>
                    {/* Matrix table */}
                    {!hasBuckets || allSizeOnly ? (
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
                            {rentPositionAnalysis.map((row, index) => {
                              const noComp = row.comp_count === 0 || row.comp_average_rent == null;
                              return (
                                <tr key={index} className={`border-b border-border/50 last:border-b-0 ${noComp ? 'opacity-50' : ''}`}>
                                  <td className="py-3 font-medium text-foreground">{row.size || '—'}</td>
                                  <td className="py-3 text-muted-foreground">{row.climate_type}</td>
                                  <td className="py-3 text-right">{formatCurrency(row.subject_current_rent)}</td>
                                  <td className="py-3 text-right">{formatCurrency(row.subject_market_rent)}</td>
                                  <td className="py-3 text-right">
                                    {noComp
                                      ? <span className="text-muted-foreground/60 italic text-xs">no comp data</span>
                                      : formatCurrency(row.comp_average_rent)}
                                  </td>
                                  <td className="py-3 text-right font-medium text-foreground">{formatRatioPercent(row.current_vs_comp_ratio)}</td>
                                  <td className="py-3 text-right font-medium text-foreground">{formatRatioPercent(row.market_vs_comp_ratio)}</td>
                                </tr>
                              );
                            })}
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
                                  const benchmark = brokerBenchmarksByBucket.get(bucket);
                                  const benchmarkAverage = benchmark ? benchmark.total / benchmark.count : null;
                                  if (!cell) {
                                    return (
                                      <td key={climate} className="py-3 px-3 text-muted-foreground">
                                        {benchmarkAverage != null ? (
                                          <span className="text-xs">
                                            Broker: {formatCurrency(benchmarkAverage)}
                                            <span className="ml-1 text-muted-foreground/70">({benchmark.count})</span>
                                          </span>
                                        ) : '—'}
                                      </td>
                                    );
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
                                        {benchmarkAverage != null && (
                                          <span className="text-[11px] text-muted-foreground/80 tabular-nums">
                                            Broker benchmark: {formatCurrency(benchmarkAverage)}
                                            {benchmark.count > 1 ? ` (${benchmark.count})` : ''}
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

                    {unknownClimateCompCount > 0 && !allSizeOnly && (
                      <p className="mt-2 text-[11px] text-muted-foreground/70">
                        {unknownClimateCompCount} facility comp row{unknownClimateCompCount !== 1 ? 's' : ''} excluded from exact climate matching because climate type was unclear
                      </p>
                    )}
                    {allSizeOnly && (
                      <p className="mt-2 text-[11px] text-muted-foreground/70">
                        Bucket-level view · facility comp climate type not fully classified
                      </p>
                    )}

                    {/* Collapsible raw comp list */}
                    {rentComps.length > 0 && (
                      <details className="mt-3">
                        <summary className="cursor-pointer select-none text-xs font-medium text-primary hover:text-primary/80">
                          View comp / benchmark rows ({rentComps.length})
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
                              {(showAllRentComps ? rentComps : rentComps.slice(0, 12)).map((c, i) => (
                                <tr key={i} className="border-b border-border/50 last:border-b-0">
                                  <td className="py-2 text-muted-foreground">{c.facility ?? '—'}</td>
                                  <td className="py-2 tabular-nums text-muted-foreground">{c.size ?? '—'}</td>
                                  <td className="py-2">
                                    {c.is_broker_market_average ? (
                                      <UnderwritingStatusBadge tone="neutral" className="px-1.5 py-0 text-[9px]">
                                        Benchmark
                                      </UnderwritingStatusBadge>
                                    ) : c.climate_type ? (
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
                          {rentComps.length > 12 ? (
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              className="mt-3 h-8 px-2 text-xs text-primary"
                              onClick={() => setShowAllRentComps((value) => !value)}
                            >
                              {showAllRentComps ? 'Show fewer comps' : `Show all ${rentComps.length} comps`}
                            </Button>
                          ) : null}
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
                        {displayedRentComps.map((row, index) => (
                          <tr key={index} className="border-b border-border/50 last:border-b-0">
                            <td className="py-3 font-medium text-foreground">{row.size || '—'}</td>
                            <td className="py-3 text-muted-foreground">
                              <div className="flex flex-col gap-1">
                                <span>{row.facility || '—'}</span>
                                {row.is_broker_market_average ? (
                                  <UnderwritingStatusBadge tone="neutral" className="w-fit px-1.5 py-0 text-[9px]">
                                    Broker benchmark
                                  </UnderwritingStatusBadge>
                                ) : null}
                              </div>
                            </td>
                            <td className="py-3 text-right">{row.asking_rent != null ? formatCurrency(row.asking_rent) : '—'}</td>
                            <td className="py-3 text-right">{row.rent_per_sqft != null ? formatCurrencyPrecise(row.rent_per_sqft) : '—'}</td>
                            <td className="py-3 text-right text-muted-foreground">{row.distance_mi ? `${row.distance_mi} mi` : '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {rentComps.length > 12 ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="mt-3 h-8 px-2 text-xs text-primary"
                        onClick={() => setShowAllRentComps((value) => !value)}
                      >
                        {showAllRentComps ? 'Show fewer comps' : `Show all ${rentComps.length} comps`}
                      </Button>
                    ) : null}
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

        </div>
      )}
    </UnderwritingSection>
  );
}
