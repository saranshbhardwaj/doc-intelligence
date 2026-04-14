import React, { useEffect, useState } from 'react';
import { useAppAuth } from '@/hooks/useAppAuth';
import { getTemplateFillAnalytics } from '../api/admin';
import { AlertCircle, Loader2 } from 'lucide-react';

const BLANK_FROM_PDF_THRESHOLD = 0.30;
const LLM_CORRECTED_THRESHOLD = 0.25;
const LLM_SUCCESS_GOOD = 0.80;

function pct(numerator, denominator) {
  if (!denominator) return '—';
  return `${Math.round((numerator / denominator) * 100)}%`;
}

function FieldFlag({ value, denominator, threshold, label }) {
  if (!denominator) return null;
  const rate = value / denominator;
  if (rate > threshold) return <span className="ml-1 text-destructive font-medium">⚠ {label}</span>;
  return null;
}

export default function AdminTemplateFillAnalyticsPage() {
  const { getToken } = useAppAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    getTemplateFillAnalytics(getToken)
      .then(setData)
      .catch((e) => setError(e.message || 'Failed to load analytics'))
      .finally(() => setLoading(false));
  }, [getToken]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 flex items-center gap-2 text-destructive">
        <AlertCircle className="h-5 w-5" />
        <span>{error}</span>
      </div>
    );
  }

  if (!data?.summary || !data?.fields) {
    return (
      <div className="p-4 flex items-center gap-2 text-destructive">
        <AlertCircle className="h-5 w-5" />
        <span>Unexpected response from analytics endpoint.</span>
      </div>
    );
  }

  const { summary, fields } = data;

  return (
    <div className="p-4 max-w-6xl mx-auto">
      <h1 className="text-xl font-semibold mb-1">Template Fill Analytics</h1>
      <p className="text-sm text-muted-foreground mb-4">
        Internal — use this to identify which YAML fields need synonym improvements or prompt fixes.
      </p>

      <div className="flex gap-4 mb-6 text-sm">
        <div><span className="text-muted-foreground">Total runs: </span><strong>{summary.total_runs}</strong></div>
        <div><span className="text-muted-foreground">Avg corrections/run: </span><strong>{summary.avg_corrected_per_run}</strong></div>
        <div><span className="text-muted-foreground">Avg blanks filled/run: </span><strong>{summary.avg_filled_blank_per_run}</strong></div>
      </div>

      <div className="text-xs text-muted-foreground mb-3 space-y-0.5">
        <div>⚠ <strong>Fix YAML synonyms</strong> when Blank (PDF) &gt; {Math.round(BLANK_FROM_PDF_THRESHOLD * 100)}% — value is in the PDF but LLM misses it</div>
        <div>⚠ <strong>Fix extraction prompt</strong> when LLM Corrected &gt; {Math.round(LLM_CORRECTED_THRESHOLD * 100)}% — LLM finds something but it's wrong</div>
        <div>✅ <strong>LLM Success</strong> ≥ {Math.round(LLM_SUCCESS_GOOD * 100)}% — field is healthy</div>
      </div>

      <div className="overflow-x-auto border rounded-md">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-muted-foreground">
            <tr>
              <th className="text-left px-3 py-2 font-medium">Field</th>
              <th className="text-right px-3 py-2 font-medium">Runs</th>
              <th className="text-right px-3 py-2 font-medium">LLM Success</th>
              <th className="text-right px-3 py-2 font-medium">Blank (PDF pick)</th>
              <th className="text-right px-3 py-2 font-medium">Blank (typed)</th>
              <th className="text-right px-3 py-2 font-medium">LLM Corrected</th>
            </tr>
          </thead>
          <tbody>
            {fields.map((f) => {
              const isHealthy = f.total_runs > 0 && (f.llm_success / f.total_runs) >= LLM_SUCCESS_GOOD;
              return (
                <tr key={f.field_id} className="border-t hover:bg-muted/20">
                  <td className="px-3 py-2 font-mono text-xs">
                    {f.field_id}
                    {isHealthy && <span className="ml-1 text-green-600">✅</span>}
                  </td>
                  <td className="px-3 py-2 text-right">{f.total_runs}</td>
                  <td className="px-3 py-2 text-right">{pct(f.llm_success, f.total_runs)}</td>
                  <td className="px-3 py-2 text-right">
                    {pct(f.blank_filled_from_pdf, f.total_runs)}
                    <FieldFlag value={f.blank_filled_from_pdf} denominator={f.total_runs} threshold={BLANK_FROM_PDF_THRESHOLD} label="Fix YAML synonyms" />
                  </td>
                  <td className="px-3 py-2 text-right">{pct(f.blank_filled_manually, f.total_runs)}</td>
                  <td className="px-3 py-2 text-right">
                    {pct(f.llm_corrected, f.total_runs)}
                    <FieldFlag value={f.llm_corrected} denominator={f.total_runs} threshold={LLM_CORRECTED_THRESHOLD} label="Fix extraction prompt" />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {fields.length === 0 && (
        <p className="text-center text-muted-foreground py-4 text-sm">
          No completed fill runs with edits yet.
        </p>
      )}
    </div>
  );
}
