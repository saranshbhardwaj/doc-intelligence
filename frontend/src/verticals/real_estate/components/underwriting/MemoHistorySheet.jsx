import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Download,
  FileText,
  History,
  Loader2,
  RotateCcw,
  Trash2,
  XCircle,
} from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { toast } from 'sonner';
import { listMemos, getMemoDownloadUrl, deleteMemo } from '../../../../api/re-memos';
import {
  canDeleteMemo,
  canDownloadMemo,
  formatMemoDate,
  getLatestMemo,
  getMemoStatusLabel,
  getMemoStatusTone,
  getMemoWarningLabel,
} from './memoHistoryUtils';

export default function MemoHistorySheet({
  runId,
  getToken,
  refreshKey,
  dealName,
  open,
  onOpenChange,
  onRegenerate,
}) {
  const [memos, setMemos] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [downloadingId, setDownloadingId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [memoToDelete, setMemoToDelete] = useState(null);
  const latestMemo = useMemo(() => getLatestMemo(memos), [memos]);

  const reload = useCallback(async () => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listMemos(getToken, runId);
      setMemos(data);
    } catch (err) {
      setError(err?.message || 'Failed to load memo history.');
    } finally {
      setLoading(false);
    }
  }, [getToken, runId]);

  useEffect(() => {
    reload();
  }, [reload, refreshKey]);

  const handleDownload = async (memoId) => {
    try {
      setDownloadingId(memoId);
      setError(null);
      const url = await getMemoDownloadUrl(getToken, memoId);
      window.open(url, '_blank', 'noopener,noreferrer');
    } catch (err) {
      setError(err?.response?.data?.detail || 'Download failed.');
    } finally {
      setDownloadingId(null);
    }
  };

  const handleRegenerate = (memo) => {
    onOpenChange?.(false);
    onRegenerate?.(memo);
  };

  const handleDeleteConfirmed = async () => {
    if (!memoToDelete) return;
    try {
      setDeletingId(memoToDelete.id);
      setError(null);
      const result = await deleteMemo(getToken, memoToDelete.id);
      setMemos((prev) => {
        const next = prev.filter((memo) => memo.id !== memoToDelete.id);
        if (next.length === 0) onOpenChange?.(false);
        return next;
      });
      toast.success(`Memo v${memoToDelete.version} deleted`);
      if (result?.warnings?.length) {
        setError(result.warnings[0]);
        toast.warning(result.warnings[0]);
      }
      setMemoToDelete(null);
    } catch (err) {
      if (err?.response?.status === 404) {
        setMemos((prev) => prev.filter((memo) => memo.id !== memoToDelete.id));
        toast.success(`Memo v${memoToDelete.version} removed`);
        setMemoToDelete(null);
      } else if (err?.response?.status === 409) {
        setError('Memo is still generating and cannot be deleted yet.');
        toast.error('Memo is still generating');
      } else {
        setError(err?.response?.data?.detail || 'Failed to delete memo.');
        toast.error('Failed to delete memo');
      }
    } finally {
      setDeletingId(null);
    }
  };

  if (loading && memos.length === 0) {
    return (
      <Button variant="outline" size="sm" disabled className="underwriting-memo-secondary">
        <Loader2 className="h-4 w-4 animate-spin" />
        Past memos
      </Button>
    );
  }

  if (!memos.length && !error) return null;

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onOpenChange?.(true)}
        className="underwriting-memo-secondary"
      >
        <History className="h-4 w-4" />
        Past memos
        <span className="underwriting-memo-count">{memos.length}</span>
      </Button>

      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent
          side="right"
          className="flex h-full w-[100vw] max-w-none flex-col overflow-hidden bg-background p-0 sm:w-[560px] sm:max-w-[560px]"
        >
          <div className="border-b border-border/70 bg-gradient-to-b from-uw-citation-soft/70 to-card px-5 py-4 backdrop-blur-xl">
            <SheetHeader className="space-y-1 text-left">
              <div className="flex items-center gap-2 pr-8">
                <div className="underwriting-memo-sheet-mark">
                  <FileText className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-uw-citation">
                    IC memos
                  </p>
                  <SheetTitle className="mt-1 font-display text-lg font-semibold tracking-tight">
                    Memo history
                  </SheetTitle>
                </div>
              </div>
              <SheetDescription className="leading-6">
                {memos.length} version{memos.length === 1 ? '' : 's'}
                {dealName ? ` for ${dealName}` : ''}
              </SheetDescription>
            </SheetHeader>
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-4">
            {error ? (
              <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
                {error}
              </div>
            ) : null}

            {latestMemo ? (
              <LatestMemoCard
                memo={latestMemo}
                downloading={downloadingId === latestMemo.id}
                onDownload={handleDownload}
                onRegenerate={handleRegenerate}
              />
            ) : null}

            <div className="mt-5">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
                  Versions
                </p>
                {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" /> : null}
              </div>
              <div className="overflow-hidden rounded-[1rem] border border-border/70 bg-card shadow-panel">
                {memos.map((memo) => (
                  <MemoHistoryRow
                    key={memo.id}
                    memo={memo}
                    latest={memo.id === latestMemo?.id}
                    downloading={downloadingId === memo.id}
                    deleting={deletingId === memo.id}
                    onDownload={handleDownload}
                    onRegenerate={handleRegenerate}
                    onDeleteRequest={setMemoToDelete}
                  />
                ))}
              </div>
            </div>
          </div>
        </SheetContent>
      </Sheet>

      <AlertDialog open={Boolean(memoToDelete)} onOpenChange={(nextOpen) => !nextOpen && setMemoToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete memo v{memoToDelete?.version}?</AlertDialogTitle>
            <AlertDialogDescription>
              This removes the memo from history and deletes the generated document. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={Boolean(deletingId)}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirmed}
              disabled={Boolean(deletingId)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deletingId ? 'Deleting...' : 'Delete memo'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

function LatestMemoCard({ memo, downloading, onDownload, onRegenerate }) {
  const warningLabel = getMemoWarningLabel(memo.section_warnings);
  return (
    <section className="underwriting-memo-latest">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-uw-citation">
            Latest memo
          </p>
          <h3 className="mt-2 font-display text-xl font-semibold tracking-tight text-foreground">
            Version {memo.version}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Generated {formatMemoDate(memo.completed_at || memo.created_at)}
          </p>
        </div>
        <StatusPill status={memo.status} />
      </div>

      {warningLabel ? (
        <div className="mt-4 flex items-start gap-2 rounded-lg border border-uw-risk/25 bg-uw-risk-soft/70 p-3 text-xs text-uw-risk">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{warningLabel} in generated sections</span>
        </div>
      ) : (
        <div className="mt-4 flex items-center gap-2 rounded-lg border border-uw-success/25 bg-uw-success-soft/70 p-3 text-xs text-uw-success">
          <CheckCircle2 className="h-3.5 w-3.5" />
          <span>No section warnings recorded</span>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          size="sm"
          onClick={() => onDownload(memo.id)}
          disabled={!canDownloadMemo(memo) || downloading}
          className="h-8 gap-1.5"
        >
          {downloading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
          Download .docx
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => onRegenerate(memo)}
          className="h-8 gap-1.5"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Regenerate
        </Button>
      </div>
    </section>
  );
}

function MemoHistoryRow({ memo, latest, downloading, deleting, onDownload, onRegenerate, onDeleteRequest }) {
  const warningLabel = getMemoWarningLabel(memo.section_warnings);
  const deleteAllowed = canDeleteMemo(memo);
  return (
    <div className="underwriting-memo-row">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-foreground">Version {memo.version}</span>
          {latest ? <span className="underwriting-memo-latest-chip">Latest</span> : null}
          <StatusPill status={memo.status} />
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {formatMemoDate(memo.completed_at || memo.created_at)}
        </p>
        {warningLabel ? (
          <p className="mt-1 flex items-center gap-1 text-xs text-uw-risk">
            <AlertTriangle className="h-3 w-3" />
            {warningLabel}
          </p>
        ) : null}
        {memo.error_message ? (
          <p className="mt-1 line-clamp-2 text-xs text-destructive">{memo.error_message}</p>
        ) : null}
      </div>
      <div className="flex items-center gap-1">
        <Button
          size="icon"
          variant="ghost"
          onClick={() => onDownload(memo.id)}
          disabled={!canDownloadMemo(memo) || downloading}
          className="h-8 w-8"
          title="Download memo"
        >
          {downloading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
        </Button>
        <Button
          size="icon"
          variant="ghost"
          onClick={() => onRegenerate(memo)}
          className="h-8 w-8"
          title="Regenerate from this memo"
        >
          <RotateCcw className="h-3.5 w-3.5" />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          onClick={() => onDeleteRequest(memo)}
          disabled={!deleteAllowed || deleting}
          className="h-8 w-8 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          title={deleteAllowed ? 'Delete memo' : 'Memo is still generating'}
        >
          {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
        </Button>
      </div>
    </div>
  );
}

function StatusPill({ status }) {
  const tone = getMemoStatusTone(status);
  const Icon = tone === 'success' ? CheckCircle2
    : tone === 'danger' ? XCircle
    : tone === 'active' ? Loader2
    : Clock3;
  return (
    <span className="underwriting-memo-status" data-tone={tone}>
      <Icon className={`h-3 w-3 ${tone === 'active' ? 'animate-spin' : ''}`} />
      {getMemoStatusLabel(status)}
    </span>
  );
}
