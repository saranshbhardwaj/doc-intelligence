import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, AlertTriangle, Loader2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { streamMemoProgress, getMemoDownloadUrl } from '../../../../api/re-memos';

/**
 * Slide-in drawer that subscribes to memo job SSE progress, then offers download.
 *
 * Props:
 *   - open {boolean}
 *   - onClose {Function}
 *   - jobId {string}
 *   - memoId {string}
 *   - getToken {Function}
 */
export default function CreditMemoProgress({ open, onClose, jobId, memoId, getToken }) {
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('Starting…');
  const [status, setStatus] = useState('running'); // running | complete | failed
  const [error, setError] = useState(null);
  const [downloadUrl, setDownloadUrl] = useState(null);
  const connRef = useRef(null);
  const completedRef = useRef(false);

  useEffect(() => {
    if (!open || !jobId) return undefined;

    setProgress(0);
    setMessage('Starting…');
    setStatus('running');
    setError(null);
    setDownloadUrl(null);
    completedRef.current = false;

    let cancelled = false;

    streamMemoProgress(getToken, jobId, {
      onProgress: (evt) => {
        if (typeof evt.progress === 'number') setProgress(evt.progress);
        if (evt.message) setMessage(evt.message);
      },
      onComplete: async () => {
        if (cancelled) return;
        completedRef.current = true;
        setStatus('complete');
        setProgress(100);
        setMessage('Ready');
        try {
          const url = await getMemoDownloadUrl(getToken, memoId);
          if (!cancelled) setDownloadUrl(url);
        } catch {
          if (!cancelled) setError('Could not fetch download link. Try refreshing.');
        }
      },
      onError: (msg) => {
        if (cancelled) return;
        // Ignore connection-drop noise after we've already completed —
        // EventSource fires onerror when the server closes after the `end`
        // event, even though the job succeeded.
        if (completedRef.current) return;
        setStatus('failed');
        setError(typeof msg === 'string' ? msg : 'Memo generation failed.');
      },
      onEnd: () => {
        // Stream closed normally — nothing to do; onComplete already handled
        // the success path.
      },
    }).then((cleanup) => {
      if (!cancelled) {
        connRef.current = cleanup;
      } else {
        // Already unmounted before the promise resolved — close immediately
        try { cleanup?.(); } catch { /* ignore */ }
      }
    }).catch((err) => {
      if (!cancelled) {
        setStatus('failed');
        setError(err?.message || 'Failed to connect to progress stream.');
      }
    });

    return () => {
      cancelled = true;
      try {
        connRef.current?.();
      } catch {
        /* ignore */
      }
      connRef.current = null;
    };
  }, [open, jobId, memoId, getToken]);

  if (!open) return null;

  return (
    <div className="fixed bottom-4 right-4 z-40 w-[calc(100vw-2rem)] max-w-sm rounded-[1rem] border border-border/70 bg-card p-4 shadow-shell">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {status === 'running' ? <Loader2 className="h-4 w-4 animate-spin text-primary" /> : null}
          {status === 'complete' ? <CheckCircle2 className="h-4 w-4 text-uw-success" /> : null}
          {status === 'failed' ? <AlertTriangle className="h-4 w-4 text-destructive" /> : null}
          <p className="text-sm font-semibold">IC memo</p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close">
          <X className="h-4 w-4 text-muted-foreground hover:text-foreground" />
        </button>
      </div>

      <Progress value={progress} className="mb-2" />
      <p className="text-xs text-muted-foreground mb-3">{message}</p>

      {downloadUrl ? (
        <a href={downloadUrl} target="_blank" rel="noopener noreferrer">
          <Button className="w-full">Download .docx</Button>
        </a>
      ) : null}

      {error ? (
        <div className="mt-2 rounded-lg border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">
          {error}
        </div>
      ) : null}
    </div>
  );
}
