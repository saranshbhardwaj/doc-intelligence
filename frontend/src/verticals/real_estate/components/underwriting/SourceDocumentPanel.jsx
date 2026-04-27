import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, FileText, Loader2, X } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import DocumentViewer from '@/components/pdf/DocumentViewer';
import { useAppAuth } from '@/hooks/useAppAuth';
import { getDocumentDownloadUrl } from '@/api/documents';
import { UnderwritingStatusBadge } from './UnderwritingUI';

const DOC_TYPE_LABELS = {
  om: 'Offering Memo',
  rent_roll: 'Rent Roll',
  t12: 'T-12',
};

function buildHighlightPayload(citation) {
  if (!citation) return null;

  const bboxPage = Number(citation.bbox?.page);
  if (citation.bbox && Number.isFinite(bboxPage) && bboxPage > 0) {
    return {
      ...citation.bbox,
      page: bboxPage,
      __ts: Date.now(),
    };
  }

  const page = Number(citation.page);
  if (Number.isFinite(page) && page > 0) {
    return {
      page,
      __scrollOnly: true,
      __ts: Date.now(),
    };
  }

  return null;
}

export default function SourceDocumentPanel({ citation, isOpen = true, onClose = null }) {
  const { getToken } = useAppAuth();
  const [isLoadingDoc, setIsLoadingDoc] = useState(false);
  const [documentUrl, setDocumentUrl] = useState(null);
  const [documentFilename, setDocumentFilename] = useState('');
  const [documentContentType, setDocumentContentType] = useState('');
  const [documentMissing, setDocumentMissing] = useState(false);
  const [documentError, setDocumentError] = useState(null);

  const activeCitation = citation ?? null;
  const docTypeLabel = DOC_TYPE_LABELS[activeCitation?.doc_type] || activeCitation?.doc_type || 'Document';
  const highlightPayload = useMemo(() => buildHighlightPayload(activeCitation), [activeCitation]);
  const defaultPage = Number(activeCitation?.page);

  useEffect(() => {
    if (!isOpen || !activeCitation?.document_id) {
      setIsLoadingDoc(false);
      setDocumentUrl(null);
      setDocumentFilename('');
      setDocumentContentType('');
      setDocumentMissing(false);
      setDocumentError(null);
      return undefined;
    }

    let cancelled = false;

    async function loadDocument() {
      setIsLoadingDoc(true);
      setDocumentError(null);
      setDocumentMissing(false);

      try {
        const result = await getDocumentDownloadUrl(getToken, activeCitation.document_id);
        if (cancelled) return;

        if (result?.missing) {
          setDocumentUrl(null);
          setDocumentFilename('');
          setDocumentContentType('');
          setDocumentMissing(true);
          return;
        }

        setDocumentUrl(result?.url || null);
        setDocumentFilename(result?.filename || '');
        setDocumentContentType(result?.content_type || '');
      } catch (error) {
        if (cancelled) return;
        setDocumentUrl(null);
        setDocumentFilename('');
        setDocumentContentType('');
        setDocumentError('Failed to load the source document.');
        console.error('Failed to load source document', error);
      } finally {
        if (!cancelled) {
          setIsLoadingDoc(false);
        }
      }
    }

    loadDocument();

    return () => {
      cancelled = true;
    };
  }, [activeCitation?.document_id, getToken, isOpen]);

  if (!activeCitation) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-950 px-6 text-center text-sm text-slate-400">
        Select a cited field to preview its source document.
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden border-l border-slate-800 bg-slate-950">
      <div className="flex shrink-0 items-center justify-between border-b border-slate-800 bg-slate-950/95 px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <FileText className="h-4 w-4 shrink-0 text-slate-400" />
          <span className="truncate text-sm font-medium text-slate-100">
            {documentFilename || activeCitation.filename || 'Data Source'}
          </span>
          {activeCitation.page ? (
            <span className="shrink-0 text-xs text-slate-500">· p.{activeCitation.page}</span>
          ) : null}
        </div>
        {onClose ? (
          <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0 text-slate-400 hover:bg-slate-900 hover:text-slate-100" onClick={onClose} title="Close source panel">
            <X className="h-4 w-4" />
          </Button>
        ) : null}
      </div>

      <div className="shrink-0 border-b border-slate-800 bg-slate-900/80 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <UnderwritingStatusBadge tone="active">{docTypeLabel}</UnderwritingStatusBadge>
          {activeCitation.page ? (
            <span className="text-xs text-slate-400">Page {activeCitation.page}</span>
          ) : null}
        </div>
        {activeCitation.source_text ? (
          <>
            <p className="mt-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Extracted text</p>
            <p className="mt-1 line-clamp-3 text-xs leading-5 text-slate-200">{activeCitation.source_text}</p>
          </>
        ) : (
          <p className="mt-2 text-xs leading-5 text-slate-400">Jump directly to the cited source page to validate the assumption.</p>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-hidden bg-slate-950">
        {isLoadingDoc ? (
          <div className="flex h-full items-center justify-center gap-2 text-sm text-slate-400">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading source document...
          </div>
        ) : null}

        {!isLoadingDoc && documentError ? (
          <div className="flex h-full items-center justify-center px-6">
            <Alert variant="destructive" className="max-w-sm">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{documentError}</AlertDescription>
            </Alert>
          </div>
        ) : null}

        {!isLoadingDoc && documentMissing ? (
          <div className="flex h-full items-center justify-center px-6">
            <Alert className="max-w-sm">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>The source document for this citation is no longer available.</AlertDescription>
            </Alert>
          </div>
        ) : null}

        {!isLoadingDoc && documentUrl ? (
          <DocumentViewer
            fileUrl={documentUrl}
            filename={documentFilename || activeCitation.filename || ''}
            contentType={documentContentType || undefined}
            defaultPage={Number.isFinite(defaultPage) && defaultPage > 0 ? defaultPage : 1}
            highlightBbox={highlightPayload}
          />
        ) : null}

        {!isLoadingDoc && !documentUrl && !documentMissing && !documentError ? (
          <div className="flex h-full items-center justify-center px-6 text-center text-sm text-slate-400">
            No document available for this citation.
          </div>
        ) : null}
      </div>
    </div>
  );
}
