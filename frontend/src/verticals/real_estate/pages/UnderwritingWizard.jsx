/**
 * Underwriting setup workspace
 * Document selection, AI extraction, and manual input review.
 */
import { useEffect, useId, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  AlertCircle,
  ArrowRight,
  BarChart2,
  Building2,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FileText,
  FolderOpen,
  Loader2,
  Plus,
  Sparkles,
  Trash2,
  TrendingUp,
  X,
} from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from '@/components/ui/resizable';
import AppLayout from '../../../components/layout/AppLayout';
import { useAppAuth } from '../../../hooks/useAppAuth';
import { useUnderwriting, useUnderwritingActions } from '../../../store';
import { createUnderwritingRun, updateUnderwritingInputs } from '../../../api/re-underwriting';
import { fromApiInputs, toApiInputs } from '../utils/underwritingInputs';
import { streamJobProgress } from '../../../api/sse-utils';
import DocumentSelectorDialog from '../components/DocumentSelectorDialog';
import {
  AIPrefilledField,
  DiscrepancyBanner,
  SourceDocumentPanel,
  UnderwritingSection,
  UnderwritingStatusBadge,
} from '../components/underwriting';

const DOC_SLOTS = [
  {
    key: 'om',
    icon: FileText,
    label: 'Offering Memorandum',
    required: true,
    hint: 'Purchase price, unit mix, cap rate, and business plan assumptions.',
  },
  {
    key: 't12',
    icon: BarChart2,
    label: 'T-12 / T-6 Statement',
    required: false,
    hint: 'Trailing income, expenses, and recent operating performance.',
  },
  {
    key: 'rent_roll',
    icon: FolderOpen,
    label: 'Rent Roll',
    required: false,
    hint: 'Occupancy, rents, lease terms, and rollover exposure.',
  },
];

const TAB_CONFIG = [
  { id: 'acquisition', label: 'Acquisition', desc: 'Price, closing costs, and upfront capital.' },
  { id: 'operations', label: 'Operations', desc: 'Revenue assumptions and operating expense inputs.' },
  { id: 'market', label: 'Market', desc: 'Nearby facilities, population, and income context.' },
  { id: 'debtExit', label: 'Debt & Exit', desc: 'Financing, hold horizon, and exit assumptions.' },
  { id: 'criteria', label: 'Criteria', desc: 'Return hurdles and leverage limits.' },
];

const VISIBLE_CITATION_FIELD_KEYS = [
  'purchase_price',
  'closing_cost_pct',
  'market_cap_rate_purchase',
  'capex_reserve_per_unit',
  'num_units',
  'rentable_sqft',
  'gross_potential_rent_annual',
  'avg_in_place_rent_per_unit_monthly',
  'avg_market_rent_per_unit_monthly',
  'other_income_annual',
  'vacancy_credit_loss_pct',
  'expense_ratio_current',
  'expense_ratio_pro_forma',
  'bad_debt_annual',
  'corrections_collections_annual',
  'rent_growth_pct',
  'property_tax_annual',
  'property_tax_growth_pct',
  'mil_rate',
  'insurance_annual',
  'mgmt_fee_pct',
  'payroll_annual',
  'repairs_maintenance_annual',
  'utilities_annual',
  'marketing_annual',
  'other_opex_annual',
  'opex_growth_pct',
  'nearby_storage_count_1mi',
  'nearby_storage_count_3mi',
  'nearby_storage_count_5mi',
  'population_3mi',
  'avg_household_income_3mi',
  'storage_sqft_per_capita_3mi',
  'interest_rate_pct',
  'loan_term_years',
  'amortization_years',
  'ltv_pct',
  'hold_period_years',
  'market_cap_rate_sale',
  'exit_cap_rate',
  'selling_cost_pct',
  'target_irr',
  'target_cash_on_cash',
  'target_equity_multiple',
  'max_ltv',
];

function countVisibleCitations(fieldCitations) {
  if (!fieldCitations) return 0;

  return VISIBLE_CITATION_FIELD_KEYS.reduce((count, fieldKey) => {
    const citation = fieldCitations[fieldKey]
      ?? fieldCitations[`om.${fieldKey}`]
      ?? fieldCitations[`t12.${fieldKey}`]
      ?? fieldCitations[`rent_roll.${fieldKey}`]
      ?? null;

    return citation && !citation.is_default ? count + 1 : count;
  }, 0);
}

const INITIAL_PROJECT_DATA = {
  name: '',
  address: '',
  asset_type: 'self_storage',
  nearby_storage_count_1mi: '',
  nearby_storage_count_3mi: '',
  nearby_storage_count_5mi: '',
  population_3mi: '',
  avg_household_income_3mi: '',
  storage_sqft_per_capita_3mi: '',
};

const createDefaultInputs = () => ({
  acquisition: { purchase_price: '', closing_cost_pct: 2, market_cap_rate_purchase: '', capex_reserve_per_unit: 0 },
  operational: {
    gross_potential_rent_annual: '',
    avg_in_place_rent_per_unit_monthly: '',
    avg_market_rent_per_unit_monthly: '',
    vacancy_credit_loss_pct: 10,
    expense_ratio_current: '',
    expense_ratio_pro_forma: '',
    other_income_annual: 0,
    bad_debt_annual: '',
    corrections_collections_annual: '',
    rent_growth_pct: 3,
    property_tax_annual: 0,
    insurance_annual: 0,
    mgmt_fee_pct: 8,
    payroll_annual: 0,
    repairs_maintenance_annual: 0,
    utilities_annual: 0,
    marketing_annual: 0,
    other_opex_annual: 0,
    property_tax_growth_pct: '',
    mil_rate: '',
    opex_growth_pct: 2,
  },
  financing: { interest_rate_pct: 6.5, loan_term_years: 10, amortization_years: 25, ltv_pct: 70 },
  exit: { hold_period_years: 10, market_cap_rate_sale: '', exit_cap_rate: 6.5, selling_cost_pct: 3 },
  criteria: { target_irr: 15, target_cash_on_cash: 8, target_equity_multiple: 2.0, max_ltv: 80 },
  rent_comps: [],
});

function computeTabProgress(inputs, projectData) {
  const has = (v) => v !== '' && v != null;
  return {
    acquisition: Math.round(
      [inputs.acquisition.purchase_price, inputs.acquisition.closing_cost_pct,
       inputs.acquisition.market_cap_rate_purchase, inputs.acquisition.capex_reserve_per_unit,
       projectData.num_units, projectData.rentable_sqft]
        .filter(has).length / 6 * 100
    ),
    operations: Math.round(
      [inputs.operational.gross_potential_rent_annual, inputs.operational.avg_in_place_rent_per_unit_monthly,
       inputs.operational.avg_market_rent_per_unit_monthly, inputs.operational.vacancy_credit_loss_pct,
       inputs.operational.expense_ratio_pro_forma, inputs.operational.rent_growth_pct,
       inputs.operational.property_tax_annual, inputs.operational.mgmt_fee_pct,
       inputs.operational.opex_growth_pct]
        .filter(has).length / 9 * 100
    ),
    market: Math.round(
      [projectData.nearby_storage_count_1mi, projectData.nearby_storage_count_3mi,
       projectData.nearby_storage_count_5mi, projectData.population_3mi,
       projectData.avg_household_income_3mi, projectData.storage_sqft_per_capita_3mi]
        .filter(has).length / 6 * 100
    ),
    debtExit: Math.round(
      [inputs.financing.interest_rate_pct, inputs.financing.loan_term_years,
       inputs.financing.amortization_years, inputs.financing.ltv_pct,
       inputs.exit.hold_period_years, inputs.exit.exit_cap_rate, inputs.exit.selling_cost_pct]
        .filter(has).length / 7 * 100
    ),
    criteria: Math.round(
      [inputs.criteria.target_irr, inputs.criteria.target_cash_on_cash,
       inputs.criteria.target_equity_multiple, inputs.criteria.max_ltv]
        .filter(has).length / 4 * 100
    ),
  };
}

