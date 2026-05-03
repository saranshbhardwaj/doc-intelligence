import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, Download, FileSpreadsheet, FileText, Loader2, X } from 'lucide-react';
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

function isSpreadsheetCitation(citation, filename = '', contentType = '') {
  const lowerName = String(filename || citation?.filename || '').toLowerCase();
  const lowerType = String(contentType || '').toLowerCase();
  return citation?.source_kind === 'spreadsheet'
    || lowerName.endsWith('.xlsx')
    || lowerName.endsWith('.xlsm')
    || lowerName.endsWith('.csv')
    || lowerType.includes('spreadsheet')
    || lowerType.includes('text/csv');
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
  const spreadsheetCitation = isSpreadsheetCitation(activeCitation, documentFilename, documentContentType);
  const sheetLocation = activeCitation?.sheet_name
    ? `${activeCitation.sheet_name}${activeCitation.row_start ? ` rows ${activeCitation.row_start}-${activeCitation.row_end}` : ''}`
    : null;

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
          {spreadsheetCitation ? (
            <FileSpreadsheet className="h-4 w-4 shrink-0 text-slate-400" />
          ) : (
            <FileText className="h-4 w-4 shrink-0 text-slate-400" />
          )}
          <span className="truncate text-sm font-medium text-slate-100">
            {documentFilename || activeCitation.filename || 'Data Source'}
          </span>
          {activeCitation.page ? (
            <span className="shrink-0 text-xs text-slate-500">· p.{activeCitation.page}</span>
          ) : null}
          {sheetLocation ? (
            <span className="shrink-0 text-xs text-slate-500">· {sheetLocation}</span>
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
          {sheetLocation ? (
            <span className="text-xs text-slate-400">{sheetLocation}</span>
          ) : null}
        </div>
        {activeCitation.source_text ? (
          <>
            <p className="mt-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Extracted text</p>
            <p className="mt-1 line-clamp-3 text-xs leading-5 text-slate-200">{activeCitation.source_text}</p>
          </>
        ) : (
          <p className="mt-2 text-xs leading-5 text-slate-400">
            {spreadsheetCitation
              ? 'Review the cited sheet and row window from the extracted spreadsheet context.'
              : 'Jump directly to the cited source page to validate the assumption.'}
          </p>
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

        {!isLoadingDoc && documentUrl && spreadsheetCitation ? (
          <div className="h-full overflow-y-auto px-5 py-5 text-sm text-slate-200">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">Spreadsheet source</p>
              <p className="mt-2 text-sm font-semibold text-slate-100">{sheetLocation || 'Spreadsheet rows'}</p>
              <p className="mt-2 text-xs leading-5 text-slate-400">
                Spreadsheet citations are anchored to sheet and row ranges. Open the source workbook if you need to inspect formulas, hidden rows, or formatting.
              </p>
              {activeCitation.source_text ? (
                <pre className="mt-4 max-h-[55vh] overflow-auto whitespace-pre-wrap rounded-xl border border-slate-800 bg-slate-950 p-3 text-xs leading-5 text-slate-200">
                  {activeCitation.source_text}
                </pre>
              ) : null}
              <Button asChild variant="outline" size="sm" className="mt-4 border-slate-700 bg-slate-950 text-slate-100 hover:bg-slate-900">
                <a href={documentUrl} target="_blank" rel="noreferrer">
                  <Download className="mr-2 h-3.5 w-3.5" />
                  Open source file
                </a>
              </Button>
            </div>
          </div>
        ) : null}

        {!isLoadingDoc && documentUrl && !spreadsheetCitation ? (
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
