import { formatMultiple, formatPercent } from './formatters';

export function sourceLabel(citation) {
  if (!citation) return 'Default assumption';
  if (citation.is_manual || citation.doc_type === 'manual') return 'Manual';
  if (citation.is_default) return 'Default assumption';
  if (citation.doc_type === 'om') return citation.is_computed ? 'OM computed' : 'OM stated';
  if (citation.doc_type === 't12') return citation.is_computed ? 'T-12 computed' : 'T-12';
  if (citation.doc_type === 'rent_roll') return 'Rent roll';
  if (citation.doc_type === 'derived') return 'Derived';
  if (citation.doc_type === 'benchmark') return 'Benchmark adjusted';
  return citation.doc_type || 'Source';
}

export function buildMemoPreflightItems({
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