/**
 * RoomInvestigations — Investigation list + create new investigation.
 * Route: /app/pe/rooms/:roomId/investigations
 */

import { useState, useEffect } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { Plus, Search, AlertCircle, Circle, ChevronRight } from "lucide-react";
import { useAppAuth } from "@/hooks/useAppAuth";
import PELayout from "./PELayout";
import { listInvestigations, createInvestigation } from "../../../api/pe-diligence";

// ─── Constants ────────────────────────────────────────────────────────────────

const INVESTIGATION_TYPES = [
  { value: "change_of_control_exposure", label: "Change-of-Control Exposure" },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

const STATUS_STYLES = {
  completed: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  running:   "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  queued:    "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  failed:    "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

const COVERAGE_COLORS = {
  strong:   "text-green-500",
  moderate: "text-yellow-500",
  weak:     "text-red-500",
};

function StatusBadge({ status }) {
  const style = STATUS_STYLES[status] || "bg-gray-100 text-gray-600";
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${style}`}>
      {status || "pending"}
    </span>
  );
}

// ─── Investigation card ───────────────────────────────────────────────────────

function InvestigationCard({ inv, roomId: _roomId, onClick }) {
  const coverageColor = COVERAGE_COLORS[inv.coverage_status] || "text-muted-foreground";
  const typeLabel = INVESTIGATION_TYPES.find((t) => t.value === inv.investigation_type)?.label
    || inv.investigation_type?.replace(/_/g, " ") || "Investigation";

  return (
    <div
      onClick={onClick}
      className="pe-card p-4 hover:border-primary/40 hover:shadow-md transition-all cursor-pointer group"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Search className="w-4 h-4 text-muted-foreground shrink-0" />
            <p className="text-sm font-semibold capitalize group-hover:text-primary truncate">
              {inv.title || typeLabel}
            </p>
          </div>
          {inv.question && (
            <p className="text-xs text-muted-foreground ml-6 line-clamp-2">{inv.question}</p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <StatusBadge status={inv.status} />
          {inv.coverage_score != null && (
            <span className={`text-xs font-semibold ${coverageColor}`}>
              {Math.round(inv.coverage_score * 100)}%
              {inv.coverage_status && (
                <span className="font-normal text-muted-foreground ml-1 capitalize">
                  {inv.coverage_status}
                </span>
              )}
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center justify-between mt-3">
        <span className="text-xs text-muted-foreground">
          {new Date(inv.created_at).toLocaleDateString()}
        </span>
        <div className="flex items-center gap-1 text-xs text-primary font-medium opacity-0 group-hover:opacity-100 transition-opacity">
          View details
          <ChevronRight className="w-3.5 h-3.5" />
        </div>
      </div>
    </div>
  );
}

// ─── Create form ──────────────────────────────────────────────────────────────

function CreateForm({ roomId, onCreated, onCancel }) {
  const { getToken } = useAppAuth();
  const [invType, setInvType] = useState("change_of_control_exposure");
  const [question, setQuestion] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await createInvestigation(getToken, roomId, {
        investigation_type: invType,
        question: question.trim() || undefined,
      });
      onCreated(result.investigation);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to create investigation");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="pe-card p-4"
    >
      <p className="text-sm font-semibold mb-3">New Investigation</p>
      <div className="space-y-3">
        <div>
          <label className="text-xs font-medium text-muted-foreground block mb-1">Type</label>
          <select
            value={invType}
            onChange={(e) => setInvType(e.target.value)}
            className="w-full text-sm border rounded-lg px-3 py-2 bg-background focus:outline-none focus:ring-1 focus:ring-primary/50"
          >
            {INVESTIGATION_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground block mb-1">
            Custom Question <span className="text-muted-foreground/60">(optional)</span>
          </label>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="What specific aspect should the investigation focus on?"
            rows={2}
            className="w-full text-sm border rounded-lg px-3 py-2 bg-background focus:outline-none focus:ring-1 focus:ring-primary/50 resize-none"
          />
        </div>

        {error && (
          <div className="flex items-center gap-2 text-xs text-destructive">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            {error}
          </div>
        )}

        <div className="flex gap-2">
          <button
            type="submit"
            disabled={submitting}
            className="pe-action-primary"
          >
            <Search className="w-3.5 h-3.5" />
            {submitting ? "Running…" : "Run Investigation"}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="pe-action-ghost"
          >
            Cancel
          </button>
        </div>
      </div>
    </form>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function RoomInvestigations() {
  const { roomId } = useParams();
  const { getToken } = useAppAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const suggestedInvestigation = location.state?.suggestedInvestigation || null;

  const [investigations, setInvestigations] = useState([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    listInvestigations(getToken, roomId)
      .then(setInvestigations)
      .catch((err) => setError(err.message || "Failed to load investigations"))
      .finally(() => setLoading(false));
  }, [roomId]);

  function handleCreated(inv) {
    setInvestigations((prev) => [inv, ...prev]);
    setShowCreate(false);
    navigate(`/app/pe/rooms/${roomId}/investigations/${inv.id}`);
  }

  return (
    <PELayout>
      <div className="pe-page min-h-full max-w-4xl">
        <div className="pe-header mb-5">
          <div>
            <h1 className="pe-title font-display">Investigations</h1>
            <p className="pe-subtitle mt-0.5">
              Evidence-backed diligence investigations
            </p>
          </div>
          {!showCreate && (
            <button
              onClick={() => setShowCreate(true)}
              className="pe-action-ghost"
            >
              <Plus className="w-4 h-4" />
              New Investigation
            </button>
          )}
        </div>

        {error && (
          <div className="flex items-center gap-2 border border-destructive/30 bg-destructive/10 text-destructive rounded-lg p-3 text-sm mb-4">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        {suggestedInvestigation && (
          <div className="mb-4 rounded-xl border border-primary/20 bg-primary/5 p-4">
            <p className="text-sm font-semibold text-foreground">
              Suggested from baseline analysis: {suggestedInvestigation.title}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              {suggestedInvestigation.rationale}
            </p>
            <p className="text-xs text-muted-foreground mt-2">
              This is a planning handoff from analysis. It does not auto-run an investigation.
            </p>
          </div>
        )}

        {showCreate && (
          <div className="mb-4">
            <CreateForm
              roomId={roomId}
              onCreated={handleCreated}
              onCancel={() => setShowCreate(false)}
            />
          </div>
        )}

        {loading && <p className="text-sm text-muted-foreground">Loading investigations…</p>}

        {!loading && investigations.length === 0 && !showCreate && (
          <div className="pe-card-muted p-16 text-center">
            <Search className="w-10 h-10 text-muted-foreground/30 mx-auto mb-4" />
            <p className="text-sm font-medium">No investigations yet</p>
            <p className="text-xs text-muted-foreground mt-1">
              Click "New Investigation" to start an AI-powered diligence investigation.
            </p>
          </div>
        )}

        {!loading && investigations.length > 0 && (
          <div className="space-y-3">
            {investigations.map((inv) => (
              <InvestigationCard
                key={inv.id}
                inv={inv}
                roomId={roomId}
                onClick={() => navigate(`/app/pe/rooms/${roomId}/investigations/${inv.id}`)}
              />
            ))}
          </div>
        )}
      </div>
    </PELayout>
  );
}
