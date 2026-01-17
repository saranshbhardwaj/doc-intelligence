/**
 * Excel Pop-Out Window
 *
 * Displays Excel grid with full editing capabilities in a separate window.
 * Has its own drawer for editing mappings.
 * Sends page navigation commands to PDF pop-out window.
 */

import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { useAuth } from '@clerk/clerk-react';
import ExcelGridView from '../components/ExcelGridView';
import { useTemplateFill, useTemplateFillActions } from '../../../store';
import { Loader2, AlertCircle, Table } from 'lucide-react';
import { Badge } from '../../../components/ui/badge';

export default function ExcelPopoutPage() {
  const { fillRunId } = useParams();
  const { getToken } = useAuth();
  const pdfPopoutRef = useRef(null);

  const { fillRun, isLoading, error } = useTemplateFill();
  const { loadFillRun } = useTemplateFillActions();

  // Load fill run data on mount
  useEffect(() => {
    loadFillRun(fillRunId, getToken);
  }, [fillRunId]);

  // Handle citation clicks - navigate PDF pop-out
  function handleCitationClick(pageNumber) {
    console.log('📊 Excel Pop-out: Citation clicked, navigating to page', pageNumber);

    // Try to find PDF pop-out window
    // Check if we have a reference to it
    if (pdfPopoutRef.current && !pdfPopoutRef.current.closed) {
      pdfPopoutRef.current.postMessage(
        { type: 'NAVIGATE_TO_PAGE', page: pageNumber },
        '*'
      );
    } else {
      // Try to find it via opener (if this was opened from main window)
      if (window.opener && !window.opener.closed) {
        // Ask main window to forward to PDF pop-out
        window.opener.postMessage(
          { type: 'NAVIGATE_PDF_TO_PAGE', page: pageNumber },
          '*'
        );
      }
    }
  }

  // Listen for messages from other windows
  useEffect(() => {
    function handleMessage(event) {
      // Register PDF pop-out window when it announces itself
      if (event.data.type === 'PDF_POPOUT_READY') {
        console.log('📊 Excel Pop-out: PDF pop-out registered');
        pdfPopoutRef.current = event.source;
      }
    }

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

  // Notify opener window that we're ready
  useEffect(() => {
    if (window.opener && !window.opener.closed) {
      window.opener.postMessage({ type: 'EXCEL_POPOUT_READY' }, '*');
    }
  }, []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="animate-spin h-8 w-8 text-primary" />
          <span className="text-sm text-muted-foreground">Loading Excel...</span>
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

  if (!fillRun) {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <p className="text-muted-foreground text-sm">Fill run not found</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-background">
      {/* Header */}
      <div className="border-b bg-card px-4 py-2.5 flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Table className="h-4 w-4 text-primary" />
            <h2 className="font-medium text-sm text-foreground">Excel Preview</h2>
          </div>
          <Badge variant="secondary" className="text-xs">
            {fillRun.total_fields_mapped || 0} / {fillRun.total_fields_detected || 0} mapped
          </Badge>
        </div>
      </div>

      {/* Excel Grid with Drawer */}
      <div className="flex-1 overflow-hidden">
        <ExcelGridView
          fillRunId={fillRunId}
          extractedData={fillRun.extracted_data}
          fieldMapping={fillRun.field_mapping}
          templateId={fillRun.template_id}
          onCitationClick={handleCitationClick}
        />
      </div>
    </div>
  );
}
