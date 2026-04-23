/**
 * Deal Dashboard
 * Decision-oriented results view for underwriting output.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  Download,
  Edit2,
  Loader2,
  MapPin,
  RotateCcw,
  SlidersHorizontal,
  TrendingUp,
  Warehouse,
  XCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from '@/components/ui/resizable';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import AppLayout from '../../../components/layout/AppLayout';
import { useAppAuth } from '../../../hooks/useAppAuth';
import { useUnderwriting, useUnderwritingActions } from '../../../store';
import { recalculateScenario, runSensitivityAnalysis } from '../../../api/re-underwriting';
import {
  RolloverRiskPanel,
  SourceDocumentPanel,
  StressTestTable,
  UnderwritingMetricCard,
  UnderwritingSection,
  UnderwritingStatusBadge,
} from '../components/underwriting';

function formatCurrency(value) {
  if (value == null) return '—';
  return `$${value.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

function formatCurrencyPrecise(value) {
  if (value == null) return '—';
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatPercent(value) {
  if (value == null) return '—';
  return `${(value > 1 ? value : value * 100).toFixed(1)}%`;
}

function formatRatioPercent(value) {
  if (value == null) return '—';
  return `${(value * 100).toFixed(0)}%`;
}

function formatMultiple(value) {
  if (value == null) return '—';
  return `${value.toFixed(2)}×`;
}

function formatCompactCurrency(value) {
  if (value == null) return '—';
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}

function pickUnitMix(artifact, persistedInputs) {
  const candidates = [
    artifact.rent_roll_data?.unit_mix,
    artifact.unit_mix,
    persistedInputs.unit_mix,
    artifact.om_data?.unit_mix,
  ];

  for (const candidate of candidates) {
    if (Array.isArray(candidate) && candidate.length > 0) {
      return candidate;
    }
  }

  return [];
}

function buildDerivedMixedRevenueWarning(unitMix) {
  if (!Array.isArray(unitMix) || unitMix.length === 0) {
    return null;
  }

  const nonStorageRows = unitMix.filter((row) => {
    const section = row?.section || '';
    const unitType = row?.unit_type || '';
    const label = `${section} ${unitType}`.trim().toLowerCase();
    return ['parking', 'residential', 'apartment', 'office'].some((keyword) => label.includes(keyword));
  });

  if (nonStorageRows.length === 0) {
    return null;
  }

  const nonStorageUnits = nonStorageRows.reduce((sum, row) => sum + (row?.num_units || 0), 0);
  const totalUnits = unitMix.reduce((sum, row) => sum + (row?.num_units || 0), 0);
  const detail = nonStorageUnits > 0 && totalUnits > 0
    ? `${nonStorageUnits} of ${totalUnits} units/spaces appear to be parking or residential`
    : 'parking or residential rows appear in the extracted unit mix';

  return {
    key: 'mixed_revenue_unit_mix',
    message: `Mixed revenue detected: ${detail}. The current underwriting model still applies blended self-storage assumptions, so per-door metrics and growth interpretations should be reviewed manually.`,
  };
}

function parseCitationPage(citationToken) {
  if (!citationToken) return null;
  const match = String(citationToken).match(/:p(\d+)\]/i);
  if (!match) return null;
  const page = Number.parseInt(match[1], 10);
  return Number.isFinite(page) && page > 0 ? page : null;
}

function normalizeCitation(fieldCitation, citationContext, citationToken) {
  if (!citationToken) return null;
  const contextEntry = citationContext?.[citationToken] || null;
  return {
    ...fieldCitation,
    citation: citationToken,
    page: contextEntry?.page ?? parseCitationPage(citationToken),
    document_id: contextEntry?.document_id ?? fieldCitation?.document_id,
    filename: contextEntry?.filename ?? fieldCitation?.filename,
    bbox: contextEntry?.bbox ?? fieldCitation?.bbox ?? null,
  };
}

function getFieldCitation(fieldCitations, citationContext, fieldKey) {
  if (!fieldCitations) return null;
  const rawCitation = fieldCitations[fieldKey]
    ?? fieldCitations[`om.${fieldKey}`]
    ?? fieldCitations[`t12.${fieldKey}`]
    ?? fieldCitations[`rent_roll.${fieldKey}`]
    ?? null;

  if (!rawCitation || rawCitation.is_default) {
    return null;
  }

  return {
    ...rawCitation,
    entries: (rawCitation.citations || [])
      .map((citationToken) => normalizeCitation(rawCitation, citationContext, citationToken))
      .filter(Boolean),
  };
}

function formatEvidenceValue(formatter, value) {
  return value == null ? '—' : formatter(value);
}

function flattenCitationEntries(citations) {
  const uniqueEntries = new Map();

  (citations || []).filter(Boolean).forEach((citation) => {
    const docTypeLabel = DOC_TYPE_LABELS[citation.doc_type] || citation.doc_type || 'Document';
    (citation.entries || []).forEach((entry, index) => {
      const id = `${citation.doc_type || 'document'}-${entry.citation || entry.page || index}`;
      if (!uniqueEntries.has(id)) {
        uniqueEntries.set(id, {
          id,
          label: entry.page ? `${docTypeLabel} p${entry.page}` : `Open ${docTypeLabel}`,
          title: citation.source_text || entry.filename || docTypeLabel,
          entry,
        });
      }
    });
  });

  return [...uniqueEntries.values()];
}

function SourceSupportActions({ citations, onOpenSource, title = 'Source support' }) {
  const entries = flattenCitationEntries(citations).slice(0, 3);
  if (entries.length === 0) return null;

  return (
    <div className="mt-4 border-t border-border/60 pt-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{title}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {entries.map(({ id, label, title: buttonTitle, entry }) => (
          <Button
            key={id}
            type="button"
            variant="outline"
            size="sm"
            className="h-8 rounded-full px-3 text-xs"
            title={buttonTitle}
            onClick={() => onOpenSource(entry)}
          >
            {label}
          </Button>
        ))}
      </div>
    </div>
  );
}

const DOC_TYPE_LABELS = {
  om: 'Offering Memo',
  rent_roll: 'Rent Roll',
  t12: 'T-12',
};

function OccupancyBadge({ pct }) {
  if (pct == null) return <span className="text-sm text-muted-foreground">—</span>;
  const pctValue = pct > 1 ? pct : pct * 100;
  const tone = pctValue >= 85 ? 'success' : pctValue >= 70 ? 'warning' : 'danger';
  return <UnderwritingStatusBadge tone={tone}>{pctValue.toFixed(0)}% occupied</UnderwritingStatusBadge>;
}

function KeyValueList({ rows }) {
  return (
    <div className="space-y-3">
      {rows.map((row) => (
        <div key={row.label} className="underwriting-kv-row">
          <div className="min-w-0">
            <p className="underwriting-kv-label">{row.label}</p>
            {row.help ? <p className="mt-1 text-xs leading-5 text-muted-foreground">{row.help}</p> : null}
          </div>
          <div className="underwriting-kv-value">{row.value}</div>
        </div>
      ))}
    </div>
  );
}

function getUnitTypeBadge(row) {
  const label = `${row.section || ''} ${row.unit_type || ''}`.toLowerCase();
  if (label.includes('parking')) return <UnderwritingStatusBadge tone="warning">Parking</UnderwritingStatusBadge>;
  if (label.includes('residential')) return <UnderwritingStatusBadge tone="neutral">Residential</UnderwritingStatusBadge>;
  // Check NC before CC — "non-climate" contains "climate"
  if (label.includes('non-climate') || label.includes('non climate')) {
    return <UnderwritingStatusBadge tone="neutral">NC</UnderwritingStatusBadge>;
  }
  if (label.includes('climate')) return <UnderwritingStatusBadge tone="active">CC</UnderwritingStatusBadge>;
  return <UnderwritingStatusBadge tone="neutral">NC</UnderwritingStatusBadge>;
}

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
  const { getToken } = useAppAuth();
  const { currentRun } = useUnderwriting();
  const { loadRun } = useUnderwritingActions();

  const [sensitivityPoints, setSensitivityPoints] = useState([]);
  const [sensitivityPrice, setSensitivityPrice] = useState(null);
  const [isSensitivityLoading, setIsSensitivityLoading] = useState(false);
  const [showSourcePanel, setShowSourcePanel] = useState(false);
  const [activeCitation, setActiveCitation] = useState(null);
  const [showScenario, setShowScenario] = useState(false);
  const [showEvidence, setShowEvidence] = useState(false);
  const [showReturns, setShowReturns] = useState(true);
  const [showOperations, setShowOperations] = useState(false);
  const [showMarket, setShowMarket] = useState(false);
  const [showOtherOpex, setShowOtherOpex] = useState(false);
  // Scenario override values stored as display units: rates as %, price as $
  const [scenarioValues, setScenarioValues] = useState({});
  const [scenarioResult, setScenarioResult] = useState(null);
  const [isScenarioLoading, setIsScenarioLoading] = useState(false);
  const scenarioDebounceRef = useRef(null);

  useEffect(() => {
    if (runId) loadRun(getToken, runId);
  }, [getToken, loadRun, runId]);

  const handleOpenSource = (citation) => {
    setActiveCitation(citation);
    setShowSourcePanel(true);
  };

  const closeSourcePanel = () => {
    setShowSourcePanel(false);
    setActiveCitation(null);
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

  const artifact = currentRun?.result_artifact || {};
  const persistedInputs = currentRun?.inputs || {};
  const verdict = artifact.verdict;
  const verdictStatus = verdict?.status;
  const verdictTone = verdictStatus === 'worth_pursuing'
    ? 'success'
    : verdictStatus === 'needs_review'
      ? 'warning'
      : verdictStatus
        ? 'danger'
        : 'neutral';
  const verdictLabel = verdictStatus === 'worth_pursuing'
    ? 'Worth Pursuing'
    : verdictStatus === 'needs_review'
      ? 'Needs Review'
      : verdictStatus
        ? 'Below Standards'
        : 'In Review';

  const projections = artifact.projections || [];
  const stressTests = artifact.stress_tests || [];
  const rolloverRisk = artifact.rollover_risk;
  const unitMix = pickUnitMix(artifact, persistedInputs);
  const demographics = artifact.demographics || (persistedInputs.project?.population_3mi != null || persistedInputs.project?.avg_household_income_3mi != null || persistedInputs.project?.storage_sqft_per_capita_3mi != null
    ? {
        population: persistedInputs.project?.population_3mi,
        avg_household_income: persistedInputs.project?.avg_household_income_3mi,
        sqft_per_capita: persistedInputs.project?.storage_sqft_per_capita_3mi,
      }
    : null);
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
  const storedVerdictWarnings = verdict?.warnings || [];
  const derivedMixedRevenueWarning = buildDerivedMixedRevenueWarning(unitMix);
  const verdictWarnings = derivedMixedRevenueWarning && !storedVerdictWarnings.some((warning) => warning.key === derivedMixedRevenueWarning.key)
    ? [...storedVerdictWarnings, derivedMixedRevenueWarning]
    : storedVerdictWarnings;
  const sourceCitations = {
    purchase_price: getFieldCitation(fieldCitations, citationContext, 'purchase_price'),
    num_units: getFieldCitation(fieldCitations, citationContext, 'num_units'),
    rentable_sqft: getFieldCitation(fieldCitations, citationContext, 'rentable_sqft'),
    gross_potential_rent_annual: getFieldCitation(fieldCitations, citationContext, 'gross_potential_rent_annual'),
    avg_in_place_rent_per_unit_monthly: getFieldCitation(fieldCitations, citationContext, 'avg_in_place_rent_per_unit_monthly'),
    avg_market_rent_per_unit_monthly: getFieldCitation(fieldCitations, citationContext, 'avg_market_rent_per_unit_monthly'),
    vacancy_credit_loss_pct: getFieldCitation(fieldCitations, citationContext, 'vacancy_credit_loss_pct'),
    expense_ratio_current: getFieldCitation(fieldCitations, citationContext, 'expense_ratio_current'),
    expense_ratio_pro_forma: getFieldCitation(fieldCitations, citationContext, 'expense_ratio_pro_forma'),
    property_tax_annual: getFieldCitation(fieldCitations, citationContext, 'property_tax_annual'),
    property_tax_growth_pct: getFieldCitation(fieldCitations, citationContext, 'property_tax_growth_pct'),
    mil_rate: getFieldCitation(fieldCitations, citationContext, 'mil_rate'),
    bad_debt_annual: getFieldCitation(fieldCitations, citationContext, 'bad_debt_annual'),
    corrections_collections_annual: getFieldCitation(fieldCitations, citationContext, 'corrections_collections_annual'),
    interest_rate_pct: getFieldCitation(fieldCitations, citationContext, 'interest_rate_pct'),
    exit_cap_rate: getFieldCitation(fieldCitations, citationContext, 'exit_cap_rate'),
    market_cap_rate_purchase: getFieldCitation(fieldCitations, citationContext, 'market_cap_rate_purchase'),
    market_cap_rate_sale: getFieldCitation(fieldCitations, citationContext, 'market_cap_rate_sale'),
    mgmt_fee_pct: getFieldCitation(fieldCitations, citationContext, 'mgmt_fee_pct'),
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
    unit_mix: [sourceCitations.num_units, sourceCitations.rentable_sqft],
  };

  const verdictRationale = verdict?.rationale
    ? (derivedMixedRevenueWarning && !verdict.rationale.includes('Mixed revenue detected:')
      ? `${verdict.rationale} Warning: ${derivedMixedRevenueWarning.message}`
      : verdict.rationale)
    : derivedMixedRevenueWarning?.message || null;
  const prioritizedWarnings = [
    ...verdictWarnings.filter((warning) => warning.severity === 'critical'),
    ...verdictWarnings.filter((warning) => warning.severity !== 'critical'),
  ];
  const criticalWarningCount = prioritizedWarnings.filter((warning) => warning.severity === 'critical').length;
  const watchItems = [
    ...(verdict?.failures || []).slice(0, 3).map((failure) => ({
      id: `failure-${failure.metric}`,
      kind: 'failure',
      label: failure.metric.replaceAll('_', ' '),
      citations: verdictFailureSupportByMetric[failure.metric] || [],
    })),
    ...prioritizedWarnings.map((warning) => ({
      id: `warning-${warning.key}`,
      kind: 'warning',
      severity: warning.severity,
      label: warning.message,
      citations: [],
    })),
  ].slice(0, Math.max(criticalWarningCount + 3, 3));

  const failedSet = new Set((verdict?.failures || []).map((failure) => failure.metric));
  const metrics = [
    {
      label: 'IRR',
      value: formatPercent(currentRun?.irr),
      tone: failedSet.has('irr') ? 'danger' : verdictStatus === 'worth_pursuing' ? 'success' : 'default',
      detail: failedSet.has('irr') ? 'Below target threshold' : 'Projected internal rate of return',
      formula: 'Discount rate that makes NPV of all cash flows (including exit proceeds) equal zero over the hold period.',
    },
    {
      label: 'Cash-on-Cash',
      value: formatPercent(currentRun?.cash_on_cash),
      tone: failedSet.has('cash_on_cash') ? 'warning' : 'default',
      detail: 'Year-one cash yield',
      formula: 'Year 1 cash flow after debt service ÷ total equity invested.',
    },
    {
      label: 'Equity Multiple',
      value: formatMultiple(currentRun?.equity_multiple),
      tone: failedSet.has('equity_multiple') ? 'warning' : 'default',
      detail: 'Total return multiple',
      formula: 'Total cash received (distributions + exit proceeds) ÷ total equity invested.',
    },
    {
      label: 'DSCR Year 1',
      value: formatMultiple(currentRun?.dscr_year_one),
      tone: currentRun?.dscr_year_one != null && currentRun.dscr_year_one < 1.25 ? 'warning' : 'default',
      detail: currentRun?.dscr_year_one != null && currentRun.dscr_year_one < 1.25 ? 'Below 1.25× minimum' : 'Debt coverage cushion',
      formula: 'Year 1 NOI ÷ annual debt service. Below 1.25× is the typical lender minimum.',
    },
  ];

  const capitalStructure = artifact.capital_structure || {};
  const purchasePrice = capitalStructure.purchase_price || 0;
  const loanAmount = capitalStructure.loan_amount || 0;

  // Scenario base values (display units: rates as %, price as $)
  const baseScenario = {
    exit_cap_rate: persistedInputs.exit?.exit_cap_rate != null ? persistedInputs.exit.exit_cap_rate * 100 : null,
    vacancy_credit_loss_pct: persistedInputs.operational?.vacancy_credit_loss_pct != null ? persistedInputs.operational.vacancy_credit_loss_pct * 100 : null,
    rent_growth_pct: persistedInputs.operational?.rent_growth_pct != null ? persistedInputs.operational.rent_growth_pct * 100 : null,
    interest_rate_pct: persistedInputs.financing?.interest_rate_pct != null ? persistedInputs.financing.interest_rate_pct * 100 : null,
    purchase_price: persistedInputs.acquisition?.purchase_price || purchasePrice || null,
  };
  const equityInvested = capitalStructure.total_equity_invested || Math.max(purchasePrice - loanAmount, 0);
  const equityPct = purchasePrice > 0 ? equityInvested / purchasePrice : 0;
  const ltvPct = purchasePrice > 0 ? loanAmount / purchasePrice : 0;
  const equityRaiseTone = equityPct >= 0.5 ? 'warning' : equityPct >= 0.4 ? 'active' : 'neutral';
  const equityRaiseLabel = equityPct >= 0.5
    ? 'Large equity raise'
    : equityPct >= 0.4
      ? 'Meaningful equity raise'
      : 'Moderate equity raise';

  const totalUnits = artifact.rent_roll_data?.summary?.total_units || persistedInputs.project?.num_units;
  const gpr = persistedInputs.operational?.gross_potential_rent_annual;
  const derivedCurrentRentPerDoor = totalUnits && gpr ? gpr / totalUnits / 12 : null;
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
  const currentExpenseRatio = persistedInputs.operational?.expense_ratio_current
    ?? artifact.t12_data?.summary?.expense_ratio_actual
    ?? t12OpexRatio;
  const proFormaExpenseRatio = persistedInputs.operational?.expense_ratio_pro_forma
    ?? artifact.om_data?.expense_ratio_pro_forma
    ?? omOpexPct;
  const propertyTaxAnnual = persistedInputs.operational?.property_tax_annual;
  const propertyTaxGrowthPct = persistedInputs.operational?.property_tax_growth_pct
    ?? artifact.om_data?.property_tax_growth_pct;
  const milRate = persistedInputs.operational?.mil_rate ?? artifact.om_data?.mil_rate;
  const badDebtAnnual = persistedInputs.operational?.bad_debt_annual
    ?? artifact.t12_data?.summary?.bad_debt_annual;
  const correctionsCollectionsAnnual = persistedInputs.operational?.corrections_collections_annual
    ?? artifact.t12_data?.summary?.corrections_collections_annual;
  const missingExpenseFields = artifact.t12_data?.summary?.missing_expense_fields || [];
  const nearbyStorageCount1Mi = marketData.nearby_storage_count_1mi;
  const nearbyStorageCount3Mi = marketData.nearby_storage_count_3mi;
  const nearbyStorageCount5Mi = marketData.nearby_storage_count_5mi;
  const rentSpreadPerDoor = marketRentPerDoor != null && currentRentPerDoor != null
    ? marketRentPerDoor - currentRentPerDoor
    : null;

  const address = currentRun?.address || '';
  const mapsKey = import.meta.env.VITE_GOOGLE_MAPS_KEY;
  const mapUrl = mapsKey && address
    ? `https://maps.googleapis.com/maps/api/staticmap?center=${encodeURIComponent(address)}&zoom=13&size=500x260&markers=color:red%7C${encodeURIComponent(address)}&key=${mapsKey}`
    : null;

  const capRateSubmarket = marketData.submarket_avg_cap_rate;
  const capRatePurchase = persistedInputs.acquisition?.market_cap_rate_purchase || artifact.om_data?.market_cap_rate_purchase || marketData.market_cap_rate_purchase || impliedCapRate;
  const capRateSale = persistedInputs.exit?.market_cap_rate_sale || artifact.om_data?.market_cap_rate_sale || marketData.market_cap_rate_sale;
  const breakEvenOccupancyPct = artifact.break_even_occupancy_pct;
  const rentPositionAnalysis = artifact.rent_position_analysis || [];
  const omStatedNoi = artifact.om_data?.noi_year_one_stated
    ?? artifact.om_data?.noi_projected
    ?? artifact.om_data?.noi_current_stated
    ?? null;
  const modeledNoi = currentRun?.noi_year_one ?? artifact.noi_year_one ?? null;
  const noiBridgeDelta = omStatedNoi != null && modeledNoi != null ? modeledNoi - omStatedNoi : null;
  const noiBridgeDeltaPct = omStatedNoi ? noiBridgeDelta / omStatedNoi : null;
  const noiBridgeAlert = noiBridgeDeltaPct != null && Math.abs(noiBridgeDeltaPct) > 0.05;
  const bpsDelta = capRateSubmarket && impliedCapRate
    ? Math.round((impliedCapRate - capRateSubmarket) * 10000)
    : null;

  const proformaData = projections.slice(0, 5).map((point) => ({
    year: `Y${point.year}`,
    NOI: Math.round(point.noi),
    CFADS: Math.round(point.cash_flow),
  }));

  const basePurchasePrice = purchasePrice || 5_000_000;
  const minPrice = Math.round(basePurchasePrice * 0.7);
  const maxPrice = Math.round(basePurchasePrice * 1.3);

  const evidenceItems = [
    {
      key: 'purchase_price',
      label: 'Purchase price',
      value: formatEvidenceValue(formatCompactCurrency, persistedInputs.acquisition?.purchase_price),
      citation: getFieldCitation(fieldCitations, citationContext, 'purchase_price'),
    },
    {
      key: 'num_units',
      label: 'Unit count',
      value: persistedInputs.project?.num_units ?? '—',
      citation: getFieldCitation(fieldCitations, citationContext, 'num_units'),
    },
    {
      key: 'rentable_sqft',
      label: 'Rentable sqft',
      value: persistedInputs.project?.rentable_sqft?.toLocaleString?.() ?? '—',
      citation: getFieldCitation(fieldCitations, citationContext, 'rentable_sqft'),
    },
    {
      key: 'gross_potential_rent_annual',
      label: 'Gross potential rent',
      value: formatEvidenceValue(formatCompactCurrency, persistedInputs.operational?.gross_potential_rent_annual),
      citation: getFieldCitation(fieldCitations, citationContext, 'gross_potential_rent_annual'),
    },
    {
      key: 'avg_in_place_rent_per_unit_monthly',
      label: 'Avg current rent / door',
      value: formatEvidenceValue(formatCurrency, persistedInputs.operational?.avg_in_place_rent_per_unit_monthly),
      citation: getFieldCitation(fieldCitations, citationContext, 'avg_in_place_rent_per_unit_monthly'),
    },
    {
      key: 'avg_market_rent_per_unit_monthly',
      label: 'Avg market rent / door',
      value: formatEvidenceValue(formatCurrency, persistedInputs.operational?.avg_market_rent_per_unit_monthly),
      citation: getFieldCitation(fieldCitations, citationContext, 'avg_market_rent_per_unit_monthly'),
    },
    {
      key: 'vacancy_credit_loss_pct',
      label: 'Vacancy loss',
      value: formatEvidenceValue(formatPercent, persistedInputs.operational?.vacancy_credit_loss_pct),
      citation: getFieldCitation(fieldCitations, citationContext, 'vacancy_credit_loss_pct'),
    },
    {
      key: 'expense_ratio_current',
      label: 'Current expense ratio',
      value: formatEvidenceValue(formatPercent, persistedInputs.operational?.expense_ratio_current),
      citation: getFieldCitation(fieldCitations, citationContext, 'expense_ratio_current'),
    },
    {
      key: 'expense_ratio_pro_forma',
      label: 'Pro forma expense ratio',
      value: formatEvidenceValue(formatPercent, persistedInputs.operational?.expense_ratio_pro_forma),
      citation: getFieldCitation(fieldCitations, citationContext, 'expense_ratio_pro_forma'),
    },
    {
      key: 'property_tax_annual',
      label: 'Property tax',
      value: formatEvidenceValue(formatCompactCurrency, persistedInputs.operational?.property_tax_annual),
      citation: getFieldCitation(fieldCitations, citationContext, 'property_tax_annual'),
    },
    {
      key: 'property_tax_growth_pct',
      label: 'Property tax growth',
      value: formatEvidenceValue(formatPercent, persistedInputs.operational?.property_tax_growth_pct),
      citation: getFieldCitation(fieldCitations, citationContext, 'property_tax_growth_pct'),
    },
    {
      key: 'mil_rate',
      label: 'Mil rate',
      value: persistedInputs.operational?.mil_rate != null ? `${persistedInputs.operational.mil_rate.toFixed(1)} mills` : '—',
      citation: getFieldCitation(fieldCitations, citationContext, 'mil_rate'),
    },
    {
      key: 'interest_rate_pct',
      label: 'Interest rate',
      value: formatEvidenceValue(formatPercent, persistedInputs.financing?.interest_rate_pct),
      citation: getFieldCitation(fieldCitations, citationContext, 'interest_rate_pct'),
    },
    {
      key: 'market_cap_rate_purchase',
      label: 'Market cap rate purchase',
      value: formatEvidenceValue(formatPercent, persistedInputs.acquisition?.market_cap_rate_purchase),
      citation: getFieldCitation(fieldCitations, citationContext, 'market_cap_rate_purchase'),
    },
    {
      key: 'exit_cap_rate',
      label: 'Exit cap rate',
      value: formatEvidenceValue(formatPercent, persistedInputs.exit?.exit_cap_rate),
      citation: getFieldCitation(fieldCitations, citationContext, 'exit_cap_rate'),
    },
    {
      key: 'market_cap_rate_sale',
      label: 'Market cap rate sale',
      value: formatEvidenceValue(formatPercent, persistedInputs.exit?.market_cap_rate_sale),
      citation: getFieldCitation(fieldCitations, citationContext, 'market_cap_rate_sale'),
    },
  ].filter((item) => item.citation);

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
  }, [getToken, maxPrice, minPrice, runId, sensitivityPrice]);

  if (!currentRun) {
    return (
      <AppLayout>
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
          <div className="underwriting-shell page-enter p-5 sm:p-6">
            <Skeleton className="h-10 w-72" />
            <Skeleton className="mt-3 h-5 w-96" />
            <div className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {[...Array(4)].map((_, index) => (
                <Skeleton key={index} className="h-32 rounded-3xl" />
              ))}
            </div>
            <div className="mt-6 grid gap-4 xl:grid-cols-[1.7fr,1fr]">
              <Skeleton className="h-80 rounded-3xl" />
              <Skeleton className="h-80 rounded-3xl" />
            </div>
          </div>
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
        key={showSourcePanel ? 'uw-result-split-open' : 'uw-result-split-closed'}
        direction="horizontal"
        className="h-full min-w-0"
      >
        <ResizablePanel id="uw-result-main" order={1} defaultSize={showSourcePanel ? 58 : 100} minSize={40}>
          <div className="h-full overflow-y-auto">
            <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6 sm:py-8">
              <div className="underwriting-shell page-enter">
                {/* Verdict accent strip — instant visual signal at top of shell */}
                <div
                  className="uw-verdict-strip"
                  data-tone={verdictTone === 'success' ? 'success' : verdictTone === 'warning' ? 'warning' : verdictTone === 'danger' ? 'danger' : undefined}
                />
                <div className="p-4 sm:p-6">
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
                      <button
                        type="button"
                        className="uw-mode-btn"
                        onClick={() => navigate(`/app/re/underwriting/new?run_id=${runId}`)}
                      >
                        Input
                      </button>
                      <button type="button" className="uw-mode-btn uw-mode-btn-active">
                        Analysis
                      </button>
                    </div>

                    <div className="underwriting-topbar-actions">
                      <UnderwritingStatusBadge tone={verdictTone}>{verdictLabel}</UnderwritingStatusBadge>
                      {currentRun.status ? (
                        <UnderwritingStatusBadge tone={currentRun.status === 'completed' ? 'success' : 'neutral'}>
                          {currentRun.status}
                        </UnderwritingStatusBadge>
                      ) : null}
                      <Button
                        variant="outline"
                        size="sm"
                        disabled
                        title="Underwriting export is not available yet."
                      >
                        <Download className="mr-1.5 h-4 w-4" />
                        Export
                      </Button>
                    </div>
                  </div>
                </div>

                <div
                  className="underwriting-hero-banner"
                  data-tone={verdictTone === 'success' ? 'success' : verdictTone === 'warning' ? 'warning' : verdictTone === 'danger' ? 'danger' : undefined}
                >
                  <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-3">
                        {verdictTone === 'success' ? (
                          <CheckCircle2 className="h-7 w-7 text-uw-success shrink-0" />
                        ) : verdictTone === 'warning' ? (
                          <AlertTriangle className="h-7 w-7 text-uw-risk shrink-0" />
                        ) : verdictTone === 'danger' ? (
                          <XCircle className="h-7 w-7 text-uw-danger shrink-0" />
                        ) : (
                          <Loader2 className="h-7 w-7 text-primary shrink-0" />
                        )}
                        <div>
                          <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">Lead verdict</p>
                          <p className="mt-0.5 font-display text-3xl font-semibold tracking-tight text-foreground leading-none">{verdictLabel}</p>
                        </div>
                      </div>
                      <div className="mt-3 flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
                        <MapPin className="h-3.5 w-3.5 shrink-0" />
                        <span>{address || 'Address not provided'}</span>
                      </div>
                      {verdictRationale ? (
                        <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">{verdictRationale}</p>
                      ) : null}
                    </div>

                    <div className="flex flex-col gap-3 xl:items-end xl:min-w-[260px]">
                      {watchItems.length > 0 ? (
                        <div className="underwriting-data-card w-full xl:max-w-sm">
                          <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
                            {criticalWarningCount > 0 ? 'Critical items' : 'Watch items'}
                          </p>
                          <div className="mt-2.5">
                            {watchItems.map((item) => (
                              <div key={item.id} className="uw-watch-item">
                                <span
                                  className="uw-watch-item-dot"
                                  style={{
                                    background: item.kind === 'failure' || item.severity === 'critical'
                                      ? 'hsl(var(--uw-danger))'
                                      : 'hsl(var(--uw-risk))',
                                  }}
                                />
                                <span className="min-w-0 capitalize">{item.label}</span>
                                {item.citations.length > 0 ? (
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
                          </div>
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>

                {artifact.om_data?.below_market_annual_upside ? (
                  <div className="uw-upside-banner mt-4">
                    <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-uw-risk">
                      Upside not in model
                    </p>
                    <p className="mt-2 text-sm leading-6 text-muted-foreground">
                      {artifact.om_data.below_market_tenant_pct
                        ? `${(artifact.om_data.below_market_tenant_pct * 100).toFixed(0)}% of tenants are below street rate. `
                        : ''}
                      Raising them to current rates could add{' '}
                      <span className="font-semibold text-foreground">
                        {formatCompactCurrency(artifact.om_data.below_market_annual_upside)}/year
                      </span>
                      {' '}in revenue — not reflected in the modeled returns.
                    </p>
                    {artifact.om_data.value_add_notes ? (
                      <p className="mt-2 text-sm leading-6 text-muted-foreground">
                        {artifact.om_data.value_add_notes}
                      </p>
                    ) : null}
                  </div>
                ) : null}

          {showScenario ? (
            <div className="mt-4 underwriting-panel p-4 sm:p-5">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">What-if scenario</p>
                  <p className="mt-1 text-sm text-muted-foreground">Adjust assumptions to preview updated returns. Changes are not saved.</p>
                </div>
                <div className="flex items-center gap-2">
                  {isScenarioLoading ? <Loader2 className="h-4 w-4 animate-spin text-primary" /> : null}
                  <Button variant="ghost" size="sm" onClick={resetScenario} disabled={Object.keys(scenarioValues).length === 0}>
                    <RotateCcw className="mr-1.5 h-4 w-4" />
                    Reset
                  </Button>
                </div>
              </div>
              <div className="grid gap-5 xl:grid-cols-[1.4fr,1fr]">
                <div className="space-y-4">
                  {[
                    { field: 'exit_cap_rate', label: 'Exit cap rate', unit: '%', min: 1, max: 15, step: 0.1 },
                    { field: 'vacancy_credit_loss_pct', label: 'Vacancy & credit loss', unit: '%', min: 0, max: 40, step: 0.5 },
                    { field: 'rent_growth_pct', label: 'Rent growth / yr', unit: '%', min: -5, max: 15, step: 0.25 },
                    { field: 'interest_rate_pct', label: 'Interest rate', unit: '%', min: 2, max: 12, step: 0.1 },
                    { field: 'purchase_price', label: 'Purchase price', unit: '$', min: Math.round((baseScenario.purchase_price || 1_000_000) * 0.5), max: Math.round((baseScenario.purchase_price || 10_000_000) * 1.5), step: 50000 },
                  ].map(({ field, label, unit, min, max, step }) => {
                    const baseVal = baseScenario[field];
                    const currentVal = scenarioValues[field] ?? baseVal ?? (min + max) / 2;
                    const isOverridden = scenarioValues[field] != null;
                    return (
                      <div key={field}>
                        <div className="mb-1.5 flex items-center justify-between gap-3">
                          <label className="text-sm text-muted-foreground">
                            {label}
                            {isOverridden ? <span className="ml-2 text-xs font-medium text-primary">modified</span> : null}
                          </label>
                          <div className="flex items-center gap-1.5">
                            <input
                              type="number"
                              value={currentVal}
                              step={step}
                              min={min}
                              max={max}
                              onChange={(e) => {
                                const v = parseFloat(e.target.value);
                                if (!Number.isNaN(v)) handleScenarioChange(field, v);
                              }}
                              className="w-24 rounded-lg border border-border bg-background px-2 py-1 text-right text-sm font-semibold text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                            />
                            <span className="text-sm text-muted-foreground">{unit}</span>
                          </div>
                        </div>
                        <input
                          type="range"
                          min={min}
                          max={max}
                          step={step}
                          value={currentVal}
                          onChange={(e) => handleScenarioChange(field, parseFloat(e.target.value))}
                          className="underwriting-range"
                        />
                        <div className="mt-0.5 flex justify-between text-[11px] text-muted-foreground">
                          <span>{unit === '$' ? `$${(min / 1_000_000).toFixed(1)}M` : `${min}%`}</span>
                          {baseVal != null ? <span className="text-primary">base: {unit === '$' ? `$${(baseVal / 1_000_000).toFixed(1)}M` : `${baseVal.toFixed(1)}%`}</span> : null}
                          <span>{unit === '$' ? `$${(max / 1_000_000).toFixed(1)}M` : `${max}%`}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="space-y-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                    {scenarioResult ? 'Scenario vs base' : 'Adjust sliders to preview'}
                  </p>
                  {[
                    { label: 'IRR', base: currentRun?.irr, scenario: scenarioResult?.irr, fmt: (v) => `${(v * 100).toFixed(1)}%`, unit: 'pp', scale: 100 },
                    { label: 'Cash-on-Cash', base: currentRun?.cash_on_cash, scenario: scenarioResult?.cash_on_cash, fmt: (v) => `${(v * 100).toFixed(1)}%`, unit: 'pp', scale: 100 },
                    { label: 'Equity Multiple', base: currentRun?.equity_multiple, scenario: scenarioResult?.equity_multiple, fmt: (v) => `${v.toFixed(2)}×`, unit: 'x', scale: 1 },
                    { label: 'DSCR Year 1', base: currentRun?.dscr_year_one, scenario: scenarioResult?.dscr_year_one, fmt: (v) => `${v.toFixed(2)}×`, unit: 'x', scale: 1 },
                    { label: 'NOI Year 1', base: currentRun?.noi_year_one, scenario: scenarioResult?.noi_year_one, fmt: (v) => `$${(v / 1000).toFixed(0)}K`, unit: '$', scale: 1 },
                  ].map(({ label, base, scenario, fmt, unit, scale }) => {
                    const hasScenario = scenarioResult != null;
                    const delta = hasScenario && base != null && scenario != null ? (scenario - base) * scale : null;
                    const deltaStr = delta != null ? `${delta >= 0 ? '▲' : '▼'}${Math.abs(delta).toFixed(unit === '$' ? 0 : 2)}${unit === 'pp' ? 'pp' : unit === 'x' ? '' : ''}` : null;
                    const deltaTone = delta == null ? '' : delta > 0 ? 'text-success' : delta < 0 ? 'text-destructive' : 'text-muted-foreground';
                    return (
                      <div key={label} className="flex items-center justify-between gap-3 rounded-2xl border border-border/60 bg-background/60 px-4 py-3">
                        <span className="text-sm text-muted-foreground">{label}</span>
                        <div className="text-right">
                          <span className="font-semibold text-foreground">
                            {hasScenario && scenario != null ? fmt(scenario) : base != null ? fmt(base) : '—'}
                          </span>
                          {deltaStr ? (
                            <span className={`ml-2 text-xs font-medium ${deltaTone}`}>{deltaStr}</span>
                          ) : null}
                        </div>
                      </div>
                    );
                  })}
                  {scenarioResult?.verdict_status ? (
                    <div className={`rounded-2xl border px-4 py-3 text-sm font-semibold ${
                      scenarioResult.verdict_status === 'worth_pursuing'
                        ? 'border-success/25 bg-success/10 text-success'
                        : scenarioResult.verdict_status === 'needs_review'
                          ? 'border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-300'
                        : 'border-destructive/25 bg-destructive/10 text-destructive'
                    }`}>
                      Scenario verdict: {scenarioResult.verdict_status === 'worth_pursuing' ? 'Worth Pursuing' : scenarioResult.verdict_status === 'needs_review' ? 'Needs Review' : 'Below Standards'}
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          ) : null}

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
                What-if
              </Button>
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {metrics.map((metric) => (
                <UnderwritingMetricCard
                  key={metric.label}
                  label={metric.label}
                  value={metric.value}
                  detail={metric.detail}
                  tone={metric.tone}
                  formula={metric.formula}
                />
              ))}
            </div>
          </div>

          <div className="mt-4">
            <div className="field-section-label mb-3">Operating Benchmarks</div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <UnderwritingMetricCard
              label="Avg Current Rent / Door"
              value={formatCurrency(currentRentPerDoor ? Math.round(currentRentPerDoor) : null)}
              detail="Monthly in-place rent basis"
              formula="Total gross potential rent ÷ total units ÷ 12. Represents the average monthly rent currently charged across all occupied and vacant units."
            />
            <UnderwritingMetricCard
              label="Avg Market Rent / Door"
              value={formatCurrency(marketRentPerDoor ? Math.round(marketRentPerDoor) : null)}
              detail="Monthly market rent basis"
              formula="OM-stated or rent-comp-derived average asking rate per unit per month at current market conditions."
            />
            <UnderwritingMetricCard
              label="Current Expense Ratio"
              value={formatPercent(currentExpenseRatio)}
              detail="T-12 actual operating ratio"
              tone={currentExpenseRatio != null && currentExpenseRatio > 0.45 ? 'warning' : 'default'}
              formula="Total operating expenses ÷ effective gross income from the trailing 12-month income statement."
            />
            <UnderwritingMetricCard
              label="Pro Forma Expense Ratio"
              value={formatPercent(proFormaExpenseRatio)}
              detail="OM / underwritten expense ratio"
              tone={proFormaExpenseRatio != null && currentExpenseRatio != null && proFormaExpenseRatio < currentExpenseRatio - 0.05 ? 'active' : 'default'}
              formula="Broker-projected or underwritten total operating expenses ÷ pro forma EGI. A ratio materially below the T-12 actual warrants scrutiny."
            />
            <UnderwritingMetricCard
              label="Break-Even Occupancy"
              value={formatRatioPercent(breakEvenOccupancyPct)}
              detail="Occupancy needed to cover year-one debt service"
              tone={
                breakEvenOccupancyPct == null
                  ? 'default'
                  : occupancy == null
                    ? 'default'
                    : breakEvenOccupancyPct > occupancy
                      ? 'danger'
                      : breakEvenOccupancyPct > occupancy - 0.1
                        ? 'warning'
                        : 'default'
              }
              formula="(Total operating expenses + annual debt service) ÷ gross potential rent. The occupancy level at which cash flow after debt service equals zero."
            />
          </div>
          </div>{/* end Operating Benchmarks */}

          <div className="mt-6 grid gap-5">
            <UnderwritingSection
              eyebrow="Returns"
              title="Returns and capital structure"
              className="underwriting-panel-strong"
              action={
                <Button variant="ghost" size="sm" onClick={() => setShowReturns((v) => !v)} className="gap-1.5 h-7 px-3 text-xs text-muted-foreground">
                  <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showReturns ? '' : '-rotate-90'}`} />
                  {showReturns ? 'Collapse' : 'Expand'}
                </Button>
              }
            >
              {showReturns && <div className="grid gap-4 xl:grid-cols-[1.7fr,1fr]">
                <div className="underwriting-panel p-4 sm:p-5">
                  <div className="mb-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">5-year pro forma</p>
                    <p className="mt-1 text-sm text-muted-foreground">NOI and cash flow after debt service.</p>
                  </div>
                  {proformaData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={280}>
                      <BarChart data={proformaData} barGap={6}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                        <XAxis dataKey="year" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                        <YAxis tickFormatter={(value) => `$${(value / 1000).toFixed(0)}K`} tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                        <Tooltip formatter={(value) => formatCompactCurrency(value)} />
                        <Legend />
                        <Bar dataKey="NOI" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                        <Bar dataKey="CFADS" fill="hsl(var(--accent))" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="underwriting-empty py-16 text-sm text-muted-foreground">No projection data available.</div>
                  )}
                </div>

                <div className="space-y-4">
                  <div className="underwriting-panel p-4 sm:p-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Capital stack</p>
                    <div className="mt-4 space-y-3">
                      <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Senior debt</p>
                        <p className="mt-2 font-display text-2xl font-semibold text-foreground">{formatCompactCurrency(loanAmount)}</p>
                        <p className="mt-1 text-sm text-muted-foreground">{formatPercent(ltvPct)} LTV</p>
                      </div>
                      <div className={`rounded-2xl border p-4 ${
                        equityPct > 0.4 ? 'border-warning/25 bg-warning/10' : 'border-border/60 bg-background/60'
                      }`}>
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Equity</p>
                        <p className="mt-2 font-display text-2xl font-semibold text-foreground">{formatCompactCurrency(equityInvested)}</p>
                        <p className="mt-1 text-sm text-muted-foreground">{formatPercent(equityPct)} of purchase price</p>
                      </div>
                    </div>
                    <div className={`mt-4 rounded-2xl border p-4 ${
                      equityPct >= 0.5
                        ? 'border-warning/25 bg-warning/10'
                        : equityPct >= 0.4
                          ? 'border-primary/20 bg-primary/5'
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
                    <KeyValueList
                      rows={[
                        { label: 'Total purchase price', value: formatCompactCurrency(purchasePrice) },
                        { label: 'NOI year 1', value: formatCompactCurrency(currentRun.noi_year_one) },
                        { label: 'Cap rate year 1', value: formatPercent(currentRun.cap_rate_year_one) },
                        { label: 'Equity raise', value: formatCompactCurrency(equityInvested) },
                      ]}
                    />
                    <SourceSupportActions
                      citations={[sourceCitations.purchase_price, sourceCitations.market_cap_rate_purchase, sourceCitations.interest_rate_pct]}
                      onOpenSource={handleOpenSource}
                      title="Purchase basis"
                    />
                  </div>

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
                      citations={[sourceCitations.num_units, sourceCitations.gross_potential_rent_annual, sourceCitations.avg_in_place_rent_per_unit_monthly, sourceCitations.avg_market_rent_per_unit_monthly]}
                      onOpenSource={handleOpenSource}
                      title="Portfolio support"
                    />

                    {omStatedNoi != null && modeledNoi != null ? (
                      <div className={`rounded-2xl border p-4 ${noiBridgeAlert ? 'border-amber-500/30 bg-amber-500/5' : 'border-border/60 bg-background/60'}`}>
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">NOI bridge</p>
                            <p className="mt-1 text-sm text-muted-foreground">OM stated NOI compared with modeled year-one NOI.</p>
                          </div>
                          <span className={`text-sm font-semibold ${noiBridgeAlert ? 'text-amber-700 dark:text-amber-300' : 'text-foreground'}`}>
                            {formatPercent(noiBridgeDeltaPct)}
                          </span>
                        </div>
                        <div className="mt-3 grid gap-3 sm:grid-cols-3">
                          <div className="rounded-2xl border border-border/60 bg-background/70 px-3 py-3">
                            <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">OM stated NOI</p>
                            <p className="mt-1 font-semibold text-foreground">{formatCompactCurrency(omStatedNoi)}</p>
                          </div>
                          <div className="rounded-2xl border border-border/60 bg-background/70 px-3 py-3">
                            <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Modeled NOI</p>
                            <p className="mt-1 font-semibold text-foreground">{formatCompactCurrency(modeledNoi)}</p>
                          </div>
                          <div className="rounded-2xl border border-border/60 bg-background/70 px-3 py-3">
                            <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Delta</p>
                            <p className={`mt-1 font-semibold ${noiBridgeAlert ? 'text-amber-700 dark:text-amber-300' : 'text-foreground'}`}>
                              {noiBridgeDelta == null ? '—' : `${noiBridgeDelta >= 0 ? '+' : ''}${formatCompactCurrency(noiBridgeDelta)}`}
                            </p>
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>}
            </UnderwritingSection>

            <UnderwritingSection
              eyebrow="Operations"
              title="Operating evidence and model support"
              className="underwriting-panel-strong"
              action={
                <Button variant="ghost" size="sm" onClick={() => setShowOperations((v) => !v)} className="gap-1.5 h-7 px-3 text-xs text-muted-foreground">
                  <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showOperations ? '' : '-rotate-90'}`} />
                  {showOperations ? 'Collapse' : 'Expand'}
                </Button>
              }
            >
              {showOperations && <div className="grid gap-4 xl:grid-cols-[1.35fr,1fr]">
                <div className="underwriting-panel p-4 sm:p-5">
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Unit mix</p>
                      <p className="mt-1 text-sm text-muted-foreground">Occupancy and rent by unit type.</p>
                    </div>
                    <OccupancyBadge pct={occupancy} />
                  </div>
                  {unitMix.length > 0 ? (
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
                              <td className="py-3">
                                {getUnitTypeBadge(row)}
                              </td>
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
                  ) : (
                    <div className="underwriting-empty py-12">
                      <Building2 className="h-6 w-6 text-primary" />
                      <p className="mt-3 text-sm text-muted-foreground">Unit mix was not extracted. Add a rent roll to populate this evidence layer.</p>
                    </div>
                  )}
                </div>

                <div className="space-y-4">
                  <div className="underwriting-panel p-4 sm:p-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Expense detail</p>
                    <div className="mt-4">
                      <KeyValueList
                        rows={[
                          { label: 'Expense ratio (T-12 actual)', value: formatPercent(currentExpenseRatio) },
                          { label: 'Expense ratio (OM pro forma)', value: formatPercent(proFormaExpenseRatio) },
                          {
                            label: 'Expense ratio delta',
                            value: currentExpenseRatio != null && proFormaExpenseRatio != null ? `${((currentExpenseRatio - proFormaExpenseRatio) * 100).toFixed(1)} pp` : '—',
                          },
                          { label: 'Property tax (year 1)', value: formatCurrency(propertyTaxAnnual) },
                          { label: 'Property tax growth', value: formatPercent(propertyTaxGrowthPct) },
                          { label: 'Mil rate', value: milRate != null ? `${milRate.toFixed(5)} mills` : '—' },
                          { label: 'Bad debt', value: formatCurrency(badDebtAnnual) },
                          { label: 'Corrections / collections', value: formatCurrency(correctionsCollectionsAnnual) },
                          {
                            label: 'Price / unit',
                            value: purchasePrice && totalUnits 
                              ? formatCurrency(Math.round(purchasePrice / totalUnits)) 
                              : '—',
                          },
                          {
                            label: 'Price / rentable sqft',
                            value: purchasePrice && persistedInputs.project?.rentable_sqft
                              ? `$${(purchasePrice / persistedInputs.project.rentable_sqft).toFixed(2)}`
                              : '—',
                          }
                        ]}
                      />
                      {(() => {
                        const op = persistedInputs.operational || {};
                        const subItems = [
                          { label: 'Office & Admin', value: op.expense_office_admin_annual },
                          { label: 'Bank Fees', value: op.expense_bank_fees_annual },
                          { label: 'Contract Services', value: op.expense_contract_services_annual },
                          { label: 'Miscellaneous', value: op.expense_miscellaneous_annual },
                          { label: 'Telephone', value: op.expense_telephone_annual },
                        ];
                        const hasAny = subItems.some((item) => item.value != null);
                        if (!hasAny) return null;
                        return (
                          <div className="mt-3">
                            <button
                              type="button"
                              onClick={() => setShowOtherOpex((v) => !v)}
                              className="flex w-full items-center justify-between gap-2 rounded-xl border border-border/60 bg-background/60 px-3 py-2 text-sm text-muted-foreground hover:bg-muted/40"
                            >
                              <span>Other OpEx breakdown</span>
                              <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${showOtherOpex ? 'rotate-180' : ''}`} />
                            </button>
                            {showOtherOpex ? (
                              <div className="mt-2 space-y-2 rounded-xl border border-border/60 bg-background/40 px-3 py-3">
                                {subItems.map(({ label, value }) => (
                                  <div key={label} className="flex items-center justify-between gap-3 text-sm">
                                    <span className="text-muted-foreground">{label}</span>
                                    <span className="font-medium text-foreground">{formatCurrency(value)}</span>
                                  </div>
                                ))}
                                <div className="mt-2 flex items-center justify-between gap-3 border-t border-border/60 pt-2 text-sm">
                                  <span className="font-medium text-muted-foreground">Total other OpEx</span>
                                  <span className="font-semibold text-foreground">
                                    {formatCurrency(subItems.reduce((sum, item) => sum + (item.value || 0), 0))}
                                  </span>
                                </div>
                              </div>
                            ) : null}
                          </div>
                        );
                      })()}
                      {missingExpenseFields.length > 0 ? (
                        <div className="mt-4 rounded-2xl border border-warning/25 bg-warning/10 p-3 text-sm text-muted-foreground">
                          <span className="font-medium text-foreground">Missing from extracted expense table:</span> {missingExpenseFields.join(', ')}
                        </div>
                      ) : null}
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
                        onOpenSource={handleOpenSource}
                        title="Expense support"
                      />
                    </div>
                  </div>

                  <div className="underwriting-panel p-4 sm:p-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Revenue quality</p>
                    <div className="mt-4">
                      <KeyValueList
                        rows={[
                          { label: 'Vacancy & credit loss', value: formatPercent(persistedInputs.operational?.vacancy_credit_loss_pct) },
                          { label: 'Bad debt', value: formatCurrency(badDebtAnnual), help: 'Historical charge-offs or delinquent losses from the T-12.' },
                          { label: 'Corrections / collections', value: formatCurrency(correctionsCollectionsAnnual), help: 'Adjustments, write-downs, or collection-related offsets.' },
                        ]}
                      />
                      <SourceSupportActions
                        citations={[
                          sourceCitations.vacancy_credit_loss_pct,
                          sourceCitations.bad_debt_annual,
                          sourceCitations.corrections_collections_annual,
                        ]}
                        onOpenSource={handleOpenSource}
                        title="Revenue support"
                      />

                      {artifact.om_data?.income_basis_months === 6 ? (
                        <div className="mt-4 rounded-2xl border border-warning/25 bg-warning/10 p-3 text-sm text-muted-foreground">
                          <span className="font-medium text-foreground">Income basis: </span>
                          Current EGI is based on trailing 6-month revenue, annualized by the broker. 
                          This may mask seasonal low periods and should be validated against a full T-12.
                        </div>
                      ) : null}
                    </div>
                  </div>

                  {stressTests.length > 0 ? (
                    <div className="underwriting-panel p-4 sm:p-5">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Stress tests</p>
                      <div className="mt-4">
                        <StressTestTable stressTests={stressTests} />
                      </div>
                    </div>
                  ) : null}

                  {rolloverRisk ? (
                    <div className="underwriting-panel p-4 sm:p-5">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Rollover risk</p>
                      <div className="mt-4">
                        <RolloverRiskPanel rolloverRisk={rolloverRisk} />
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>}
            </UnderwritingSection>

            <UnderwritingSection
              eyebrow="Source evidence"
              title="Key assumptions and source support"
              className="underwriting-panel-strong"
              action={
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowEvidence((v) => !v)}
                  className="gap-1.5 h-7 px-3 text-xs text-muted-foreground"
                >
                  {showEvidence ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5 -rotate-90" />}
                  {showEvidence ? 'Collapse' : 'Expand'}
                </Button>
              }
            >
              {showEvidence && evidenceItems.length > 0 ? (
                <div className="grid gap-3 lg:grid-cols-2">
                  {evidenceItems.map((item) => {
                    const confidence = Number(item.citation?.confidence);
                    const confidenceLabel = Number.isFinite(confidence) && confidence > 0
                      ? `${Math.round(confidence * 100)}% confidence`
                      : 'Cited input';
                    const docTypeLabel = DOC_TYPE_LABELS[item.citation?.doc_type] || item.citation?.doc_type || 'Document';

                    return (
                      <div key={item.key} className="underwriting-quote-card">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{item.label}</p>
                            <p className="mt-2 font-display text-2xl font-semibold tracking-tight text-foreground">{item.value}</p>
                          </div>
                          <UnderwritingStatusBadge tone="active">{docTypeLabel}</UnderwritingStatusBadge>
                        </div>

                        <p className="mt-3 text-xs font-medium uppercase tracking-[0.16em] text-uw-citation">{confidenceLabel}</p>
                        {item.citation?.source_text ? (
                          <p className="mt-2 text-sm leading-6 text-muted-foreground">“{item.citation.source_text}”</p>
                        ) : null}

                        <div className="mt-4 flex flex-wrap items-center gap-2">
                          {item.citation.entries?.map((entry, index) => (
                            <Button
                              key={`${item.key}-${entry.citation}-${index}`}
                              type="button"
                              variant="outline"
                              size="sm"
                              className="h-8 rounded-full px-3 text-xs"
                              onClick={() => handleOpenSource(entry)}
                            >
                              {entry.page ? `Open page ${entry.page}` : 'Open source'}
                            </Button>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : showEvidence ? (
                <div className="underwriting-empty py-12">
                  <AlertTriangle className="h-6 w-6 text-primary" />
                  <p className="mt-3 text-sm text-muted-foreground">This run does not have extracted field citations yet. Run AI extraction on an OM, rent roll, or T-12 to populate source-backed assumptions.</p>
                </div>
              ) : null}
            </UnderwritingSection>

            <UnderwritingSection
              eyebrow="Market context"
              title="Location, comps, and pricing sensitivity"
              className="underwriting-panel-strong"
              action={
                <Button variant="ghost" size="sm" onClick={() => setShowMarket((v) => !v)} className="gap-1.5 h-7 px-3 text-xs text-muted-foreground">
                  <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showMarket ? '' : '-rotate-90'}`} />
                  {showMarket ? 'Collapse' : 'Expand'}
                </Button>
              }
            >
              {showMarket && <div className="grid gap-4 xl:grid-cols-[1fr,1fr]">
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
                    {(nearbyStorageCount1Mi != null || nearbyStorageCount3Mi != null || nearbyStorageCount5Mi != null) ? (
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
                    ) : null}
                  </div>

                  <div className="underwriting-panel p-4 sm:p-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Market demographics</p>
                    <div className="mt-4">
                      {demographics ? (
                        <KeyValueList
                          rows={[
                            { label: 'Population (3-mile radius)', value: demographics.population?.toLocaleString() ?? '—' },
                            { label: 'Avg household income', value: formatCurrency(demographics.avg_household_income) },
                            { label: 'Storage sqft / capita', value: demographics.sqft_per_capita != null ? `${demographics.sqft_per_capita.toFixed(1)} sqft` : '—' },
                            { label: 'Median age', value: demographics.median_age ?? '—' },
                          ]}
                        />
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
                      <KeyValueList
                        rows={[
                          { label: 'Submarket average cap rate', value: formatPercent(capRateSubmarket) },
                          { label: 'Purchase cap rate basis', value: formatPercent(capRatePurchase) },
                          { label: 'Sale cap rate assumption', value: formatPercent(capRateSale) },
                          {
                            label: 'Spread vs submarket',
                            value: bpsDelta != null ? `${Math.abs(bpsDelta)} bps ${bpsDelta > 0 ? 'premium' : 'discount'}` : '—',
                          },
                        ]}
                      />
                    </div>
                  </div>

                  <div className="underwriting-panel p-4 sm:p-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Rent position</p>
                    <div className="mt-4">
                      {rentPositionAnalysis.length > 0 ? (
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
                      {sensitivityPoints.length > 0 ? (
                        <div className="mt-4">
                          <ResponsiveContainer width="100%" height={240}>
                            <LineChart data={sensitivityPoints}>
                              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                              <XAxis dataKey="purchase_price" tickFormatter={(value) => `$${(value / 1_000_000).toFixed(1)}M`} tick={{ fontSize: 11 }} />
                              <YAxis tickFormatter={(value) => `${(value * 100).toFixed(1)}%`} tick={{ fontSize: 11 }} />
                              <Tooltip
                                labelFormatter={(value) => formatCompactCurrency(value)}
                                formatter={(value, name) => [`${(value * 100).toFixed(1)}%`, name]}
                              />
                              <Legend />
                              <Line type="monotone" dataKey="irr" stroke="hsl(var(--primary))" name="IRR" dot={false} strokeWidth={2.4} />
                              <Line type="monotone" dataKey="cash_on_cash" stroke="hsl(var(--accent))" name="Cash-on-Cash" dot={false} strokeWidth={2.4} />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
              </div>}
            </UnderwritingSection>

            {discrepancies.length > 0 ? (
              <UnderwritingSection
                eyebrow="Review flags"
                title="Cross-document discrepancies"
                description="These mismatches do not change the verdict directly, but they are worth reconciling before final approval."
                className="underwriting-panel-strong"
              >
                <div className="grid gap-3 md:grid-cols-2">
                  {discrepancies.map((discrepancy) => (
                    <div
                      key={discrepancy.field}
                      className={`underwriting-panel p-4 ${
                        discrepancy.severity === 'error'
                          ? 'border-destructive/25 bg-destructive/10'
                          : discrepancy.severity === 'warning'
                            ? 'border-warning/25 bg-warning/10'
                            : ''
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-uw-risk" />
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-foreground">{discrepancy.field}</p>
                          <p className="mt-1 text-sm leading-6 text-muted-foreground">{discrepancy.note}</p>
                          <SourceSupportActions
                            citations={discrepancySupportByField[discrepancy.field] || []}
                            onOpenSource={handleOpenSource}
                            title="Trace to source"
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </UnderwritingSection>
            ) : null}
              </div>
            </div>
            </div>
            </div>
            </div>
        </ResizablePanel>
        {showSourcePanel ? <ResizableHandle withHandle /> : null}
        {showSourcePanel ? (
          <ResizablePanel id="uw-result-source" order={2} defaultSize={42} minSize={28}>
            <SourceDocumentPanel citation={activeCitation} isOpen={showSourcePanel} onClose={closeSourcePanel} />
          </ResizablePanel>
        ) : null}
      </ResizablePanelGroup>
    </AppLayout>
  );
}