/**
 * ActiveChat Component - Redesigned
 *
 * Production-level active chat interface with session management.
 * Includes inline title editing, proper document selection, and real-time updates.
 *
 * Input:
 *   - currentSession: { id, title, documents: [{id, filename, added_at}, ...] }
 *   - messages: Array<{role: 'user'|'assistant', content: string, created_at: string}>
 *   - isStreaming: boolean
 *   - streamingMessage: string
 *   - chatError: string | null
 *   - collections: Array (for adding documents)
 *   - getToken: () => Promise<string>
 *   - onSendMessage: (message: string) => void
 *   - onAddDocuments: (documentIds: string[]) => void
 *   - onRemoveDocument: (documentId: string) => void
 *   - onUpdateSessionTitle: (title: string) => void
 *   - onExportSession: () => void
 *
 * Output:
 *   - Renders active chat interface
 *   - Handles message sending
 *   - Manages document chips
 *   - Editable session title
 */

import { useState, useRef, useEffect, useLayoutEffect } from "react";
import {
  Send,
  Download,
  FileText,
  FileDown,
  Loader2,
  Bot,
  X,
  ChevronDown,
} from "lucide-react";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import Spinner from "../common/Spinner";
import { ComparisonMessage, StreamingComparisonContent } from "./comparison";
import ComparisonDocumentPicker from "./comparison/ComparisonDocumentPicker";
import { useComparison, usePdfViewer, useChatActions, useStore } from "../../store";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ComparisonPanel from "../comparison/ComparisonPanel";
import CitationLink from "../common/CitationLink";
import { splitTextWithCitations } from "../../utils/citations";
import ChatMessageFeedback from "./ChatMessageFeedback";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "../ui/resizable";
import DocumentViewer from "../pdf/DocumentViewer";

