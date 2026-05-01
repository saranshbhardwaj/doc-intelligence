/**
 * CitationDrawer
 * Right-side sheet showing source identity and an inline document viewer.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Alert, AlertDescription } from '@/components/ui/alert';
import DocumentViewer from '@/components/pdf/DocumentViewer';
import { AlertCircle, Download, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAppAuth } from '@/hooks/useAppAuth';
import { getDocumentDownloadUrl } from '@/api/documents';

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

export default function CitationDrawer({ isOpen, onClose, citation }) {
  const { getToken } = useAppAuth();
  const [isLoadingDoc, setIsLoadingDoc] = useState(false);
  const [documentUrl, setDocumentUrl] = useState(null);
  const [documentFilename, setDocumentFilename] = useState('');
  const [documentContentType, setDocumentContentType] = useState('');
  const [documentMissing, setDocumentMissing] = useState(false);
  const [documentError, setDocumentError] = useState(null);

  const activeCitation = citation ?? null;

  const highlightPayload = useMemo(() => buildHighlightPayload(activeCitation), [activeCitation]);
  const defaultPage = Number(activeCitation?.page);
  const spreadsheetCitation = isSpreadsheetCitation(activeCitation, documentFilename, documentContentType);

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
    return null;
  }

  return (
    <Sheet open={isOpen} onOpenChange={onClose}>
      <SheetContent side="right" className="flex h-full w-[min(92vw,1120px)] max-w-none flex-col overflow-hidden p-0 sm:w-[min(90vw,1120px)]">
        <SheetHeader>
          <div className="border-b border-border/60 px-6 py-5">
            <SheetTitle>Data Source</SheetTitle>
          </div>
        </SheetHeader>

        <div className="grid flex-1 min-h-0 grid-cols-1 overflow-hidden md:grid-cols-[300px,minmax(0,1fr)] xl:grid-cols-[340px,minmax(0,1fr)]">
          <div className="min-h-0 overflow-y-auto border-b border-border/60 px-6 py-5 md:border-b-0 md:border-r">
            <div className="space-y-4">
              {/* <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="outline">{docTypeLabel}</Badge>
                {activeCitation.page && (
                  <span className="text-sm text-muted-foreground">
                    Page {activeCitation.page}
                  </span>
                )}
                {(documentFilename || activeCitation.filename) && (
                  <span className="max-w-[220px] truncate text-xs text-muted-foreground" title={documentFilename || activeCitation.filename}>
                    {documentFilename || activeCitation.filename}
                  </span>
                )}
              </div> */}

              {documentError ? (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>{documentError}</AlertDescription>
                </Alert>
              ) : null}

              {documentMissing ? (
                <Alert>
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>The source document for this citation is no longer available.</AlertDescription>
                </Alert>
              ) : null}
            </div>
          </div>

          <div className="min-h-0 overflow-hidden bg-muted/20">
            {isLoadingDoc ? (
              <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading source document...
              </div>
            ) : null}

            {!isLoadingDoc && documentUrl && spreadsheetCitation ? (
              <div className="h-full overflow-y-auto p-6">
                <div className="rounded-xl border bg-card p-4">
                  <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Spreadsheet source</p>
                  {activeCitation?.sheet_name ? (
                    <p className="mt-2 text-sm font-medium">
                      {activeCitation.sheet_name}
                      {activeCitation.row_start ? ` rows ${activeCitation.row_start}-${activeCitation.row_end}` : ''}
                    </p>
                  ) : null}
                  {activeCitation?.source_text ? (
                    <pre className="mt-4 max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-lg bg-muted p-3 text-xs leading-5">
                      {activeCitation.source_text}
                    </pre>
                  ) : null}
                  <Button asChild variant="outline" size="sm" className="mt-4">
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
              <div className="flex h-full items-center justify-center px-6 text-center text-sm text-muted-foreground">
                Select a cited field to preview its source document.
              </div>
            ) : null}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
