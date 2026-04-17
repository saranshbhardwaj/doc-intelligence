import { useMemo, useState } from "react";

import { PLAYBOOK_LABELS, REVIEW_BADGE } from "../../../analysis/displayConstants";
import FilterPill from "../shared/FilterPill";
import ClauseCard from "./ClauseCard";

export default function ClausesTab({ clauses, docNameMap, onCitationClick }) {
  const [reviewFilter, setReviewFilter] = useState("all");
  const [playbookFilter, setPlaybookFilter] = useState("all");

  const reviewOptions = useMemo(() => {
    const values = Array.from(new Set((clauses || []).map((clause) => clause.review_status).filter(Boolean)));
    return ["all", ...values];
  }, [clauses]);

  const playbookOptions = useMemo(() => {
    const values = Array.from(new Set((clauses || []).map((clause) => clause.playbook_id).filter(Boolean)));
    return ["all", ...values];
  }, [clauses]);

  const filteredClauses = useMemo(() => {
    return (clauses || []).filter((clause) => {
      if (reviewFilter !== "all" && clause.review_status !== reviewFilter) return false;
      if (playbookFilter !== "all" && clause.playbook_id !== playbookFilter) return false;
      return true;
    });
  }, [clauses, playbookFilter, reviewFilter]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3 items-start justify-between">
        <div>
          <h3 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">Review Status</h3>
          <div className="flex flex-wrap gap-2">
            {reviewOptions.map((option) => (
              <FilterPill
                key={option}
                active={reviewFilter === option}
                onClick={() => setReviewFilter(option)}
                label={option === "all" ? `All (${clauses.length})` : `${option.replace(/_/g, " ")}`}
                count={option === "all" ? undefined : clauses.filter((clause) => clause.review_status === option).length}
                className={option !== "all" ? (REVIEW_BADGE[option] || REVIEW_BADGE.not_reviewed) : undefined}
              />
            ))}
          </div>
        </div>

        <div>
          <h3 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">Playbook</h3>
          <div className="flex flex-wrap gap-2 justify-end">
            {playbookOptions.map((option) => (
              <FilterPill
                key={option}
                active={playbookFilter === option}
                onClick={() => setPlaybookFilter(option)}
                label={option === "all" ? "All clauses" : (PLAYBOOK_LABELS[option] || option)}
              />
            ))}
          </div>
        </div>
      </div>

      {filteredClauses.length ? (
        <div className="space-y-3">
          {filteredClauses.map((clause) => (
            <ClauseCard key={clause.id} clause={clause} docNameMap={docNameMap} onCitationClick={onCitationClick} />
          ))}
        </div>
      ) : (
        <div className="pe-card p-6 text-sm text-muted-foreground">No clauses match the current filters.</div>
      )}
    </div>
  );
}
