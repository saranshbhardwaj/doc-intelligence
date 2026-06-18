import { useCallback, useEffect, useState } from 'react';
import { ChevronDown, Download, RotateCcw, AlertTriangle, FileText } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { listMemos, getMemoDownloadUrl } from '../../../../api/re-memos';

/**
 * Past-memos popover. Renders an outline button "Past memos (N)" that opens a
 * dropdown listing prior memos with download and regenerate actions. Hidden
 * entirely until at least one memo exists. Sits inline alongside the
 * "Generate Credit Memo" button on UnderwritingResult.
 */
export default function PastMemosList({ runId, getToken, refreshKey, onRegenerate }) {
  const [memos, setMemos] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listMemos(getToken, runId);
      setMemos(data);
    } catch (err) {
      setError(err?.message || 'Failed to load past memos.');
    } finally {
      setLoading(false);
    }
  }, [getToken, runId]);

  useEffect(() => {
    reload();
  }, [reload, refreshKey]);

  const handleDownload = async (memoId) => {
    try {
      const url = await getMemoDownloadUrl(getToken, memoId);
      window.open(url, '_blank', 'noopener,noreferrer');
    } catch (err) {
      setError(err?.response?.data?.detail || 'Download failed.');
    }
  };

  // Hide entirely until at least one memo exists.
  if (loading && memos.length === 0) return null;
  if (!memos.length && !error) return null;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="underwriting-memo-secondary">
          <FileText className="h-4 w-4" />
          Past memos
          <span className="underwriting-memo-count">
            {memos.length}
          </span>
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 overflow-hidden rounded-[1rem] border-border/70 bg-card p-0 shadow-panel">
        <div className="border-b border-border/70 bg-uw-citation-soft/50 px-3 py-3">
          <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-uw-citation">
            Past memos
          </p>
        </div>

        {error ? (
          <div className="mx-3 mt-3 rounded-md border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">
            {error}
          </div>
        ) : null}

        <ul className="max-h-80 divide-y divide-border/60 overflow-y-auto">
          {memos.map((m) => (
            <li
              key={m.id}
              className="flex flex-wrap items-center justify-between gap-2 px-3 py-3 text-sm transition-colors hover:bg-muted/35"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-foreground">v{m.version}</span>
                  <span className="text-xs text-muted-foreground">
                    {m.created_at?.slice(0, 10)}
                  </span>
                  <StatusBadge status={m.status} />
                </div>
                {m.section_warnings?.length ? (
                  <span
                    title={m.section_warnings.join('\n')}
                    className="mt-1 inline-flex items-center gap-1 text-xs text-warning"
                  >
                    <AlertTriangle className="h-3 w-3" />
                    {m.section_warnings.length} warning{m.section_warnings.length > 1 ? 's' : ''}
                  </span>
                ) : null}
              </div>
              <div className="flex items-center gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => handleDownload(m.id)}
                  disabled={m.status !== 'complete'}
                  className="h-7 gap-1 px-2 text-xs"
                >
                  <Download className="h-3.5 w-3.5" />
                  Download
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => onRegenerate?.(m)}
                  className="h-7 gap-1 px-2 text-xs"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  Regenerate
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}

function StatusBadge({ status }) {
  const tone =
    status === 'complete'
      ? 'bg-success/15 text-success'
      : status === 'failed'
      ? 'bg-destructive/15 text-destructive'
      : 'bg-muted text-muted-foreground';
  return (
    <span
      className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${tone}`}
    >
      {status}
    </span>
  );
}
