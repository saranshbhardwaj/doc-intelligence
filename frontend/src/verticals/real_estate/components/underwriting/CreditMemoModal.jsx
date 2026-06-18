import { useEffect, useMemo, useState } from 'react';
import { X, Plus, Trash2, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { generateMemo, getMemoReadiness } from '../../../../api/re-memos';

const MIN_COVER_TEXT_LEN = 3;

const EMPTY_SPONSOR = {
  sponsor_name: '',
  entity: '',
  // Structured fields the memo cites as concrete mitigants
  years_experience: '',
  deals_in_asset_class: '',
  track_record_irr: '',
  sponsor_role: '',
  // Existing free-text fields kept for back-compat
  experience: '',
  net_worth: '',
  liquidity: '',
  notes: '',
};

const EMPTY_THESIS = {
  thesis_text: '',
  strategy_type: '',
  hold_period_years: '',
  verdict_override: '',
  verdict_override_reason: '',
  custom_conditions: [],
  sourcing_type: '',
  sourcing_detail: '',
};

const STRATEGY_OPTIONS = [
  { value: '', label: '— select —' },
  { value: 'Stable Income', label: 'Stable Income' },
  { value: 'Value-Add', label: 'Value-Add' },
  { value: 'Distressed', label: 'Distressed' },
  { value: 'Conversion', label: 'Conversion' },
  { value: 'Portfolio Build', label: 'Portfolio Build' },
  { value: 'Opportunistic', label: 'Opportunistic' },
];

const SOURCING_OPTIONS = [
  { value: '', label: '— select —' },
  { value: 'Broker', label: 'Broker' },
  { value: 'Off-market', label: 'Off-market' },
  { value: 'Repeat seller', label: 'Repeat seller' },
  { value: 'Distressed', label: 'Distressed sale' },
  { value: 'Portfolio', label: 'Portfolio acquisition' },
  { value: 'Other', label: 'Other' },
];

const VERDICT_OPTIONS = [
  { value: '', label: 'Agree with calculator' },
  { value: 'Pursue', label: 'Override → Pursue' },
  { value: 'Needs Review', label: 'Override → Needs Review' },
  { value: 'Pass', label: 'Override → Pass' },
];

const SPONSOR_ROLE_OPTIONS = [
  { value: '', label: '— select —' },
  { value: 'Sole', label: 'Sole sponsor' },
  { value: 'Co-GP', label: 'Co-GP' },
];

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

/**
 * Pre-fill strategy_type from underwriting cues:
 *   - value_add_opportunities w/ conversion → "Conversion"
 *   - verdict "worth_pursuing" + no upside → "Stable Income"
 *   - verdict "needs_review" → "" (let analyst pick)
 *   - else → ""
 */
function inferStrategyType(persistedInputs, verdict) {
  const opps = persistedInputs?.value_add_opportunities || [];
  if (Array.isArray(opps) && opps.some((o) => /convert/i.test(o?.kind || o?.label || ''))) {
    return 'Conversion';
  }
  if (verdict === 'worth_pursuing') return 'Stable Income';
  return '';
}

export default function CreditMemoModal({
  open,
  onClose,
  runId,
  getToken,
  persistedInputs,
  currentUser,
  prefill,
  onSubmitted,
}) {
  const [tab, setTab] = useState('cover');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const [cover, setCover] = useState({
    deal_name: '',
    address: '',
    prepared_by: '',
    firm: '',
    date: todayIso(),
  });
  const [sponsor, setSponsor] = useState(EMPTY_SPONSOR);
  const [thesis, setThesis] = useState(EMPTY_THESIS);
  const [marketNotes, setMarketNotes] = useState('');
  const [readiness, setReadiness] = useState(null);

  // Underwriting verdict (used for strategy inference). Not directly editable here;
  // analyst sees it as context for the override field.
  const underwritingVerdict = persistedInputs?.verdict_status || null;

  const inferredHoldYears = useMemo(
    () => persistedInputs?.exit?.hold_period_years || '',
    [persistedInputs],
  );

  useEffect(() => {
    if (!open) return;
    if (prefill) {
      setCover((prev) => ({ ...prev, ...(prefill.cover_data || {}) }));
      setSponsor({ ...EMPTY_SPONSOR, ...(prefill.sponsor_data || {}) });
      setThesis({ ...EMPTY_THESIS, ...(prefill.thesis_data || {}) });
      setMarketNotes(prefill.market_notes || '');
      setError(null);
      setTab('cover');
      return;
    }
    setCover({
      deal_name: persistedInputs?.project?.name || '',
      address: persistedInputs?.project?.address || '',
      prepared_by: currentUser?.name || '',
      firm: '',
      date: todayIso(),
    });
    setSponsor(EMPTY_SPONSOR);
    setThesis({
      ...EMPTY_THESIS,
      strategy_type: inferStrategyType(persistedInputs, underwritingVerdict),
      hold_period_years: inferredHoldYears,
    });
    setMarketNotes('');
    setError(null);
    setTab('cover');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Fetch OM-indexing readiness when the modal opens so the analyst sees a
  // warning banner if the memo will lack source citations.
  useEffect(() => {
    if (!open || !runId) return;
    let cancelled = false;
    setReadiness(null);
    getMemoReadiness(getToken, runId)
      .then((r) => {
        if (!cancelled) setReadiness(r);
      })
      .catch(() => {
        // Soft-fail: readiness is informational only.
        if (!cancelled) setReadiness(null);
      });
    return () => { cancelled = true; };
  }, [open, runId, getToken]);

  if (!open) return null;

  const isOverrideActive = Boolean(thesis.verdict_override);
  const overrideMissingReason =
    isOverrideActive && !thesis.verdict_override_reason.trim();

  const preparedByValid = (cover.prepared_by || '').trim().length >= MIN_COVER_TEXT_LEN;
  const firmValid = (cover.firm || '').trim().length >= MIN_COVER_TEXT_LEN;
  const coverValid = preparedByValid && firmValid;

  const canSubmit = !submitting && !overrideMissingReason && coverValid;

  const handleSubmit = async () => {
    if (!coverValid) {
      setError('Prepared by and Firm are required (minimum 3 characters each).');
      setTab('cover');
      return;
    }
    if (overrideMissingReason) {
      setError('Override reason is required when overriding the calculator verdict.');
      setTab('thesis');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const sanitizedCustomConditions = (thesis.custom_conditions || [])
        .map((c) => (c || '').trim())
        .filter(Boolean);

      const thesisPayload = {
        thesis_text: thesis.thesis_text.trim() || null,
        strategy_type: thesis.strategy_type || null,
        hold_period_years: thesis.hold_period_years
          ? Number(thesis.hold_period_years)
          : null,
        verdict_override: thesis.verdict_override || null,
        verdict_override_reason: thesis.verdict_override_reason.trim() || null,
        custom_conditions: sanitizedCustomConditions,
        sourcing_type: thesis.sourcing_type || null,
        sourcing_detail: thesis.sourcing_detail.trim() || null,
      };

      const resp = await generateMemo(getToken, runId, {
        cover_data: cover,
        sponsor_data: sponsor,
        market_notes: marketNotes || null,
        thesis_data: thesisPayload,
      });
      onSubmitted?.(resp);
      onClose?.();
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to generate memo.');
    } finally {
      setSubmitting(false);
    }
  };

  const addCondition = () =>
    setThesis((prev) => ({ ...prev, custom_conditions: [...prev.custom_conditions, ''] }));

  const updateCondition = (idx, val) =>
    setThesis((prev) => ({
      ...prev,
      custom_conditions: prev.custom_conditions.map((c, i) => (i === idx ? val : c)),
    }));

  const removeCondition = (idx) =>
    setThesis((prev) => ({
      ...prev,
      custom_conditions: prev.custom_conditions.filter((_, i) => i !== idx),
    }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-xl border border-border bg-card p-5 shadow-lg">
        <button
          type="button"
          className="absolute right-3 top-3 text-muted-foreground hover:text-foreground"
          onClick={onClose}
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>

        <h2 className="text-lg font-semibold mb-1">Generate Credit Memo</h2>
        <p className="text-sm text-muted-foreground mb-4">
          Pre-filled from the underwriting run. Edit any field before generating.
        </p>

        {readiness && readiness.warnings && readiness.warnings.length > 0 ? (
          <div className="mb-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs">
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-warning shrink-0 mt-0.5" />
              <div className="space-y-1">
                {readiness.warnings.map((w, i) => (
                  <p key={i} className="text-foreground">{w}</p>
                ))}
              </div>
            </div>
          </div>
        ) : null}

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="grid grid-cols-4 gap-1 mb-4">
            <TabsTrigger value="cover">Cover</TabsTrigger>
            <TabsTrigger value="sponsor">Sponsor</TabsTrigger>
            <TabsTrigger value="thesis">Thesis & Strategy</TabsTrigger>
            <TabsTrigger value="notes">Notes</TabsTrigger>
          </TabsList>

          <TabsContent value="cover" className="space-y-3">
            <Field label="Deal name" value={cover.deal_name}
                   onChange={(v) => setCover({ ...cover, deal_name: v })} />
            <Field label="Address" value={cover.address}
                   onChange={(v) => setCover({ ...cover, address: v })} />
            <Field
              label="Prepared by"
              value={cover.prepared_by}
              onChange={(v) => setCover({ ...cover, prepared_by: v })}
              placeholder="Your full name"
              invalid={cover.prepared_by !== undefined && cover.prepared_by !== '' && !preparedByValid}
              hint={!preparedByValid ? 'Required — minimum 3 characters.' : null}
              required
            />
            <Field
              label="Firm"
              value={cover.firm}
              onChange={(v) => setCover({ ...cover, firm: v })}
              placeholder="Your firm name"
              invalid={cover.firm !== undefined && cover.firm !== '' && !firmValid}
              hint={!firmValid ? 'Required — minimum 3 characters.' : null}
              required
            />
            <Field label="Date" type="date" value={cover.date}
                   onChange={(v) => setCover({ ...cover, date: v })} />
          </TabsContent>

          <TabsContent value="sponsor" className="space-y-3">
            <Field label="Sponsor name" value={sponsor.sponsor_name}
                   onChange={(v) => setSponsor({ ...sponsor, sponsor_name: v })} />
            <Field label="Entity" value={sponsor.entity}
                   onChange={(v) => setSponsor({ ...sponsor, entity: v })} />
            <div className="grid grid-cols-2 gap-3">
              <Field label="Years of experience" type="number" value={sponsor.years_experience}
                     onChange={(v) => setSponsor({ ...sponsor, years_experience: v })} />
              <Field label="Deals in asset class" type="number" value={sponsor.deals_in_asset_class}
                     onChange={(v) => setSponsor({ ...sponsor, deals_in_asset_class: v })} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Track record IRR (%)" type="number" value={sponsor.track_record_irr}
                     onChange={(v) => setSponsor({ ...sponsor, track_record_irr: v })}
                     hint="Optional. Reported avg net IRR on prior storage deals." />
              <Select label="Sponsor role" value={sponsor.sponsor_role}
                      onChange={(v) => setSponsor({ ...sponsor, sponsor_role: v })}
                      options={SPONSOR_ROLE_OPTIONS} />
            </div>
            <Field label="Experience summary" value={sponsor.experience}
                   onChange={(v) => setSponsor({ ...sponsor, experience: v })} multiline
                   hint="Free-text background — used when structured fields are empty." />
            <Field label="Net worth" value={sponsor.net_worth}
                   onChange={(v) => setSponsor({ ...sponsor, net_worth: v })} />
            <Field label="Liquidity" value={sponsor.liquidity}
                   onChange={(v) => setSponsor({ ...sponsor, liquidity: v })} />
            <Field label="Notes" value={sponsor.notes}
                   onChange={(v) => setSponsor({ ...sponsor, notes: v })} multiline />
          </TabsContent>

          <TabsContent value="thesis" className="space-y-3">
            <Field
              label="Investment thesis (1-3 sentences)"
              value={thesis.thesis_text}
              onChange={(v) => setThesis({ ...thesis, thesis_text: v })}
              multiline
              hint="Why this deal — the angle. Leave empty to let the system infer from value-add opportunities."
            />
            <div className="grid grid-cols-2 gap-3">
              <Select label="Strategy type" value={thesis.strategy_type}
                      onChange={(v) => setThesis({ ...thesis, strategy_type: v })}
                      options={STRATEGY_OPTIONS} />
              <Field label="Hold period (years)" type="number" value={thesis.hold_period_years}
                     onChange={(v) => setThesis({ ...thesis, hold_period_years: v })}
                     hint={`Underwriting assumed ${inferredHoldYears || '—'} years.`} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Select label="Deal sourcing" value={thesis.sourcing_type}
                      onChange={(v) => setThesis({ ...thesis, sourcing_type: v })}
                      options={SOURCING_OPTIONS} />
              <Field label="Sourcing detail" value={thesis.sourcing_detail}
                     onChange={(v) => setThesis({ ...thesis, sourcing_detail: v })}
                     hint="Broker name, seller name, etc." />
            </div>

            <div className="rounded-md border border-border/60 bg-muted/40 p-3 space-y-3">
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
                Verdict override (optional)
              </p>
              <Select label="" value={thesis.verdict_override}
                      onChange={(v) => setThesis({ ...thesis, verdict_override: v })}
                      options={VERDICT_OPTIONS} />
              {isOverrideActive ? (
                <Field
                  label="Override reason (required)"
                  value={thesis.verdict_override_reason}
                  onChange={(v) => setThesis({ ...thesis, verdict_override_reason: v })}
                  multiline
                  hint="Quoted in the memo's Recommendation section."
                />
              ) : null}
            </div>

            <div className="space-y-2">
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
                Custom conditions for proceeding
              </p>
              <p className="text-xs text-muted-foreground">
                These appear FIRST in the memo's Conditions section, before auto-derived ones.
              </p>
              {thesis.custom_conditions.map((cond, i) => (
                <div key={i} className="flex items-center gap-2">
                  <input
                    value={cond}
                    onChange={(e) => updateCondition(i, e.target.value)}
                    className="flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-sm"
                    placeholder="e.g. Obtain Phase I environmental before closing"
                  />
                  <button
                    type="button"
                    onClick={() => removeCondition(i)}
                    className="text-muted-foreground hover:text-destructive"
                    aria-label="Remove condition"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
              <Button variant="ghost" size="sm" onClick={addCondition} className="gap-1 h-7 px-2 text-xs">
                <Plus className="h-3.5 w-3.5" />
                Add condition
              </Button>
            </div>
          </TabsContent>

          <TabsContent value="notes" className="space-y-3">
            <Field
              label="Additional market notes (optional)"
              value={marketNotes}
              onChange={setMarketNotes}
              multiline
              hint="Anything not in the OM — recent dispositions, upcoming supply, submarket nuances."
            />
          </TabsContent>
        </Tabs>

        {error ? (
          <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
            {error}
          </div>
        ) : null}

        <div className="mt-5 flex items-center justify-end gap-2">
          <Button variant="ghost" onClick={onClose} disabled={submitting}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {submitting ? 'Generating…' : 'Generate'}
          </Button>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = 'text',
  multiline = false,
  hint = null,
  placeholder = '',
  invalid = false,
  required = false,
}) {
  const borderClass = invalid ? 'border-destructive' : 'border-border';
  const hintClass = invalid ? 'text-destructive' : 'text-muted-foreground';
  return (
    <label className="block">
      {label ? (
        <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
          {label}{required ? <span className="text-destructive"> *</span> : null}
        </span>
      ) : null}
      {multiline ? (
        <textarea
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className={`mt-1 w-full rounded-md border ${borderClass} bg-background px-2 py-1.5 text-sm`}
          rows={3}
        />
      ) : (
        <input
          type={type}
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className={`mt-1 w-full rounded-md border ${borderClass} bg-background px-2 py-1.5 text-sm`}
        />
      )}
      {hint ? <span className={`mt-1 block text-xs ${hintClass}`}>{hint}</span> : null}
    </label>
  );
}

function Select({ label, value, onChange, options }) {
  return (
    <label className="block">
      {label ? (
        <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
          {label}
        </span>
      ) : null}
      <select
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}
