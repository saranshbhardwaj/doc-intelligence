import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  AlertCircle,
  ChevronLeft,
  Loader2,
  Trash2,
  Warehouse,
} from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { UnderwritingWizardSkeleton } from '../../../components/skeletons/PageSkeletons';
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
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from '@/components/ui/resizable';
import AppLayout from '../../../components/layout/AppLayout';
import { useAppAuth } from '../../../hooks/useAppAuth';
import { useUnderwritingActions, useUnderwritingCurrentRun, useUnderwritingExtraction } from '../../../store';
import {
  createUnderwritingRun,
  deleteUnderwritingRun,
  startUnderwritingExtraction,
  streamUnderwritingExtractionProgress,
  updateUnderwritingInputs,
  updateUnderwritingRunMetadata,
} from '../../../api/re-underwriting';
import { fromApiInputs, toApiInputs } from '../utils/underwritingInputs';
import { streamJobProgress } from '../../../api/sse-utils';
import DocumentSelectorDialog from '../components/DocumentSelectorDialog';
import {
  buildExtractionDocuments,
  hydrateProjectDataFromRun,
  buildSelectedDoc,
  buildSelectedDocsFromRun,
  EMPTY_UNDERWRITING_DOCS,
} from '../utils/underwritingDocuments';
import {
  DOC_SLOTS,
  INITIAL_PROJECT_DATA,
  SourceDocumentPanel,
  TAB_CONFIG,
  UnderwritingDefaultsModal,
  WorkflowRail,
  WizardInputStage,
  countVisibleCitations,
  createDefaultInputs,
  computeTabProgress,
} from '../components/underwriting';
import { getMyThresholds } from '../../../api/users';
import { toast } from 'sonner';

function WorkspaceMark() {
  return (
    <div className="underwriting-brand-mark">
      <Warehouse className="h-4 w-4" aria-hidden="true" />
    </div>
  );
}

const UNDERWRITING_SOURCE_EXTENSIONS = {
  om: ['pdf', 'docx', 'pptx', 'jpg', 'jpeg', 'png', 'bmp', 'tif', 'tiff', 'heif', 'heic'],
  t12: ['pdf', 'docx', 'pptx', 'xlsx', 'xlsm', 'csv', 'jpg', 'jpeg', 'png', 'bmp', 'tif', 'tiff', 'heif', 'heic'],
  rent_roll: ['pdf', 'docx', 'pptx', 'xlsx', 'xlsm', 'csv', 'jpg', 'jpeg', 'png', 'bmp', 'tif', 'tiff', 'heif', 'heic'],
};

const EMPTY_SELECTED_DOCS = EMPTY_UNDERWRITING_DOCS;

function valuesEqual(left, right) {
  if ((left == null || left === '') && (right == null || right === '')) return true;
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
    return Math.abs(leftNumber - rightNumber) < 0.0000001;
  }
  return left === right;
}

function citationLookup(citations, fieldKey) {
  if (!citations) return null;
  return citations[fieldKey]
    ?? citations[`om.${fieldKey}`]
    ?? citations[`t12.${fieldKey}`]
    ?? citations[`rent_roll.${fieldKey}`]
    ?? null;
}

function toManualCitation(existingCitation, previousValue) {
  const existing = existingCitation && typeof existingCitation === 'object' ? existingCitation : null;
  const originalCitation = existing?.is_manual ? existing.original_citation : existing;
  return {
    doc_type: 'manual',
    source: 'manual',
    is_manual: true,
    manual_override: true,
    confidence: null,
    citations: [],
    source_text: null,
    original_value: existing?.is_manual ? existing.original_value : previousValue,
    original_citation: originalCitation ?? null,
    selection_note: 'Analyst manually updated this field.',
  };
}

