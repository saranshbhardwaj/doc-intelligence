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

const FIELDS = [
  { key: 'target_irr', label: 'Target IRR', hint: 'e.g. 0.15 = 15%', isPercent: true },
  { key: 'target_cash_on_cash', label: 'Target Cash-on-Cash', hint: 'e.g. 0.08 = 8%', isPercent: true },
  { key: 'target_equity_multiple', label: 'Target Equity Multiple', hint: 'e.g. 2.0', isPercent: false },
  { key: 'max_ltv', label: 'Max LTV', hint: 'e.g. 0.80 = 80%', isPercent: true },
  { key: 'dscr_year_one_floor', label: 'Min DSCR Year 1', hint: 'default 1.25', isPercent: false },
  { key: 'stress_dscr_floor', label: 'Min Stress DSCR', hint: 'default 1.15', isPercent: false },
  { key: 'rollover_risk_pct', label: 'Rollover Warning Threshold', hint: 'default 0.40 = 40%', isPercent: true },
];

export default function UnderwritingDefaultsModal({ getToken, trigger }) {
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open) return;
    getMyThresholds(getToken).then(setValues).catch(() => setValues({}));
  }, [open, getToken]);

  function handleChange(key, raw) {
    setValues(prev => ({ ...prev, [key]: raw === '' ? undefined : Number(raw) }));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const payload = {};
      for (const { key } of FIELDS) {
        const v = values[key];
        if (v !== undefined && v !== '' && !isNaN(v)) payload[key] = Number(v);
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
          {FIELDS.map(({ key, label, hint }) => (
            <div key={key} className="grid gap-1">
              <Label className="text-xs">{label}</Label>
              <Input
                type="number"
                step="0.01"
                placeholder={hint}
                value={values[key] ?? ''}
                onChange={e => handleChange(key, e.target.value)}
                className="h-8 text-sm"
              />
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
