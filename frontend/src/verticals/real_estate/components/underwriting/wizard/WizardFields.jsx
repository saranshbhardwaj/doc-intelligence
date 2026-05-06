import { useId, useState } from 'react';
import { ChevronRight, Sigma } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipPortal, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import AIPrefilledField from '../AIPrefilledField';

function humanizeFieldName(field) {
  if (!field) return null;
  return field.replace(/^expense_/, '').replace(/_/g, ' ');
}

function citationTier(citation) {
  if (!citation) return null;
  if (citation.is_default) {
    return { label: 'Default', tone: 'default', title: 'System default; review before relying on this assumption.' };
  }
  if (citation.doc_type === 'benchmark') {
    return { label: 'Benchmark', tone: 'derived', title: citation.selection_note ?? citation.formula ?? 'Raised to an underwriting benchmark floor.' };
  }
  if (citation.is_derived) {
    return { label: 'Derived', tone: 'derived', title: citation.formula ?? 'Computed from extracted fields.' };
  }
  if (citation.doc_type === 'om' && citation.is_computed) {
    return { label: 'OM computed', tone: 'om', title: citation.formula ?? 'Computed from OM source-backed line items.' };
  }
  if (citation.doc_type === 't12' && citation.is_computed) {
    return { label: 'T-12 computed', tone: 'actual', title: citation.formula ?? 'Computed from T-12 operating statement evidence.' };
  }
  if (citation.doc_type === 't12' && citation.annualized_from_months) {
    return { label: 'T-12 annualized', tone: 'actual', title: citation.selection_note ?? citation.formula ?? 'Annualized from a partial-period T-12.' };
  }
  if (citation.doc_type === 'om' && citation.used_fallback_source) {
    return { label: 'OM fallback', tone: 'om', title: citation.selection_note ?? 'Used an OM fallback field because the preferred source was unavailable.' };
  }
  if (citation.doc_type === 't12' && citation.used_fallback_source) {
    return { label: 'T-12 fallback', tone: 'actual', title: citation.selection_note ?? 'Used a T-12 fallback field because the preferred source was unavailable.' };
  }
  if (citation.doc_type === 'rent_roll' && citation.used_fallback_source) {
    return { label: 'Rent roll fallback', tone: 'actual', title: citation.selection_note ?? 'Used a rent roll fallback field because the preferred source was unavailable.' };
  }
  if (citation.doc_type === 't12') {
    return { label: 'T-12 actual', tone: 'actual', title: citation.formula ?? 'Supported by T-12 operating statement evidence.' };
  }
  if (citation.doc_type === 'rent_roll') {
    return { label: 'Rent roll actual', tone: 'actual', title: 'Supported by rent roll evidence.' };
  }
  if (citation.doc_type === 'om') {
    return { label: 'OM stated', tone: 'om', title: 'Broker or offering memorandum stated assumption.' };
  }
  if (citation.is_uncited_extraction) {
    return {
      label: citation.doc_type === 't12' ? 'T-12 extracted' : citation.doc_type === 'om' ? 'OM extracted' : 'Extracted',
      tone: citation.doc_type === 'om' ? 'om' : 'extracted',
      title: citation.selection_note ?? 'Extracted from a source document, but exact citation was not captured.',
    };
  }
  return { label: 'Extracted', tone: 'extracted', title: 'Extracted from source evidence.' };
}

function confidenceTone(citation) {
  const confidence = Number(citation?.confidence);
  if (!Number.isFinite(confidence)) return 'neutral';
  if (confidence >= 0.9) return 'high';
  if (confidence >= 0.7) return 'mid';
  return 'low';
}

function confidenceLabel(citation) {
  const confidence = Number(citation?.confidence);
  if (!Number.isFinite(confidence)) return null;
  return `${Math.round(confidence * 100)}%`;
}

