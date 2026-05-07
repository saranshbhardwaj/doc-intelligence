import { useEffect, useState } from 'react';
import { Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { getMyThresholds, updateMyThresholds } from '../../../../api/users';

// isPercent=true fields are stored as fractions (0.15) but displayed/entered as percentages (15).
const FIELDS = [
  { key: 'target_irr', label: 'Target IRR', hint: 'e.g. 15 for 15%', suffix: '%', isPercent: true },
  { key: 'target_cash_on_cash', label: 'Target Cash-on-Cash', hint: 'e.g. 8 for 8%', suffix: '%', isPercent: true },
  { key: 'target_equity_multiple', label: 'Target Equity Multiple', hint: 'e.g. 2.0', suffix: '×', isPercent: false },
  { key: 'max_ltv', label: 'Max LTV', hint: 'e.g. 80 for 80%', suffix: '%', isPercent: true },
  { key: 'dscr_year_one_floor', label: 'Min DSCR Year 1', hint: 'default 1.25', suffix: 'x', isPercent: false },
  { key: 'stress_dscr_floor', label: 'Min Stress DSCR', hint: 'default 1.15', suffix: 'x', isPercent: false },
  { key: 'rollover_risk_pct', label: 'Rollover Warning Threshold', hint: 'e.g. 40 for 40%', suffix: '%', isPercent: true },
];

export default function UnderwritingDefaultsModal({ getToken, trigger }) {
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open) return;
    getMyThresholds(getToken).then(saved => {
      if (!saved) return setValues({});
      // Convert fraction storage values → display values for percent fields
      const display = {};
      for (const { key, isPercent } of FIELDS) {
        if (saved[key] != null) display[key] = isPercent ? saved[key] * 100 : saved[key];
      }
      setValues(display);
    }).catch(() => setValues({}));
  }, [open, getToken]);

  function handleChange(key, raw) {
    setValues(prev => ({ ...prev, [key]: raw === '' ? undefined : Number(raw) }));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const payload = {};
      for (const { key, isPercent } of FIELDS) {
        const v = values[key];
        if (v !== undefined && v !== '' && !isNaN(v)) {
          payload[key] = isPercent ? Number(v) / 100 : Number(v);
        }
      }
      await updateMyThresholds(getToken, payload);
      setOpen(false);
    } catch {
      setError('Failed to save. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button variant="outline" size="sm" className="gap-1.5">
            <Settings2 className="h-3.5 w-3.5" />
            My defaults
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>My Underwriting Defaults</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground -mt-2 mb-1">
          Saved values pre-fill the wizard. You can still override per deal.
        </p>
        <div className="grid gap-3">
          {FIELDS.map(({ key, label, hint, suffix }) => (
            <div key={key} className="grid gap-1">
              <Label className="text-xs">{label}</Label>
              <div className="relative">
                <Input
                  type="number"
                  step="0.01"
                  placeholder={hint}
                  value={values[key] ?? ''}
                  onChange={e => handleChange(key, e.target.value)}
                  className="h-8 text-sm pr-7"
                />
                {suffix && (
                  <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">
                    {suffix}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
        {error && <p className="text-xs text-destructive mt-1">{error}</p>}
        <div className="flex justify-end gap-2 mt-2">
          <Button variant="outline" size="sm" onClick={() => setOpen(false)}>Cancel</Button>
          <Button size="sm" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
