/**
 * PDF Viewer Component
 * Displays PDF documents with pagination, zoom controls, and text selection
 */

import React, { useState, useEffect, useRef } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { ZoomIn, ZoomOut, FileText } from 'lucide-react';
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
  const [containerWidth, setContainerWidth] = useState(null);
  const [loadedPages, setLoadedPages] = useState(3);  // Start with 3 pages
  const pageRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    setPageNumber(defaultPage);
  }, [defaultPage]);

  // Scroll to page when highlight changes
  useEffect(() => {
    if (highlightBbox && highlightBbox.page) {
      const targetPage = highlightBbox.page;

      // Ensure target page is loaded
      if (targetPage > loadedPages) {
        setLoadedPages(targetPage + 2);  // Load a bit extra
      }

      // Scroll to the page after a brief delay (for rendering)
      setTimeout(() => {
        const pageElement = containerRef.current?.querySelector(
          `[data-page-number="${targetPage}"]`
        );
        if (pageElement) {
          pageElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }, 100);
    }
  }, [highlightBbox, loadedPages]);

  // Reset state when PDF URL changes
  useEffect(() => {
    setNumPages(null);
    setPageNumber(1);
    setLoadedPages(3);  // Reset to initial 3 pages
    setLoading(true);
    setError(null);
  }, [pdfUrl]);

  // Measure container width for responsive sizing
  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        // Use 90% of container width for padding
        setContainerWidth(containerRef.current.offsetWidth * 0.9);
      }
    };

    updateWidth();
    window.addEventListener('resize', updateWidth);
    return () => window.removeEventListener('resize', updateWidth);
  }, []);

  // Lazy load more pages as user scrolls
  useEffect(() => {
    if (!containerRef.current || !numPages || loadedPages >= numPages) return;

    const observer = new IntersectionObserver(
      (entries) => {
        // Check if the last page is visible
        if (entries[0].isIntersecting && loadedPages < numPages) {
          // Load 3 more pages
          setLoadedPages(prev => Math.min(prev + 3, numPages));
        }
      },
      {
        root: containerRef.current,
        rootMargin: '200px' // Trigger 200px before reaching bottom
      }
    );

    // Observe the last rendered page
    const lastPageElement = containerRef.current.querySelector(`[data-page-number="${loadedPages}"]`);
    if (lastPageElement) {
      observer.observe(lastPageElement);
    }

    return () => observer.disconnect();
  }, [loadedPages, numPages]);

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
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-muted-foreground" />
          <span className="text-xs font-medium text-muted-foreground">
            {numPages ? `Showing ${Math.min(loadedPages, numPages)} of ${numPages} pages` : 'Loading...'}
          </span>
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
      <div ref={containerRef} className="flex-1 overflow-auto bg-muted/20 p-4 scrollbar-thin">
        <div className="flex flex-col items-center gap-4">
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
            {/* Render multiple pages */}
            {numPages && Array.from(new Array(Math.min(loadedPages, numPages)), (el, index) => {
              const currentPage = index + 1;
              return (
                <div key={`page_${currentPage}`} data-page-number={currentPage} className="mb-4 relative">
                  <Page
                    pageNumber={currentPage}
                    width={containerWidth ? containerWidth * scale : undefined}
                    renderTextLayer={true}
                    renderAnnotationLayer={true}
                    onMouseUp={handleTextSelection}
                    onLoadSuccess={onPageLoadSuccess}
                    className="shadow-md bg-card"
                  />

                  {/* Highlight overlay - show on correct page */}
                  {highlightBbox && highlightBbox.page === currentPage && pageWidth && pageHeight && (
                    <HighlightOverlay
                      bbox={highlightBbox}
                      pageWidth={pageWidth}
                      pageHeight={pageHeight}
                      scale={scale}
                      onClick={handleHighlightClick}
                    />
                  )}

                  {/* Page number label */}
                  <div className="text-center text-xs text-muted-foreground mt-2">
                    Page {currentPage} of {numPages}
                  </div>
                </div>
              );
            })}

            {/* Loading indicator for more pages */}
            {loadedPages < numPages && (
              <div className="flex items-center justify-center p-4 gap-2">
                <div className="animate-spin rounded-full h-6 w-6 border-2 border-primary border-t-transparent"></div>
                <span className="text-sm text-muted-foreground">Loading more pages...</span>
              </div>
            )}
          </Document>
        </div>
      </div>
    </div>
  );
}