function CitationTooltipContent({ citation, tier, canOpen }) {
  const token = citation?.citations?.[0];
  const sourceText = citation?.source_text;
  const formula = citation?.formula;
  const isComputed = citation?.is_computed || citation?.is_derived;
  const confidence = confidenceLabel(citation);
  const confidenceClass = `uw-confidence-dot-${confidenceTone(citation)}`;
  const selectionNote = citation?.selection_note;
  const sourceField = humanizeFieldName(citation?.source_field);
  const preferredSources = Array.isArray(citation?.preferred_sources_missing)
    ? citation.preferred_sources_missing
    : [];
  const annualizedFromMonths = citation?.annualized_from_months;
  const annualizationFactor = Number(citation?.annualization_factor);
  const originalValue = citation?.original_value;

  return (
    <div className="w-[320px] overflow-hidden rounded-2xl border border-border/70 bg-popover p-0 text-popover-foreground shadow-2xl shadow-foreground/10">
      <div className="border-b border-border/60 bg-gradient-to-br from-card via-card to-muted/40 px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Source Basis
            </p>
            <p className="mt-1 text-sm font-semibold text-foreground">{tier.label}</p>
          </div>
          <span className={`cite-tier-badge cite-tier-${tier.tone}`}>
            {tier.label}
          </span>
        </div>
      </div>

      <div className="space-y-3 px-4 py-3">
        {confidence ? (
          <div className="flex items-center justify-between rounded-xl border border-border/60 bg-background/70 px-3 py-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              AI confidence
            </span>
            <span className="inline-flex items-center gap-2 text-xs font-semibold text-foreground">
              <span className={`uw-confidence-dot ${confidenceClass}`} />
              {confidence}
            </span>
          </div>
        ) : null}

        {formula ? (
          <div className="rounded-xl border border-border/60 bg-background/70 p-3">
            <div className="mb-1.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              {isComputed ? <Sigma className="h-3.5 w-3.5 text-primary" /> : null}
              Calculation
            </div>
            <p className="font-mono text-[12px] leading-5 text-foreground">{formula}</p>
          </div>
        ) : null}

        {selectionNote ? (
          <div className="rounded-xl border border-border/60 bg-background/70 p-3">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Selection
            </div>
            <p className="text-xs leading-5 text-foreground">{selectionNote}</p>
          </div>
        ) : null}

        {sourceField || annualizedFromMonths || originalValue != null || preferredSources.length ? (
          <div className="rounded-xl border border-border/60 bg-background/70 p-3 text-xs leading-5 text-foreground">
            {sourceField ? (
              <p><span className="font-semibold text-muted-foreground">Selected field:</span> {sourceField}</p>
            ) : null}
            {annualizedFromMonths ? (
              <p>
                <span className="font-semibold text-muted-foreground">Annualization:</span> {annualizedFromMonths}-month figure
                {Number.isFinite(annualizationFactor) ? ` scaled by ×${annualizationFactor.toFixed(2)}` : ''}
              </p>
            ) : null}
            {originalValue != null ? (
              <p><span className="font-semibold text-muted-foreground">Original value:</span> ${Number(originalValue).toLocaleString()}</p>
            ) : null}
            {preferredSources.length ? (
              <p><span className="font-semibold text-muted-foreground">Missing preferred sources:</span> {preferredSources.join(', ')}</p>
            ) : null}
          </div>
        ) : null}

        {sourceText ? (
          <div>
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Source Text
            </p>
            <p className="rounded-xl bg-muted/50 px-3 py-2 text-xs leading-5 text-muted-foreground">
              "{sourceText}"
            </p>
          </div>
        ) : null}

        <div className="flex items-center justify-between gap-3 text-xs">
          <span className="rounded-full bg-muted px-2.5 py-1 font-mono text-[11px] text-muted-foreground">
            {token || 'No exact source token'}
          </span>
          {canOpen ? (
            <span className="inline-flex items-center gap-1 font-medium text-primary/80">
              Click badge to open source <ChevronRight className="h-3.5 w-3.5" />
            </span>
          ) : (
            <span className="text-muted-foreground">Review manually</span>
          )}
        </div>
      </div>
    </div>
  );
}

function CitationControl({ citation, onOpenSource }) {
  const tier = citationTier(citation);
  if (!tier) return null;

  const className = `cite-tier-badge cite-tier-${tier.tone}`;
  const canOpen = Boolean(citation
    && citation.citations?.length
    && !citation.is_default
    && !citation.is_derived
    && !citation.is_uncited_extraction);
  const trigger = canOpen ? (
    <button
      type="button"
      className={`${className} as-button`}
      onClick={() => onOpenSource?.(citation)}
    >
      {tier.label}
    </button>
  ) : (
    <span className={className}>
      {tier.label}
    </span>
  );

  return (
    <TooltipProvider delayDuration={120}>
      <Tooltip>
        <TooltipTrigger asChild>{trigger}</TooltipTrigger>
        <TooltipPortal>
          <TooltipContent
            side="top"
            align="end"
            sideOffset={10}
            collisionPadding={18}
            className="border-0 bg-transparent p-0 shadow-none"
          >
            <CitationTooltipContent citation={citation} tier={tier} canOpen={canOpen} />
          </TooltipContent>
        </TooltipPortal>
      </Tooltip>
    </TooltipProvider>
  );
}

