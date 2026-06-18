import { useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, Info } from 'lucide-react';
import { formatMultiple, formatPercent } from './formatters';

function sourceLabel(citation) {
  if (!citation) return 'Unavailable';
  if (citation.is_manual || citation.doc_type === 'manual') return 'Manual';
  if (citation.is_default) return 'Default';
  if (citation.doc_type === 'om') return citation.is_computed ? 'OM computed' : 'OM stated';
  if (citation.doc_type === 't12') return citation.is_computed ? 'T-12 computed' : 'T-12';
  if (citation.doc_type === 'rent_roll') return 'Rent roll';
  if (citation.doc_type === 'derived') return 'Derived';
  if (citation.doc_type === 'benchmark') return 'Benchmark adjusted';
  return citation.doc_type || 'Source';
}

function toneClasses(tone) {
  if (tone === 'danger') return 'border-destructive/25 bg-destructive/10 text-destructive';
  if (tone === 'warning') return 'border-warning/25 bg-warning/10 text-uw-risk';
  if (tone === 'success') return 'border-success/25 bg-success/10 text-success';
  return 'border-border/60 bg-background/70 text-muted-foreground';
}

function iconForTone(tone) {
  if (tone === 'success') return CheckCircle2;
  if (tone === 'warning' || tone === 'danger') return AlertTriangle;
  return Info;
}

function buildMemoPreflightItems({
  persistedInputs,
  artifact,
  currentRun,
  sourceCitations,
  unitMixSummary,
  stressTests,
  prioritizedWarnings,
}) {
  const hasT12 = Boolean(artifact?.t12_data?.summary);
  const hasRentRoll = Boolean(artifact?.rent_roll_data?.summary);
  const exitCapCitation = sourceCitations?.exit_cap_rate;
  const rentGrowthCitation = sourceCitations?.rent_growth_pct;
  const expenseRatio = artifact?.expense_basis?.expense_ratio ?? artifact?.expense_basis?.ratio ?? null;
  const baseStress = stressTests?.find((row) => row.scenario_key === 'base');
  const zeroGrowthStress = stressTests?.find((row) => row.scenario_key === 'rent_growth_zero');
  const zeroGrowthIrrDrop = baseStress?.irr != null && zeroGrowthStress?.irr != null
    ? baseStress.irr - zeroGrowthStress.irr
    : null;
  const nonStorageUnits = unitMixSummary?.parkingOtherUnits || 0;

  return [
    {
      tone: hasT12 && hasRentRoll ? 'success' : 'warning',
      title: hasT12 || hasRentRoll ? 'Source package is partial' : 'OM-only underwriting',
      detail: hasT12 && hasRentRoll
        ? 'T-12 and rent roll support are present.'
        : 'Memo should say operating results rely on OM support until T-12 and rent roll are uploaded.',
    },
    {
      tone: exitCapCitation?.is_default ? 'warning' : 'neutral',
      title: `Exit cap source: ${sourceLabel(exitCapCitation)}`,
      detail: `Exit cap is ${formatPercent(persistedInputs?.exit?.exit_cap_rate)}. This drives sale value and equity multiple.`,
    },
    {
      tone: rentGrowthCitation?.is_default ? 'warning' : 'neutral',
      title: `Rent growth source: ${sourceLabel(rentGrowthCitation)}`,
      detail: `Recurring rent growth is ${formatPercent(persistedInputs?.operational?.rent_growth_pct)}. Stress case should be reviewed if returns depend on growth.`,
    },
    nonStorageUnits > 0 ? {
      tone: 'warning',
      title: 'Mixed storage / non-storage unit base',
      detail: `${nonStorageUnits} units or spaces are parking, residential, office, or other non-storage categories. Memo should avoid blended per-door conclusions without this caveat.`,
    } : null,
    expenseRatio != null && expenseRatio < 0.30 ? {
      tone: 'warning',
      title: 'Expense ratio below benchmark',
      detail: `Modeled expense ratio is ${formatPercent(expenseRatio)}. Validate tax, insurance, management, utilities, and maintenance before committee.`,
    } : null,
    zeroGrowthIrrDrop != null && zeroGrowthIrrDrop > 0.05 ? {
      tone: 'danger',
      title: 'High sensitivity to rent growth',
      detail: `Zero-growth stress moves IRR from ${formatPercent(baseStress.irr)} to ${formatPercent(zeroGrowthStress.irr)} and EM to ${formatMultiple(zeroGrowthStress.equity_multiple)}.`,
    } : null,
    prioritizedWarnings?.length ? {
      tone: 'warning',
      title: `${prioritizedWarnings.length} underwriting watch item${prioritizedWarnings.length === 1 ? '' : 's'}`,
      detail: prioritizedWarnings[0]?.message || 'Review warnings before memo generation.',
    } : {
      tone: currentRun?.irr != null ? 'success' : 'neutral',
      title: 'No major watch items surfaced',
      detail: 'Review the calculation bridges and source citations before issuing the memo.',
    },
  ].filter(Boolean);
}

export default function MemoPreflightPanel(props) {
  const [expanded, setExpanded] = useState(false);
  const items = buildMemoPreflightItems(props);
  const severityRank = { danger: 0, warning: 1, neutral: 2, success: 3 };
  const sortedItems = [...items].sort((a, b) => (severityRank[a.tone] ?? 2) - (severityRank[b.tone] ?? 2));
  const visibleItems = expanded ? sortedItems : sortedItems.slice(0, 3);
  const hiddenCount = Math.max(sortedItems.length - visibleItems.length, 0);

  return (
    <div className="border-b border-border/70 bg-background/50 px-5 py-3 sm:px-6">
      <div className="flex flex-col gap-2.5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
              Committee review flags
            </p>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              Key assumptions the committee reader will expect to see reconciled.
            </p>
          </div>
          {sortedItems.length > 3 ? (
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border/70 bg-background/70 px-3 py-1.5 text-xs font-semibold text-muted-foreground transition-colors hover:text-foreground"
            >
              {expanded ? 'Show less' : `${hiddenCount} more`}
              <ChevronDown className={`h-3.5 w-3.5 transition-transform ${expanded ? 'rotate-180' : ''}`} />
            </button>
          ) : null}
        </div>
        {visibleItems.length ? (
          <div className={`grid gap-2 ${expanded ? 'md:grid-cols-2' : 'lg:grid-cols-3'}`}>
            {visibleItems.map((item) => {
              const Icon = iconForTone(item.tone);
              return (
                <div key={item.title} className={`rounded-xl border px-3 py-2 ${toneClasses(item.tone)}`}>
                  <div className="flex items-start gap-2">
                    <Icon className="mt-0.5 h-4 w-4 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-foreground">{item.title}</p>
                      <p className="mt-0.5 line-clamp-2 text-xs leading-5 text-muted-foreground">
                        {item.detail}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
            No committee review flags
          </p>
        )}
      </div>
    </div>
  );
}
