import { useEffect, useMemo, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronUp,
  Edit2,
  FileText,
  Flag,
  RotateCcw,
  Save,
  Search,
  Shield,
} from "lucide-react";

import { reviewClause } from "../../../../api/pe-diligence";
import {
  CATEGORY_COLORS,
  CLAUSES_PAGE_SIZE,
  PLAYBOOK_LABELS,
  REVIEW_BADGE,
} from "../../analysis/displayConstants";
import { FilterPill } from "./shared.jsx";

export function FieldPills({ fields, schema }) {
  if (!fields || typeof fields !== "object") return null;

  const pills = [];
  const consumedKeys = new Set();
  const schemaProps = schema?.items?.properties || {};
  const schemaKeys = Object.keys(schemaProps);
  const STANDARD_KEYS = new Set(["clause_type", "raw_quote", "interpretation", "confidence"]);

  const getLabel = (key) => {
    const prop = schemaProps[key];
    if (prop?.title) return prop.title;
    return key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  };

  const formatNumber = (val, key) => {
    if (typeof val !== "number") return null;
    if ((key.includes("amount") || key.includes("cap") || key.includes("basket") || key.endsWith("_usd")) && !key.includes("pct")) {
      return `$${val.toLocaleString()}`;
    }
    if (key.includes("pct") || key.endsWith("_pct")) return `${val}%`;
    if (key.endsWith("_months")) return `${val} months`;
    if (key.endsWith("_days")) return `${val} days`;
    if (key.endsWith("_hours")) return `${val} hours`;
    if (key.endsWith("_years")) return `${val} years`;
    return val;
  };

  const fieldKeys = schemaKeys.length > 0
    ? [...schemaKeys.filter((key) => !STANDARD_KEYS.has(key) && key in fields), ...Object.keys(fields).filter((key) => !schemaKeys.includes(key))]
    : Object.keys(fields);

  fieldKeys.forEach((key) => {
    const value = fields[key];
    if (consumedKeys.has(key) || value === null || value === undefined || value === "") return;

    if (key === "threshold_value" && fields.threshold_unit) {
      pills.push(
        <span key={key} className="inline-flex items-center gap-1 text-xs bg-muted px-2 py-1 rounded">
          <span className="text-muted-foreground">{getLabel("threshold_value")}</span>
          <span className="font-semibold text-foreground">{value}{fields.threshold_unit}</span>
        </span>
      );
      consumedKeys.add(key);
      consumedKeys.add("threshold_unit");
      return;
    }

    if (key === "threshold_unit") return;

    if (key === "earnout_period_months" && fields.earnout_metric) {
      pills.push(
        <span key={key} className="inline-flex items-center gap-1 text-xs bg-muted px-2 py-1 rounded">
          <span className="text-muted-foreground">Earnout</span>
          <span className="font-semibold text-foreground">{value}mo on {fields.earnout_metric}</span>
        </span>
      );
      consumedKeys.add(key);
      consumedKeys.add("earnout_metric");
      return;
    }

    if (key === "earnout_metric") return;

    let displayValue = null;
    const label = getLabel(key);

    if (typeof value === "number") {
      displayValue = formatNumber(value, key);
    } else if (typeof value === "boolean") {
      displayValue = value ? "Yes" : "No";
    } else if (Array.isArray(value)) {
      if (value.length === 0) return;
      const truncated = value.slice(0, 3);
      displayValue = truncated.join(", ");
      if (value.length > 3) displayValue += ` +${value.length - 3} more`;
    } else if (typeof value === "string") {
      if (value.length === 0) return;
      displayValue = value;
    }

    if (displayValue) {
      consumedKeys.add(key);
      const bgColor = typeof value === "boolean"
        ? value
          ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300"
          : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300"
        : "bg-muted";

      pills.push(
        <span key={key} className={`inline-flex items-center gap-1 text-xs ${bgColor} px-2 py-1 rounded`}>
          <span className="text-muted-foreground">{label}</span>
          <span className="font-semibold text-foreground">{displayValue}</span>
        </span>
      );
    }
  });

  return pills.length > 0 ? <div className="flex flex-wrap gap-2 mt-2">{pills}</div> : null;
}

