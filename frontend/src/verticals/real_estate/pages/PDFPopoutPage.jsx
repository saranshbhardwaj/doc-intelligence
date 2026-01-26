/**
 * PDF Pop-Out Window
 *
 * Displays PDF viewer in a separate window for multi-monitor setups.
 * Listens for page navigation commands from other windows (Excel pop-out, main window).
 */

import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useAuth } from '@clerk/clerk-react';
import PDFViewer from '../../../components/pdf/PDFViewer';
import { useTemplateFill, useTemplateFillActions } from '../../../store';
import { Loader2, AlertCircle, FileText } from 'lucide-react';
import { Badge } from '../../../components/ui/badge';

export default function PDFPopoutPage() {
  const { fillRunId } = useParams();
  const { getToken } = useAuth();
  const [currentPage, setCurrentPage] = useState(1);

  const { fillRun, pdfUrl, isLoading, error } = useTemplateFill();
  const { loadFillRun } = useTemplateFillActions();

  // Load fill run data on mount
  useEffect(() => {
    loadFillRun(fillRunId, getToken);
  }, [fillRunId]);

  // Listen for page navigation commands from other windows
  useEffect(() => {
    function handleMessage(event) {
      // Security: In production, validate event.origin
      if (event.data.type === 'NAVIGATE_TO_PAGE') {
        setCurrentPage(event.data.page);
      }
    }

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

  // Notify opener window that we're ready
  useEffect(() => {
    if (window.opener && !window.opener.closed) {
      window.opener.postMessage({ type: 'PDF_POPOUT_READY' }, '*');
    }
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="animate-spin h-8 w-8 text-primary" />
          <span className="text-sm text-muted-foreground">Loading PDF...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="bg-destructive/10 p-6 rounded-lg max-w-md border border-destructive/20">
          <div className="flex items-center mb-4">
            <AlertCircle className="h-6 w-6 text-destructive mr-2" />
            <h2 className="text-lg font-semibold text-foreground">Error</h2>
          </div>
          <p className="text-destructive text-sm">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-background">
      {/* Header */}
      <div className="border-b bg-card px-4 py-2.5 flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-primary" />
            <h2 className="font-medium text-sm text-foreground">PDF Document</h2>
          </div>
          {fillRun?.document_metadata && (
            <Badge variant="secondary" className="text-xs">
              {fillRun.document_metadata.page_count} pages
            </Badge>
          )}
        </div>
      </div>

      {/* PDF Viewer */}
      <div className="flex-1 overflow-hidden">
        {pdfUrl ? (
          <PDFViewer
            pdfUrl={pdfUrl}
            defaultPage={currentPage}
            onTextSelect={() => {}} // No text selection in pop-out
          />
        ) : (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <p className="text-sm">PDF not available</p>
          </div>
        )}
      </div>
    </div>
  );
}