export function FieldGroup({ label }) {
  return (
    <div className="field-section">
      <div className="field-section-label">{label}</div>
    </div>
  );
}

export function NumericField({
  label,
  value,
  onChange,
  prefix,
  suffix,
  citation,
  onOpenSource,
  wide = false,
  placeholder,
  disabled = false,
  badge = null,
  note = null,
}) {
  const id = useId();
  const [raw, setRaw] = useState('');
  const [focused, setFocused] = useState(false);
  const isSourceCited = Boolean(citation
    && !citation.is_default
    && !citation.is_derived
    && !citation.is_uncited_extraction);
  const inputToneClass = isSourceCited ? ` cited confidence-${confidenceTone(citation)}` : '';

  const display = focused
    ? raw
    : (value !== '' && value != null
      ? Number(String(value).replace(/,/g, '')).toLocaleString('en-US', { maximumFractionDigits: 2 })
      : '');

  const handleFocus = () => {
    if (disabled) return;
    setFocused(true);
    setRaw(String(value ?? '').replace(/,/g, ''));
  };

  const handleBlur = () => {
    if (disabled) return;
    setFocused(false);
    const normalized = raw.replace(/,/g, '').trim();
    if (normalized === '') {
      onChange('');
      return;
    }
    const n = parseFloat(normalized);
    if (!Number.isNaN(n)) onChange(n);
  };

  return (
    <div className={`field-wrap${wide ? ' wide' : ''}${disabled ? ' opacity-70' : ''}`}>
      <div className="field-label-row">
        <label htmlFor={id} className="field-label">{label}</label>
        {badge ? <span className="rounded-full border border-border/60 bg-muted/50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{badge}</span> : null}
        <CitationControl citation={citation} onOpenSource={onOpenSource} />
      </div>

      <div className={`field-input-row${inputToneClass}`}>
        {prefix ? <span className="field-affix">{prefix}</span> : null}
        <input
          id={id}
          className="field-input"
          type="text"
          inputMode="decimal"
          value={display}
          placeholder={placeholder ?? '—'}
          onChange={(e) => setRaw(e.target.value)}
          onFocus={handleFocus}
          onBlur={handleBlur}
          disabled={disabled}
        />
        {suffix ? <span className="field-affix suffix">{suffix}</span> : null}
      </div>
      {note ? <p className="mt-1 text-xs text-muted-foreground">{note}</p> : null}
    </div>
  );
}

const formatCurrency = (value) => (
  value == null ? '—' : `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
);

const formatPercent = (value) => (
  value == null ? '—' : `${(Number(value) * 100).toFixed(2)}%`
);

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

export function OperationsModelBasisPanel({ expenseBasis }) {
  if (!expenseBasis) return null;

  return (
    <div className="col-span-full rounded-xl border border-border/60 bg-muted/30 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Model Basis</p>
          <p className="mt-1 text-base font-semibold text-foreground">Using {expenseBasis.label}</p>
          <p className="mt-1 text-sm text-muted-foreground">{expenseBasis.reason}</p>
        </div>
        <span className="rounded-full bg-uw-success/15 px-3 py-1 text-xs font-semibold text-uw-success">Drives model</span>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <div>
          <p className="text-xs text-muted-foreground">Period</p>
          <p className="font-semibold text-foreground">{periodLabel[expenseBasis.period] ?? 'Unknown'}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Method</p>
          <p className="font-semibold text-foreground">{methodLabel[expenseBasis.method] ?? expenseBasis.method ?? '—'}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">EGI</p>
          <p className="font-semibold text-foreground">{formatCurrency(expenseBasis.modeled_egi)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">OpEx</p>
          <p className="font-semibold text-foreground">{formatCurrency(expenseBasis.modeled_total_expenses ?? expenseBasis.year1_line_item_opex)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Expense Ratio</p>
          <p className="font-semibold text-foreground">{formatPercent(expenseBasis.expense_ratio ?? expenseBasis.ratio)}</p>
        </div>
      </div>
      {Array.isArray(expenseBasis.warnings) && expenseBasis.warnings.length ? (
        <div className="mt-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-muted-foreground">
          {expenseBasis.warnings.join(' ')}
        </div>
      ) : null}
    </div>
  );
}

export function ValueAddEvidence({ omData, getCitation, onOpenSource }) {
  const fmt = (v, suffix) => {
    if (v == null) return '—';
    return `${typeof v === 'number' && suffix === '%' ? (v * 100).toFixed(1) : Number(v).toLocaleString()}${suffix ?? ''}`;
  };
  return (
    <>
      <div className="col-span-full grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div>
          <AIPrefilledField label="Physical Occupancy (stated)" citation={getCitation('physical_occupancy_pct')} onOpenSource={onOpenSource}>
            <div className="h-10 flex items-center rounded-lg border border-border/60 bg-muted/30 px-3 text-sm text-foreground">
              {fmt(omData.physical_occupancy_pct, '%')}
            </div>
          </AIPrefilledField>
        </div>
        <div>
          <AIPrefilledField label="Below-Market Tenants" citation={getCitation('below_market_tenant_pct')} onOpenSource={onOpenSource}>
            <div className="h-10 flex items-center rounded-lg border border-border/60 bg-muted/30 px-3 text-sm text-foreground">
              {fmt(omData.below_market_tenant_pct, '%')}
            </div>
          </AIPrefilledField>
        </div>
        <div>
          <AIPrefilledField label="Monthly Rent Gap (below-mkt)" citation={getCitation('below_market_monthly_variance')} onOpenSource={onOpenSource}>
            <div className="h-10 flex items-center rounded-lg border border-border/60 bg-muted/30 px-3 text-sm text-foreground">
              {fmt(omData.below_market_monthly_variance, '/mo')}
            </div>
          </AIPrefilledField>
        </div>
        <div>
          <AIPrefilledField label="Annual Upside to Market" citation={getCitation('below_market_annual_upside')} onOpenSource={onOpenSource}>
            <div className="h-10 flex items-center rounded-lg border border-border/60 bg-muted/30 px-3 text-sm text-foreground">
              {fmt(omData.below_market_annual_upside, '/yr')}
            </div>
          </AIPrefilledField>
        </div>
        {omData.income_basis_months != null ? (
          <div>
            <AIPrefilledField label="Income Statement Basis" citation={getCitation('income_basis_months')} onOpenSource={onOpenSource}>
              <div className="h-10 flex items-center rounded-lg border border-border/60 bg-muted/30 px-3 text-sm text-foreground">
                T-{omData.income_basis_months}
              </div>
            </AIPrefilledField>
          </div>
        ) : null}
      </div>
      {omData.value_add_notes ? (
        <div className="col-span-full">
          <p className="mb-1 text-xs font-medium text-muted-foreground">Value-Add Notes (from OM)</p>
          <div className="rounded-xl border border-border/60 bg-muted/30 p-3 text-sm leading-relaxed text-foreground">
            {omData.value_add_notes}
          </div>
        </div>
      ) : null}
    </>
  );
}


export function OperationsIncomeBasisStrip({ inputs, currentRun }) {
  const artifact = currentRun?.result_artifact || {};
  const expenseBasisSource = artifact.expense_basis?.source;
  // Prefer saved model inputs because they reflect any analyst edits, then fall back to
  // preserved extraction artifacts so historical runs still show a useful basis strip.
  const months = inputs.operational?.income_basis_months
    ?? artifact.income_basis_months
    ?? artifact.t12_data?.summary?.period_months
    ?? artifact.om_data?.income_basis_months
    ?? null;

  let tone = 'neutral';
  let title = 'Income period not stated';
  let detail = 'The source period is unknown. Treat income and expense support as preliminary.';

  if (expenseBasisSource === 'om_noi') {
    tone = 'warning';
    title = 'OM-NOI quick screen';
    detail = 'Returns are driven by OM-stated NOI. Upload a T-12 to validate actual income and expenses.';
  } else if (months === 12) {
    tone = 'success';
    title = 'T-12 actuals';
    detail = '12-month operating statement support is driving the operations assumptions.';
  } else if (months != null && months > 0 && months <= 3) {
    tone = 'danger';
    title = `T-${months} very short period`;
    detail = `Only ${months} month(s) of income support are annualized. Request a fuller T-12 before relying on this screen.`;
  } else if (months != null && months > 0 && months < 12) {
    tone = 'warning';
    title = `T-${months} annualized × ${(12 / months).toFixed(1)}`;
    detail = 'Short-period operating statement annualized for screening. Request a full T-12 before close.';
  }

  const toneClasses = {
    success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
    warning: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
    danger: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300',
    neutral: 'border-border/70 bg-muted/40 text-muted-foreground',
  };

  return (
    <div className={`col-span-full rounded-2xl border px-4 py-3 ${toneClasses[tone]}`}>
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs font-bold uppercase tracking-[0.18em]">{title}</p>
        <p className="text-xs text-muted-foreground sm:text-right">{detail}</p>
      </div>
    </div>
  );
}
