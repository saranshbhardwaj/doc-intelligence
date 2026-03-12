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
  onHighlightClick,      // Callback when highlight is clicked
  suppressDefaultPageScroll = false
}) {
  const INITIAL_RENDERED_PAGES = 1;
  const PAGE_LOAD_BATCH = 2;

  const [numPages, setNumPages] = useState(null);
  const [pageNumber, setPageNumber] = useState(defaultPage);
  const [scale, setScale] = useState(1.0);
  const [error, setError] = useState(null);
  const [pageDimensions, setPageDimensions] = useState({});
  const [containerWidth, setContainerWidth] = useState(null);
  const [loadedPages, setLoadedPages] = useState(INITIAL_RENDERED_PAGES);
  const [pdfReady, setPdfReady] = useState(false);  // True after PDF document loads
  const containerRef = useRef(null);
  const prevHighlightRef = useRef(null);

  useEffect(() => {
    setPageNumber(defaultPage);
  }, [defaultPage]);

  useEffect(() => {
    prevHighlightRef.current = highlightBbox;
  }, [highlightBbox]);

  // Scroll to page when highlight target changes (with retry until page is rendered).
  useEffect(() => {
    if (!pdfReady || !highlightBbox || !highlightBbox.page) return;

    const targetPage = Number(highlightBbox.page);
    if (!Number.isFinite(targetPage) || targetPage < 1) return;

    setPageNumber(targetPage);

    // Ensure target page is loaded (lazy loading)
    if (targetPage > loadedPages) {
      setLoadedPages((prev) => {
        const desired = targetPage + 2;
        const maxAllowed = numPages || desired;
        return Math.min(Math.max(prev, desired), maxAllowed);
      });
      return;
    }

    let attempts = 0;
    const maxAttempts = 20;
    const timer = setInterval(() => {
      attempts += 1;
      const pageElement = containerRef.current?.querySelector(
        `[data-page-number="${targetPage}"]`
      );
      if (pageElement) {
        pageElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
        clearInterval(timer);
      } else if (attempts >= maxAttempts) {
        clearInterval(timer);
      }
    }, 100);

    return () => clearInterval(timer);
  }, [highlightBbox, pdfReady, loadedPages, numPages]);

  // Scroll for page-only navigation (no bbox payload).
  useEffect(() => {
    if (suppressDefaultPageScroll) return;
    if (!pdfReady || !defaultPage || (highlightBbox && highlightBbox.page)) return;
    if (prevHighlightRef.current?.page && !highlightBbox) return;

    const targetPage = Number(defaultPage);
    if (!Number.isFinite(targetPage) || targetPage < 1) return;

    if (targetPage > loadedPages) {
      setLoadedPages((prev) => {
        const desired = targetPage + 2;
        const maxAllowed = numPages || desired;
        return Math.min(Math.max(prev, desired), maxAllowed);
      });
      return;
    }

    let attempts = 0;
    const maxAttempts = 20;
    const timer = setInterval(() => {
      attempts += 1;
      const pageElement = containerRef.current?.querySelector(
        `[data-page-number="${targetPage}"]`
      );
      if (pageElement) {
        pageElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
        clearInterval(timer);
      } else if (attempts >= maxAttempts) {
        clearInterval(timer);
      }
    }, 100);

    return () => clearInterval(timer);
  }, [defaultPage, pdfReady, loadedPages, numPages, highlightBbox]);

  // Reset state when PDF URL changes
  useEffect(() => {
    setNumPages(null);
    setPageNumber(1);
    setLoadedPages(INITIAL_RENDERED_PAGES);
    setPageDimensions({});
    setError(null);
    setPdfReady(false);  // Wait for new PDF to load before scrolling
  }, [pdfUrl]);

  // Measure container width for responsive sizing using ResizeObserver
  useEffect(() => {
    let debounceTimer = null;

    // Direct set — used only for initial measurement on mount
    const applyWidth = (width) => setContainerWidth(width);

    // Debounced set — used for all resize events to prevent flash caused by
    // the Sheet drawer opening/closing (Radix removes the scrollbar ~17px change)
    const applyWidthDebounced = (width) => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => applyWidth(width), 150);
    };

    // Initial measurement with slight delay to ensure container is rendered
    const initialTimer = setTimeout(() => {
      if (containerRef.current) {
        applyWidth(containerRef.current.offsetWidth * 0.9);
      }
    }, 50);

    // Use ResizeObserver for responsive updates (debounced)
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        applyWidthDebounced(entry.contentRect.width * 0.9);
      }
    });

    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    // Fallback for window resize (debounced)
    const handleWindowResize = () => {
      if (containerRef.current) {
        applyWidthDebounced(containerRef.current.offsetWidth * 0.9);
      }
    };
    window.addEventListener('resize', handleWindowResize);

    return () => {
      clearTimeout(initialTimer);
      clearTimeout(debounceTimer);
      resizeObserver.disconnect();
      window.removeEventListener('resize', handleWindowResize);
    };
  }, []);

  // Lazy load more pages as user scrolls
  useEffect(() => {
    if (!containerRef.current || !numPages || loadedPages >= numPages) return;

    const observer = new IntersectionObserver(
      (entries) => {
        // Check if the last page is visible
        if (entries[0].isIntersecting && loadedPages < numPages) {
          // Load a small batch to keep interactions responsive
          setLoadedPages(prev => Math.min(prev + PAGE_LOAD_BATCH, numPages));
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
    setError(null);
    setPdfReady(true);  // PDF loaded -- safe to scroll to highlights
  }

  function onDocumentLoadError(error) {
    console.error('Error loading PDF:', error);
    setError('Failed to load PDF. Please try again.');
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

  function onPageLoadSuccess(pageNum, page) {
    // Keep per-page dimensions to avoid mismatches when documents include mixed page sizes.
    const width =
      page?.originalWidth ||
      page?.width ||
      (Array.isArray(page?.view) ? Math.abs(page.view[2] - page.view[0]) : null);
    const height =
      page?.originalHeight ||
      page?.height ||
      (Array.isArray(page?.view) ? Math.abs(page.view[3] - page.view[1]) : null);

    if (!width || !height) return;

    setPageDimensions((prev) => {
      const existing = prev[pageNum];
      if (existing?.width === width && existing?.height === height) {
        return prev;
      }
      return {
        ...prev,
        [pageNum]: { width, height },
      };
    });
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
      <div className="flex items-center justify-between px-2 py-1 border-b bg-muted/30">
        <div className="flex items-center gap-2">
          <FileText className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="text-[11px] font-medium text-muted-foreground">
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

          <span className="text-[11px] font-medium text-muted-foreground px-2 min-w-[46px] text-center">
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
            {numPages && Array.from(new Array(Math.min(loadedPages, numPages)), (_, index) => {
              const currentPage = index + 1;
              const renderedPageWidth = containerWidth ? containerWidth * scale : undefined;
              const pageSize = pageDimensions[currentPage];
              const hasRenderableBbox =
                highlightBbox &&
                Number.isFinite(Number(highlightBbox.x0)) &&
                Number.isFinite(Number(highlightBbox.y0)) &&
                Number.isFinite(Number(highlightBbox.x1)) &&
                Number.isFinite(Number(highlightBbox.y1));
              return (
                <div key={`page_${currentPage}`} data-page-number={currentPage} className="mb-4 relative">
                  <Page
                    pageNumber={currentPage}
                    width={renderedPageWidth}
                    renderTextLayer={true}
                    renderAnnotationLayer={true}
                    onMouseUp={handleTextSelection}
                    onLoadSuccess={(page) => onPageLoadSuccess(currentPage, page)}
                    className="shadow-md bg-card"
                  />

                  {/* Highlight overlay - show on correct page */}
                  {hasRenderableBbox && highlightBbox.page === currentPage && pageSize?.width && pageSize?.height && (
                    <HighlightOverlay
                      bbox={highlightBbox}
                      pageWidth={pageSize.width}
                      pageHeight={pageSize.height}
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