export default function UnderwritingWizard() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const runIdFromUrl = searchParams.get('run_id');
  const { getToken } = useAppAuth();
  const currentRun = useUnderwritingCurrentRun();
  const extraction = useUnderwritingExtraction();
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
  const savedMeta = useRef({ name: "", address: null });
  const hydratedInputsKey = useRef(null);
  const [selectedDocs, setSelectedDocs] = useState(EMPTY_SELECTED_DOCS);
  const [docPickerOpen, setDocPickerOpen] = useState(null);
  const [activeTab, setActiveTab] = useState(TAB_CONFIG[0].id);

  const [inputs, setInputs] = useState(createDefaultInputs);
  const [draftFieldCitations, setDraftFieldCitations] = useState(null);
  const [isExtracting, setIsExtracting] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [savingMeta, setSavingMeta] = useState(false);
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
    setDraftFieldCitations(null);
    setSelectedDocs(EMPTY_SELECTED_DOCS);
    setDocPickerOpen(null);
    setActiveTab(TAB_CONFIG[0].id);
    setIsExtracting(false);
    setIsSubmitting(false);
    setError(null);
    setLeftCollapsed(false);
    setShowSourcePanel(false);
    setActiveCitation(null);
    savedMeta.current = { name: "", address: null };
    hydratedInputsKey.current = null;
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

  // For new runs only: prefill criteria from saved user defaults.
  useEffect(() => {
    if (runIdFromUrl) return;
    let active = true;
    getMyThresholds(getToken).then(saved => {
      if (!active || !saved || !Object.keys(saved).length) return;
      setInputs(prev => ({
        ...prev,
        criteria: {
          ...prev.criteria,
          ...(saved.target_irr != null && { target_irr: saved.target_irr * 100 }),
          ...(saved.target_cash_on_cash != null && { target_cash_on_cash: saved.target_cash_on_cash * 100 }),
          ...(saved.target_equity_multiple != null && { target_equity_multiple: saved.target_equity_multiple }),
          ...(saved.max_ltv != null && { max_ltv: saved.max_ltv * 100 }),
          ...(saved.dscr_year_one_floor != null && { dscr_year_one_floor: saved.dscr_year_one_floor }),
          ...(saved.stress_dscr_floor != null && { stress_dscr_floor: saved.stress_dscr_floor }),
          ...(saved.rollover_risk_pct != null && { rollover_risk_pct: saved.rollover_risk_pct * 100 }),
        },
      }));
    }).catch(() => {});
    return () => { active = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reconnect extraction stream after refresh/navigation if this run is still processing.
  // job_id === run_id in the backend, so runIdFromUrl is always the correct job ID.
  useEffect(() => {
    const isRunStillProcessing = currentRun?.status === 'extracting' || currentRun?.status === 'calculating';
    if (!runIdFromUrl || !isRunStillProcessing || isExtracting) return;
    if (extraction.isProcessing) return;

    let cancelled = false;

    const reconnect = async () => {
      setIsExtracting(true);
      // Guard: set to true when onComplete/onError fires during fetchInitialState,
      // before startExtraction is called. Without this, startExtraction re-sets
      // isProcessing=true after completeExtraction() already cleared it.
      let alreadyTerminated = false;
      try {
        const cleanup = await streamUnderwritingExtractionProgress(runIdFromUrl, getToken, {
          onProgress: (data) => {
            updateExtractionProgress({
              progress: data.progress_percent,
              stage: data.current_stage,
              message: data.message,
            });
          },
          onComplete: async () => {
            if (cancelled) return;
            alreadyTerminated = true;
            completeExtraction();
            await loadRun(getToken, runIdFromUrl);
            setWizardStep(2);
            setIsExtracting(false);
          },
          onError: (err) => {
            if (cancelled) return;
            alreadyTerminated = true;
            setError(err?.message || 'Extraction failed');
            setIsExtracting(false);
          },
        });

        if (cancelled) {
          cleanup?.();
          return;
        }

        // Only register the ongoing stream if the job wasn't already resolved
        // during fetchInitialState (avoids overwriting completeExtraction's work).
        if (!alreadyTerminated) {
          startExtraction(runIdFromUrl, cleanup);
        }
      } catch (err) {
        if (cancelled) return;
        setError(err?.message || 'Failed to reconnect extraction');
        setIsExtracting(false);
      }
    };

    reconnect();

    return () => {
      cancelled = true;
    };
  }, [
    completeExtraction,
    currentRun?.status,
    extraction.isProcessing,
    getToken,
    isExtracting,
    loadRun,
    runIdFromUrl,
    setWizardStep,
    startExtraction,
    updateExtractionProgress,
  ]);

  // When a run is loaded, hydrate source document slots even before extraction has created inputs.
  useEffect(() => {
    const currentRunId = currentRun?.id || currentRun?.run_id;
    if (!runIdFromUrl || !currentRun || String(currentRunId) !== String(runIdFromUrl)) {
      return;
    }

    if (currentRun.name || currentRun.address || currentRun.inputs?.project) {
      setProjectData((prev) => hydrateProjectDataFromRun(prev, currentRun));
      savedMeta.current = {
        name: currentRun.name || "",
        address: currentRun.address || currentRun.inputs?.project?.address || null,
      };
    }

    const hydratedDocs = buildSelectedDocsFromRun(currentRun);
    if (Object.values(hydratedDocs).some(Boolean)) {
      setSelectedDocs(hydratedDocs);
    }
  }, [
    runIdFromUrl,
    currentRun,
    currentRun?.id,
    currentRun?.run_id,
    currentRun?.name,
    currentRun?.address,
    currentRun?.inputs,
    currentRun?.document_ids,
    currentRun?.source_documents,
  ]);

  // When a run is loaded post-extraction, populate extracted inputs and citations.
  useEffect(() => {
    const currentRunId = currentRun?.id || currentRun?.run_id;
    if (!runIdFromUrl || !currentRun?.inputs || String(currentRunId) !== String(runIdFromUrl)) {
      return;
    }
    const runHydrationKey = [
      currentRunId,
      currentRun?.updated_at || currentRun?.completed_at || '',
      currentRun?.status || '',
    ].join(':');
    if (hydratedInputsKey.current === runHydrationKey) {
      return;
    }

    if (currentRun.name || currentRun.address || currentRun.inputs.project) {
      setProjectData((prev) => hydrateProjectDataFromRun(prev, currentRun));
      savedMeta.current = {
        name: currentRun.name || "",
        address: currentRun.address || currentRun.inputs.project?.address || null,
      };
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
    setDraftFieldCitations(currentRun.field_citations || null);
    hydratedInputsKey.current = runHydrationKey;
  }, [
    runIdFromUrl,
    currentRun,
    currentRun?.id,
    currentRun?.run_id,
    currentRun?.inputs,
    currentRun?.field_citations,
    currentRun?.updated_at,
    currentRun?.completed_at,
    currentRun?.status,
  ]);

  // Consider docs "attached" if user selected any in the UI OR the run already has documents from a prior extraction.
  const anyDocSelected = Object.values(selectedDocs).some(Boolean)
    || (currentRun?.document_ids?.length > 0)
    || !!runIdFromUrl;
  const extractionDocuments = buildExtractionDocuments(selectedDocs, currentRun?.document_ids);
  const hasOmForExtraction = Boolean(selectedDocs.om)
    || Boolean(extractionDocuments.some((doc) => doc.doc_type === 'om'));
  const extractionDone = currentRun?.inputs != null;

  const fieldCitations = draftFieldCitations ?? currentRun?.field_citations;
  const citCtx = currentRun?.citation_context;

  const citationCount = useMemo(() => countVisibleCitations(fieldCitations), [fieldCitations]);

  const getCitation = useMemo(() => (fieldKey) => {
    if (!fieldCitations) return null;
    const raw = citationLookup(fieldCitations, fieldKey);
    if (!raw) return null;
    if (raw.is_default || raw.is_derived || raw.is_uncited_extraction || !raw.citations?.length) {
      return { ...raw };
    }
    const token = raw.citations?.[0];
    const ctx = token && citCtx ? citCtx[token] : null;
    return {
      ...raw,
      page: ctx?.page ?? raw.page,
      document_id: ctx?.document_id ?? raw.document_id,
      filename: ctx?.filename ?? raw.filename,
      bbox: ctx?.bbox ?? raw.bbox ?? null,
    };
  }, [fieldCitations, citCtx]);
  const rentCompsCitation = getCitation('rent_comps');
  const analysisRunId = currentRun?.id || currentRun?.run_id || runIdFromUrl;

  const handleDeleteRun = async () => {
    if (!analysisRunId || isDeleting) return;
    setIsDeleting(true);
    setError(null);
    try {
      await deleteUnderwritingRun(getToken, analysisRunId);
      setCurrentRun(null);
      navigate('/app/re/underwriting');
    } catch (err) {
      console.error('Delete failed:', err);
      setError(err?.message || 'Failed to delete analysis');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleDocumentSelect = (docType, document) => {
    const selectedDoc = buildSelectedDoc(docType, document);
    if (selectedDoc) {
      setSelectedDocs((prev) => ({
        ...prev,
        [docType]: selectedDoc,
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
      const existingRunId = currentRun?.run_id || currentRun?.id || runIdFromUrl;
      const run = existingRunId
        ? await startUnderwritingExtraction(getToken, existingRunId, extractionDocuments)
        : await createUnderwritingRun(getToken, {
            name: projectData.name,
            asset_type: projectData.asset_type,
            address: projectData.address,
            documents: extractionDocuments,
          });

      setCurrentRun({
        ...(currentRun || {}),
        ...run,
        id: existingRunId || run.run_id,
        run_id: existingRunId || run.run_id,
        status: 'extracting',
        document_ids: extractionDocuments,
      });
      navigate(`/app/re/underwriting/new?run_id=${existingRunId || run.run_id}`, { replace: true });

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
          num_units: projectData.num_units,
          rentable_sqft: projectData.rentable_sqft,
          year_built: projectData.year_built,
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
        const nextName = projectData.name?.trim() || "";
        const nextAddress = projectData.address?.trim() || null;
        const metaChanged = nextName !== savedMeta.current.name
          || (nextAddress || "") !== (savedMeta.current.address || "");
        if (metaChanged) {
          await persistMeta(existingRunId, nextName, nextAddress);
        }
        await updateUnderwritingInputs(getToken, existingRunId, inputPayload, draftFieldCitations);
        navigate(`/app/re/underwriting/${existingRunId}`);
      } else {
        const run = await createUnderwritingRun(getToken, {
          name: projectData.name,
          asset_type: projectData.asset_type,
          address: projectData.address,
          documents: [],
        });
        await updateUnderwritingInputs(getToken, run.run_id, inputPayload, draftFieldCitations);
        navigate(`/app/re/underwriting/${run.run_id}`);
      }
    } catch (err) {
      setError(err.message || 'Failed to save');
    } finally {
      setIsSubmitting(false);
    }
  };

  async function persistMeta(runId, name, address) {
    await updateUnderwritingRunMetadata(getToken, runId, { name, address: address || null });
    savedMeta.current = { name, address: address || null };
  }

  async function handleSaveMeta() {
    if (!analysisRunId || !projectData.name?.trim()) return;
    setSavingMeta(true);
    try {
      await persistMeta(analysisRunId, projectData.name.trim(), projectData.address?.trim() || null);
      toast.success("Saved");
    } catch {
      toast.error("Failed to save — try again");
    } finally {
      setSavingMeta(false);
    }
  }

  const markManualCitation = (fieldKey, previousValue, nextValue) => {
    if (valuesEqual(previousValue, nextValue)) return;
    setDraftFieldCitations((prev) => {
      const next = { ...(prev || {}) };
      const existingCitation = citationLookup(next, fieldKey);
      const originalValue = existingCitation?.is_manual
        ? existingCitation.original_value
        : previousValue;

      if (valuesEqual(nextValue, originalValue)) {
        if (existingCitation?.is_manual && existingCitation.original_citation) {
          next[fieldKey] = existingCitation.original_citation;
        } else {
          delete next[fieldKey];
        }
        return next;
      }

      next[fieldKey] = toManualCitation(existingCitation, previousValue);
      return next;
    });
  };

  const createPatcher = (section) => (key, value) => {
    const previousValue = inputs?.[section]?.[key];
    markManualCitation(key, previousValue, value);
    setInputs((prev) => ({ ...prev, [section]: { ...prev[section], [key]: value } }));
  };
  const patchAcq = createPatcher('acquisition');
  const patchOp = createPatcher('operational');
  const patchFin = createPatcher('financing');
  const patchExit = createPatcher('exit');
  const patchCrit = createPatcher('criteria');
  const patchProject = (key, value) => {
    markManualCitation(key, projectData?.[key], value);
    setProjectData((prev) => ({ ...prev, [key]: value }));
  };
  const addRentComp = () => {
    markManualCitation('rent_comps', inputs.rent_comps, [...(inputs.rent_comps || []), {}]);
    setInputs((prev) => ({
      ...prev,
      rent_comps: [
        ...(prev.rent_comps || []),
        { facility: '', size: '', asking_rent: '', rent_per_sqft: '', distance_mi: '', notes: '' },
      ],
    }));
  };
  const patchRentComp = (index, key, value) => {
    const previousValue = inputs.rent_comps?.[index]?.[key];
    markManualCitation(`rent_comps.${index}.${key}`, previousValue, value);
    markManualCitation('rent_comps', inputs.rent_comps, (inputs.rent_comps || []).map((row, rowIndex) => (
      rowIndex === index ? { ...row, [key]: value } : row
    )));
    setInputs((prev) => ({
      ...prev,
      rent_comps: (prev.rent_comps || []).map((row, rowIndex) => (
        rowIndex === index ? { ...row, [key]: value } : row
      )),
    }));
  };
  const removeRentComp = (index) => {
    markManualCitation('rent_comps', inputs.rent_comps, (inputs.rent_comps || []).filter((_, rowIndex) => rowIndex !== index));
    setInputs((prev) => ({
      ...prev,
      rent_comps: (prev.rent_comps || []).filter((_, rowIndex) => rowIndex !== index),
    }));
  };

  const handleOpenSource = (citation) => {
    setActiveCitation(citation);
    setShowSourcePanel(true);
    setLeftCollapsed(true);
  };

  const closeSourcePanel = () => {
    setShowSourcePanel(false);
    setActiveCitation(null);
  };

  const tabProgress = useMemo(() => computeTabProgress(inputs, projectData), [inputs, projectData]);

  const navigateToResults = () => {
    navigate(`/app/re/underwriting/${currentRun?.id || currentRun?.run_id || runIdFromUrl}`);
  };

  const isMetaDirty =
    !!analysisRunId &&
    !!currentRun &&
    (projectData.name !== savedMeta.current.name ||
      (projectData.address || "") !== (savedMeta.current.address || ""));
  const acquisitionSource = currentRun?.source_metadata?.source === 'acquisition_candidate'
    ? currentRun.source_metadata
    : null;
  const acquisitionDocSummary = [
    selectedDocs.om ? 'OM attached' : 'OM missing',
    selectedDocs.rent_roll ? 'Rent roll attached' : 'Rent roll missing',
    selectedDocs.t12 ? 'T-12 attached' : 'T-12 missing',
  ].join(' · ');

  // Show skeleton while loading run data from URL
  if (runIdFromUrl && !currentRun) {
    return (
      <AppLayout lockViewport>
        <div className="h-full">
          <UnderwritingWizardSkeleton />
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
          className="flex items-center gap-1.5 bg-transparent p-0 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronLeft size={14} />
          All deals
        </button>
      )}
    >
      <ResizablePanelGroup
        direction="horizontal"
        className="h-full min-w-0"
      >
        {/* ── Main content panel ── */}
        <ResizablePanel id="uw-main" order={1} defaultSize={showSourcePanel ? 58 : 100} minSize={40}>
          <div className="h-full overflow-y-auto">
            <div className="mx-auto max-w-[90rem] px-3 py-7 sm:px-4 h-full">
            <div className="underwriting-shell flex flex-col flex-1 overflow-hidden">
              <div className="underwriting-topbar shrink-0 sm:mb-46">
                <div className="underwriting-topbar-row">
                  <div className="underwriting-topbar-main">
                    <WorkspaceMark />
                    <div className="underwriting-topbar-identity">
                      <p className="underwriting-kicker">Underwriting setup</p>
                      <input
                        value={projectData.name}
                        placeholder="Deal name or property name"
                        onChange={(e) => setProjectData({ ...projectData, name: e.target.value })}
                        className="uw-wizard-header-title"
                      />
                      <input
                        placeholder="Property address (optional)"
                        value={projectData.address}
                        onChange={(e) => setProjectData({ ...projectData, address: e.target.value })}
                        className="uw-wizard-header-address"
                      />
                      {isMetaDirty && (
                        <div className="mt-1.5">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleSaveMeta}
                            disabled={savingMeta || !projectData.name?.trim()}
                          >
                            {savingMeta && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                            Save name & address
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="uw-mode-switch justify-self-center">
                    <button type="button" className="uw-mode-btn uw-mode-btn-active">
                      Input
                    </button>
                    <button
                      type="button"
                      className="uw-mode-btn"
                      onClick={() => {
                        if (analysisRunId) navigate(`/app/re/underwriting/${analysisRunId}`);
                      }}
                      disabled={!analysisRunId}
                    >
                      Analysis
                    </button>
                  </div>

                  <div className="underwriting-topbar-actions">
                    <span className="uw-wizard-header-status-item text-uw-citation">
                      {citationCount > 0 ? `${citationCount} cited` : 'Manual draft'}
                    </span>
                    <span className="uw-wizard-header-status-item text-primary">
                      {extractionDone ? 'AI extracted' : anyDocSelected ? 'Docs attached' : 'Awaiting docs'}
                    </span>
                    {analysisRunId ? (
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-9 w-9 rounded-full text-destructive hover:bg-destructive/10 hover:text-destructive"
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
                              "{projectData?.name?.trim() || currentRun?.name || 'Untitled analysis'}" will be permanently deleted. This action cannot be undone.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction onClick={handleDeleteRun} className="bg-destructive hover:bg-destructive/90" disabled={isDeleting}>
                              {isDeleting ? 'Deleting...' : 'Delete'}
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    ) : null}
                  </div>
                </div>
                {acquisitionSource ? (
                  <div className="mt-3 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-sm">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <p className="font-semibold text-foreground">Created from Acquisition Workspace</p>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {acquisitionSource.candidate_source_name || 'Sourced candidate'}
                          {acquisitionSource.asset_class_confidence != null
                            ? ` · Self-storage ${Math.round(Number(acquisitionSource.asset_class_confidence) * 100)}%`
                            : ''}
                          {' · '}{acquisitionDocSummary}
                        </p>
                      </div>
                      {acquisitionSource.acquisition_candidate_id ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => navigate(`/app/re/acquisitions?candidate_id=${acquisitionSource.acquisition_candidate_id}`)}
                        >
                          Open candidate
                        </Button>
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </div>


              {/* Body: rail + scrollable inputs */}
              <div className="flex flex-1 min-h-0 gap-0">
                {/* Collapsible left rail */}
                <div className={`hidden lg:flex flex-shrink-0 flex-col overflow-hidden border-r border-border/60 bg-card/70 transition-all duration-300 ${leftCollapsed ? 'w-[52px]' : 'w-[280px] xl:w-[300px]'}`}>
                  <WorkflowRail
                    selectedDocs={selectedDocs}
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

                {/* Inputs — scrollable */}
                <div className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto p-4 sm:p-5">
                  {error ? (
                    <Alert variant="destructive" className="mb-4">
                      <AlertCircle className="h-4 w-4" />
                      <AlertDescription>{error}</AlertDescription>
                    </Alert>
                  ) : null}
                  <div className={`mx-auto ${activeTab === 'market' ? 'max-w-[1280px]' : 'max-w-[980px]'}`}>
                    {activeTab === 'criteria' && (
                      <div className="mb-3 flex justify-end">
                        <UnderwritingDefaultsModal
                          getToken={getToken}
                          trigger={
                            <button type="button" className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground transition-colors">
                              Edit my defaults
                            </button>
                          }
                        />
                      </div>
                    )}
                    <WizardInputStage
                      activeTab={activeTab}
                      setActiveTab={setActiveTab}
                      tabProgress={tabProgress}
                      inputs={inputs}
                      projectData={projectData}
                      currentRun={currentRun}
                      runIdFromUrl={runIdFromUrl}
                      citationCount={citationCount}
                      extractionDone={extractionDone}
                      anyDocSelected={anyDocSelected}
                      getCitation={getCitation}
                      handleOpenSource={handleOpenSource}
                      patchAcq={patchAcq}
                      patchOp={patchOp}
                      patchProject={patchProject}
                      patchFin={patchFin}
                      patchExit={patchExit}
                      patchCrit={patchCrit}
                      addRentComp={addRentComp}
                      patchRentComp={patchRentComp}
                      removeRentComp={removeRentComp}
                      rentCompsCitation={rentCompsCitation}
                      showValueAdd={showValueAdd}
                      setShowValueAdd={setShowValueAdd}
                      handleSaveAndCalculate={handleSaveAndCalculate}
                      isSubmitting={isSubmitting}
                      navigateToResults={navigateToResults}
                    />
                  </div>
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
          allowedExtensions={UNDERWRITING_SOURCE_EXTENSIONS[slot.key] || null}
          dialogDescription={`Choose a source document for ${slot.label}.`}
          emptyStateLabel={`No ready ${slot.label} documents in this collection`}
          emptyStateDescription="Upload the source document to your library first"
          submitLabel="Select source"
          showFillName={false}
        />
      ))}
    </AppLayout>
  );
}
