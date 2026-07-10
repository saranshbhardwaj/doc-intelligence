import { useState } from 'react';
import { X } from 'lucide-react';

const INITIAL_FORM = {
  name: '',
  address: '',
  market: '',
  sourceType: 'manual',
  sourceName: 'Manual candidate',
  assetClassConfidence: 90,
  price: '',
  units: '',
  rentableSqft: '',
  capRate: '',
};

export default function NewCandidateDialog({ open, onClose, onCreate, isCreating = false }) {
  const [form, setForm] = useState(INITIAL_FORM);

  if (!open) return null;

  const update = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));
  const canSubmit = form.name.trim().length > 0;

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!canSubmit) return;
    const facts = {};
    if (form.price) facts.price = Number(form.price);
    if (form.units) facts.units = Number(form.units);
    if (form.rentableSqft) facts.rentableSqft = Number(form.rentableSqft);
    if (form.capRate) facts.capRate = Number(form.capRate) / 100;
    await onCreate({
      name: form.name.trim(),
      address: form.address.trim() || null,
      market: form.market.trim() || null,
      sourceType: form.sourceType,
      sourceName: form.sourceName.trim() || 'Manual candidate',
      assetClass: 'self_storage',
      assetClassConfidence: Number(form.assetClassConfidence) || 90,
      status: 'needs_docs',
      priority: 'medium',
      readinessScore: 25,
      facts,
      evidence: [{ label: 'Manual candidate', detail: 'Created manually from Acquisition Workspace.', confidence: 1, source: 'Analyst' }],
      missingItems: ['om'],
    });
    setForm(INITIAL_FORM);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm">
      <div className="absolute inset-x-4 top-8 mx-auto max-w-2xl rounded-lg border border-border bg-card shadow-xl">
        <form onSubmit={handleSubmit}>
          <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
            <div>
              <h2 className="text-lg font-semibold text-foreground">New Acquisition Candidate</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Create a self-storage candidate, then attach indexed Library documents before handoff.
              </p>
            </div>
            <button type="button" onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Close new candidate dialog">
              <X className="h-5 w-5" />
            </button>
          </div>
          <div className="grid max-h-[70vh] gap-3 overflow-y-auto p-4 sm:grid-cols-2">
            <Field label="Deal name" required value={form.name} onChange={(value) => update('name', value)} />
            <Field label="Market" value={form.market} onChange={(value) => update('market', value)} />
            <Field label="Address" className="sm:col-span-2" value={form.address} onChange={(value) => update('address', value)} />
            <label className="text-xs font-medium text-muted-foreground">
              Source type
              <select value={form.sourceType} onChange={(event) => update('sourceType', event.target.value)} className="mt-1 h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground">
                <option value="manual">Manual</option>
                <option value="gmail">Gmail</option>
                <option value="outlook">Outlook</option>
                <option value="public_api">Public API</option>
                <option value="private_api">Private API</option>
              </select>
            </label>
            <Field label="Source name" value={form.sourceName} onChange={(value) => update('sourceName', value)} />
            <Field label="Self-storage confidence (%)" type="number" value={form.assetClassConfidence} onChange={(value) => update('assetClassConfidence', value)} />
            <Field label="Purchase price" type="number" value={form.price} onChange={(value) => update('price', value)} />
            <Field label="Units/spaces" type="number" value={form.units} onChange={(value) => update('units', value)} />
            <Field label="Rentable sqft" type="number" value={form.rentableSqft} onChange={(value) => update('rentableSqft', value)} />
            <Field label="Going-in cap (%)" type="number" value={form.capRate} onChange={(value) => update('capRate', value)} />
          </div>
          <div className="flex justify-end gap-2 border-t border-border px-4 py-3">
            <button type="button" onClick={onClose} className="rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-muted-foreground">
              Cancel
            </button>
            <button type="submit" disabled={!canSubmit || isCreating} className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60">
              {isCreating ? 'Creating...' : 'Create Candidate'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, type = 'text', required = false, className = '' }) {
  return (
    <label className={`text-xs font-medium text-muted-foreground ${className}`}>
      {label}{required ? ' *' : ''}
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground outline-none"
      />
    </label>
  );
}