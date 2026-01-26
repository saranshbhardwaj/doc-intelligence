/**
 * PDF Viewer Component
 * Displays PDF documents with pagination, zoom controls, and text selection
 */

import React, { useState, useEffect, useRef } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { ZoomIn, ZoomOut, ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '../ui/button';
import HighlightOverlay from './HighlightOverlay';

// Configure PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

export default function PDFViewer({
  pdfUrl,
  onTextSelect,
  defaultPage = 1,
  highlightBbox = null,  // { page, x0, y0, x1, y1 } for highlighting
  onHighlightClick       // Callback when highlight is clicked
}) {
  const [numPages, setNumPages] = useState(null);
  const [pageNumber, setPageNumber] = useState(defaultPage);
  const [scale, setScale] = useState(1.0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pageWidth, setPageWidth] = useState(null);
  const [pageHeight, setPageHeight] = useState(null);
  const pageRef = useRef(null);

  useEffect(() => {
    setPageNumber(defaultPage);
  }, [defaultPage]);

  // Navigate to page when highlight changes
  useEffect(() => {
    if (highlightBbox && highlightBbox.page !== pageNumber) {
      setPageNumber(highlightBbox.page);
    }
  }, [highlightBbox]);

  // Reset state when PDF URL changes
  useEffect(() => {
    setNumPages(null);
    setPageNumber(1);
    setLoading(true);
    setError(null);
  }, [pdfUrl]);

  function onDocumentLoadSuccess({ numPages }) {
    setNumPages(numPages);
    setLoading(false);
    setError(null);
  }

  function onDocumentLoadError(error) {
    console.error('Error loading PDF:', error);
    setError('Failed to load PDF. Please try again.');
    setLoading(false);
  }

  function handleTextSelection() {
    const selection = window.getSelection();
    const text = selection.toString().trim();

    if (onTextSelect) {
      if (text) {
        // User selected text - pass selection data
        onTextSelect({
          text,
          page: pageNumber,
        });
      } else {
        // User clicked without selecting text - clear selection
        onTextSelect(null);
      }
    }
  }

  function goToPreviousPage() {
    setPageNumber((prev) => Math.max(prev - 1, 1));
  }

  function goToNextPage() {
    setPageNumber((prev) => Math.min(prev + 1, numPages));
  }

  function zoomIn() {
    setScale((prev) => Math.min(prev + 0.1, 2.0));
  }

  function zoomOut() {
    setScale((prev) => Math.max(prev - 0.1, 0.5));
  }

  function onPageLoadSuccess(page) {
    // Get page dimensions for coordinate transformation
    const { width, height } = page.originalWidth
      ? { width: page.originalWidth, height: page.originalHeight }
      : page;
    setPageWidth(width);
    setPageHeight(height);
  }

  function handleHighlightClick() {
    if (onHighlightClick) {
      onHighlightClick();
    }
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 bg-destructive/10 rounded-lg border border-destructive/20">
        <p className="text-destructive mb-4 text-sm">{error}</p>
        <Button
          variant="destructive"
          size="sm"
          onClick={() => {
            setError(null);
            setLoading(true);
          }}
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center justify-between p-2 border-b bg-muted/30">
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={goToPreviousPage}
            disabled={pageNumber <= 1}
            title="Previous Page"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>

          <span className="text-xs font-medium text-muted-foreground px-2 min-w-[80px] text-center">
            {numPages ? `${pageNumber} / ${numPages}` : 'Loading...'}
          </span>

          <Button
            variant="ghost"
            size="icon"
            onClick={goToNextPage}
            disabled={pageNumber >= numPages}
            title="Next Page"
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={zoomOut}
            disabled={scale <= 0.5}
            title="Zoom Out"
          >
            <ZoomOut className="h-4 w-4" />
          </Button>

          <span className="text-xs font-medium text-muted-foreground px-2 min-w-[50px] text-center">
            {Math.round(scale * 100)}%
          </span>

          <Button
            variant="ghost"
            size="icon"
            onClick={zoomIn}
            disabled={scale >= 2.0}
            title="Zoom In"
          >
            <ZoomIn className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* PDF Document */}
      <div className="flex-1 overflow-auto bg-muted/20 p-4 scrollbar-thin">
        <div className="flex justify-center">
          <Document
            key={pdfUrl}
            file={pdfUrl}
            onLoadSuccess={onDocumentLoadSuccess}
            onLoadError={onDocumentLoadError}
            loading={
              <div className="flex items-center justify-center p-8">
                <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent"></div>
              </div>
            }
          >
            <div ref={pageRef} className="relative">
              <Page
                pageNumber={pageNumber}
                scale={scale}
                renderTextLayer={true}
                renderAnnotationLayer={true}
                onMouseUp={handleTextSelection}
                onLoadSuccess={onPageLoadSuccess}
                className="shadow-md bg-card"
              />

              {/* Highlight overlay - shown when citation is clicked */}
              {highlightBbox && highlightBbox.page === pageNumber && pageWidth && pageHeight && (
                <HighlightOverlay
                  bbox={highlightBbox}
                  pageWidth={pageWidth}
                  pageHeight={pageHeight}
                  scale={scale}
                  onClick={handleHighlightClick}
                />
              )}
            </div>
          </Document>
        </div>
      </div>
    </div>
  );
}