export function ClauseCard({ clause, docNameMap, onCitationClick, schema, onReview, getToken, roomId }) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editFields, setEditFields] = useState({});
  const [saving, setSaving] = useState(false);
  const [localClause, setLocalClause] = useState(clause);

  const docName = docNameMap?.[localClause.source_document_id] || "Source";
  const categoryColor = CATEGORY_COLORS[localClause.category] || CATEGORY_COLORS.contract;
  const displayFields = localClause.corrected_fields || localClause.extracted_fields;
  const reviewBadge = REVIEW_BADGE[localClause.review_status];
  const borderColor = localClause.review_status === "approved"
    ? "border-green-300 dark:border-green-700"
    : localClause.review_status === "flagged"
      ? "border-orange-300 dark:border-orange-700"
      : "border-border";

  const handleReview = async (status) => {
    setSaving(true);
    try {
      const updated = await reviewClause(getToken, roomId, localClause.id, { status });
      setLocalClause((prev) => ({ ...prev, ...updated }));
      onReview?.(updated);
    } catch {
      // silently handle
    }
    setSaving(false);
  };

  const handleSaveEdit = async () => {
    setSaving(true);
    try {
      const merged = { ...(localClause.extracted_fields || {}), ...editFields };
      const updated = await reviewClause(getToken, roomId, localClause.id, {
        status: "edited",
        corrected_fields: merged,
      });
      setLocalClause((prev) => ({ ...prev, ...updated }));
      onReview?.(updated);
      setEditing(false);
    } catch {
      // silently handle
    }
    setSaving(false);
  };

  return (
    <div className={`border ${borderColor} rounded-lg p-4 bg-card`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold px-2 py-1 rounded ${categoryColor}`}>
            {localClause.clause_type}
          </span>
          <button
            onClick={() => onCitationClick({
              documentId: localClause.source_document_id,
              page: localClause.source_page_number,
              filename: docName,
              bbox: localClause.metadata?.bbox ?? null,
            })}
            className="text-xs text-primary hover:text-primary/80 hover:underline font-medium transition-colors"
            title={`Open ${docName} at page ${localClause.source_page_number}`}
          >
            <FileText className="w-3 h-3 inline mr-1" />
            {docName.length > 30 ? `${docName.slice(0, 28)}…` : docName} • p.{localClause.source_page_number}
          </button>
        </div>
        <div className="flex items-center gap-2">
          {reviewBadge && (
            <span className={`text-xs font-semibold px-2 py-1 rounded ${reviewBadge.className}`}>
              {reviewBadge.label}
            </span>
          )}
          {localClause.confidence && (
            <span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">
              {Math.round(localClause.confidence * 100)}%
            </span>
          )}
        </div>
      </div>

      {localClause.interpretation && (
        <p className="text-sm font-semibold text-foreground mb-2">{localClause.interpretation}</p>
      )}

      {!editing && <FieldPills fields={displayFields} schema={schema} />}

      {editing && (
        <div className="mt-2 space-y-2 bg-muted/30 rounded p-3">
          {Object.entries(localClause.extracted_fields || {}).map(([key, value]) => (
            <div key={key} className="flex items-center gap-2">
              <label className="text-xs text-muted-foreground w-40 shrink-0">
                {schema?.items?.properties?.[key]?.title || key.replace(/_/g, " ")}
              </label>
              <input
                className="text-xs border border-border rounded px-2 py-1 bg-background text-foreground flex-1"
                defaultValue={typeof value === "object" ? JSON.stringify(value) : String(value ?? "")}
                onChange={(e) => {
                  let val = e.target.value;
                  if (val === "true") val = true;
                  else if (val === "false") val = false;
                  else if (!isNaN(Number(val)) && val.trim() !== "") val = Number(val);
                  setEditFields((prev) => ({ ...prev, [key]: val }));
                }}
              />
            </div>
          ))}
          <div className="flex gap-2 mt-2">
            <button
              onClick={handleSaveEdit}
              disabled={saving}
              className="text-xs bg-primary text-primary-foreground px-3 py-1 rounded hover:bg-primary/90 flex items-center gap-1"
            >
              <Save className="w-3 h-3" /> Save
            </button>
            <button
              onClick={() => {
                setEditing(false);
                setEditFields({});
              }}
              className="text-xs text-muted-foreground hover:text-foreground px-3 py-1"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 mt-3 border-t border-border pt-3">
        <button
          onClick={() => handleReview("approved")}
          disabled={saving || localClause.review_status === "approved"}
          className="text-xs px-2 py-1 rounded border border-green-300 text-green-700 hover:bg-green-50 dark:border-green-700 dark:text-green-400 dark:hover:bg-green-900/20 disabled:opacity-40 flex items-center gap-1"
        >
          <Check className="w-3 h-3" /> Approve
        </button>
        <button
          onClick={() => handleReview("flagged")}
          disabled={saving || localClause.review_status === "flagged"}
          className="text-xs px-2 py-1 rounded border border-orange-300 text-orange-700 hover:bg-orange-50 dark:border-orange-700 dark:text-orange-400 dark:hover:bg-orange-900/20 disabled:opacity-40 flex items-center gap-1"
        >
          <Flag className="w-3 h-3" /> Flag
        </button>
        {displayFields && Object.keys(displayFields).length > 0 && (
          <button
            onClick={() => {
              setEditing(true);
              setEditFields({});
            }}
            disabled={saving || editing}
            className="text-xs px-2 py-1 rounded border border-blue-300 text-blue-700 hover:bg-blue-50 dark:border-blue-700 dark:text-blue-400 dark:hover:bg-blue-900/20 disabled:opacity-40 flex items-center gap-1"
          >
            <Edit2 className="w-3 h-3" /> Edit
          </button>
        )}
        {(localClause.review_status === "approved" || localClause.review_status === "flagged") && (
          <button
            onClick={() => handleReview("pending")}
            disabled={saving}
            className="text-xs px-2 py-1 rounded border border-border text-muted-foreground hover:text-foreground hover:border-foreground/30 disabled:opacity-40 flex items-center gap-1"
          >
            <RotateCcw className="w-3 h-3" /> Undo
          </button>
        )}

        {localClause.raw_quote && (
          <button
            onClick={() => setExpanded((value) => !value)}
            className="ml-auto text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            Quote
          </button>
        )}
      </div>

      {expanded && localClause.raw_quote && (
        <p className="text-xs text-muted-foreground bg-muted/50 p-2 rounded mt-2 font-mono">
          {localClause.raw_quote}
        </p>
      )}

      {localClause.reviewed_by && (
        <p className="text-[10px] text-muted-foreground mt-2">
          Reviewed by {localClause.reviewed_by.slice(0, 8)}…
          {localClause.reviewed_at && ` • ${new Date(localClause.reviewed_at).toLocaleDateString()}`}
        </p>
      )}
    </div>
  );
}

export function ClausesTab({ clauses, setClauses, docNameMap, onCitationClick, playbookSchemas, getToken, roomId }) {
  const [clauseFilter, setClauseFilter] = useState({ playbook: "all", review: "all", search: "" });
  const [clausesPage, setClausesPage] = useState(1);
  const [approvingAll, setApprovingAll] = useState(false);

  useEffect(() => {
    setClausesPage(1);
  }, [clauseFilter]);

  const playbookIds = useMemo(() => {
    const ids = new Set(clauses.map((clause) => clause.playbook_id).filter(Boolean));
    return [...ids];
  }, [clauses]);

  const filteredClauses = useMemo(() => {
    return clauses.filter((clause) => {
      if (clauseFilter.playbook !== "all" && clause.playbook_id !== clauseFilter.playbook) return false;
      if (clauseFilter.review !== "all") {
        if (clauseFilter.review === "pending" && clause.review_status) return false;
        if (clauseFilter.review !== "pending" && clause.review_status !== clauseFilter.review) return false;
      }
      if (clauseFilter.search) {
        const q = clauseFilter.search.toLowerCase();
        if (
          !clause.interpretation?.toLowerCase().includes(q)
          && !clause.raw_quote?.toLowerCase().includes(q)
          && !clause.clause_type?.toLowerCase().includes(q)
        ) return false;
      }
      return true;
    });
  }, [clauses, clauseFilter]);

  const visibleClauses = filteredClauses.slice(0, clausesPage * CLAUSES_PAGE_SIZE);
  const hasMore = visibleClauses.length < filteredClauses.length;

  const grouped = useMemo(() => {
    const groups = {};
    visibleClauses.forEach((clause) => {
      const pid = clause.playbook_id || "other";
      if (!groups[pid]) groups[pid] = [];
      groups[pid].push(clause);
    });
    return Object.entries(groups).sort(([, a], [, b]) => b.length - a.length);
  }, [visibleClauses]);

  const pendingClauses = clauses.filter((clause) => !clause.review_status);

  async function handleApproveAll() {
    setApprovingAll(true);
    try {
      await Promise.all(pendingClauses.map((clause) => reviewClause(getToken, roomId, clause.id, { status: "approved" })));
      setClauses((prev) => prev.map((clause) => clause.review_status ? clause : { ...clause, review_status: "approved" }));
    } catch {
      // silently handle
    }
    setApprovingAll(false);
  }

  if (clauses.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Shield className="w-8 h-8 mx-auto mb-2 opacity-50" />
        <p className="text-sm">No structured clauses extracted yet.</p>
        <p className="text-xs text-muted-foreground mt-1">Run analysis to extract clauses.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="pe-filter-bar">
        <select
          value={clauseFilter.playbook}
          onChange={(e) => setClauseFilter((value) => ({ ...value, playbook: e.target.value }))}
          className="text-xs bg-background border border-border/60 rounded-lg px-2 py-1 text-foreground"
        >
          <option value="all">All Playbooks</option>
          {playbookIds.map((playbookId) => (
            <option key={playbookId} value={playbookId}>{PLAYBOOK_LABELS[playbookId] || playbookId}</option>
          ))}
        </select>
        <div className="w-px h-4 bg-border/60" />
        {["all", "pending", "approved", "flagged", "edited"].map((status) => (
          <FilterPill key={status} active={clauseFilter.review === status} onClick={() => setClauseFilter((value) => ({ ...value, review: status }))}>
            {status.charAt(0).toUpperCase() + status.slice(1)}
          </FilterPill>
        ))}
        <div className="flex-1 min-w-0 flex items-center gap-1.5 bg-background border border-border/60 rounded-lg px-2 py-1">
          <Search className="w-3 h-3 text-muted-foreground shrink-0" />
          <input
            type="text"
            placeholder="Search clauses…"
            value={clauseFilter.search}
            onChange={(e) => setClauseFilter((value) => ({ ...value, search: e.target.value }))}
            className="text-xs bg-transparent border-0 outline-none w-full placeholder:text-muted-foreground"
          />
        </div>
        {pendingClauses.length > 0 && (
          <button
            onClick={handleApproveAll}
            disabled={approvingAll}
            className="text-xs px-3 py-1 rounded-lg bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 font-semibold hover:brightness-95 disabled:opacity-50 whitespace-nowrap flex items-center gap-1"
          >
            <Check className="w-3 h-3" />
            {approvingAll ? "Approving…" : `Approve All (${pendingClauses.length})`}
          </button>
        )}
      </div>

      <p className="text-xs text-muted-foreground">
        Showing {visibleClauses.length} of {filteredClauses.length} clauses
        {filteredClauses.length !== clauses.length ? ` (${clauses.length} total)` : ""}
      </p>

      <div className="space-y-6">
        {grouped.map(([playbookId, clauseList]) => (
          <div key={playbookId} className="border border-border rounded-lg overflow-hidden">
            <div className="bg-muted/50 px-4 py-3 border-b border-border">
              <h3 className="font-semibold text-foreground">
                {PLAYBOOK_LABELS[playbookId] || playbookId}
                <span className="ml-2 text-sm text-muted-foreground font-normal">({clauseList.length})</span>
              </h3>
            </div>
            <div className="p-4 space-y-3">
              {clauseList.map((clause) => (
                <ClauseCard
                  key={clause.id}
                  clause={clause}
                  docNameMap={docNameMap}
                  onCitationClick={onCitationClick}
                  schema={playbookSchemas?.[playbookId]}
                  getToken={getToken}
                  roomId={roomId}
                  onReview={(updated) =>
                    setClauses((prev) => prev.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)))
                  }
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      {hasMore && (
        <button
          onClick={() => setClausesPage((page) => page + 1)}
          className="w-full text-xs text-muted-foreground hover:text-foreground border border-border/60 rounded-lg py-2.5 hover:bg-muted/30 transition-colors"
        >
          Show {Math.min(CLAUSES_PAGE_SIZE, filteredClauses.length - visibleClauses.length)} more clauses
        </button>
      )}
    </div>
  );
}
