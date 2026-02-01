/**
 * ComparisonPanel Component
 *
 * Full-screen side-by-side document comparison view showing:
 * - Document selector tabs
 * - View mode toggle (Cards | Table | PDFs)
 * - Side-by-side PDF viewers with highlights
 * - Topic navigation bar
 *
 * Rendered as a Sheet that slides from the right.
 */

import { useState, useMemo, useEffect } from "react";
import { useAuth } from "@clerk/clerk-react";
import {
  Sheet,
  SheetContent,
  SheetTitle,
} from "../ui/sheet";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { ScrollArea } from "../ui/scroll-area";
import { Card } from "../ui/card";
import { useComparison, useChatActions, usePdfViewer } from "../../store";
import PairedChunksView from "../chat/comparison/PairedChunksView";
import ComparisonTable from "./ComparisonTable";
import PDFViewer from "../pdf/PDFViewer";
import Spinner from "../common/Spinner";
import {
  ResizablePanelGroup as InnerResizablePanelGroup,
  ResizablePanel as InnerResizablePanel,
  ResizableHandle as InnerResizableHandle,
} from "../ui/resizable";

export default function ComparisonPanel({ isOpen, onClose }) {
  // 1. ALL HOOKS FIRST (no conditions before these)
  const { getToken } = useAuth();
  const comparison = useComparison();
  const pdfViewer = usePdfViewer();
  const { setComparisonViewMode, loadPdfUrlForDocument } = useChatActions();
  const [viewMode, setViewMode] = useState("cards"); // 'cards' | 'table' | 'pdfs'
  const [pdfUrls, setPdfUrls] = useState({});
  const [loadingPdfs, setLoadingPdfs] = useState(false);

  // 2. Extract data safely (handles null)
  const context = comparison?.context;
  const documents = context?.documents || [];
  const paired_chunks = context?.paired_chunks || [];
  const clustered_chunks = context?.clustered_chunks || [];
  const isPaired = paired_chunks.length > 0;
  const chunks = isPaired ? paired_chunks : clustered_chunks;

  // 3. ALL REMAINING HOOKS
  const topics = useMemo(() => {
    if (!chunks || chunks.length === 0) return [];
    const topicSet = new Set(chunks.map((c) => c.topic));
    return Array.from(topicSet).sort();
  }, [chunks]);

  useEffect(() => {
    if (viewMode === "pdfs" && documents.length > 0) {
      const loadPdfUrls = async () => {
        setLoadingPdfs(true);
        const urls = {};

        // Load URLs for first 2 documents (for side-by-side)
        const docsToLoad = documents.slice(0, 2);

        await Promise.all(
          docsToLoad.map(async (doc) => {
            const url = await loadPdfUrlForDocument(doc.id, getToken);
            if (url) {
              urls[doc.id] = url;
            }
          })
        );

        setPdfUrls(urls);
        setLoadingPdfs(false);
      };

      loadPdfUrls();
    }
  }, [viewMode, documents, getToken, loadPdfUrlForDocument]);

  // 4. NOW conditional return is safe
  if (!isOpen || !context) {
    return null;
  }

  const handleViewModeChange = (mode) => {
    setViewMode(mode);
    setComparisonViewMode(mode);
  };

  const toTopicSlug = (value) =>
    String(value || "")
      .toLowerCase()
      .trim()
      .replace(/\s+/g, "-")
      .replace(/[^a-z0-9-]/g, "");

  const scrollToTopic = (topic) => {
    const slug = toTopicSlug(topic);
    const target = document.querySelector(
      `[data-comparison-topic="${slug}"]`
    );
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <Sheet open={isOpen} onOpenChange={onClose}>
      <SheetContent
        side="right"
        className="!w-[98vw] !max-w-none sm:!max-w-none p-0 flex flex-col bg-background"
      >
        {/* Header */}
        <div className="comparison-header">
          <div className="space-y-1">
            <SheetTitle className="comparison-title">
              Document Comparison
            </SheetTitle>
            <p className="comparison-subtitle">
              Review matched sections, citations, and side-by-side context.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="text-xs">
              {documents.length} documents
            </Badge>
          </div>
        </div>

        {/* Toolbar */}
        <div className="comparison-toolbar">
          {/* View mode toggle */}
          <div className="comparison-segment">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleViewModeChange("cards")}
              className={`comparison-segment-button ${
                viewMode === "cards"
                  ? "bg-background shadow-sm text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Cards
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleViewModeChange("table")}
              className={`comparison-segment-button ${
                viewMode === "table"
                  ? "bg-background shadow-sm text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Table
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleViewModeChange("pdfs")}
              className={`comparison-segment-button ${
                viewMode === "pdfs"
                  ? "bg-background shadow-sm text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              PDFs
            </Button>
          </div>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {viewMode === "cards" && (
            <div className="flex-1 min-h-0 p-5">
              <Card className="comparison-surface h-full min-h-0 overflow-hidden">
                <ScrollArea className="h-full p-4 scrollbar-thin">
                  <PairedChunksView context={context} internalScroll={false} />
                </ScrollArea>
              </Card>
            </div>
          )}

          {viewMode === "table" && (
            <div className="flex-1 min-h-0 p-5">
              <Card className="comparison-surface h-full min-h-0 overflow-hidden">
                <ScrollArea className="h-full p-4 scrollbar-thin">
                  <ComparisonTable context={context} />
                </ScrollArea>
              </Card>
            </div>
          )}

          {viewMode === "pdfs" && (
            <div className="flex-1 overflow-hidden">
              {loadingPdfs ? (
                <div className="flex items-center justify-center h-full">
                  <Spinner size="lg" />
                  <span className="ml-3 text-sm text-muted-foreground">
                    Loading PDFs...
                  </span>
                </div>
              ) : (
                <InnerResizablePanelGroup direction="horizontal" className="h-full">
                  {/* Left PDF */}
                  <InnerResizablePanel defaultSize={50} minSize={30}>
                    <div className="h-full flex flex-col bg-background overflow-hidden">
                      <div className="bg-card px-4 py-2 border-b flex-shrink-0">
                        <div className="flex items-center gap-2">
                          <Badge
                            variant="secondary"
                            className="text-xs bg-doc-a/10 text-doc-a"
                          >
                            Doc A
                          </Badge>
                          <h3 className="font-medium text-xs text-foreground truncate">
                            {documents[0]?.filename.split("/").pop()}
                          </h3>
                        </div>
                      </div>
                      <div className="flex-1 overflow-hidden">
                        {pdfUrls[documents[0]?.id] ? (
                          <PDFViewer
                            pdfUrl={pdfUrls[documents[0]?.id]}
                            highlightBbox={
                              pdfViewer.highlightBbox?.docId === "A"
                                ? pdfViewer.highlightBbox
                                : null
                            }
                            onHighlightClick={() => {}}
                          />
                        ) : (
                          <div className="flex items-center justify-center h-full text-muted-foreground">
                            <p className="text-sm">No PDF available</p>
                          </div>
                        )}
                      </div>
                    </div>
                  </InnerResizablePanel>

                  <InnerResizableHandle withHandle />

                  {/* Right PDF */}
                  {documents.length > 1 && (
                    <InnerResizablePanel defaultSize={50} minSize={30}>
                      <div className="h-full flex flex-col bg-background overflow-hidden">
                        <div className="bg-card px-4 py-2 border-b flex-shrink-0">
                          <div className="flex items-center gap-2">
                            <Badge
                              variant="secondary"
                              className="text-xs bg-doc-b/10 text-doc-b"
                            >
                              Doc B
                            </Badge>
                            <h3 className="font-medium text-xs text-foreground truncate">
                              {documents[1]?.filename.split("/").pop()}
                            </h3>
                          </div>
                        </div>
                        <div className="flex-1 overflow-hidden">
                          {pdfUrls[documents[1]?.id] ? (
                            <PDFViewer
                              pdfUrl={pdfUrls[documents[1]?.id]}
                              highlightBbox={
                                pdfViewer.highlightBbox?.docId === "B"
                                  ? pdfViewer.highlightBbox
                                  : null
                              }
                              onHighlightClick={() => {}}
                            />
                          ) : (
                            <div className="flex items-center justify-center h-full text-muted-foreground">
                              <p className="text-sm">No PDF available</p>
                            </div>
                          )}
                        </div>
                      </div>
                    </InnerResizablePanel>
                  )}
                </InnerResizablePanelGroup>
              )}
            </div>
          )}
        </div>

        {/* Topic Navigation Bar */}
        {topics.length > 0 && (
          <div className="border-t px-6 py-3 bg-muted/20">
            <p className="text-xs font-medium text-muted-foreground mb-2 uppercase">
              Navigate Topics
            </p>
            <ScrollArea className="w-full scrollbar-thin">
              <div className="flex gap-2 pb-2">
                {topics.map((topic) => (
                  <Badge
                    key={topic}
                    variant="outline"
                    className="comparison-topic-chip whitespace-nowrap"
                    onClick={() => {
                      scrollToTopic(topic);
                    }}
                  >
                    {topic}
                  </Badge>
                ))}
              </div>
            </ScrollArea>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