export default function ActiveChat({
  currentSession,
  messages = [],
  isStreaming = false,
  isThinking = false,
  thinkingMessage = "",
  streamingMessage = "",
  chatError = null,
  collections = [],
  getToken,
  onSendMessage,
  onAddDocuments,
  onRemoveDocument,
  onUpdateSessionTitle,
  onExportSession,
}) {
  const [message, setMessage] = useState("");
  const [showComparisonPanel, setShowComparisonPanel] = useState(false);
  const [showPdfPanel, setShowPdfPanel] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const shouldAutoScrollRef = useRef(true);
  const messagesScrollTopRef = useRef(0);
  const textareaRef = useRef(null);

  const handleTextareaInput = (e) => {
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
  };

  const isNearBottom = (element, threshold = 120) => {
    if (!element) return true;
    const distanceFromBottom =
      element.scrollHeight - element.scrollTop - element.clientHeight;
    return distanceFromBottom <= threshold;
  };

  // Auto-scroll when new content arrives, but only if user is near the bottom.
  // Use direct scrollTop during streaming to avoid repeated smooth-scroll pinning.
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container || !shouldAutoScrollRef.current) return;

    if (isStreaming) {
      container.scrollTop = container.scrollHeight;
      return;
    }

    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingMessage]);

  const handleMessagesScroll = () => {
    if (messagesContainerRef.current) {
      messagesScrollTopRef.current = messagesContainerRef.current.scrollTop;
    }
    shouldAutoScrollRef.current = isNearBottom(messagesContainerRef.current);
  };

  const handleMessagesWheel = (e) => {
    if (e.deltaY < 0) {
      shouldAutoScrollRef.current = false;
    }
  };

  // Reset to bottom when switching sessions.
  useEffect(() => {
    shouldAutoScrollRef.current = true;
    messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
  }, [currentSession?.id]);

  // Preserve chat scroll position when PDF panel toggles (e.g., citation click).
  useLayoutEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    container.scrollTop = messagesScrollTopRef.current;
  }, [showPdfPanel]);

  const handleSendMessage = (e) => {
    e.preventDefault();
    if (!message.trim() || isStreaming) return;

    onSendMessage?.(message.trim());
    setMessage("");
  };

  const sessionDocIds = currentSession?.documents?.map((d) => d.id) || [];

  // Get comparison context for rendering
  const comparison = useComparison();
  const pdfViewer = usePdfViewer();
  const actions = useChatActions();
  const { clearHighlight, clearPdfUrlCache } = actions;
  const citationContext = useStore((state) => state.chat.citationContext);

  useEffect(() => {
    const updateViewport = () => {
      setIsMobile(window.innerWidth < 768);
    };
    updateViewport();
    window.addEventListener("resize", updateViewport);
    return () => window.removeEventListener("resize", updateViewport);
  }, []);

  const renderCitationsInText = (text, context) => {
    if (!text || !context?.citations?.length) return text;
    const parts = splitTextWithCitations(text);
    if (parts.length === 1 && typeof parts[0] === "string") return text;
    return parts.map((part, i) =>
      typeof part === "string" ? part : (
        <CitationLink key={i} token={part.token} citationContext={context} variant="inline" />
      )
    );
  };

  const processChildrenForCitations = (children, context) => {
    if (typeof children === "string") {
      return renderCitationsInText(children, context);
    }
    if (Array.isArray(children)) {
      return children.map((child, i) =>
        typeof child === "string"
          ? renderCitationsInText(child, context)
          : child
      );
    }
    return children;
  };

  // Handler for opening full comparison panel
  const handleOpenComparisonPanel = () => {
    setShowComparisonPanel(true);
  };

  // Clear PDF cache and reset panel state when session changes
  useEffect(() => {
    clearPdfUrlCache();
    setShowPdfPanel(false); // Reset local panel state
  }, [currentSession?.id, clearPdfUrlCache]);

  // Auto-show PDF panel when active document is set AND URL is available
  useEffect(() => {
    if (pdfViewer.activeDocumentId && pdfViewer.urlCache[pdfViewer.activeDocumentId]?.url) {
      if (messagesContainerRef.current) {
        messagesScrollTopRef.current = messagesContainerRef.current.scrollTop;
      }
      setShowPdfPanel(true);
    }
  }, [pdfViewer.activeDocumentId, pdfViewer.urlCache]);

  // Auto-show PDF panel when highlight changes (for citation clicks)
  useEffect(() => {
    if (pdfViewer.highlightBbox) {
      if (messagesContainerRef.current) {
        messagesScrollTopRef.current = messagesContainerRef.current.scrollTop;
      }
      setShowPdfPanel(true);
    }
  }, [pdfViewer.highlightBbox]);

  // Get active PDF URL from cache
  const activePdfUrl = pdfViewer.activeDocumentId
    ? pdfViewer.urlCache[pdfViewer.activeDocumentId]?.url
    : null;

  return (
    <>
      <ResizablePanelGroup
        key={showPdfPanel ? "chat-split-open" : "chat-split-closed"}
        direction="horizontal"
        className="h-full min-w-0"
      >
      {/* Left Panel: Chat Interface */}
      <ResizablePanel
        id="chat-left-panel"
        order={1}
        defaultSize={showPdfPanel ? 55 : 100}
        minSize={35}
      >
        <div className="w-full flex flex-col h-full min-w-0 overflow-hidden relative">
          <div className="absolute right-5 top-2 z-20">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-10 shrink-0 rounded-full border border-border/70 bg-background/85 pl-2 pr-3 shadow-lg backdrop-blur-md hover:bg-background hover:shadow-xl"
                >
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-primary">
                    <Download className="h-3.5 w-3.5" />
                  </span>
                  <span className="text-xs font-medium text-foreground">Export</span>
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" sideOffset={10} className="w-48 rounded-xl">
                <DropdownMenuItem onClick={() => onExportSession?.("markdown")}>
                  <FileText className="w-4 h-4 mr-2" />
                  <div className="flex flex-col">
                    <span className="font-medium">Markdown</span>
                    <span className="text-xs text-muted-foreground">
                      Simple .md file
                    </span>
                  </div>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => onExportSession?.("word")}>
                  <FileDown className="w-4 h-4 mr-2" />
                  <div className="flex flex-col">
                    <span className="font-medium">Word Document</span>
                    <span className="text-xs text-muted-foreground">
                      Professional .docx
                    </span>
                  </div>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

      {/* Messages Area */}
      <div
        ref={messagesContainerRef}
        onScroll={handleMessagesScroll}
        onWheel={handleMessagesWheel}
        className="flex-1 overflow-y-auto bg-background"
      >
        {messages.length === 0 && !streamingMessage ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-md">
              <div className="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <FileText className="w-8 h-8 text-primary" />
              </div>
              <h3 className="text-lg font-medium text-foreground mb-2">
                Ready to chat!
              </h3>
              <p className="text-sm text-muted-foreground">
                {sessionDocIds.length > 0
                  ? `Ask questions about your ${
                      sessionDocIds.length
                    } selected document${sessionDocIds.length !== 1 ? "s" : ""}`
                  : "Add documents to start asking questions"}
              </p>
            </div>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto w-full py-4 md:py-6 px-3 md:px-8 space-y-8">
            {messages.map((msg, index) => {
              const isLastMessage = index === messages.length - 1;
              const isComparisonResponse =
                msg.role === "assistant" &&
                ((isLastMessage && comparison.isActive && comparison.context) ||
                  Boolean(msg.comparison_metadata));

              if (isComparisonResponse) {
                return (
                  <div
                    key={index}
                    className="flex items-start gap-4 animate-message-slide-left w-full"
                  >
                    <div className="h-9 w-9 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center shrink-0 mt-1 shadow-md">
                      <Bot className="w-4 h-4 text-primary-foreground" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <ComparisonMessage
                        message={msg}
                        onOpenComparisonPanel={handleOpenComparisonPanel}
                      />
                      {msg.id && (
                        <ChatMessageFeedback
                          messageId={msg.id}
                          sessionId={currentSession?.id}
                        />
                      )}
                    </div>
                  </div>
                );
              }

              if (msg.role === "user") {
                return (
                  <div key={index} className="flex flex-row-reverse items-end gap-3 animate-message-slide-left">
                    <div className="flex flex-col items-end gap-1 max-w-[80%] md:max-w-[75%]">
                      <div className="px-6 py-4 bg-primary/10 border border-primary/10 rounded-3xl rounded-br-sm text-foreground text-sm leading-relaxed">
                        <div className="whitespace-pre-wrap">{msg.content}</div>
                      </div>
                    </div>
                  </div>
                );
              }

              return (
                <div key={index} className="flex items-start gap-4 animate-message-slide-left">
                  <div className="h-9 w-9 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center shrink-0 mt-1 shadow-md">
                    <Bot className="w-4 h-4 text-primary-foreground" />
                  </div>
                  <div className="flex flex-col items-start gap-2 flex-1 min-w-0">
                    <div className="group px-7 py-6 bg-card rounded-3xl rounded-bl-sm border border-border shadow-sm">
                      <div className="prose prose-sm max-w-none dark:prose-invert
                        prose-table:border-collapse prose-table:w-full
                        prose-th:border prose-th:border-border prose-th:bg-muted/50 prose-th:p-2
                        prose-td:border prose-td:border-border prose-td:p-2
                        prose-tr:even:bg-muted/30
                        prose-p:text-muted-foreground prose-p:leading-relaxed
                        prose-strong:text-foreground prose-strong:font-semibold
                        prose-ul:text-muted-foreground prose-ul:my-3
                        prose-ol:text-muted-foreground prose-ol:my-3
                        prose-li:my-1
                        prose-a:text-primary prose-a:no-underline hover:prose-a:underline
                        prose-blockquote:border-l-primary prose-blockquote:bg-muted/50 prose-blockquote:py-1
                        prose-code:text-primary prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:before:content-none prose-code:after:content-none
                        prose-pre:bg-muted prose-pre:border prose-pre:border-border
                        prose-h3:text-lg prose-h3:mt-6 prose-h3:mb-3
                        prose-h4:text-base prose-h4:mt-4 prose-h4:mb-2
                        prose-headings:font-bold prose-headings:text-foreground
                      ">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            p: ({ children }) => (
                              <p>{processChildrenForCitations(children, msg.citation_context || citationContext)}</p>
                            ),
                            li: ({ children }) => (
                              <li>{processChildrenForCitations(children, msg.citation_context || citationContext)}</li>
                            ),
                            td: ({ children }) => (
                              <td>{processChildrenForCitations(children, msg.citation_context || citationContext)}</td>
                            ),
                            th: ({ children }) => (
                              <th>{processChildrenForCitations(children, msg.citation_context || citationContext)}</th>
                            ),
                            strong: ({ children }) => (
                              <strong>{processChildrenForCitations(children, msg.citation_context || citationContext)}</strong>
                            ),
                          }}
                        >
                          {msg.content}
                        </ReactMarkdown>
                      </div>
                    </div>
                    {msg.id && (
                      <ChatMessageFeedback
                        messageId={msg.id}
                        sessionId={currentSession?.id}
                      />
                    )}
                  </div>
                </div>
              );
            })}

            {/* Comparison Document Picker - shown when selection needed */}
            {comparison.selectionNeeded && (
              <ComparisonDocumentPicker
                documents={comparison.selectionDocuments}
                preSelected={comparison.selectionPreSelected}
                message={comparison.selectionMessage}
                onConfirm={(docIds) => {
                  actions.confirmComparisonSelection(
                    getToken,
                    currentSession.id,
                    docIds,
                    comparison.selectionQuery,
                    false // skipComparison = false
                  );
                }}
                onSkip={() => {
                  actions.confirmComparisonSelection(
                    getToken,
                    currentSession.id,
                    [],
                    comparison.selectionQuery,
                    true // skipComparison = true → normal RAG
                  );
                }}
              />
            )}

            {/* Thinking indicator - shown during processing before streaming */}
            {isThinking && (
              <div className="flex items-start gap-4 animate-fade-in">
                <div className="h-9 w-9 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center shrink-0 mt-1 shadow-md">
                  <Bot className="w-4 h-4 text-primary-foreground" />
                </div>
                <div className="px-7 py-5 bg-card rounded-3xl rounded-bl-sm border border-border shadow-sm">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span className="text-sm">{thinkingMessage || "Thinking..."}</span>
                  </div>
                </div>
              </div>
            )}

            {isStreaming && streamingMessage && (
              <div className="flex items-start gap-4 animate-fade-in">
                <div className="h-9 w-9 rounded-full bg-gradient-to-br from-primary to-accent flex items-center justify-center shrink-0 mt-1 shadow-md">
                  <Bot className="w-4 h-4 text-primary-foreground" />
                </div>
                <div className="px-7 py-6 bg-card rounded-3xl rounded-bl-sm border border-border shadow-sm flex-1 min-w-0">
                  {comparison.isActive && comparison.context ? (
                    // Render streaming comparison message with markdown + styled citations
                    <div className="prose prose-sm max-w-none dark:prose-invert
                      prose-table:border-collapse prose-table:w-full
                      prose-th:border prose-th:border-border prose-th:bg-muted/50 prose-th:p-2
                      prose-td:border prose-td:border-border prose-td:p-2
                      prose-tr:even:bg-muted/30
                      prose-p:text-muted-foreground prose-p:leading-relaxed
                      prose-strong:text-foreground prose-strong:font-semibold
                      prose-ul:text-muted-foreground prose-ul:my-3
                      prose-ol:text-muted-foreground prose-ol:my-3
                      prose-li:my-1
                      prose-a:text-primary prose-a:no-underline hover:prose-a:underline
                      prose-blockquote:border-l-primary prose-blockquote:bg-muted/50 prose-blockquote:py-1
                      prose-code:text-primary prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:before:content-none prose-code:after:content-none
                      prose-pre:bg-muted prose-pre:border prose-pre:border-border
                      prose-h3:text-lg prose-h3:mt-6 prose-h3:mb-3
                      prose-h4:text-base prose-h4:mt-4 prose-h4:mb-2
                      prose-headings:font-bold prose-headings:text-foreground
                    ">
                      <StreamingComparisonContent content={streamingMessage} />
                    </div>
                  ) : (
                    // Regular streaming message (markdown)
                    <div className="prose prose-sm max-w-none dark:prose-invert
                      prose-table:border-collapse prose-table:w-full
                      prose-th:border prose-th:border-border prose-th:bg-muted/50 prose-th:p-2
                      prose-td:border prose-td:border-border prose-td:p-2
                      prose-tr:even:bg-muted/30
                      prose-p:text-muted-foreground prose-p:leading-relaxed
                      prose-strong:text-foreground prose-strong:font-semibold
                      prose-ul:text-muted-foreground prose-ul:my-3
                      prose-ol:text-muted-foreground prose-ol:my-3
                      prose-li:my-1
                      prose-a:text-primary prose-a:no-underline hover:prose-a:underline
                      prose-blockquote:border-l-primary prose-blockquote:bg-muted/50 prose-blockquote:py-1
                      prose-code:text-primary prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:before:content-none prose-code:after:content-none
                      prose-pre:bg-muted prose-pre:border prose-pre:border-border
                      prose-h3:text-lg prose-h3:mt-6 prose-h3:mb-3
                      prose-h4:text-base prose-h4:mt-4 prose-h4:mb-2
                      prose-headings:font-bold prose-headings:text-foreground
                    ">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          p: ({ children }) => (
                            <p>{processChildrenForCitations(children, citationContext)}</p>
                          ),
                          li: ({ children }) => (
                            <li>{processChildrenForCitations(children, citationContext)}</li>
                          ),
                          td: ({ children }) => (
                            <td>{processChildrenForCitations(children, citationContext)}</td>
                          ),
                          th: ({ children }) => (
                            <th>{processChildrenForCitations(children, citationContext)}</th>
                          ),
                          strong: ({ children }) => (
                            <strong>{processChildrenForCitations(children, citationContext)}</strong>
                          ),
                        }}
                      >
                        {streamingMessage}
                      </ReactMarkdown>
                    </div>
                  )}
                  {/* Typing indicator */}
                  <div className="flex items-center gap-1 mt-2">
                    <div className="w-1.5 h-1.5 bg-primary rounded-full animate-typing-dot" />
                    <div
                      className="w-1.5 h-1.5 bg-primary rounded-full animate-typing-dot"
                      style={{ animationDelay: "0.2s" }}
                    />
                    <div
                      className="w-1.5 h-1.5 bg-primary rounded-full animate-typing-dot"
                      style={{ animationDelay: "0.4s" }}
                    />
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Composer - floating glass card */}
      <div className="sticky bottom-0 bg-gradient-to-t from-background via-background/95 to-transparent pt-2 pb-2 px-0">
        <div className="max-w-4xl mx-auto w-full px-3 md:px-8">
          {chatError && (
            <div className="mb-3 p-3 bg-destructive/10 text-destructive rounded-xl text-sm border border-destructive/20">
              ⚠️ {chatError}
            </div>
          )}

          <div className="bg-card border border-border rounded-2xl shadow-xl flex flex-col overflow-hidden transition-all focus-within:ring-2 focus-within:ring-primary/30 focus-within:border-primary/50">
            <textarea
              ref={textareaRef}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onInput={handleTextareaInput}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSendMessage(e);
                }
              }}
              placeholder={
                sessionDocIds.length === 0
                  ? "Add documents to start chatting..."
                  : "Ask frearaAI anything about your documents..."
              }
              disabled={isStreaming || sessionDocIds.length === 0}
              rows={1}
              className="w-full bg-transparent border-none text-foreground placeholder:text-muted-foreground focus:ring-0 resize-none py-2 px-4 min-h-[32px] max-h-[72px] text-sm disabled:cursor-not-allowed outline-none"
            />
            <div className="flex justify-end items-center px-4 pb-1 gap-3">
              <span className="text-[11px] text-muted-foreground font-medium hidden md:inline-block">
                Shift+Enter for new line
              </span>
              <button
                type="button"
                onClick={handleSendMessage}
                disabled={!message.trim() || isStreaming || sessionDocIds.length === 0}
                className="bg-primary hover:bg-primary/90 text-primary-foreground h-9 w-9 rounded-xl flex items-center justify-center shadow-lg shadow-primary/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                title="Send message"
              >
                {isStreaming ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <Send className="w-5 h-5" />
                )}
              </button>
            </div>
          </div>
          <p className="text-center text-[10px] text-muted-foreground mt-3 tracking-wide opacity-70">
            frearaAI can make mistakes. Verify important information.
          </p>
        </div>
      </div>
      {/* End: Outer flex container from line 254 */}
      </div>
      </ResizablePanel>

      {/* Resizable Handle - only show if PDF panel is visible */}
      {showPdfPanel && sessionDocIds.length > 0 && !isMobile && (
        <ResizableHandle withHandle />
      )}

      {/* Right Panel: PDF Viewer */}
      {showPdfPanel && sessionDocIds.length > 0 && !isMobile && (
        <ResizablePanel
          id="chat-pdf-panel"
          order={2}
          defaultSize={45}
          minSize={30}
        >
          <div className="w-full h-full flex flex-col bg-background overflow-hidden">
            <div className="bg-card px-4 py-2 border-b flex-shrink-0">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  <h2 className="font-medium text-sm text-foreground">
                    {activePdfUrl && pdfViewer.activeDocumentId
                      ? currentSession?.documents?.find(d => d.id === pdfViewer.activeDocumentId)?.name || "Document"
                      : "Document"}
                  </h2>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setShowPdfPanel(false)}
                  className="h-7 w-7"
                  title="Close document viewer"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <div className="flex-1 overflow-hidden">
              {pdfViewer.isLoadingUrl ? (
                <div className="flex flex-col items-center justify-center h-full gap-2">
                  <Spinner size="md" />
                  <p className="text-sm text-muted-foreground">Loading document...</p>
                </div>
              ) : activePdfUrl ? (
                <DocumentViewer
                  fileUrl={activePdfUrl}
                  filename={currentSession?.documents?.find(d => d.id === pdfViewer.activeDocumentId)?.name || ''}
                  highlightBbox={pdfViewer.highlightBbox}
                  onHighlightClick={clearHighlight}
                  suppressDefaultPageScroll
                />
              ) : pdfViewer.activeDocumentId ? (
                <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground">
                  <FileText className="w-12 h-12 opacity-20" />
                  <p className="text-sm">Click a document chip to view it</p>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground">
                  <FileText className="w-12 h-12 opacity-20" />
                  <p className="text-sm">No document selected</p>
                </div>
              )}
            </div>
          </div>
        </ResizablePanel>
      )}

    </ResizablePanelGroup>

      {/* Mobile PDF Overlay */}
      {showPdfPanel && sessionDocIds.length > 0 && isMobile && (
        <div className="fixed inset-0 z-[70] bg-background md:hidden">
          <div className="bg-card px-3 py-2 border-b flex items-center justify-between">
            <div className="flex items-center gap-2 min-w-0">
              <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
              <h2 className="font-medium text-sm text-foreground truncate">
                {activePdfUrl && pdfViewer.activeDocumentId
                  ? currentSession?.documents?.find((d) => d.id === pdfViewer.activeDocumentId)?.name || "Document"
                  : "Document"}
              </h2>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowPdfPanel(false)}
              className="h-8 px-3"
            >
              <X className="h-4 w-4 mr-1" />
              Close
            </Button>
          </div>
          <div className="h-[calc(100dvh-49px)] overflow-hidden">
            {pdfViewer.isLoadingUrl ? (
              <div className="flex flex-col items-center justify-center h-full gap-2">
                <Spinner size="md" />
                  <p className="text-sm text-muted-foreground">Loading document...</p>
              </div>
            ) : activePdfUrl ? (
              <DocumentViewer
                fileUrl={activePdfUrl}
                filename={currentSession?.documents?.find(d => d.id === pdfViewer.activeDocumentId)?.name || ''}
                highlightBbox={pdfViewer.highlightBbox}
                onHighlightClick={clearHighlight}
                suppressDefaultPageScroll
              />
            ) : (
              <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground">
                <FileText className="w-12 h-12 opacity-20" />
                <p className="text-sm">No document selected</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Comparison Panel Sheet */}
      <ComparisonPanel
        isOpen={showComparisonPanel}
        onClose={() => setShowComparisonPanel(false)}
      />
    </>
  );
}
