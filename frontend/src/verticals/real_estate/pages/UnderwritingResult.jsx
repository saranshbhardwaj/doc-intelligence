/**
 * Deal Dashboard
 * Decision-oriented results view for underwriting output.
 * Coordinates state and data derivation; delegates rendering to section components.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  Loader2,
  MapPin,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Warehouse,
  XCircle,
} from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from '@/components/ui/resizable';
import { UnderwritingResultSkeleton } from '../../../components/skeletons/PageSkeletons';
import AppLayout from '../../../components/layout/AppLayout';
import { useAppAuth } from '../../../hooks/useAppAuth';
import { useUnderwriting, useUnderwritingActions } from '../../../store';
import { deleteUnderwritingRun, recalculateScenario, runSensitivityAnalysis } from '../../../api/re-underwriting';
import {
  CreditMemoModal,
  CreditMemoProgress,
  DiscrepanciesSection,
  EvidenceSection,
  MarketSection,
  MaxBidPanel,
  MaxLoanPanel,
  MemoHistorySheet,
  ModelBasisPanel,
  OperationsSection,
  ReturnsSection,
  ScenarioPanel,
  SourceDocumentPanel,
  TrustPanel,
  UnderwritingMetricCard,
  UnderwritingStatusBadge,
  buildDerivedMixedRevenueWarning,
  formatCompactCurrency,
  formatCurrency,
  formatEvidenceValue,
  formatMultiple,
  formatPercent,
  formatRatioPercent,
  getFieldCitation,
  getRentCompCoverage,
  getRevenueBasis,
  getUnitMixSource,
  getUnitMixSummary,
  pickUnitMix,
} from '../components/underwriting';

function WorkspaceMark() {
  return (
    <div className="underwriting-brand-mark">
      <Warehouse className="h-4 w-4" aria-hidden="true" />
    </div>
  );
}

export default function UnderwritingResult() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const { getToken, user: currentUser } = useAppAuth();
  const { currentRun } = useUnderwriting();
  const { loadRun } = useUnderwritingActions();

  const [showSourcePanel, setShowSourcePanel] = useState(false);
  const [activeCitation, setActiveCitation] = useState(null);
  const [showScenario, setShowScenario] = useState(false);
  const [showReturns, setShowReturns] = useState(true);
  const [showOperations, setShowOperations] = useState(false);
  const [showEvidence, setShowEvidence] = useState(false);
  const [showMarket, setShowMarket] = useState(false);
  const [showTrustPanel, setShowTrustPanel] = useState(false);
  const [scenarioValues, setScenarioValues] = useState({});
  const [scenarioResult, setScenarioResult] = useState(null);
  const [isScenarioLoading, setIsScenarioLoading] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const scenarioDebounceRef = useRef(null);

  // Credit memo state
  const [memoModalOpen, setMemoModalOpen] = useState(false);
  const [memoHistoryOpen, setMemoHistoryOpen] = useState(false);
  const [memoProgress, setMemoProgress] = useState(null); // { jobId, memoId } | null
  const [memoRefreshKey, setMemoRefreshKey] = useState(0);
  const [memoPrefill, setMemoPrefill] = useState(null);

  useEffect(() => {
    if (runId) loadRun(getToken, runId);
  }, [getToken, loadRun, runId]);

  const handleOpenSource = (citation) => {
    setActiveCitation(citation);
    setShowSourcePanel(true);
  };

  const triggerScenarioRecalc = useCallback((values) => {
    if (scenarioDebounceRef.current) clearTimeout(scenarioDebounceRef.current);
    if (Object.keys(values).length === 0) {
      setScenarioResult(null);
      return;
    }
    scenarioDebounceRef.current = setTimeout(async () => {
      setIsScenarioLoading(true);
      try {
        const overrides = {};
        if (values.exit_cap_rate != null) overrides.exit_cap_rate = values.exit_cap_rate / 100;
        if (values.vacancy_credit_loss_pct != null) overrides.vacancy_credit_loss_pct = values.vacancy_credit_loss_pct / 100;
        if (values.rent_growth_pct != null) overrides.rent_growth_pct = values.rent_growth_pct / 100;
        if (values.interest_rate_pct != null) overrides.interest_rate_pct = values.interest_rate_pct / 100;
        if (values.purchase_price != null) overrides.purchase_price = values.purchase_price;
        const result = await recalculateScenario(getToken, runId, overrides);
        setScenarioResult(result);
      } catch (err) {
        console.error('Scenario recalculate error:', err);
      } finally {
        setIsScenarioLoading(false);
      }
    }, 400);
  }, [getToken, runId]);

  const handleScenarioChange = useCallback((field, value) => {
    setScenarioValues((prev) => {
      const next = { ...prev, [field]: value };
      triggerScenarioRecalc(next);
      return next;
    });
  }, [triggerScenarioRecalc]);

  const resetScenario = useCallback(() => {
    setScenarioValues({});
    setScenarioResult(null);
  }, []);

  const handleDelete = useCallback(async () => {
    if (!runId || isDeleting) return;
    setIsDeleting(true);
    try {
      await deleteUnderwritingRun(getToken, runId);
      navigate('/app/re/underwriting');
    } catch (err) {
      console.error('Delete failed:', err);
    } finally {
      setIsDeleting(false);
    }
  }, [getToken, isDeleting, navigate, runId]);

  const handleMemoSubmitted = (resp) => {
    setMemoProgress({ jobId: resp.job_id, memoId: resp.memo_id });
    setMemoRefreshKey((k) => k + 1);
  };

  const handleRegenerate = (memo) => {
    // NOTE: MemoSummary includes prior analyst inputs so regeneration can start from a previous version.
    setMemoPrefill({
      cover_data: memo.cover_data || {},
      sponsor_data: memo.sponsor_data || {},
      thesis_data: memo.thesis_data || {},
      market_notes: memo.market_notes || null,
    });
    setMemoModalOpen(true);
  };

  // ── Derived data ──────────────────────────────────────────────────────────

  const artifact = currentRun?.result_artifact || {};
  const persistedInputs = currentRun?.inputs || {};
  const verdict = artifact.verdict;
  const verdictStatus = verdict?.status;
  const verdictTone = verdictStatus === 'worth_pursuing' ? 'success'
    : verdictStatus === 'needs_review' ? 'warning'
    : verdictStatus ? 'danger' : 'neutral';
  const verdictLabel = verdictStatus === 'worth_pursuing' ? 'Passes Screen'
    : verdictStatus === 'needs_review' ? 'Passes With Conditions'
    : verdictStatus ? 'Below Screen' : 'In Review';

  const projections = artifact.projections || [];
  const stressTests = artifact.stress_tests || [];
  const rolloverRisk = artifact.rollover_risk;
  const unitMix = pickUnitMix(artifact, persistedInputs);

  const demographics = artifact.demographics || (
    persistedInputs.project?.population_3mi != null ||
    persistedInputs.project?.avg_household_income_3mi != null ||
    persistedInputs.project?.storage_sqft_per_capita_3mi != null
      ? {
          population: persistedInputs.project?.population_3mi,
          avg_household_income: persistedInputs.project?.avg_household_income_3mi,
          sqft_per_capita: persistedInputs.project?.storage_sqft_per_capita_3mi,
        }
      : null
  );

  const rentComps = (persistedInputs.rent_comps?.length ? persistedInputs.rent_comps : artifact.rent_comps) || [];
  const marketData = {
    ...(artifact.market_data || {}),
    nearby_storage_count_1mi: artifact.market_data?.nearby_storage_count_1mi ?? persistedInputs.project?.nearby_storage_count_1mi,
    nearby_storage_count_3mi: artifact.market_data?.nearby_storage_count_3mi ?? persistedInputs.project?.nearby_storage_count_3mi,
    nearby_storage_count_5mi: artifact.market_data?.nearby_storage_count_5mi ?? persistedInputs.project?.nearby_storage_count_5mi,
  };

  const discrepancies = currentRun?.discrepancies || [];
  const fieldCitations = currentRun?.field_citations || {};
  const citationContext = currentRun?.citation_context || {};
  const noiBridge = artifact.noi_bridge || null;

  const storedVerdictWarnings = verdict?.warnings || [];
  const extractionReviewWarnings = [
    ...(artifact.t12_data?.review_warnings || []),
    ...(artifact.rent_roll_data?.review_warnings || []),
  ].map((warning, index) => ({
    key: warning.key || `extraction-review-${index}`,
    severity: warning.severity || 'warning',
    message: warning.message || 'Source document extraction needs analyst review.',
  }));
  const discrepancyReviewWarnings = discrepancies
    .filter((discrepancy) => ['critical', 'error', 'warning'].includes(discrepancy.severity))
    .slice(0, 3)
    .map((discrepancy, index) => ({
      key: `discrepancy-${discrepancy.field}-${index}`,
      severity: discrepancy.severity === 'error' ? 'critical' : 'warning',
      message: discrepancy.reason
        ? `${discrepancy.note} Model used ${discrepancy.preferred_source || 'the preferred source'}.`
        : discrepancy.note,
    }));
  const derivedMixedRevenueWarning = buildDerivedMixedRevenueWarning(unitMix);
  const verdictWarningsBase = [
    ...storedVerdictWarnings,
    ...extractionReviewWarnings,
    ...discrepancyReviewWarnings,
  ];
  const verdictWarnings = derivedMixedRevenueWarning && !verdictWarningsBase.some((w) => w.key === derivedMixedRevenueWarning.key)
    ? [...verdictWarningsBase, derivedMixedRevenueWarning]
    : verdictWarningsBase;

  const sourceCitations = {
    purchase_price: getFieldCitation(fieldCitations, citationContext, 'purchase_price'),
    num_units: getFieldCitation(fieldCitations, citationContext, 'num_units'),
    rentable_sqft: getFieldCitation(fieldCitations, citationContext, 'rentable_sqft'),
    gross_potential_rent_annual: getFieldCitation(fieldCitations, citationContext, 'gross_potential_rent_annual'),
    avg_in_place_rent_per_unit_monthly: getFieldCitation(fieldCitations, citationContext, 'avg_in_place_rent_per_unit_monthly'),
    avg_market_rent_per_unit_monthly: getFieldCitation(fieldCitations, citationContext, 'avg_market_rent_per_unit_monthly'),
    vacancy_credit_loss_pct: getFieldCitation(fieldCitations, citationContext, 'vacancy_credit_loss_pct'),
    expense_ratio_t12: getFieldCitation(fieldCitations, citationContext, 'expense_ratio_t12'),
    expense_ratio_current: getFieldCitation(fieldCitations, citationContext, 'expense_ratio_current'),
    expense_ratio_year1: getFieldCitation(fieldCitations, citationContext, 'expense_ratio_year1'),
    expense_ratio_pro_forma: getFieldCitation(fieldCitations, citationContext, 'expense_ratio_pro_forma'),
    property_tax_annual: getFieldCitation(fieldCitations, citationContext, 'property_tax_annual'),
    insurance_annual: getFieldCitation(fieldCitations, citationContext, 'insurance_annual'),
    payroll_annual: getFieldCitation(fieldCitations, citationContext, 'payroll_annual'),
    repairs_maintenance_annual: getFieldCitation(fieldCitations, citationContext, 'repairs_maintenance_annual'),
    utilities_annual: getFieldCitation(fieldCitations, citationContext, 'utilities_annual'),
    marketing_annual: getFieldCitation(fieldCitations, citationContext, 'marketing_annual'),
    other_income_annual: getFieldCitation(fieldCitations, citationContext, 'other_income_annual'),
    property_tax_growth_pct: getFieldCitation(fieldCitations, citationContext, 'property_tax_growth_pct'),
    property_tax_value_basis_amount: getFieldCitation(fieldCitations, citationContext, 'property_tax_value_basis_amount'),
    property_tax_assessed_value: getFieldCitation(fieldCitations, citationContext, 'property_tax_assessed_value'),
    property_tax_assessment_ratio: getFieldCitation(fieldCitations, citationContext, 'property_tax_assessment_ratio'),
    property_tax_millage_rate: getFieldCitation(fieldCitations, citationContext, 'property_tax_millage_rate'),
    property_tax_rate_per_assessed_dollar: getFieldCitation(fieldCitations, citationContext, 'property_tax_rate_per_assessed_dollar'),
    bad_debt_annual: getFieldCitation(fieldCitations, citationContext, 'bad_debt_annual'),
    corrections_collections_annual: getFieldCitation(fieldCitations, citationContext, 'corrections_collections_annual'),
    interest_rate_pct: getFieldCitation(fieldCitations, citationContext, 'interest_rate_pct'),
    exit_cap_rate: getFieldCitation(fieldCitations, citationContext, 'exit_cap_rate'),
    market_cap_rate_purchase: getFieldCitation(fieldCitations, citationContext, 'market_cap_rate_purchase'),
    market_cap_rate_sale: getFieldCitation(fieldCitations, citationContext, 'market_cap_rate_sale'),
    mgmt_fee_pct: getFieldCitation(fieldCitations, citationContext, 'mgmt_fee_pct'),
    noi_year_one_stated: getFieldCitation(fieldCitations, citationContext, 'noi_year_one_stated'),
    noi_current_stated: getFieldCitation(fieldCitations, citationContext, 'noi_current_stated'),
    noi_actual: getFieldCitation(fieldCitations, citationContext, 'noi_actual'),
  };

  const verdictFailureSupportByMetric = {
    irr: [sourceCitations.purchase_price, sourceCitations.exit_cap_rate],
    cash_on_cash: [sourceCitations.purchase_price, sourceCitations.interest_rate_pct],
    equity_multiple: [sourceCitations.purchase_price, sourceCitations.exit_cap_rate],
    dscr: [sourceCitations.interest_rate_pct, sourceCitations.gross_potential_rent_annual],
    dscr_year_one: [sourceCitations.interest_rate_pct, sourceCitations.gross_potential_rent_annual],
    ltv: [sourceCitations.purchase_price],
  };

  const discrepancySupportByField = {
    num_units: [sourceCitations.num_units],
    gross_potential_rent_annual: [sourceCitations.gross_potential_rent_annual],
    rentable_sqft: [sourceCitations.rentable_sqft],
    occupancy_pct: [sourceCitations.vacancy_credit_loss_pct],
    opex_ratio: [sourceCitations.expense_ratio_current, sourceCitations.expense_ratio_pro_forma, sourceCitations.property_tax_annual],
    expense_ratio: [sourceCitations.expense_ratio_current, sourceCitations.expense_ratio_pro_forma],
    other_income_annual: [sourceCitations.other_income_annual],
    noi: [sourceCitations.gross_potential_rent_annual, sourceCitations.expense_ratio_current],
    avg_in_place_rent_per_unit_monthly: [sourceCitations.avg_in_place_rent_per_unit_monthly],
    avg_market_rent_per_unit_monthly: [sourceCitations.avg_market_rent_per_unit_monthly],
    property_tax_annual: [sourceCitations.property_tax_annual],
    insurance_annual: [sourceCitations.insurance_annual],
    payroll_annual: [sourceCitations.payroll_annual],
    repairs_maintenance_annual: [sourceCitations.repairs_maintenance_annual],
    utilities_annual: [sourceCitations.utilities_annual],
    marketing_annual: [sourceCitations.marketing_annual],
    unit_mix: [sourceCitations.num_units, sourceCitations.rentable_sqft],
  };

  const verdictRationale = verdict?.rationale
    ? (derivedMixedRevenueWarning && !verdict.rationale.includes('Mixed revenue detected:')
      ? `${verdict.rationale} Warning: ${derivedMixedRevenueWarning.message}`
      : verdict.rationale)
    : derivedMixedRevenueWarning?.message || null;
  const leadSummary = verdictStatus === 'worth_pursuing'
    ? 'Returns clear the configured screen based on the current underwriting assumptions.'
    : verdictStatus === 'needs_review'
      ? 'Returns clear the initial screen, but the source support needs analyst review before relying on this result.'
      : verdictStatus
        ? 'The current assumptions do not clear the configured screen. Review the failed metrics and source support before revising.'
        : verdictRationale;

  const criticalWarningCount = verdictWarnings.filter((w) => w.severity === 'critical').length;
  const prioritizedWarnings = [
    ...verdictWarnings.filter((w) => w.severity === 'critical'),
    ...verdictWarnings.filter((w) => w.severity !== 'critical'),
  ];
  const watchItems = [
    ...(verdict?.failures || []).slice(0, 3).map((failure) => ({
      id: `failure-${failure.metric}`,
      kind: 'failure',
      label: failure.metric.replaceAll('_', ' '),
      citations: verdictFailureSupportByMetric[failure.metric] || [],
      gap: failure.gap,
    })),
    ...prioritizedWarnings.map((warning) => ({
      id: `warning-${warning.key}`,
      kind: 'warning',
      severity: warning.severity,
      label: warning.message,
      citations: [],
    })),
  ].slice(0, Math.max(criticalWarningCount + 4, 4));
  const leadWatchItems = watchItems.slice(0, 3);
  const hiddenWatchCount = Math.max(watchItems.length - leadWatchItems.length, 0);

  const failedSet = new Set((verdict?.failures || []).map((f) => f.metric));

  const fm = artifact.formula_metadata || {};
  function buildTooltip(key, valueFn, fallbackFn = null, descriptionOverride = null) {
    const meta = fm[key];
    if (meta) {
      const cv = meta.computed_values || {};
      const computed = valueFn ? valueFn(cv) : null;
      const fallback = !computed && fallbackFn ? fallbackFn() : null;
      const description = descriptionOverride || meta.description;
      const calculation = computed || fallback;
      return calculation ? `${description}\n\n${calculation}` : description;
    }
    const fallback = fallbackFn ? fallbackFn() : null;
    return fallback || null;
  }

  const capitalStructure = artifact.capital_structure || {};
  const purchasePrice = capitalStructure.purchase_price || 0;
  const loanAmount = capitalStructure.loan_amount || 0;
  const equityInvested = capitalStructure.total_equity_invested || Math.max(purchasePrice - loanAmount, 0);
  const equityPct = purchasePrice > 0 ? equityInvested / purchasePrice : 0;
  const ltvPct = purchasePrice > 0 ? loanAmount / purchasePrice : 0;
  const equityRaiseTone = equityPct >= 0.5 ? 'warning' : equityPct >= 0.4 ? 'active' : 'neutral';
  const equityRaiseLabel = equityPct >= 0.5 ? 'Large equity raise' : equityPct >= 0.4 ? 'Meaningful equity raise' : 'Moderate equity raise';

  const baseScenario = {
    exit_cap_rate: persistedInputs.exit?.exit_cap_rate != null ? persistedInputs.exit.exit_cap_rate * 100 : null,
    vacancy_credit_loss_pct: persistedInputs.operational?.vacancy_credit_loss_pct != null ? persistedInputs.operational.vacancy_credit_loss_pct * 100 : null,
    rent_growth_pct: persistedInputs.operational?.rent_growth_pct != null ? persistedInputs.operational.rent_growth_pct * 100 : null,
    interest_rate_pct: persistedInputs.financing?.interest_rate_pct != null ? persistedInputs.financing.interest_rate_pct * 100 : null,
    purchase_price: persistedInputs.acquisition?.purchase_price || purchasePrice || null,
  };
  const totalUnits = artifact.rent_roll_data?.summary?.total_units || persistedInputs.project?.num_units;
  const gpr = persistedInputs.operational?.gross_potential_rent_annual;
  const derivedCurrentRentPerDoor = totalUnits && gpr ? gpr / totalUnits / 12 : null;

  const computedAvgInPlaceRent = useMemo(() => {
    const rows = unitMix?.filter((r) => r.current_rent != null && r.occupied_units > 0) ?? [];
    const weightedSum = rows.reduce((s, r) => s + r.current_rent * r.occupied_units, 0);
    const totalOccupied = rows.reduce((s, r) => s + r.occupied_units, 0);
    return totalOccupied > 0 ? Math.round((weightedSum / totalOccupied) * 100) / 100 : null;
  }, [unitMix]);

  const omStatedAvgRent = persistedInputs.operational?.avg_in_place_rent_per_unit_monthly
    ?? artifact.om_data?.avg_in_place_rent_per_unit_monthly
    ?? null;
  const rentGapPct = omStatedAvgRent && computedAvgInPlaceRent
    ? Math.abs(omStatedAvgRent - computedAvgInPlaceRent) / computedAvgInPlaceRent
    : 0;
  const showAvgRentGap = rentGapPct > 0.05;

  const currentRentPerDoor = persistedInputs.operational?.avg_in_place_rent_per_unit_monthly
    ?? artifact.rent_roll_data?.summary?.avg_in_place_rent_per_unit_monthly
    ?? artifact.om_data?.avg_in_place_rent_per_unit_monthly
    ?? derivedCurrentRentPerDoor;
  const marketRentPerDoor = persistedInputs.operational?.avg_market_rent_per_unit_monthly
    ?? artifact.rent_roll_data?.summary?.avg_market_rent_per_unit_monthly
    ?? artifact.om_data?.avg_market_rent_per_unit_monthly
    ?? null;
  const impliedCapRate = purchasePrice && currentRun?.noi_year_one ? currentRun.noi_year_one / purchasePrice : null;
  const occupancy = artifact.rent_roll_data?.summary?.occupancy_pct;
  const t12OpexRatio = artifact.t12_data?.summary?.opex_ratio;
  const omOpexPct = artifact.om_data?.opex_pct;
  const hasT12Data = !!(artifact.t12_data?.summary &&
    (artifact.t12_data.summary.expense_ratio_actual != null || artifact.t12_data.summary.opex_ratio != null));
  const currentExpenseRatio = hasT12Data
    ? (artifact.t12_data.summary.expense_ratio_actual ?? t12OpexRatio)
    : persistedInputs.operational?.expense_ratio_current ?? artifact.om_data?.expense_ratio_current ?? null;
  const proFormaExpenseRatio = persistedInputs.operational?.expense_ratio_pro_forma
    ?? artifact.om_data?.expense_ratio_pro_forma
    ?? omOpexPct;
  const expenseBasis = artifact.expense_basis || null;
  const isOmNoiMode = expenseBasis?.source === 'om_noi';
  const modelExpenseRatio = expenseBasis?.expense_ratio ?? expenseBasis?.ratio ?? null;
  const decisionSnapshotRows = [
    { label: 'NOI Y1', value: formatCompactCurrency(currentRun?.noi_year_one) },
    { label: 'Cap rate Y1', value: formatPercent(currentRun?.cap_rate_year_one) },
    { label: 'DSCR Y1', value: formatMultiple(currentRun?.dscr_year_one) },
    { label: 'Basis', value: expenseBasis?.label || '—' },
    { label: 'Current ask', value: formatCompactCurrency(purchasePrice) },
    { label: 'Review items', value: `${prioritizedWarnings.length}` },
  ];
  const expenseBasisFormula = buildTooltip('expense_basis',
    (cv) => {
      const lines = [];
      const isLineItemBasis = expenseBasis?.method === 'line_items'
        || String(expenseBasis?.source || '').endsWith('_line_items');
      if (isLineItemBasis) {
        const opex = expenseBasis?.modeled_total_expenses ?? cv.year1_line_item_opex;
        const egi = expenseBasis?.modeled_egi ?? cv.year1_egi;
        if (opex != null) lines.push(`Line-item OpEx: ${formatCompactCurrency(opex)}`);
        if (opex != null && egi != null) lines.push(`Implied ratio: ${formatCompactCurrency(opex)} ÷ ${formatCompactCurrency(egi)} EGI = ${formatPercent(opex / egi)}`);
      } else {
        const ratio = expenseBasis?.expense_ratio ?? expenseBasis?.ratio ?? cv.ratio;
        const egi = expenseBasis?.modeled_egi ?? cv.year1_egi;
        if (ratio != null && egi != null) lines.push(`Ratio-driven OpEx: ${formatPercent(ratio)} × ${formatCompactCurrency(egi)} EGI = ${formatCompactCurrency(ratio * egi)}`);
      }
      return lines.length ? lines.join('\n') : null;
    },
  );
  const rentSpreadPerDoor = marketRentPerDoor != null && currentRentPerDoor != null
    ? marketRentPerDoor - currentRentPerDoor : null;
  const breakEvenOccupancyPct = artifact.break_even_occupancy_pct;
  const isLineItemExpenseBasis = expenseBasis?.method === 'line_items'
    || String(expenseBasis?.source || '').endsWith('_line_items');
  const expenseRatioBenchmarkNote = modelExpenseRatio != null && modelExpenseRatio < 0.3
    ? 'Below 30% expense benchmark'
    : null;
  const modelExpenseRatioDetail = isLineItemExpenseBasis
    ? [expenseRatioBenchmarkNote, 'Implied by selected line items'].filter(Boolean).join(' · ')
    : [expenseRatioBenchmarkNote, expenseBasis?.label || 'Selected expense basis'].filter(Boolean).join(' · ');
  const breakEvenOccupancyDetail = (() => {
    if (breakEvenOccupancyPct == null) return 'Needs NOI, debt service, and revenue support';
    if (occupancy != null) {
      const cushion = occupancy - breakEvenOccupancyPct;
      if (cushion < 0) return 'Above stated occupancy';
      if (cushion < 0.1) return 'Narrow cushion to stated occupancy';
      return 'Debt-service occupancy cushion';
    }
    return 'Minimum occupancy to cover Year-1 debt service';
  })();
  const rentPositionAnalysis = artifact.rent_position_analysis || [];
  const revenueBasis = getRevenueBasis(artifact, persistedInputs, sourceCitations);
  const unitMixSummary = getUnitMixSummary(unitMix);
  const propertyUnits = persistedInputs.project?.num_units
    ?? artifact.om_data?.num_units
    ?? currentRun?.num_units
    ?? null;
  const extractedUnits = unitMixSummary?.totalUnits || 0;
  const hasRentRollUnitMix = Array.isArray(artifact.rent_roll_data?.unit_mix)
    && artifact.rent_roll_data.unit_mix.length > 0;
  const unitMixIsPartial = !hasRentRollUnitMix
    && propertyUnits > 0
    && extractedUnits > 0
    && extractedUnits < propertyUnits * 0.9;
  const unitMixCoveragePct = propertyUnits > 0 ? extractedUnits / propertyUnits : null;
  const unitMixSource = getUnitMixSource(artifact, persistedInputs, {
    isPartial: unitMixIsPartial,
    propertyUnits,
    extractedUnits,
    coveragePct: unitMixCoveragePct,
  });
  const rentCompCoverage = getRentCompCoverage(unitMix, rentComps, rentPositionAnalysis);

  const omStatedNoi = persistedInputs.operational?.noi_year_one_stated
    ?? artifact.om_data?.noi_year_one_stated
    ?? artifact.om_data?.noi_projected
    ?? persistedInputs.operational?.noi_current_stated
    ?? artifact.om_data?.noi_current_stated
    ?? null;
  const modeledNoi = currentRun?.noi_year_one ?? artifact.noi_year_one ?? null;
  const noiBridgeDelta = omStatedNoi != null && modeledNoi != null ? modeledNoi - omStatedNoi : null;
  const noiBridgeDeltaPct = omStatedNoi ? noiBridgeDelta / omStatedNoi : null;
  const noiBridgeAlert = !isOmNoiMode && noiBridgeDeltaPct != null && Math.abs(noiBridgeDeltaPct) > 0.05;

  const capRateSubmarket = marketData.submarket_avg_cap_rate;
  const capRatePurchase = persistedInputs.acquisition?.market_cap_rate_purchase
    || artifact.om_data?.market_cap_rate_purchase
    || marketData.market_cap_rate_purchase
    || impliedCapRate;
  const capRateSale = persistedInputs.exit?.market_cap_rate_sale
    || artifact.om_data?.market_cap_rate_sale
    || marketData.market_cap_rate_sale;
  const bpsDelta = capRateSubmarket && impliedCapRate
    ? Math.round((impliedCapRate - capRateSubmarket) * 10000) : null;
  const capRateSpreadBps = capRatePurchase != null && capRateSale != null
    ? Math.round((capRateSale - capRatePurchase) * 10000)
    : null;

  const dscrFloor = persistedInputs?.criteria?.dscr_year_one_floor ?? 1.25;
  const debtYield = artifact?.debt_yield ?? null;

  const address = currentRun?.address
    || persistedInputs.project?.address
    || artifact.om_data?.address
    || '';
  const mapsKey = import.meta.env.VITE_GOOGLE_MAPS_KEY;
  const mapUrl = mapsKey && address
    ? `https://maps.googleapis.com/maps/api/staticmap?center=${encodeURIComponent(address)}&zoom=13&size=500x260&markers=color:red%7C${encodeURIComponent(address)}&key=${mapsKey}`
    : null;

  const proformaData = projections.slice(0, 5).map((p) => ({
    year: `Y${p.year}`,
    NOI: Math.round(p.noi),
    CFADS: Math.round(p.cash_flow),
  }));

  const metrics = [
    {
      label: 'IRR',
      value: formatPercent(currentRun?.irr),
      tone: failedSet.has('irr') ? 'danger' : verdictStatus === 'worth_pursuing' ? 'success' : 'default',
      detail: failedSet.has('irr') ? 'Below target threshold' : 'Projected internal rate of return',
      formula: buildTooltip('irr',
        (cv) => {
          if (cv.entry_equity == null || cv.total_distributions == null || cv.exit_proceeds == null) return null;
          const total = cv.total_distributions + cv.exit_proceeds;
          const em = cv.entry_equity > 0 ? total / cv.entry_equity : null;
          const lines = [
            `Equity in:         −${formatCompactCurrency(cv.entry_equity)}`,
            `Distributions:      ${formatCompactCurrency(cv.total_distributions)}${cv.hold_years ? ` (${cv.hold_years} yrs)` : ''}`,
          ];
          if (cv.loan_balance_at_exit != null) {
            lines.push(`Gross sale:         ${formatCompactCurrency(cv.exit_proceeds + cv.loan_balance_at_exit)}`);
            lines.push(`  Loan payoff:     −${formatCompactCurrency(cv.loan_balance_at_exit)}`);
            lines.push(`  Equity from sale: ${formatCompactCurrency(cv.exit_proceeds)}`);
          } else {
            lines.push(`Net exit:           ${formatCompactCurrency(cv.exit_proceeds)}`);
          }
          lines.push(`─────────────────────────`);
          lines.push(`Total out:          ${formatCompactCurrency(total)}${em != null ? ` = ${em.toFixed(2)}× equity` : ''}`);
          return lines.join('\n');
        },
        () => {
          const eq = capitalStructure.total_equity_invested;
          const em = currentRun?.equity_multiple;
          if (!eq) return null;
          return em
            ? `Equity in: −${formatCompactCurrency(eq)}\nTotal out: ${formatCompactCurrency(em * eq)} = ${em.toFixed(2)}× equity`
            : `Equity in: −${formatCompactCurrency(eq)}`;
        },
        'Annualized return on equity across the full hold, accounting for timing of every cash flow in and out. IRR uses the annual cash-flow schedule and exit proceeds; the summary below reconciles total proceeds.',
      ),
    },
    {
      label: 'Cash-on-Cash',
      value: formatPercent(currentRun?.cash_on_cash),
      tone: failedSet.has('cash_on_cash') ? 'warning' : 'default',
      detail: 'Year-one cash yield',
      formula: buildTooltip('cash_on_cash',
        (cv) => {
          if (cv.year1_cash_flow == null || cv.total_equity == null) return null;
          const year1Noi = cv.year1_noi ?? currentRun?.noi_year_one;
          const lines = [];
          if (year1Noi != null) lines.push(`Year-1 NOI:                     ${formatCompactCurrency(year1Noi)}`);
          if (cv.annual_debt_service != null) lines.push(`Debt service:                  −${formatCompactCurrency(cv.annual_debt_service)}`);
          lines.push(`Cash flow after debt service:  ${formatCompactCurrency(cv.year1_cash_flow)}`);
          lines.push(`Equity invested:               ${formatCompactCurrency(cv.total_equity)}`);
          return lines.join('\n');
        },
        () => {
          const eq = capitalStructure.total_equity_invested;
          const coc = currentRun?.cash_on_cash;
          if (!eq || !coc) return null;
          const cashFlow = coc * eq;
          const lines = [];
          if (currentRun?.noi_year_one != null) lines.push(`Year-1 NOI: ${formatCompactCurrency(currentRun.noi_year_one)}`);
          if (currentRun?.noi_year_one != null && currentRun?.dscr_year_one) {
            lines.push(`Debt service: −${formatCompactCurrency(currentRun.noi_year_one / currentRun.dscr_year_one)}`);
          }
          lines.push(`Cash flow after debt service: ${formatCompactCurrency(cashFlow)}`);
          lines.push(`Equity invested: ${formatCompactCurrency(eq)}`);
          return lines.join('\n');
        },
      ),
    },
    {
      label: 'Equity Multiple',
      value: formatMultiple(currentRun?.equity_multiple),
      tone: failedSet.has('equity_multiple') ? 'warning' : 'default',
      detail: 'Total return multiple',
      formula: buildTooltip('equity_multiple',
        (cv) => {
          const equityFromSale = cv.equity_from_sale ?? cv.net_sale_price;
          if (cv.total_cash_flows == null || equityFromSale == null || cv.total_equity == null) return null;
          const total = cv.total_cash_flows + equityFromSale;
          const lines = [`Distributions: ${formatCompactCurrency(cv.total_cash_flows)}${cv.hold_years ? ` (${cv.hold_years} yrs)` : ''}`];
          if (cv.net_sale_price != null && cv.loan_balance_at_exit != null) {
            lines.push(`Gross sale:     ${formatCompactCurrency(cv.net_sale_price)}`);
            lines.push(`  Loan payoff: −${formatCompactCurrency(cv.loan_balance_at_exit)}`);
            lines.push(`  Equity:       ${formatCompactCurrency(equityFromSale)}`);
          } else {
            lines.push(`Net exit:       ${formatCompactCurrency(equityFromSale)}`);
          }
          lines.push(`─────────────────────────`);
          lines.push(`Total ÷ equity: ${formatCompactCurrency(total)} ÷ ${formatCompactCurrency(cv.total_equity)}`);
          return lines.join('\n');
        },
        () => {
          const eq = capitalStructure.total_equity_invested;
          const em = currentRun?.equity_multiple;
          if (!eq || !em) return null;
          return `Total return: ${formatCompactCurrency(em * eq)} ÷ ${formatCompactCurrency(eq)} equity`;
        },
      ),
    },
    {
      label: 'DSCR Year 1',
      value: formatMultiple(currentRun?.dscr_year_one),
      tone: currentRun?.dscr_year_one != null && currentRun.dscr_year_one < dscrFloor ? 'warning' : 'default',
      detail: currentRun?.dscr_year_one != null && currentRun.dscr_year_one < dscrFloor ? `Below ${dscrFloor.toFixed(2)}× minimum` : 'Debt coverage cushion',
      formula: buildTooltip('dscr_year_one',
        (cv) => {
          if (cv.year1_noi == null || cv.annual_debt_service == null) return null;
          const cushion = cv.year1_noi - cv.annual_debt_service;
          return [
            `Year-1 NOI:     ${formatCompactCurrency(cv.year1_noi)}`,
            `Debt service:   ${formatCompactCurrency(cv.annual_debt_service)}`,
            `─────────────────────────`,
            `Cash cushion:   ${formatCompactCurrency(cushion)}/yr above breakeven`,
            `Lender min:     ${dscrFloor.toFixed(2)}×`,
          ].join('\n');
        },
        () => {
          const noi = currentRun?.noi_year_one;
          const dscr = currentRun?.dscr_year_one;
          if (!noi || !dscr) return null;
          const ds = noi / dscr;
          return `Year-1 NOI: ${formatCompactCurrency(noi)}\nDebt service: ${formatCompactCurrency(ds)}\nCushion: ${formatCompactCurrency(noi - ds)}/yr\nLender min: ${dscrFloor.toFixed(2)}×`;
        },
      ),
    },
  ];

  const evidenceItems = [
    {
      key: 'purchase_price',
      category: 'Acquisition',
      label: 'Purchase price',
      value: formatEvidenceValue(formatCompactCurrency, persistedInputs.acquisition?.purchase_price),
      citation: getFieldCitation(fieldCitations, citationContext, 'purchase_price'),
    },
    {
      key: 'num_units',
      category: 'Property',
      label: 'Unit count',
      value: persistedInputs.project?.num_units ?? '—',
      citation: getFieldCitation(fieldCitations, citationContext, 'num_units'),
    },
    {
      key: 'rentable_sqft',
      category: 'Property',
      label: 'Rentable sqft',
      value: persistedInputs.project?.rentable_sqft?.toLocaleString?.() ?? '—',
      citation: getFieldCitation(fieldCitations, citationContext, 'rentable_sqft'),
    },
    {
      key: 'gross_potential_rent_annual',
      category: 'Revenue',
      label: 'Year 1 GPR',
      value: formatEvidenceValue(formatCompactCurrency, persistedInputs.operational?.gross_potential_rent_annual),
      citation: getFieldCitation(fieldCitations, citationContext, 'gross_potential_rent_annual'),
    },
    {
      key: 'avg_in_place_rent_per_unit_monthly',
      category: 'Revenue',
      label: 'Avg in-place rent / door',
      value: computedAvgInPlaceRent != null
        ? formatCurrency(computedAvgInPlaceRent)
        : formatEvidenceValue(formatCurrency, omStatedAvgRent),
      note: showAvgRentGap
        ? `OM states ${formatCurrency(omStatedAvgRent)} — unit mix implies ${formatCurrency(computedAvgInPlaceRent)}`
        : computedAvgInPlaceRent != null ? 'Weighted avg from unit mix' : null,
      citation: computedAvgInPlaceRent != null
        ? { doc_type: 'derived', is_derived: true, formula: null, entries: [] }
        : null,
    },
    {
      key: 'avg_market_rent_per_unit_monthly',
      category: 'Revenue',
      label: 'Avg market rent / door',
      value: formatEvidenceValue(formatCurrency, persistedInputs.operational?.avg_market_rent_per_unit_monthly),
      citation: getFieldCitation(fieldCitations, citationContext, 'avg_market_rent_per_unit_monthly'),
    },
    {
      key: 'vacancy_credit_loss_pct',
      category: 'Revenue',
      label: 'Year 1 vacancy loss',
      value: formatEvidenceValue(formatPercent, persistedInputs.operational?.vacancy_credit_loss_pct),
      citation: getFieldCitation(fieldCitations, citationContext, 'vacancy_credit_loss_pct'),
    },
    {
      key: 'expense_ratio_current',
      category: 'Expenses',
      label: 'Current expense ratio',
      value: formatEvidenceValue(formatPercent, persistedInputs.operational?.expense_ratio_current),
      citation: getFieldCitation(fieldCitations, citationContext, 'expense_ratio_current'),
    },
    {
      key: 'expense_ratio_year1',
      category: 'Expenses',
      label: 'Year 1 expense ratio',
      value: formatEvidenceValue(formatPercent, persistedInputs.operational?.expense_ratio_year1),
      citation: getFieldCitation(fieldCitations, citationContext, 'expense_ratio_year1'),
    },
    {
      key: 'expense_ratio_pro_forma',
      category: 'Expenses',
      label: 'Pro forma expense ratio',
      value: formatEvidenceValue(formatPercent, persistedInputs.operational?.expense_ratio_pro_forma),
      citation: getFieldCitation(fieldCitations, citationContext, 'expense_ratio_pro_forma'),
    },
    {
      key: 'property_tax_annual',
      category: 'Expenses',
      label: 'Year 1 property tax',
      value: formatEvidenceValue(formatCompactCurrency, persistedInputs.operational?.property_tax_annual),
      citation: getFieldCitation(fieldCitations, citationContext, 'property_tax_annual'),
    },
    {
      key: 'property_tax_growth_pct',
      category: 'Tax Support',
      label: 'Property tax growth',
      value: formatEvidenceValue(formatPercent, persistedInputs.operational?.property_tax_growth_pct),
      citation: getFieldCitation(fieldCitations, citationContext, 'property_tax_growth_pct'),
    },
    {
      key: 'property_tax_value_basis_amount',
      category: 'Tax Support',
      label: 'Tax value basis',
      value: formatEvidenceValue(formatCompactCurrency, persistedInputs.operational?.property_tax_value_basis_amount),
      citation: getFieldCitation(fieldCitations, citationContext, 'property_tax_value_basis_amount'),
    },
    {
      key: 'property_tax_assessed_value',
      category: 'Tax Support',
      label: 'Tax assessed value',
      value: formatEvidenceValue(formatCompactCurrency, persistedInputs.operational?.property_tax_assessed_value),
      citation: getFieldCitation(fieldCitations, citationContext, 'property_tax_assessed_value'),
    },
    {
      key: 'property_tax_assessment_ratio',
      category: 'Tax Support',
      label: 'Tax assessment ratio',
      value: formatEvidenceValue(formatPercent, persistedInputs.operational?.property_tax_assessment_ratio),
      citation: getFieldCitation(fieldCitations, citationContext, 'property_tax_assessment_ratio'),
    },
    {
      key: 'property_tax_millage_rate',
      category: 'Tax Support',
      label: 'Tax millage rate',
      value: persistedInputs.operational?.property_tax_millage_rate != null
        ? `${persistedInputs.operational.property_tax_millage_rate.toFixed(2)} mills` : '—',
      citation: getFieldCitation(fieldCitations, citationContext, 'property_tax_millage_rate'),
    },
    {
      key: 'property_tax_rate_per_assessed_dollar',
      category: 'Tax Support',
      label: 'Tax rate / assessed $',
      value: persistedInputs.operational?.property_tax_rate_per_assessed_dollar != null
        ? persistedInputs.operational.property_tax_rate_per_assessed_dollar.toFixed(5) : '—',
      citation: getFieldCitation(fieldCitations, citationContext, 'property_tax_rate_per_assessed_dollar'),
    },
    {
      key: 'interest_rate_pct',
      category: 'Financing / Exit',
      label: 'Interest rate',
      value: formatEvidenceValue(formatPercent, persistedInputs.financing?.interest_rate_pct),
      citation: getFieldCitation(fieldCitations, citationContext, 'interest_rate_pct'),
    },
    {
      key: 'market_cap_rate_purchase',
      category: 'Acquisition',
      label: 'Market cap rate purchase',
      value: formatEvidenceValue(formatPercent, persistedInputs.acquisition?.market_cap_rate_purchase),
      citation: getFieldCitation(fieldCitations, citationContext, 'market_cap_rate_purchase'),
    },
    {
      key: 'exit_cap_rate',
      category: 'Financing / Exit',
      label: 'Exit cap rate',
      value: formatEvidenceValue(formatPercent, persistedInputs.exit?.exit_cap_rate),
      citation: getFieldCitation(fieldCitations, citationContext, 'exit_cap_rate'),
    },
    {
      key: 'market_cap_rate_sale',
      category: 'Financing / Exit',
      label: 'Market cap rate sale',
      value: formatEvidenceValue(formatPercent, persistedInputs.exit?.market_cap_rate_sale),
      citation: getFieldCitation(fieldCitations, citationContext, 'market_cap_rate_sale'),
    },
  ].filter((item) => item.citation);

  // ── Render ────────────────────────────────────────────────────────────────

  if (!currentRun) {
    return (
      <AppLayout>
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
          <UnderwritingResultSkeleton />
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout
      lockViewport
      headerLeft={(
        <button
          onClick={() => navigate('/app/re/underwriting')}
          className="flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronLeft className="h-4 w-4" />
          All deals
        </button>
      )}
    >
      <ResizablePanelGroup
        direction="horizontal"
        className="h-full min-w-0"
      >
        <ResizablePanel id="uw-result-main" order={1} defaultSize={showSourcePanel ? 58 : 100} minSize={40}>
          <div className="h-full overflow-y-auto">
            <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6 sm:py-8">
              <div className="underwriting-shell page-enter">
                <div
                  className="uw-verdict-strip"
                  data-tone={verdictTone === 'success' ? 'success' : verdictTone === 'warning' ? 'warning' : verdictTone === 'danger' ? 'danger' : undefined}
                />
                <div className="p-4 sm:p-6">

                  {/* Top bar */}
                  <div className="underwriting-topbar -m-4 mb-4 sm:-m-6 sm:mb-6">
                    <div className="underwriting-topbar-row">
                      <div className="underwriting-topbar-main">
                        <WorkspaceMark />
                        <div className="underwriting-topbar-identity">
                          <p className="underwriting-kicker">Underwriting analysis</p>
                          <p className="underwriting-topbar-deal mt-0.5">{currentRun.name}</p>
                          <p className="underwriting-topbar-address mt-0.5">{address || 'Address not provided'}</p>
                        </div>
                      </div>
                      <div className="uw-mode-switch justify-self-center">
                        <button type="button" className="uw-mode-btn" onClick={() => navigate(`/app/re/underwriting/new?run_id=${runId}`)}>
                          Input
                        </button>
                        <button type="button" className="uw-mode-btn uw-mode-btn-active">Analysis</button>
                      </div>
                      <div className="underwriting-topbar-actions">
                        <UnderwritingStatusBadge tone={verdictTone}>{verdictLabel}</UnderwritingStatusBadge>
                        {currentRun.status ? (
                          <UnderwritingStatusBadge tone={currentRun.status === 'completed' ? 'success' : 'neutral'}>
                            {currentRun.status}
                          </UnderwritingStatusBadge>
                        ) : null}
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="underwriting-topbar-delete h-9 w-9 rounded-full text-destructive hover:bg-destructive/10 hover:text-destructive"
                              disabled={isDeleting}
                              title="Delete this analysis"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>Delete analysis?</AlertDialogTitle>
                              <AlertDialogDescription>
                                "{currentRun?.name || 'Untitled analysis'}" will be permanently deleted. This action cannot be undone.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Cancel</AlertDialogCancel>
                              <AlertDialogAction onClick={handleDelete} className="bg-destructive hover:bg-destructive/90" disabled={isDeleting}>
                                {isDeleting ? 'Deleting...' : 'Delete'}
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                        <div className="underwriting-memo-actions" aria-label="Credit memo actions">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => { setMemoPrefill(null); setMemoModalOpen(true); }}
                            disabled={!verdict}
                            className="underwriting-memo-primary"
                          >
                            <Sparkles className="h-4 w-4" />
                            Generate memo
                          </Button>
                          <MemoHistorySheet
                            runId={runId}
                            getToken={getToken}
                            refreshKey={memoRefreshKey}
                            dealName={currentRun.name}
                            open={memoHistoryOpen}
                            onOpenChange={setMemoHistoryOpen}
                            onRegenerate={handleRegenerate}
                          />
                        </div>
                      </div>
                    </div>
                  </div>

                  <TrustPanel
                    expanded={showTrustPanel}
                    onToggle={() => setShowTrustPanel(v => !v)}
                    verdictTone={verdictTone}
                    verdictLabel={verdictLabel}
                    revenueBasis={revenueBasis}
                    warningCount={prioritizedWarnings.length}
                    persistedInputs={persistedInputs}
                    artifact={artifact}
                    currentRentPerDoor={currentRentPerDoor}
                    currentExpenseRatio={currentExpenseRatio}
                    proFormaExpenseRatio={proFormaExpenseRatio}
                    expenseBasis={expenseBasis}
                    capitalStructure={capitalStructure}
                    omStatedNoi={omStatedNoi}
                    noiBridge={noiBridge}
                    sourceCitations={sourceCitations}
                    rentCompCoverage={rentCompCoverage}
                    currentRun={currentRun}
                    noiBridgeDeltaPct={noiBridgeDeltaPct}
                    noiBridgeAlert={noiBridgeAlert}
                    breakEvenOccupancyPct={breakEvenOccupancyPct}
                    prioritizedWarnings={prioritizedWarnings}
                  />

                  {/* Verdict hero banner */}
                  <div
                    className="underwriting-hero-banner"
                    data-tone={verdictTone === 'success' ? 'success' : verdictTone === 'warning' ? 'warning' : verdictTone === 'danger' ? 'danger' : undefined}
                  >
                    <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-3">
                          {verdictTone === 'success' ? <CheckCircle2 className="h-7 w-7 text-uw-success shrink-0" />
                            : verdictTone === 'warning' ? <AlertTriangle className="h-7 w-7 text-uw-risk shrink-0" />
                            : verdictTone === 'danger' ? <XCircle className="h-7 w-7 text-uw-danger shrink-0" />
                            : <Loader2 className="h-7 w-7 text-primary shrink-0" />}
                          <div>
                            <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">Lead verdict</p>
                            <p className="mt-0.5 font-display text-3xl font-semibold tracking-tight text-foreground leading-none">{verdictLabel}</p>
                          </div>
                        </div>
                        <div className="mt-3 flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
                          <MapPin className="h-3.5 w-3.5 shrink-0" />
                          <span>{address || 'Address not provided'}</span>
                        </div>
                        {leadSummary ? (
                          <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">{leadSummary}</p>
                        ) : null}
                        <div className="mt-5 grid max-w-3xl gap-2 sm:grid-cols-2 xl:grid-cols-3">
                          {decisionSnapshotRows.map((row) => (
                            <div key={row.label} className="rounded-xl border border-border/50 bg-background/45 px-3 py-2">
                              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">{row.label}</p>
                              <p className="mt-1 truncate text-sm font-semibold text-foreground">{row.value}</p>
                            </div>
                          ))}
                        </div>
                      </div>

                      {watchItems.length > 0 && (
                        <div className="flex flex-col gap-3 xl:items-end xl:min-w-[260px]">
                          <div className="underwriting-data-card w-full xl:max-w-sm">
                            <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
                              {criticalWarningCount > 0 ? 'Critical items' : 'Watch items'}
                            </p>
                            <div className="mt-2.5">
                              {leadWatchItems.map((item) => (
                                <div key={item.id} className="uw-watch-item">
                                  <span
                                    className="uw-watch-item-dot"
                                    style={{
                                      background: item.kind === 'failure' || item.severity === 'critical'
                                        ? 'hsl(var(--uw-danger))'
                                        : 'hsl(var(--uw-risk))',
                                    }}
                                  />
                                  <span className="min-w-0">{item.label}</span>
                                  {item.kind === 'failure' && item.gap != null ? (
                                    <span
                                      className="ml-auto shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold tabular-nums"
                                      style={{
                                        background: Math.abs(item.gap) > 0.01 ? 'hsl(var(--uw-danger) / 0.12)' : 'hsl(var(--uw-risk) / 0.15)',
                                        color: Math.abs(item.gap) > 0.01 ? 'hsl(var(--uw-danger))' : 'hsl(var(--uw-risk))',
                                      }}
                                    >
                                      {item.gap > 0 ? '+' : ''}
                                      {Math.abs(item.gap) < 0.1
                                        ? `${(item.gap * 10000).toFixed(0)} bps`
                                        : `${(item.gap * 100).toFixed(1)}%`}
                                    </span>
                                  ) : item.citations.length > 0 ? (
                                    <button
                                      type="button"
                                      className="ml-auto shrink-0 text-[9px] font-bold uppercase tracking-wider text-uw-citation hover:underline"
                                      onClick={() => handleOpenSource(item.citations[0])}
                                    >
                                      Source
                                    </button>
                                  ) : null}
                                </div>
                              ))}
                              {hiddenWatchCount > 0 ? (
                                <button
                                  type="button"
                                  onClick={() => setShowTrustPanel(true)}
                                  className="mt-2 text-xs font-semibold text-primary hover:underline"
                                >
                                  +{hiddenWatchCount} more in trust summary
                                </button>
                              ) : null}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  <ModelBasisPanel
                    revenueBasis={revenueBasis}
                    expenseBasis={expenseBasis}
                    noiBasis={{ modeledNoi, omStatedNoi, noiBridgeDeltaPct }}
                    isOmNoiMode={isOmNoiMode}
                    unitMixSource={unitMixSource}
                    rentCompCoverage={rentCompCoverage}
                  />

                  {/* Upside not in base case */}
                  {artifact.om_data?.below_market_annual_upside || artifact.om_data?.value_add_notes ? (
                    <div className="uw-upside-banner mt-4">
                      <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-uw-risk">Upside not in base case</p>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        {artifact.om_data?.below_market_annual_upside ? (
                          <div className="rounded-xl border border-border/50 bg-background/50 p-3">
                            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">Rent mark-to-market</p>
                            <p className="mt-2 text-sm leading-6 text-muted-foreground">
                              {artifact.om_data.below_market_tenant_pct
                                ? `${(artifact.om_data.below_market_tenant_pct * 100).toFixed(0)}% of tenants are below street rate. ` : ''}
                              Potential upside:{' '}
                              <span className="font-semibold text-foreground">{formatCompactCurrency(artifact.om_data.below_market_annual_upside)}/year</span>.
                              {' '}Not included in modeled returns.
                            </p>
                          </div>
                        ) : null}
                        {artifact.om_data?.value_add_notes ? (
                          <div className="rounded-xl border border-border/50 bg-background/50 p-3">
                            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">Conversion opportunity</p>
                            <p className="mt-2 text-sm leading-6 text-muted-foreground">{artifact.om_data.value_add_notes}</p>
                            <p className="mt-2 text-xs leading-5 text-muted-foreground">
                              Broker-stated upside only. Requires feasibility, capex, permitting, and demand review.
                            </p>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  ) : null}

                  {/* What-if scenario panel */}
                  {showScenario && (
                    <ScenarioPanel
                      baseScenario={baseScenario}
                      scenarioValues={scenarioValues}
                      onValueChange={handleScenarioChange}
                      onReset={resetScenario}
                      scenarioResult={scenarioResult}
                      isScenarioLoading={isScenarioLoading}
                      currentRun={currentRun}
                    />
                  )}

                  {/* Key returns metrics */}
                  <div className="mt-5">
                    <div className="flex items-center justify-between mb-3">
                      <div className="field-section-label">Key Returns</div>
                      <Button
                        variant={showScenario ? 'default' : 'outline'}
                        size="sm"
                        onClick={() => setShowScenario((v) => !v)}
                        className="gap-1.5 h-7 px-3 text-xs"
                      >
                        <SlidersHorizontal className="h-3.5 w-3.5" />
                        Scenario What-If
                      </Button>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                      {metrics.map((metric) => (
                        <UnderwritingMetricCard key={metric.label} {...metric} />
                      ))}
                    </div>
                  </div>

                  <div className="mt-5">
                    <MaxBidPanel
                      purchasePrice={purchasePrice}
                      currentVerdictLabel={verdictLabel}
                      currentVerdictTone={verdictTone}
                      currentNoi={currentRun?.noi_year_one}
                      criteria={persistedInputs.criteria}
                      getToken={getToken}
                      runId={runId}
                      runSensitivityAnalysis={runSensitivityAnalysis}
                      purchasePriceCitation={sourceCitations.purchase_price}
                      onOpenSource={handleOpenSource}
                    />
                  </div>
                  <div className="mt-5">
                    <MaxLoanPanel
                      runId={runId}
                      getToken={getToken}
                      persistedInputs={persistedInputs}
                    />
                  </div>

                  {/* Operating benchmarks */}
                  <div className="mt-4">
                    <div className="field-section-label mb-3">Operating Benchmarks</div>
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5">
                      <UnderwritingMetricCard
                        label="Avg Current Rent / Door"
                        value={formatCurrency(currentRentPerDoor != null ? Math.round(currentRentPerDoor) : null)}
                        detail="Rent reasonableness benchmark"
                        formula={buildTooltip('avg_current_rent_per_door',
                          (cv) => cv.gpr != null && cv.num_units != null ? `${formatCompactCurrency(cv.gpr)} ÷ ${cv.num_units} units ÷ 12` : null,
                          () => gpr != null && totalUnits ? `${formatCompactCurrency(gpr)} ÷ ${totalUnits} units ÷ 12` : null,
                          'Monthly in-place rent benchmark. Used for sanity checks and rent-position context; modeled revenue comes from GPR.',
                        )}
                      />
                      {marketRentPerDoor != null ? (
                        <UnderwritingMetricCard
                          label="Avg Market Rent / Door"
                          value={formatCurrency(Math.round(marketRentPerDoor))}
                          detail="Rent-position benchmark"
                          formula={buildTooltip('avg_market_rent_per_door',
                            (cv) => cv.market_rate != null ? `Market rate: ${formatCurrency(Math.round(cv.market_rate))}/month` : null,
                            () => `Market rate: ${formatCurrency(Math.round(marketRentPerDoor))}/month`,
                            'Monthly market-rate benchmark from the OM or rent roll. Used only for rent-position context; modeled revenue still comes from GPR.',
                          )}
                        />
                      ) : null}
                      {modelExpenseRatio != null ? (
                        <UnderwritingMetricCard
                          label="Model Expense Ratio"
                          value={formatPercent(modelExpenseRatio)}
                          detail={modelExpenseRatioDetail || 'Selected expense basis'}
                          tone={modelExpenseRatio < 0.3 ? 'warning' : 'default'}
                          formula={buildTooltip('expense_basis',
                            (cv) => {
                              const egi = expenseBasis?.modeled_egi ?? cv.year1_egi;
                              const lineItemOpex = expenseBasis?.modeled_total_expenses ?? cv.year1_line_item_opex;
                              const ratio = modelExpenseRatio ?? cv.ratio;
                              if (isLineItemExpenseBasis && lineItemOpex != null && egi != null) {
                                return `${formatCompactCurrency(lineItemOpex)} OpEx ÷ ${formatCompactCurrency(egi)} EGI = ${formatPercent(ratio ?? lineItemOpex / egi)}`;
                              }
                              if (ratio != null && egi != null) {
                                return `${formatPercent(ratio)} × ${formatCompactCurrency(egi)} EGI = ${formatCompactCurrency(ratio * egi)} OpEx`;
                              }
                              return null;
                            },
                            () => expenseBasis?.modeled_total_expenses != null && expenseBasis?.modeled_egi != null
                              ? `${formatCompactCurrency(expenseBasis.modeled_total_expenses)} ÷ ${formatCompactCurrency(expenseBasis.modeled_egi)}`
                              : null,
                            isLineItemExpenseBasis
                              ? 'Line items drive modeled expenses. This ratio is implied by OpEx ÷ EGI and shown as an operating benchmark.'
                              : 'The selected expense ratio drives modeled expenses because coherent line-item OpEx was unavailable.',
                          )}
                        />
                      ) : null}
                      <UnderwritingMetricCard
                        label="Break-Even Occupancy"
                        value={formatRatioPercent(breakEvenOccupancyPct)}
                        detail={breakEvenOccupancyDetail}
                        tone={
                          breakEvenOccupancyPct == null ? 'default'
                          : occupancy == null ? 'default'
                          : breakEvenOccupancyPct > occupancy ? 'danger'
                          : breakEvenOccupancyPct > occupancy - 0.1 ? 'warning'
                          : 'default'
                        }
                        formula={buildTooltip('break_even_occupancy',
                          (cv) => cv.debt_service != null && cv.fixed_opex != null && cv.gpr_adj != null
                            ? `(${formatCompactCurrency(cv.debt_service)} + ${formatCompactCurrency(cv.fixed_opex)} − ${formatCompactCurrency(cv.other_income_adj ?? 0)}) ÷ ${formatCompactCurrency(cv.gpr_adj)}`
                            : null,
                          () => {
                            const noi = currentRun?.noi_year_one;
                            const dscr = currentRun?.dscr_year_one;
                            if (!noi || !dscr || !gpr) return null;
                            const ds = noi / dscr;
                            return `Debt service: ${formatCompactCurrency(ds)} | GPR: ${formatCompactCurrency(gpr)}`;
                          },
                          'Minimum occupancy needed for Year-1 NOI to cover annual debt service. Lower is safer; compare it with supported physical or economic occupancy.',
                        )}
                      />
                      <UnderwritingMetricCard
                        label="Debt Yield"
                        value={debtYield != null ? `${(debtYield * 100).toFixed(1)}%` : null}
                        tone={
                          debtYield == null ? 'default'
                          : debtYield < 0.07 ? 'danger'
                          : debtYield < 0.08 ? 'warning'
                          : 'default'
                        }
                        detail={
                          debtYield == null ? null
                          : debtYield < 0.07 ? 'Below 7% agency floor'
                          : debtYield < 0.08 ? 'In lender watch zone'
                          : 'Above 8% threshold'
                        }
                        formula={buildTooltip('debt_yield',
                          (cv) => {
                            if (cv.year1_noi == null || cv.loan_amount == null) return null;
                            return [
                              `Year-1 NOI:   ${formatCompactCurrency(cv.year1_noi)}`,
                              `Loan amount:  ${formatCompactCurrency(cv.loan_amount)}`,
                              `─────────────────────────`,
                              `Watch: 8%  |  Hard stop: 7%`,
                            ].join('\n');
                          },
                          () => debtYield != null ? `Watch: 8%  |  Hard stop: 7%` : null,
                          'Debt Yield = Year-1 NOI ÷ Loan Amount. CMBS/agency lenders typically require ≥8%. Below 7% is a hard stop for most agency debt.',
                        )}
                      />
                    </div>
                  </div>

                  {/* Sections */}
                  <div className="mt-6 grid gap-5">
                    <ReturnsSection
                      show={showReturns}
                      onToggle={() => setShowReturns((v) => !v)}
                      projections={projections}
                      proformaData={proformaData}
                      incomeBasisMonths={artifact.income_basis_months}
                      capitalStructure={capitalStructure}
                      loanAmount={loanAmount}
                      purchasePrice={purchasePrice}
                      equityInvested={equityInvested}
                      equityPct={equityPct}
                      ltvPct={ltvPct}
                      equityRaiseTone={equityRaiseTone}
                      equityRaiseLabel={equityRaiseLabel}
                      currentRun={currentRun}
                      currentRentPerDoor={currentRentPerDoor}
                      marketRentPerDoor={marketRentPerDoor}
                      rentSpreadPerDoor={rentSpreadPerDoor}
                      occupancy={occupancy}
                      impliedCapRate={impliedCapRate}
                      breakEvenOccupancyPct={breakEvenOccupancyPct}
                      totalUnits={totalUnits}
                      sourceCitations={sourceCitations}
                      omStatedNoi={omStatedNoi}
                      noiBridge={noiBridge}
                      modeledNoi={modeledNoi}
                      noiBridgeDelta={noiBridgeDelta}
                      noiBridgeDeltaPct={noiBridgeDeltaPct}
                      noiBridgeAlert={noiBridgeAlert}
                      expenseBasisSource={expenseBasis?.source}
                      onOpenSource={handleOpenSource}
                    />

                    <OperationsSection
                      show={showOperations}
                      onToggle={() => setShowOperations((v) => !v)}
                      unitMix={unitMix}
                      unitMixSummary={unitMixSummary}
                      unitMixIsPartial={unitMixIsPartial}
                      propertyUnits={propertyUnits}
                      extractedUnits={extractedUnits}
                      unitMixCoveragePct={unitMixCoveragePct}
                      occupancy={occupancy}
                      currentExpenseRatio={currentExpenseRatio}
                      proFormaExpenseRatio={proFormaExpenseRatio}
                      propertyTaxAnnual={persistedInputs.operational?.property_tax_annual}
                      propertyTaxGrowthPct={persistedInputs.operational?.property_tax_growth_pct ?? artifact.om_data?.property_tax_growth_pct}
                      badDebtAnnual={persistedInputs.operational?.bad_debt_annual ?? artifact.t12_data?.summary?.bad_debt_annual}
                      correctionsCollectionsAnnual={persistedInputs.operational?.corrections_collections_annual ?? artifact.t12_data?.summary?.corrections_collections_annual}
                      purchasePrice={purchasePrice}
                      totalUnits={totalUnits}
                      rentableSqft={persistedInputs.project?.rentable_sqft}
                      operational={persistedInputs.operational}
                      expenseBasis={expenseBasis}
                      expenseBasisFormula={expenseBasisFormula}
                      sourceCitations={sourceCitations}
                      stressTests={stressTests}
                      rolloverRisk={rolloverRisk}
                      missingExpenseFields={artifact.t12_data?.summary?.missing_expense_fields || []}
                      onOpenSource={handleOpenSource}
                    />

                    <EvidenceSection
                      show={showEvidence}
                      onToggle={() => setShowEvidence((v) => !v)}
                      evidenceItems={evidenceItems}
                      onOpenSource={handleOpenSource}
                    />

                    <MarketSection
                      show={showMarket}
                      onToggle={() => setShowMarket((v) => !v)}
                      address={address}
                      mapUrl={mapUrl}
                      nearbyStorageCount1Mi={marketData.nearby_storage_count_1mi}
                      nearbyStorageCount3Mi={marketData.nearby_storage_count_3mi}
                      nearbyStorageCount5Mi={marketData.nearby_storage_count_5mi}
                      demographics={demographics}
                      impliedCapRate={impliedCapRate}
                      purchasePrice={purchasePrice}
                      capRateSubmarket={capRateSubmarket}
                      capRatePurchase={capRatePurchase}
                      capRateSale={capRateSale}
                      bpsDelta={bpsDelta}
                      capRateSpreadBps={capRateSpreadBps}
                      rentPositionAnalysis={rentPositionAnalysis}
                      rentComps={rentComps}
                      rentCompCoverage={rentCompCoverage}
                      unknownClimateCompCount={artifact.unknown_climate_comp_count ?? 0}
                    />

                    <DiscrepanciesSection
                      discrepancies={discrepancies}
                      discrepancySupportByField={discrepancySupportByField}
                      onOpenSource={handleOpenSource}
                    />
                  </div>

                </div>
              </div>
            </div>
          </div>
        </ResizablePanel>
        {showSourcePanel ? <ResizableHandle withHandle /> : null}
        {showSourcePanel ? (
          <ResizablePanel id="uw-result-source" order={2} defaultSize={42} minSize={28}>
            <SourceDocumentPanel citation={activeCitation} isOpen={showSourcePanel} onClose={() => { setShowSourcePanel(false); setActiveCitation(null); }} />
          </ResizablePanel>
        ) : null}
      </ResizablePanelGroup>
      <CreditMemoModal
        open={memoModalOpen}
        onClose={() => setMemoModalOpen(false)}
        runId={runId}
        getToken={getToken}
        persistedInputs={persistedInputs}
        currentUser={currentUser}
        prefill={memoPrefill}
        onSubmitted={handleMemoSubmitted}
      />
      <CreditMemoProgress
        open={Boolean(memoProgress)}
        onClose={() => setMemoProgress(null)}
        jobId={memoProgress?.jobId}
        memoId={memoProgress?.memoId}
        getToken={getToken}
      />
    </AppLayout>
  );
}