function FieldGroup({ label }) {
  return (
    <div className="col-span-full pt-2 first:pt-0">
      <div className="border-b border-border/60 pb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </div>
    </div>
  );
}

function NumericField({ label, value, onChange, prefix, suffix, citation, onOpenSource, wide = false, placeholder }) {
  const id = useId();
  return (
    <div className={wide ? 'xl:col-span-2' : ''}>
      <AIPrefilledField label={label} inputId={id} citation={citation} onOpenSource={onOpenSource}>
        <div className="uw-field-row" data-cited={citation ? 'true' : undefined}>
          {prefix ? <span className="uw-field-affix uw-field-affix-prefix">{prefix}</span> : null}
          <input
            id={id}
            type="number"
            className="uw-field-input"
            value={value ?? ''}
            placeholder={placeholder}
            onChange={(e) => {
              if (e.target.value === '') { onChange(''); return; }
              const n = parseFloat(e.target.value);
              onChange(Number.isFinite(n) ? n : '');
            }}
            onWheel={(e) => e.currentTarget.blur()}
          />
          {suffix ? <span className="uw-field-affix uw-field-affix-suffix">{suffix}</span> : null}
        </div>
      </AIPrefilledField>
    </div>
  );
}

function DocCard({ slot, selected, onOpen, onRemove, extracting }) {
  const Icon = slot.icon;

  return (
    <div className="underwriting-panel p-3">
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ${
          selected ? 'bg-primary/12 text-primary' : 'bg-muted/70 text-muted-foreground'
        }`}>
          <Icon className="h-4 w-4" />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-foreground">{slot.label}</p>
            {slot.required ? <UnderwritingStatusBadge tone="warning">Required</UnderwritingStatusBadge> : null}
            {selected ? <CheckCircle2 className="h-3.5 w-3.5 text-uw-success" /> : null}
          </div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            {selected ? selected.name : slot.hint}
          </p>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between gap-3">
        {selected ? (
          <button
            type="button"
            onClick={onRemove}
            disabled={extracting}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-destructive disabled:cursor-not-allowed disabled:opacity-50"
          >
            <X className="h-3.5 w-3.5" />
            Remove
          </button>
        ) : (
          <span className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">No document attached</span>
        )}

        <Button size="sm" variant={selected ? 'outline' : 'default'} onClick={onOpen} disabled={extracting}>
          {selected ? 'Change' : 'Select'}
        </Button>
      </div>
    </div>
  );
}

function WorkflowRail({
  selectedDocs,
  anyDocSelected,
  hasOmForExtraction,
  extraction,
  extractionDone,
  handleRunExtraction,
  isExtracting,
  projectName,
  currentRun,
  setDocPickerOpen,
  setSelectedDocs,
  citationCount,
  leftCollapsed,
  setLeftCollapsed,
}) {
  const attachedCount = Object.values(selectedDocs).filter(Boolean).length;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Rail header with collapse toggle */}
      <div className="doc-rail-header">
        {!leftCollapsed && (
          <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
            Source Docs
          </span>
        )}
        <button
          onClick={() => setLeftCollapsed((v) => !v)}
          className="ml-auto flex h-7 w-7 items-center justify-center rounded-lg border border-border/50 bg-card text-muted-foreground shadow-sm transition-colors hover:bg-muted hover:text-foreground"
          title={leftCollapsed ? 'Expand panel' : 'Collapse panel'}
        >
          {leftCollapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
        </button>
      </div>

      {leftCollapsed ? (
        /* Collapsed: icon-only stacked view */
        <div className="flex flex-col items-center py-2">
          {DOC_SLOTS.map((slot) => {
            const Icon = slot.icon;
            const attached = Boolean(selectedDocs[slot.key]);
            return (
              <button
                key={slot.key}
                onClick={() => setDocPickerOpen(slot.key)}
                title={slot.label}
                className={`flex h-10 w-full items-center justify-center border-l-2 transition-colors ${
                  attached
                    ? 'border-l-primary bg-primary/5 text-primary'
                    : 'border-l-transparent text-muted-foreground hover:bg-muted/50'
                }`}
              >
                <Icon className="h-4 w-4" />
              </button>
            );
          })}
        </div>
      ) : (
        /* Expanded: full rail */
        <>
          <div className="flex-1 overflow-y-auto">
            <UnderwritingSection
              eyebrow="Workflow"
              title="Source documents"
              description="Attach the materials you trust, then let AI draft the model inputs before you review them."
              className="rounded-none border-x-0 border-t-0 shadow-none"
            >
              <div className="space-y-2.5">
                {DOC_SLOTS.map((slot) => (
                  <DocCard
                    key={slot.key}
                    slot={slot}
                    selected={selectedDocs[slot.key]}
                    onOpen={() => setDocPickerOpen(slot.key)}
                    onRemove={() => setSelectedDocs((prev) => ({ ...prev, [slot.key]: null }))}
                    extracting={extraction.isProcessing}
                  />
                ))}
              </div>

              {extraction.isProcessing ? (
                <div className="underwriting-panel mt-3 border-primary/20 bg-primary/5 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2 text-sm font-medium text-primary">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {extraction.message || 'Extracting data'}
                    </div>
                    <span className="text-sm font-semibold text-primary">{extraction.progress || 0}%</span>
                  </div>
                  <Progress value={extraction.progress || 0} className="mt-2.5 h-1.5" />
                </div>
              ) : null}

              <div className="mt-3 rounded-2xl border border-border/60 bg-background/55 p-3.5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">AI drafting</p>
                    <p className="mt-1 text-sm font-semibold text-foreground">
                      {extractionDone ? 'Inputs are ready for review' : 'Populate the model from source docs'}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      {extractionDone
                        ? `${citationCount} field${citationCount === 1 ? '' : 's'} now carry source-backed citations.`
                        : 'Run extraction after selecting an OM and naming the deal.'}
                    </p>
                  </div>
                  {extractionDone
                    ? <CheckCircle2 className="mt-1 h-5 w-5 shrink-0 text-uw-success" />
                    : <Sparkles className="mt-1 h-5 w-5 shrink-0 text-primary" />}
                </div>

                <Button
                  onClick={handleRunExtraction}
                  disabled={isExtracting || !hasOmForExtraction || !projectName.trim()}
                  className="mt-3 w-full gap-2"
                  variant={extractionDone ? 'outline' : 'default'}
                >
                  <Sparkles className="h-4 w-4" />
                  {extractionDone ? 'Re-run extraction' : 'Extract with AI'}
                </Button>
              </div>
            </UnderwritingSection>

            {currentRun?.discrepancies?.length ? (
              <div className="space-y-2.5 px-4 pb-4">
                {currentRun.discrepancies.map((disc) => (
                  <DiscrepancyBanner key={disc.field} discrepancy={disc} />
                ))}
              </div>
            ) : null}
          </div>

          {/* AI stats footer */}
          <div className="doc-rail-footer">
            <div>
              <div className="doc-rail-stat-val text-primary">{citationCount}</div>
              <div className="doc-rail-stat-label">Cited fields</div>
            </div>
            <div>
              <div className="doc-rail-stat-val text-uw-citation">{attachedCount}/3</div>
              <div className="doc-rail-stat-label">Docs attached</div>
            </div>
            {extractionDone && (
              <div>
                <div className="doc-rail-stat-val text-uw-success">Ready</div>
                <div className="doc-rail-stat-label">Extraction</div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function UnderwritingWizard() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const runIdFromUrl = searchParams.get('run_id');
  const { getToken } = useAppAuth();
  const { currentRun, extraction } = useUnderwriting();
  const {
    completeExtraction,
    loadRun,
    resetExtraction,
    setCurrentRun,
    setWizardStep,
    startExtraction,
    updateExtractionProgress,
  } = useUnderwritingActions();

  const [projectData, setProjectData] = useState(INITIAL_PROJECT_DATA);
  const [selectedDocs, setSelectedDocs] = useState({ om: null, t12: null, rent_roll: null });
  const [docPickerOpen, setDocPickerOpen] = useState(null);
  const [activeTab, setActiveTab] = useState(TAB_CONFIG[0].id);

  const [inputs, setInputs] = useState(createDefaultInputs);
  const [isExtracting, setIsExtracting] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // Value-add evidence section (Operations tab)
  const [showValueAdd, setShowValueAdd] = useState(false);

  // Left panel collapse
  const [leftCollapsed, setLeftCollapsed] = useState(false);

  // Right source panel
  const [showSourcePanel, setShowSourcePanel] = useState(false);
  const [activeCitation, setActiveCitation] = useState(null);

  const resetWizardState = () => {
    setProjectData(INITIAL_PROJECT_DATA);
    setInputs(createDefaultInputs());
    setSelectedDocs({ om: null, t12: null, rent_roll: null });
    setDocPickerOpen(null);
    setActiveTab(TAB_CONFIG[0].id);
    setIsExtracting(false);
    setIsSubmitting(false);
    setError(null);
    setLeftCollapsed(false);
    setShowSourcePanel(false);
    setActiveCitation(null);
  };

  // On mount: re-hydrate from DB if run_id is in URL; otherwise start fresh.
  useEffect(() => {
    if (runIdFromUrl) {
      loadRun(getToken, runIdFromUrl);
    } else {
      setCurrentRun(null);
      setWizardStep(0);
      resetExtraction();
      resetWizardState();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runIdFromUrl]);

  useEffect(() => {
    return () => {
      resetExtraction();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // When a run is loaded (post-extraction or re-hydrated from DB), populate form.
  useEffect(() => {
    const currentRunId = currentRun?.id || currentRun?.run_id;
    if (!runIdFromUrl || !currentRun?.inputs || String(currentRunId) !== String(runIdFromUrl)) {
      return;
    }
    if (currentRun.name || currentRun.address || currentRun.inputs.project) {
      const { name: _ignoredName, ...projectInputs } = currentRun.inputs.project || {};

      setProjectData((prev) => ({
        ...prev,
        ...projectInputs,
        name: currentRun.name || prev.name,
        address: currentRun.address || prev.address,
      }));
    }
    setInputs((prev) => {
      const converted = fromApiInputs(currentRun.inputs);
      return {
        acquisition: { ...prev.acquisition, ...converted.acquisition },
        operational:  { ...prev.operational,  ...converted.operational },
        financing:    { ...prev.financing,    ...converted.financing },
        exit:         { ...prev.exit,         ...converted.exit },
        criteria:     { ...prev.criteria,     ...converted.criteria },
        rent_comps: Array.isArray(converted.rent_comps) ? converted.rent_comps : prev.rent_comps,
      };
    });
  }, [runIdFromUrl, currentRun?.id, currentRun?.run_id, currentRun?.inputs]);

  // Consider docs "attached" if user selected any in the UI OR the run already has documents from a prior extraction.
  const anyDocSelected = Object.values(selectedDocs).some(Boolean)
    || (currentRun?.document_ids?.length > 0)
    || !!runIdFromUrl;
  const extractionDocuments = Object.values(selectedDocs).some(Boolean)
    ? Object.values(selectedDocs)
        .filter(Boolean)
        .map(({ document_id, doc_type }) => ({ document_id, doc_type }))
    : (currentRun?.document_ids || []).filter(
        (doc) => doc && typeof doc === 'object' && doc.document_id && doc.doc_type
      );
  const hasOmForExtraction = Boolean(selectedDocs.om)
    || Boolean(extractionDocuments.some((doc) => doc.doc_type === 'om'));
  const extractionDone = currentRun?.inputs != null;

  // Count only real AI-extracted citations (not hardcoded defaults).
  const citationCount = countVisibleCitations(currentRun?.field_citations);
  const getCitation = (fieldKey) => {
    const citations = currentRun?.field_citations;
    const citCtx = currentRun?.citation_context;
    if (!citations) return null;
    const raw = citations[fieldKey]
      ?? citations[`om.${fieldKey}`]
      ?? citations[`t12.${fieldKey}`]
      ?? citations[`rent_roll.${fieldKey}`]
      ?? null;
    // is_default means the merger used a hardcoded fallback — not a real AI finding.
    if (!raw || raw.is_default) return null;
    const token = raw.citations?.[0];
    const ctx = token && citCtx ? citCtx[token] : null;
    return {
      ...raw,
      page: ctx?.page ?? raw.page,
      document_id: ctx?.document_id ?? raw.document_id,
      filename: ctx?.filename ?? raw.filename,
      bbox: ctx?.bbox ?? raw.bbox ?? null,
    };
  };
  const rentCompsCitation = getCitation('rent_comps');

  const handleDocumentSelect = (docType, document) => {
    if (document) {
      setSelectedDocs((prev) => ({
        ...prev,
        [docType]: {
          document_id: document.id,
          doc_type: docType,
          name: document.name || document.filename || 'Document',
        },
      }));
    }
    setDocPickerOpen(null);
  };

  const handleRunExtraction = async () => {
    if (!projectData.name.trim()) {
      setError('Enter a deal name first');
      return;
    }
    if (!hasOmForExtraction) {
      setError('Select an Offering Memorandum before running AI extraction');
      return;
    }

    setIsExtracting(true);
    setError(null);

    try {
      const run = await createUnderwritingRun(getToken, {
        name: projectData.name,
        asset_type: projectData.asset_type,
        address: projectData.address,
        documents: extractionDocuments,
      });

      setCurrentRun(run);
      navigate(`/app/re/underwriting/new?run_id=${run.run_id}`, { replace: true });

      const cleanup = await streamJobProgress(run.extraction_job_id, getToken, {
        onProgress: (data) => updateExtractionProgress({
          progress: data.progress_percent,
          stage: data.current_stage,
          message: data.message,
        }),
        onComplete: async () => {
          completeExtraction();
          await loadRun(getToken, run.run_id);
          setWizardStep(2);
          setIsExtracting(false);
        },
        onError: (err) => {
          setError(err.message || 'Extraction failed');
          resetExtraction();
          setIsExtracting(false);
        },
      });

      startExtraction(run.extraction_job_id, cleanup);
    } catch (err) {
      setError(err.message || 'Failed to start extraction');
      setIsExtracting(false);
    }
  };

  const handleSaveAndCalculate = async () => {
    if (!projectData.name.trim()) {
      setError('Deal name is required');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const inputPayload = toApiInputs({
        ...inputs,
        project: {
          ...(currentRun?.inputs?.project || {}),
          name: projectData.name,
          asset_type: projectData.asset_type,
          address: projectData.address,
          nearby_storage_count_1mi: projectData.nearby_storage_count_1mi,
          nearby_storage_count_3mi: projectData.nearby_storage_count_3mi,
          nearby_storage_count_5mi: projectData.nearby_storage_count_5mi,
          population_3mi: projectData.population_3mi,
          avg_household_income_3mi: projectData.avg_household_income_3mi,
          storage_sqft_per_capita_3mi: projectData.storage_sqft_per_capita_3mi,
        },
      });
      const existingRunId = currentRun?.run_id || currentRun?.id || runIdFromUrl;
      if (existingRunId) {
        await updateUnderwritingInputs(getToken, existingRunId, inputPayload);
        navigate(`/app/re/underwriting/${existingRunId}`);
      } else {
        const run = await createUnderwritingRun(getToken, {
          name: projectData.name,
          asset_type: projectData.asset_type,
          address: projectData.address,
          documents: [],
        });
        await updateUnderwritingInputs(getToken, run.run_id, inputPayload);
        navigate(`/app/re/underwriting/${run.run_id}`);
      }
    } catch (err) {
      setError(err.message || 'Failed to save');
    } finally {
      setIsSubmitting(false);
    }
  };

  const patchAcq = (key, value) => setInputs((prev) => ({ ...prev, acquisition: { ...prev.acquisition, [key]: value } }));
  const patchOp = (key, value) => setInputs((prev) => ({ ...prev, operational: { ...prev.operational, [key]: value } }));
  const patchProject = (key, value) => setProjectData((prev) => ({ ...prev, [key]: value }));
  const patchFin = (key, value) => setInputs((prev) => ({ ...prev, financing: { ...prev.financing, [key]: value } }));
  const patchExit = (key, value) => setInputs((prev) => ({ ...prev, exit: { ...prev.exit, [key]: value } }));
  const patchCrit = (key, value) => setInputs((prev) => ({ ...prev, criteria: { ...prev.criteria, [key]: value } }));
  const addRentComp = () => setInputs((prev) => ({
    ...prev,
    rent_comps: [
      ...(prev.rent_comps || []),
      { facility: '', size: '', asking_rent: '', rent_per_sqft: '', distance_mi: '', notes: '' },
    ],
  }));
  const patchRentComp = (index, key, value) => setInputs((prev) => ({
    ...prev,
    rent_comps: (prev.rent_comps || []).map((row, rowIndex) => (
      rowIndex === index ? { ...row, [key]: value } : row
    )),
  }));
  const removeRentComp = (index) => setInputs((prev) => ({
    ...prev,
    rent_comps: (prev.rent_comps || []).filter((_, rowIndex) => rowIndex !== index),
  }));

  const handleOpenSource = (citation) => {
    setActiveCitation(citation);
    setShowSourcePanel(true);
    setLeftCollapsed(true);
  };

  const closeSourcePanel = () => {
    setShowSourcePanel(false);
    setActiveCitation(null);
  };

  // Shared onOpenSource handler passed to every NumericField → AIPrefilledField
  const onOpenSource = (citation) => handleOpenSource(citation);

  const tabProgress = computeTabProgress(inputs, projectData);

  // Tabs content extracted so it can be shared between collapsed/expanded layouts
  const inputTabs = (
    <UnderwritingSection
      eyebrow="Inputs"
      title="Review and refine the model"
      description="Each section is organized around one job: acquisition assumptions, operating performance, debt structure, or decision thresholds."
      className="underwriting-panel-strong"
    >
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="uw-tabs-grid h-auto p-0 rounded-none border-none bg-transparent">
          {TAB_CONFIG.map((tab) => (
            <TabsTrigger
              key={tab.id}
              value={tab.id}
              className="uw-tab-btn"
            >
              <span className="uw-tab-label">{tab.label}</span>
              <span className="uw-tab-desc">{tab.desc}</span>
            </TabsTrigger>
          ))}
        </TabsList>
        {/* Confidence legend */}
        <div className="flex items-center gap-3 px-1 pt-2 pb-1 text-[10px] text-muted-foreground">
          <span>AI confidence:</span>
          {[
            ['hsl(var(--uw-success))', '≥90%'],
            ['hsl(var(--uw-risk))', '70–89%'],
            ['hsl(var(--uw-danger))', '<70%'],
          ].map(([color, label]) => (
            <span key={label} className="flex items-center gap-1">
              <span style={{ background: color }} className="inline-block h-1.5 w-1.5 rounded-full" />
              {label}
            </span>
          ))}
          {citationCount > 0 && (
            <span className="ml-auto font-semibold text-uw-citation">
              {citationCount} fields cited · AI extracted
            </span>
          )}
        </div>

        <TabsContent value="acquisition" className="mt-6 animate-fade-in">
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <NumericField label="Purchase Price" value={inputs.acquisition.purchase_price} onChange={(v) => patchAcq('purchase_price', v)} placeholder="5,000,000" prefix="$" citation={getCitation('purchase_price')} onOpenSource={onOpenSource} />
            <NumericField label="Closing Cost" value={inputs.acquisition.closing_cost_pct} onChange={(v) => patchAcq('closing_cost_pct', v)} placeholder="2" suffix="%" citation={getCitation('closing_cost_pct')} onOpenSource={onOpenSource} />
            <NumericField label="Market Cap Rate Purchase" value={inputs.acquisition.market_cap_rate_purchase} onChange={(v) => patchAcq('market_cap_rate_purchase', v)} placeholder="6.0" suffix="%" citation={getCitation('market_cap_rate_purchase')} onOpenSource={onOpenSource} />
            <NumericField label="CapEx Reserve / Unit" value={inputs.acquisition.capex_reserve_per_unit} onChange={(v) => patchAcq('capex_reserve_per_unit', v)} placeholder="0" prefix="$" suffix="/unit" citation={getCitation('capex_reserve_per_unit')} onOpenSource={onOpenSource} />
            <FieldGroup label="Property" />
              <NumericField 
                label="Total Units" 
                value={projectData.num_units ?? ''} 
                onChange={(v) => patchProject('num_units', v === '' ? '' : parseInt(v, 10) || '')}
                citation={getCitation('num_units')} 
                onOpenSource={onOpenSource} 
              />
              <NumericField 
                label="Rentable Sq Ft" 
                value={projectData.rentable_sqft ?? ''} 
                onChange={(v) => patchProject('rentable_sqft', v)} 
                suffix="sqft" 
                citation={getCitation('rentable_sqft')} 
                onOpenSource={onOpenSource} 
              />
          </div>
        </TabsContent>

        <TabsContent value="operations" className="mt-6 animate-fade-in">
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <FieldGroup label="Revenue" />
            <NumericField label="Gross Potential Rent (Annual)" value={inputs.operational.gross_potential_rent_annual} onChange={(v) => patchOp('gross_potential_rent_annual', v)} placeholder="600,000" prefix="$" citation={getCitation('gross_potential_rent_annual')} onOpenSource={onOpenSource} />
            <NumericField label="Avg Current Rent / Door / Mo" value={inputs.operational.avg_in_place_rent_per_unit_monthly} onChange={(v) => patchOp('avg_in_place_rent_per_unit_monthly', v)} placeholder="115" prefix="$" citation={getCitation('avg_in_place_rent_per_unit_monthly')} onOpenSource={onOpenSource} />
            <NumericField label="Avg Market Rent / Door / Mo" value={inputs.operational.avg_market_rent_per_unit_monthly} onChange={(v) => patchOp('avg_market_rent_per_unit_monthly', v)} placeholder="132" prefix="$" citation={getCitation('avg_market_rent_per_unit_monthly')} onOpenSource={onOpenSource} />
            <NumericField label="Other Income (Annual)" value={inputs.operational.other_income_annual} onChange={(v) => patchOp('other_income_annual', v)} placeholder="0" prefix="$" citation={getCitation('other_income_annual')} onOpenSource={onOpenSource} />
            <NumericField label="Vacancy & Credit Loss" value={inputs.operational.vacancy_credit_loss_pct} onChange={(v) => patchOp('vacancy_credit_loss_pct', v)} placeholder="10" suffix="%" citation={getCitation('vacancy_credit_loss_pct')} onOpenSource={onOpenSource} />
            <NumericField label="Current Expense Ratio" value={inputs.operational.expense_ratio_current} onChange={(v) => patchOp('expense_ratio_current', v)} placeholder="41" suffix="%" citation={getCitation('expense_ratio_current')} onOpenSource={onOpenSource} />
            <NumericField label="Pro Forma Expense Ratio" value={inputs.operational.expense_ratio_pro_forma} onChange={(v) => patchOp('expense_ratio_pro_forma', v)} placeholder="34" suffix="%" citation={getCitation('expense_ratio_pro_forma')} onOpenSource={onOpenSource} />
            <NumericField label="Bad Debt (Annual)" value={inputs.operational.bad_debt_annual} onChange={(v) => patchOp('bad_debt_annual', v)} placeholder="0" prefix="$" citation={getCitation('bad_debt_annual')} onOpenSource={onOpenSource} />
            <NumericField label="Corrections / Collections" value={inputs.operational.corrections_collections_annual} onChange={(v) => patchOp('corrections_collections_annual', v)} placeholder="0" prefix="$" citation={getCitation('corrections_collections_annual')} onOpenSource={onOpenSource} />
            <NumericField label="Rent Growth" value={inputs.operational.rent_growth_pct} onChange={(v) => patchOp('rent_growth_pct', v)} placeholder="3" suffix="%" citation={getCitation('rent_growth_pct')} onOpenSource={onOpenSource} />
            <FieldGroup label="Operating Expenses" />
            <NumericField label="Property Tax (Annual)" value={inputs.operational.property_tax_annual} onChange={(v) => patchOp('property_tax_annual', v)} placeholder="0" prefix="$" citation={getCitation('property_tax_annual')} onOpenSource={onOpenSource} />
            <NumericField label="Property Tax Growth" value={inputs.operational.property_tax_growth_pct} onChange={(v) => patchOp('property_tax_growth_pct', v)} placeholder="4" suffix="%" citation={getCitation('property_tax_growth_pct')} onOpenSource={onOpenSource} />
            <NumericField label="Mil Rate" value={inputs.operational.mil_rate} onChange={(v) => patchOp('mil_rate', v)} placeholder="28.5" suffix="mills" citation={getCitation('mil_rate')} onOpenSource={onOpenSource} />
            <NumericField label="Insurance (Annual)" value={inputs.operational.insurance_annual} onChange={(v) => patchOp('insurance_annual', v)} placeholder="0" prefix="$" citation={getCitation('insurance_annual')} onOpenSource={onOpenSource} />
            <NumericField label="Mgmt Fee" value={inputs.operational.mgmt_fee_pct} onChange={(v) => patchOp('mgmt_fee_pct', v)} placeholder="8" suffix="%" citation={getCitation('mgmt_fee_pct')} onOpenSource={onOpenSource} />
            <NumericField label="Payroll (Annual)" value={inputs.operational.payroll_annual} onChange={(v) => patchOp('payroll_annual', v)} placeholder="0" prefix="$" citation={getCitation('payroll_annual')} onOpenSource={onOpenSource} />
            <NumericField label="Repairs & Maintenance" value={inputs.operational.repairs_maintenance_annual} onChange={(v) => patchOp('repairs_maintenance_annual', v)} placeholder="0" prefix="$" citation={getCitation('repairs_maintenance_annual')} onOpenSource={onOpenSource} />
            <NumericField label="Utilities (Annual)" value={inputs.operational.utilities_annual} onChange={(v) => patchOp('utilities_annual', v)} placeholder="0" prefix="$" citation={getCitation('utilities_annual')} onOpenSource={onOpenSource} />
            <NumericField label="Marketing (Annual)" value={inputs.operational.marketing_annual} onChange={(v) => patchOp('marketing_annual', v)} placeholder="0" prefix="$" citation={getCitation('marketing_annual')} onOpenSource={onOpenSource} />
            <NumericField label="Other OpEx (Annual)" value={inputs.operational.other_opex_annual} onChange={(v) => patchOp('other_opex_annual', v)} placeholder="0" prefix="$" citation={getCitation('other_opex_annual')} onOpenSource={onOpenSource} />
            <NumericField label="OpEx Growth" value={inputs.operational.opex_growth_pct} onChange={(v) => patchOp('opex_growth_pct', v)} placeholder="2" suffix="%" citation={getCitation('opex_growth_pct')} onOpenSource={onOpenSource} />

            {/* Value-Add Evidence — collapsible, read-only display from OM extraction */}
            <div className="col-span-full">
              <button
                type="button"
                onClick={() => setShowValueAdd((v) => !v)}
                className="flex w-full items-center gap-2 rounded-xl border border-border/60 bg-muted/40 px-3 py-2 text-left text-xs font-semibold uppercase tracking-[0.15em] text-muted-foreground hover:bg-muted/70 transition-colors"
              >
                {showValueAdd ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                Value-Add Evidence
                {getCitation('physical_occupancy_pct') || getCitation('below_market_tenant_pct') ? (
                  <span className="ml-auto flex items-center gap-1 text-uw-citation normal-case tracking-normal">
                    <Sparkles className="h-3 w-3" />
                    AI extracted
                  </span>
                ) : null}
              </button>
            </div>

            {showValueAdd ? (
              <>
                {(() => {
                  const omData = currentRun?.result_artifact?.om_data ?? {};
                  const fmt = (v, suffix) => v != null ? `${typeof v === 'number' && suffix === '%' ? (v * 100).toFixed(1) : Number(v).toLocaleString()}${suffix ?? ''}` : '—';
                  return (
                    <>
                      <div className="col-span-full grid grid-cols-1 gap-4 xl:grid-cols-2">
                        <div>
                          <AIPrefilledField label="Physical Occupancy (stated)" citation={getCitation('physical_occupancy_pct')} onOpenSource={onOpenSource}>
                            <div className="h-10 flex items-center px-3 rounded-lg border border-border/60 bg-muted/30 text-sm text-foreground">
                              {fmt(omData.physical_occupancy_pct, '%')}
                            </div>
                          </AIPrefilledField>
                        </div>
                        <div>
                          <AIPrefilledField label="Below-Market Tenants" citation={getCitation('below_market_tenant_pct')} onOpenSource={onOpenSource}>
                            <div className="h-10 flex items-center px-3 rounded-lg border border-border/60 bg-muted/30 text-sm text-foreground">
                              {fmt(omData.below_market_tenant_pct, '%')}
                            </div>
                          </AIPrefilledField>
                        </div>
                        <div>
                          <AIPrefilledField label="Monthly Rent Gap (below-mkt)" citation={getCitation('below_market_monthly_variance')} onOpenSource={onOpenSource}>
                            <div className="h-10 flex items-center px-3 rounded-lg border border-border/60 bg-muted/30 text-sm text-foreground">
                              {fmt(omData.below_market_monthly_variance, '/mo')}
                            </div>
                          </AIPrefilledField>
                        </div>
                        <div>
                          <AIPrefilledField label="Annual Upside to Market" citation={getCitation('below_market_annual_upside')} onOpenSource={onOpenSource}>
                            <div className="h-10 flex items-center px-3 rounded-lg border border-border/60 bg-muted/30 text-sm text-foreground">
                              {fmt(omData.below_market_annual_upside, '/yr')}
                            </div>
                          </AIPrefilledField>
                        </div>
                        {omData.income_basis_months != null ? (
                          <div>
                            <AIPrefilledField label="Income Statement Basis" citation={getCitation('income_basis_months')} onOpenSource={onOpenSource}>
                              <div className="h-10 flex items-center px-3 rounded-lg border border-border/60 bg-muted/30 text-sm text-foreground">
                                T-{omData.income_basis_months}
                              </div>
                            </AIPrefilledField>
                          </div>
                        ) : null}
                      </div>
                      {omData.value_add_notes ? (
                        <div className="col-span-full">
                          <p className="mb-1 text-xs font-medium text-muted-foreground">Value-Add Notes (from OM)</p>
                          <div className="rounded-xl border border-border/60 bg-muted/30 p-3 text-sm text-foreground leading-relaxed">
                            {omData.value_add_notes}
                          </div>
                        </div>
                      ) : null}
                    </>
                  );
                })()}
              </>
            ) : null}
          </div>
        </TabsContent>

        {(() => {
          const milRateVal = inputs.operational.mil_rate;
          const purchasePriceVal = inputs.acquisition.purchase_price;
          const currentTaxVal = inputs.operational.property_tax_annual;
          if (!milRateVal || !purchasePriceVal || !currentTaxVal) return null;
          // mil rate is per $1,000 of assessed value; Oklahoma typically assesses at ~11% of market
          const estimatedAssessed = purchasePriceVal * 0.11;
          const estimatedTax = (milRateVal / 1000) * estimatedAssessed;
          const delta = estimatedTax - currentTaxVal;
          if (delta < 2000) return null; // not worth flagging small differences
          return (
            <div className="xl:col-span-2 rounded-2xl border border-warning/30 bg-warning/8 p-3 text-sm text-muted-foreground">
              <span className="font-medium text-foreground">Reassessment note: </span>
              At the {milRateVal} mil rate and {(0.11 * 100).toFixed(0)}% assessment ratio, 
              post-acquisition property tax could be approximately{' '}
              <span className="font-semibold text-foreground">
                ${Math.round(estimatedTax).toLocaleString()}
              </span>
              {' '}vs the currently stated{' '}
              <span className="font-semibold text-foreground">
                ${Math.round(currentTaxVal).toLocaleString()}
              </span>. 
              Verify with the county assessor.
            </div>
          );
        })()}

        {/* T-6 income basis warning */}
        {currentRun?.result_artifact?.om_data?.income_basis_months === 6 ? (
          <Alert className="mb-4 border-warning/40 bg-warning/10">
            <AlertCircle className="h-4 w-4 text-warning" />
            <AlertDescription className="text-sm text-muted-foreground">
              Income figures are based on a trailing 6-month statement, annualized by the broker. 
              Consider requesting a full T-12 before closing.
            </AlertDescription>
          </Alert>
        ) : null}

        <TabsContent value="market" className="mt-6 animate-fade-in">
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <FieldGroup label="Nearby Facilities" />
            <NumericField label="Nearby Storage Facilities (1 mi)" value={projectData.nearby_storage_count_1mi} onChange={(v) => patchProject('nearby_storage_count_1mi', v)} citation={getCitation('nearby_storage_count_1mi')} onOpenSource={onOpenSource} />
            <NumericField label="Nearby Storage Facilities (3 mi)" value={projectData.nearby_storage_count_3mi} onChange={(v) => patchProject('nearby_storage_count_3mi', v)} citation={getCitation('nearby_storage_count_3mi')} onOpenSource={onOpenSource} />
            <NumericField label="Nearby Storage Facilities (5 mi)" value={projectData.nearby_storage_count_5mi} onChange={(v) => patchProject('nearby_storage_count_5mi', v)} citation={getCitation('nearby_storage_count_5mi')} onOpenSource={onOpenSource} />
            <FieldGroup label="Demographics" />
            <NumericField label="Population (3 mi)" value={projectData.population_3mi} onChange={(v) => patchProject('population_3mi', v)} citation={getCitation('population_3mi')} onOpenSource={onOpenSource} />
            <NumericField label="Avg Household Income (3 mi)" value={projectData.avg_household_income_3mi} onChange={(v) => patchProject('avg_household_income_3mi', v)} prefix="$" citation={getCitation('avg_household_income_3mi')} onOpenSource={onOpenSource} />
            <NumericField label="Storage Sq Ft / Capita" value={projectData.storage_sqft_per_capita_3mi} onChange={(v) => patchProject('storage_sqft_per_capita_3mi', v)} suffix="sqft" citation={getCitation('storage_sqft_per_capita_3mi')} onOpenSource={onOpenSource} />
            <FieldGroup label="Tight Comp Set" />
            <div className={`xl:col-span-2 rounded-2xl border p-4 ${rentCompsCitation ? 'border-green-500/40 bg-green-500/5' : 'border-border/60 bg-background/60'}`}>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold text-foreground">Nearby rent comps</p>
                    {rentCompsCitation ? <Sparkles className="h-3.5 w-3.5 text-uw-citation" /> : null}
                    {rentCompsCitation ? <span className="text-[11px] font-medium uppercase tracking-[0.16em] text-uw-citation">AI extracted</span> : null}
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">Add your tight comp set manually, or review rows extracted from OM competitive-set tables.</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {rentCompsCitation ? (
                    <Button type="button" variant="ghost" size="sm" className="h-8 rounded-full px-3 text-[11px] font-semibold text-uw-citation hover:bg-background/70" onClick={() => onOpenSource(rentCompsCitation)}>
                      Source
                    </Button>
                  ) : null}
                  <Button type="button" variant="outline" size="sm" className="gap-2" onClick={addRentComp}>
                    <Plus className="h-4 w-4" />
                    Add comp
                  </Button>
                </div>
              </div>

              {(inputs.rent_comps || []).length > 0 ? (
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full min-w-[1120px] text-sm">
                    <colgroup>
                      <col className="w-[180px]" />
                      <col className="w-[180px]" />
                      <col className="w-[120px]" />
                      <col className="w-[120px]" />
                      <col className="w-[120px]" />
                      <col className="w-[320px]" />
                      <col className="w-[72px]" />
                    </colgroup>
                    <thead>
                      <tr className="border-b border-border/70 text-left text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                        <th className="pb-3">Facility</th>
                        <th className="pb-3">Size</th>
                        <th className="pb-3 text-right">Rent/Unit</th>
                        <th className="pb-3 text-right">Rent/Sq Ft</th>
                        <th className="pb-3 text-right">Distance</th>
                        <th className="pb-3">Notes</th>
                        <th className="pb-3 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(inputs.rent_comps || []).map((row, index) => (
                        <tr key={`rent-comp-${index}`} className="border-b border-border/50 align-top last:border-b-0">
                          <td className="py-3 pr-3">
                            <Input value={row.facility ?? ''} onChange={(e) => patchRentComp(index, 'facility', e.target.value)} className="h-9" />
                          </td>
                          <td className="py-3 pr-3">
                            <Input value={row.size ?? ''} onChange={(e) => patchRentComp(index, 'size', e.target.value)} className="h-9" />
                          </td>
                          <td className="py-3 pr-3">
                            <Input type="number" value={row.asking_rent ?? ''} onChange={(e) => patchRentComp(index, 'asking_rent', e.target.value === '' ? '' : parseFloat(e.target.value) || '')} className="h-9 text-right" />
                          </td>
                          <td className="py-3 pr-3">
                            <Input type="number" value={row.rent_per_sqft ?? ''} onChange={(e) => patchRentComp(index, 'rent_per_sqft', e.target.value === '' ? '' : parseFloat(e.target.value) || '')} className="h-9 text-right" />
                          </td>
                          <td className="py-3 pr-3">
                            <Input type="number" value={row.distance_mi ?? ''} onChange={(e) => patchRentComp(index, 'distance_mi', e.target.value === '' ? '' : parseFloat(e.target.value) || '')} className="h-9 text-right" />
                          </td>
                          <td className="py-3 pr-3 align-top">
                            <Textarea value={row.notes ?? ''} onChange={(e) => patchRentComp(index, 'notes', e.target.value)} className="min-h-[92px] min-w-[320px] resize-y leading-5" />
                          </td>
                          <td className="py-3 text-right">
                            <Button type="button" variant="ghost" size="icon" onClick={() => removeRentComp(index)} title="Remove comp">
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="mt-4 rounded-2xl border border-dashed border-border/70 bg-background/40 p-4 text-sm text-muted-foreground">
                  No rent comps yet. Add a tight comp set manually or run OM extraction on a package with a competitive-set table.
                </div>
              )}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="debtExit" className="mt-6 animate-fade-in">
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <FieldGroup label="Debt" />
            <NumericField label="Interest Rate" value={inputs.financing.interest_rate_pct} onChange={(v) => patchFin('interest_rate_pct', v)} suffix="%" citation={getCitation('interest_rate_pct')} onOpenSource={onOpenSource} />
            <NumericField label="Loan Term" value={inputs.financing.loan_term_years} onChange={(v) => patchFin('loan_term_years', v)} suffix="yrs" citation={getCitation('loan_term_years')} onOpenSource={onOpenSource} />
            <NumericField label="Amortization" value={inputs.financing.amortization_years} onChange={(v) => patchFin('amortization_years', v)} suffix="yrs" citation={getCitation('amortization_years')} onOpenSource={onOpenSource} />
            <NumericField label="LTV" value={inputs.financing.ltv_pct} onChange={(v) => patchFin('ltv_pct', v)} suffix="%" citation={getCitation('ltv_pct')} onOpenSource={onOpenSource} />
            <div className="xl:col-span-2 rounded-2xl border border-border/60 bg-background/60 p-3 text-sm text-muted-foreground">
              Debt sizing is derived from purchase price and LTV in the current model. Loan amount is not edited separately.
            </div>
            <FieldGroup label="Exit" />
            <NumericField label="Hold Period" value={inputs.exit.hold_period_years} onChange={(v) => patchExit('hold_period_years', v)} suffix="yrs" citation={getCitation('hold_period_years')} onOpenSource={onOpenSource} />
            <NumericField label="Market Cap Rate Sale" value={inputs.exit.market_cap_rate_sale} onChange={(v) => patchExit('market_cap_rate_sale', v)} suffix="%" citation={getCitation('market_cap_rate_sale')} onOpenSource={onOpenSource} />
            <NumericField label="Exit Cap Rate" value={inputs.exit.exit_cap_rate} onChange={(v) => patchExit('exit_cap_rate', v)} suffix="%" citation={getCitation('exit_cap_rate')} onOpenSource={onOpenSource} />
            <NumericField label="Selling Cost" value={inputs.exit.selling_cost_pct} onChange={(v) => patchExit('selling_cost_pct', v)} suffix="%" citation={getCitation('selling_cost_pct')} onOpenSource={onOpenSource} />
          </div>
        </TabsContent>

        <TabsContent value="criteria" className="mt-6 animate-fade-in">
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <FieldGroup label="Return Thresholds" />
            <NumericField label="Target IRR" value={inputs.criteria.target_irr} onChange={(v) => patchCrit('target_irr', v)} suffix="%" citation={getCitation('target_irr')} onOpenSource={onOpenSource} />
            <NumericField label="Target Cash-on-Cash" value={inputs.criteria.target_cash_on_cash} onChange={(v) => patchCrit('target_cash_on_cash', v)} suffix="%" citation={getCitation('target_cash_on_cash')} onOpenSource={onOpenSource} />
            <NumericField label="Target Equity Multiple" value={inputs.criteria.target_equity_multiple} onChange={(v) => patchCrit('target_equity_multiple', v)} suffix="×" citation={getCitation('target_equity_multiple')} onOpenSource={onOpenSource} />
            <NumericField label="Max LTV" value={inputs.criteria.max_ltv} onChange={(v) => patchCrit('max_ltv', v)} suffix="%" citation={getCitation('max_ltv')} onOpenSource={onOpenSource} />
          </div>
        </TabsContent>
      </Tabs>

      <div className="underwriting-action-bar mt-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-end gap-4">
            {TAB_CONFIG.map((t) => {
              const pct = tabProgress[t.id] ?? 0;
              return (
                <div
                  key={t.id}
                  className="flex cursor-pointer flex-col gap-1"
                  onClick={() => setActiveTab(t.id)}
                >
                  <span className={`text-[10px] font-semibold ${t.id === activeTab ? 'text-foreground' : 'text-muted-foreground/60'}`}>
                    {t.label}
                  </span>
                  <div className="uw-tab-progress-bar">
                    <div
                      className="uw-tab-progress-fill"
                      data-complete={pct === 100 ? 'true' : undefined}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            {(currentRun?.status === 'completed' || runIdFromUrl) ? (
              <Button variant="outline" onClick={() => navigate(`/app/re/underwriting/${currentRun?.id || currentRun?.run_id || runIdFromUrl}`)} className="gap-2">
                <BarChart2 className="h-4 w-4" />
                View results
              </Button>
            ) : (
              <Button
                variant="outline"
                onClick={() => {
                  const idx = TAB_CONFIG.findIndex((t) => t.id === activeTab);
                  if (idx < TAB_CONFIG.length - 1) setActiveTab(TAB_CONFIG[idx + 1].id);
                }}
                disabled={activeTab === TAB_CONFIG[TAB_CONFIG.length - 1].id}
              >
                Next section
                <ArrowRight className="ml-1.5 h-4 w-4" />
              </Button>
            )}
            <Button onClick={handleSaveAndCalculate} disabled={isSubmitting || !projectData.name.trim()} className="gap-2">
              {isSubmitting ? <><Loader2 className="h-4 w-4 animate-spin" />Saving...</> : <><TrendingUp className="h-4 w-4" />Save & calculate</>}
            </Button>
          </div>
        </div>
      </div>
    </UnderwritingSection>
  );

  return (
    <AppLayout
      lockViewport
      headerLeft={(
        <button
          onClick={() => navigate('/app/re/underwriting')}
          className="flex items-center gap-1.5 bg-transparent p-0 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronLeft size={14} />
          All deals
        </button>
      )}
    >
      <ResizablePanelGroup
        key={showSourcePanel ? 'uw-split-open' : 'uw-split-closed'}
        direction="horizontal"
        className="h-full min-w-0"
      >
        {/* ── Main content panel ── */}
        <ResizablePanel id="uw-main" order={1} defaultSize={showSourcePanel ? 58 : 100} minSize={40}>
          <div className="h-full overflow-y-auto">
            <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6 sm:py-8">
              <div className="underwriting-shell page-enter p-4 sm:p-6">

                {/* Header */}
                <div className="border-b border-border/60 pb-6">
                  <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
                    <div className="min-w-0 flex-1">
                      <p className="underwriting-kicker">Underwriting setup</p>
                      <div className="mt-3 flex items-start gap-4">
                        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-[1.25rem] bg-primary/10 text-primary">
                          <Building2 className="h-5 w-5" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <input
                            value={projectData.name}
                            placeholder="Deal name or property name"
                            onChange={(e) => setProjectData({ ...projectData, name: e.target.value })}
                            className="w-full bg-transparent p-0 font-display text-3xl font-semibold tracking-tight text-foreground outline-none placeholder:text-muted-foreground/50"
                          />
                          <p className="underwriting-subtitle mt-2">
                            Start from source documents, let AI draft the assumptions, then tighten the model before running the analysis.
                          </p>
                          <input
                            placeholder="Property address (optional)"
                            value={projectData.address}
                            onChange={(e) => setProjectData({ ...projectData, address: e.target.value })}
                            className="mt-3 w-full bg-transparent p-0 text-sm text-muted-foreground outline-none placeholder:text-muted-foreground/55"
                          />
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 xl:justify-end">
                      <UnderwritingStatusBadge tone={citationCount > 0 ? 'success' : 'neutral'}>
                        {citationCount > 0 ? `${citationCount} cited fields` : 'Manual draft'}
                      </UnderwritingStatusBadge>
                      <UnderwritingStatusBadge tone={extractionDone ? 'success' : anyDocSelected ? 'active' : 'neutral'}>
                        {extractionDone ? 'AI extracted' : anyDocSelected ? 'Docs attached' : 'Awaiting documents'}
                      </UnderwritingStatusBadge>
                    </div>
                  </div>
                </div>

                {error ? (
                  <Alert variant="destructive" className="mt-5">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                ) : null}

                {/* Body: collapsible left rail + inputs */}
                <div className="relative mt-6 flex gap-5">
                  {/* Collapsible left rail */}
                  <div className={`hidden lg:flex flex-shrink-0 flex-col overflow-hidden border-r border-border/60 bg-card transition-all duration-300 ${leftCollapsed ? 'w-[52px]' : 'w-[300px] xl:w-[320px]'}`}>
                    <WorkflowRail
                      selectedDocs={selectedDocs}
                      anyDocSelected={anyDocSelected}
                      hasOmForExtraction={hasOmForExtraction}
                      extraction={extraction}
                      extractionDone={extractionDone}
                      handleRunExtraction={handleRunExtraction}
                      isExtracting={isExtracting}
                      projectName={projectData.name}
                      currentRun={currentRun}
                      citationCount={citationCount}
                      setDocPickerOpen={setDocPickerOpen}
                      setSelectedDocs={setSelectedDocs}
                      leftCollapsed={leftCollapsed}
                      setLeftCollapsed={setLeftCollapsed}
                    />
                  </div>


                  {/* Inputs */}
                  <div className="min-w-0 flex-1">
                    {inputTabs}
                  </div>
                </div>

              </div>
            </div>
          </div>
        </ResizablePanel>

        {/* ── Resize handle + right source panel ── */}
        {showSourcePanel && (
          <ResizableHandle withHandle />
        )}
        {showSourcePanel && (
          <ResizablePanel id="uw-source" order={2} defaultSize={42} minSize={28}>
            <SourceDocumentPanel citation={activeCitation} isOpen={showSourcePanel} onClose={closeSourcePanel} />
          </ResizablePanel>
        )}
      </ResizablePanelGroup>

      {DOC_SLOTS.map((slot) => (
        <DocumentSelectorDialog
          key={slot.key}
          open={docPickerOpen === slot.key}
          onOpenChange={(open) => !open && setDocPickerOpen(null)}
          onSelect={({ document }) => handleDocumentSelect(slot.key, document)}
          templateName={slot.label}
        />
      ))}
    </AppLayout>
  );
}
