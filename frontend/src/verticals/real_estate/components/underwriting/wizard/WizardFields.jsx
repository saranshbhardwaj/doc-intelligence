import { useId, useState } from 'react';
import { AlertCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import AIPrefilledField from '../AIPrefilledField';

export function FieldGroup({ label }) {
  return (
    <div className="field-section">
      <div className="field-section-label">{label}</div>
    </div>
  );
}

export function NumericField({ label, value, onChange, prefix, suffix, citation, onOpenSource, wide = false, placeholder }) {
  const id = useId();
  const [raw, setRaw] = useState('');
  const [focused, setFocused] = useState(false);

  const display = focused
    ? raw
    : (value !== '' && value != null
      ? Number(String(value).replace(/,/g, '')).toLocaleString('en-US', { maximumFractionDigits: 2 })
      : '');

  const handleFocus = () => {
    setFocused(true);
    setRaw(String(value ?? '').replace(/,/g, ''));
  };

  const handleBlur = () => {
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
    <div className={`field-wrap${wide ? ' wide' : ''}`}>
      <div className="field-label-row">
        <label htmlFor={id} className="field-label">{label}</label>
        {citation?.is_derived ? (
          <span
            className="cite-derived-badge"
            title={citation.formula ?? 'Computed from extracted fields'}
          >
            Derived
          </span>
        ) : citation && !citation.is_default ? (
          <button type="button" className="cite-btn" onClick={() => onOpenSource?.(citation)}>
            <svg width="9" height="9" viewBox="0 0 9 9" fill="none" aria-hidden="true">
              <path d="M1 8L8 1M8 1H3.5M8 1V5.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
            </svg>
            SOURCE
          </button>
        ) : citation?.is_default ? (
          <span className="cite-default-badge">Default</span>
        ) : null}
      </div>

      <div className={`field-input-row${citation && !citation.is_default && !citation.is_derived ? ' cited' : ''}`}>
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
        />
        {suffix ? <span className="field-affix suffix">{suffix}</span> : null}
      </div>
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

export function OperationsWarnings({ inputs, currentRun }) {
  const milRateVal = inputs.operational.mil_rate;
  const purchasePriceVal = inputs.acquisition.purchase_price;
  const currentTaxVal = inputs.operational.property_tax_annual;

  const reassessmentNote = (() => {
    if (!milRateVal || !purchasePriceVal || !currentTaxVal) return null;
    const estimatedAssessed = purchasePriceVal * 0.11;
    const estimatedTax = (milRateVal / 1000) * estimatedAssessed;
    if (estimatedTax - currentTaxVal < 2000) return null;
    return (
      <div className="rounded-2xl border border-warning/30 bg-warning/8 p-3 text-sm text-muted-foreground">
        <span className="font-medium text-foreground">Reassessment note: </span>
        At the {milRateVal} mil rate and {(0.11 * 100).toFixed(0)}% assessment ratio,
        post-acquisition property tax could be approximately{' '}
        <span className="font-semibold text-foreground">
          ${Math.round((milRateVal / 1000) * purchasePriceVal * 0.11).toLocaleString()}
        </span>
        {' '}vs the currently stated{' '}
        <span className="font-semibold text-foreground">
          ${Math.round(currentTaxVal).toLocaleString()}
        </span>.
        {' '}Verify with the county assessor.
      </div>
    );
  })();

  const incomeBasisWarning = currentRun?.result_artifact?.om_data?.income_basis_months === 6 ? (
    <Alert className="border-warning/40 bg-warning/10">
      <AlertCircle className="h-4 w-4 text-warning" />
      <AlertDescription className="text-sm text-muted-foreground">
        Income figures are based on a trailing 6-month statement, annualized by the broker.
        Consider requesting a full T-12 before closing.
      </AlertDescription>
    </Alert>
  ) : null;

  if (!reassessmentNote && !incomeBasisWarning) return null;
  return (
    <div className="col-span-full space-y-4">
      {reassessmentNote}
      {incomeBasisWarning}
    </div>
  );
}
