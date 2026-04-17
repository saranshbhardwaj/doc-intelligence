import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertCircle, FileText, Play, Shield, X } from "lucide-react";

import { useAppAuth } from "@/hooks/useAppAuth";

import DocumentViewer from "../../../components/pdf/DocumentViewer";
import { getDocumentDownloadUrl } from "../../../api/documents";
import {
  getRoomChecklist,
  getRoomFindings,
  getRoomSummary,
  getRoomFinancials,
  listPlaybooks,
  listRoomClauses,
  startAnalysis,
} from "../../../api/pe-diligence";
import { usePeDiligence, usePeDiligenceActions } from "../../../store";
import { WarningBanner } from "../hooks/useAnalysisRun";
import PELayout from "./PELayout";
import { ByDocumentTab } from "../components/analysis/byDocument.jsx";
import { ClausesTab } from "../components/analysis/clauses.jsx";
import { DealSourcingTab } from "../components/analysis/drivers.jsx";
import { ExecutiveSummary, RoomOverviewTab } from "../components/analysis/overview.jsx";
import { TabButton } from "../components/analysis/shared.jsx";

export default function RoomAnalysisPage() {
  const { roomId } = useParams();
  const { getToken } = useAppAuth();
  const navigate = useNavigate();

  const peDiligence = usePeDiligence();
  const actions = usePeDiligenceActions();
  const room = peDiligence.room;
  const analysisWarnings = peDiligence.analysisWarnings;
  const isRunning = peDiligence.analysisJobId != null;
  const analysisStatus = {
    ...peDiligence.analysisStatus,
    loading: peDiligence.analysisStatusLoading,
  };

  const docs = peDiligence.documents;
  const docNameMap = useMemo(() => {
    const map = {};
    peDiligence.documents.forEach((doc) => {
      if (doc.document_id) map[doc.document_id] = doc.filename;
    });
    return map;
  }, [peDiligence.documents]);

  const [checklist, setChecklist] = useState([]);
  const [findings, setFindings] = useState([]);
  const [summary, setSummary] = useState(null);
  const [clauses, setClauses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [playbookSchemas, setPlaybookSchemas] = useState({});
  const [financials, setFinancials] = useState(null);

  const clausesLoaded = useRef(false);
  const financialsLoaded = useRef(false);
  // Cache pre-signed URLs with a 45-min TTL (R2/S3 URLs expire at 1h)
  const urlCache = useRef({}); // { [documentId]: { url, expiresAt } }

  const [documentPanel, setDocumentPanel] = useState(null);
  const [documentLoading, setDocumentLoading] = useState(false);

  const loadData = useCallback(() => {
    setLoading(true);
    Promise.all([
      getRoomChecklist(getToken, roomId).catch(() => []),
      getRoomFindings(getToken, roomId).catch(() => []),
      getRoomSummary(getToken, roomId).catch(() => null),
    ])
      .then(([loadedChecklist, loadedFindings, loadedSummary]) => {
        setChecklist(loadedChecklist);
        setFindings(loadedFindings);
        setSummary(loadedSummary);
      })
      .catch((err) => setError(err.message || "Failed to load analysis"))
      .finally(() => setLoading(false));
  }, [getToken, roomId]);

  useEffect(() => {
    // Reset lazy-load flags when room changes so new room data is fetched
    clausesLoaded.current = false;
    financialsLoaded.current = false;
    setClauses([]);
    setFinancials(null);
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (peDiligence.analysisCompletedAt) loadData();
  }, [loadData, peDiligence.analysisCompletedAt]);

  useEffect(() => {
    if ((activeTab === "clauses" || activeTab === "deal-sourcing") && !clausesLoaded.current && roomId) {
      clausesLoaded.current = true;
      listRoomClauses(getToken, roomId).then(setClauses).catch(() => {});
      listPlaybooks(getToken)
        .then((playbooks) => {
          const schemas = {};
          (playbooks || []).forEach((playbook) => {
            if (playbook.slug && playbook.output_schema) schemas[playbook.slug] = playbook.output_schema;
          });
          setPlaybookSchemas(schemas);
        })
        .catch(() => {});
    }

    if (activeTab === "deal-sourcing" && !financialsLoaded.current && roomId) {
      financialsLoaded.current = true;
      getRoomFinancials(getToken, roomId).then(setFinancials).catch(() => {});
    }
  }, [activeTab, getToken, roomId]);

  const handleCitationClick = useCallback(async ({ documentId, page, filename, bbox }) => {
    if (!documentId) return;

    if (documentPanel?.documentId === documentId) {
      setDocumentPanel((prev) => ({ ...prev, page, bbox: bbox ?? prev.bbox }));
      return;
    }

    setDocumentLoading(true);
    setDocumentPanel({ documentId, page, filename, bbox: bbox ?? null, url: null });

    try {
      const cached = urlCache.current[documentId];
      const now = Date.now();
      let url = cached && cached.expiresAt > now ? cached.url : null;
      if (!url) {
        const data = await getDocumentDownloadUrl(getToken, documentId);
        url = data.url;
        urlCache.current[documentId] = { url, expiresAt: now + 45 * 60 * 1000 };
      }
      setDocumentPanel({ documentId, page, filename, bbox: bbox ?? null, url });
    } catch {
      setDocumentPanel(null);
    } finally {
      setDocumentLoading(false);
    }
  }, [documentPanel?.documentId, getToken]);

  async function handleRerun(incremental = false) {
    try {
      const result = await startAnalysis(getToken, roomId, !incremental, incremental);
      if (result?.job_id) {
        actions.peSetAnalysisJob(roomId, result.job_id);
      }
    } catch {
      // silently handle
    }
  }

  function handleInvestigationLaunch(suggestedInvestigation) {
    navigate(`/app/pe/rooms/${roomId}/investigations`, {
      state: { suggestedInvestigation },
    });
  }

  const closeDocumentPanel = useCallback(() => setDocumentPanel(null), []);
  const showDocumentPanel = documentPanel != null;
  const hasData = checklist.length > 0 || findings.length > 0;

  return (
    <PELayout>
      <div className="flex h-full">
        <div className={`${showDocumentPanel ? "w-[60%]" : "w-full"} overflow-y-auto transition-all duration-300`}>
          <div className="pe-page min-h-full max-w-6xl">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h1 className="pe-title font-display">Analysis</h1>
                {room?.target_company && (
                  <p className="text-sm text-muted-foreground mt-0.5">{room.target_company}</p>
                )}
              </div>
            </div>

            <WarningBanner warnings={analysisWarnings} />

            {loading && <p className="text-sm text-muted-foreground">Loading analysis…</p>}

            {error && (
              <div className="flex items-center gap-2 border border-destructive/30 bg-destructive/10 text-destructive rounded-lg p-3 text-sm mb-4">
                <AlertCircle className="w-4 h-4 shrink-0" />
                {error}
              </div>
            )}

            {!loading && !hasData && (
              <div className="glass-card p-16 text-center rounded-2xl">
                <div className="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center mx-auto mb-4">
                  <Shield className="w-8 h-8 text-primary opacity-60" />
                </div>
                <p className="text-sm font-semibold">No analysis results yet</p>
                <p className="text-xs text-muted-foreground mt-1 mb-4">
                  Upload documents and run analysis to see diligence results here.
                </p>
                <Link to={`/app/pe/rooms/${roomId}/documents`} className="pe-action-primary">
                  <Play className="w-4 h-4" />
                  Go to Documents
                </Link>
              </div>
            )}

            {!loading && hasData && (
              <>
                <ExecutiveSummary
                  checklist={checklist}
                  findings={findings}
                  summary={summary}
                  analysisStatus={analysisStatus}
                  roomId={roomId}
                  isRunning={isRunning}
                  onAnalysisStart={handleRerun}
                />

                <div className="glass-panel flex items-center gap-1 rounded-xl p-1 mb-6 w-fit border border-border/50">
                  <TabButton active={activeTab === "overview"} onClick={() => setActiveTab("overview")}>Room Overview</TabButton>
                  <TabButton active={activeTab === "by-document"} onClick={() => setActiveTab("by-document")}>By Document ({docs.length})</TabButton>
                  <TabButton active={activeTab === "deal-sourcing"} onClick={() => setActiveTab("deal-sourcing")}>Diligence Drivers</TabButton>
                  <TabButton active={activeTab === "clauses"} onClick={() => setActiveTab("clauses")}>
                    Clauses {clauses.length > 0 ? `(${clauses.length})` : ""}
                  </TabButton>
                </div>

                {activeTab === "overview" && (
                  <RoomOverviewTab
                    checklist={checklist}
                    findings={findings}
                    summary={summary}
                    docNameMap={docNameMap}
                    onCitationClick={handleCitationClick}
                    roomId={roomId}
                    setFindings={setFindings}
                    showPdf={showDocumentPanel}
                    onInvestigationLaunch={handleInvestigationLaunch}
                  />
                )}

                {activeTab === "by-document" && (
                  <ByDocumentTab
                    docs={docs}
                    checklist={checklist}
                    findings={findings}
                    docNameMap={docNameMap}
                    onCitationClick={handleCitationClick}
                    roomId={roomId}
                    setFindings={setFindings}
                  />
                )}

                {activeTab === "deal-sourcing" && (
                  <DealSourcingTab
                    clauses={clauses}
                    findings={findings}
                    summary={summary}
                    docNameMap={docNameMap}
                    onCitationClick={handleCitationClick}
                    roomId={roomId}
                    setFindings={setFindings}
                    financials={financials}
                  />
                )}

                {activeTab === "clauses" && (
                  <ClausesTab
                    clauses={clauses}
                    setClauses={setClauses}
                    docNameMap={docNameMap}
                    onCitationClick={handleCitationClick}
                    playbookSchemas={playbookSchemas}
                    getToken={getToken}
                    roomId={roomId}
                  />
                )}
              </>
            )}
          </div>
        </div>

        {showDocumentPanel && (
          <div className="w-[40%] border-l border-border/50 flex flex-col bg-background">
            <div className="glass-sidebar flex items-center justify-between px-4 py-3 border-b border-border/50 shrink-0">
              <div className="flex items-center gap-2 min-w-0">
                <FileText className="w-4 h-4 text-primary shrink-0" />
                <span className="text-sm font-medium truncate">{documentPanel.filename || "Document"}</span>
                {documentPanel.page && <span className="text-xs text-muted-foreground shrink-0">p.{documentPanel.page}</span>}
              </div>
              <button onClick={closeDocumentPanel} className="p-1 hover:bg-muted rounded transition-colors shrink-0" title="Close viewer">
                <X className="w-4 h-4 text-muted-foreground" />
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              {documentLoading && !documentPanel.url && (
                <div className="flex items-center justify-center h-full">
                  <p className="text-sm text-muted-foreground">Loading document…</p>
                </div>
              )}
              {documentPanel.url && (
                <DocumentViewer
                  fileUrl={documentPanel.url}
                  filename={documentPanel.filename || ""}
                  defaultPage={documentPanel.page || 1}
                  highlightBbox={documentPanel.bbox ?? (documentPanel.page ? { page: documentPanel.page, x0: 0, y0: 0, x1: 0, y1: 0 } : null)}
                />
              )}
            </div>
          </div>
        )}
      </div>
    </PELayout>
  );
}
