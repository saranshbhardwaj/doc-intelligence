# PE Diligence Concierge — Implementation Plan

## Goal

Production-grade, provenance-first VDR diligence backend that is:
- useful for real PE diligence teams (false negatives are unacceptable),
- auditable and human-reviewable,
- easy to extend into adjacent PE products,
- easy to extract into a microservice later.

---

## Completed Work

### Phase A — Scaffold

- Data model + migration (`db_models_pe_diligence.py`, 11 ORM models)
- Diligence module skeleton: `schemas.py`, `repository.py`, `service.py`, `tasks.py`
- API wiring: `api/diligence.py` → `api/router.py`
- Runtime wiring: model imports in `database.py`, `migrations/env.py`, Celery routes in `celery_app.py`

### Phase B — Trust Core

- Evidence span persistence: normalized `pe_diligence_evidence_spans` table + migration
- Clause extraction via deterministic regex engine
- Numeric reconciliation hooks (spread checks, sanity checks) in findings
- Multi-page evidence correctness using `chunk_metadata` (page range / bbox / regions)

### Phase C — Classification & Investigations

#### Analysis Pipeline
- Document classification (rule-based v1 + LLM fallback with anchor gate)
  - Module: `document_classifier.py`
  - Per-doc output: `document_type`, `confidence`, `needs_review`, `signals`
  - Anchor-gated LLM fallback rejects unanchored candidates with audit events
- Finding verification (deterministic v1): `verifier.py`
- Claim lifecycle + dual-score schema: `status`, `supersedes_claim_id`, `source_workers`, `confidence_history`, `interpretation_confidence`, `coverage_score`

#### Investigation Pipeline — Hardened (Week 1-2)

**Problem:** The original investigation pipeline was regex-only with 4 patterns, 5 seed queries, and no document-type awareness. PE firms cannot afford false negatives — a missed CoC clause means the deal team makes decisions on incomplete information.

**What we built:**

1. **Expanded regex recall** (`claim_builder.py`)
   - 4 patterns → 27 patterns across 4 signal groups
   - `PatternEntry` frozen dataclass: signal, regex, confidence, label
   - `SIGNAL_REGISTRY` — extensible pattern list (add patterns without modifying adjudication)
   - Legal synonyms covered: novation, merger/consolidation, successor-in-interest, sale of substantially all assets, anti-assignment, prior written consent, freely assignable, consent waived, material adverse change, acceleration, penalty/damages
   - Negation detection: scans 40-char window before match, applies 0.12 confidence penalty (never flips signal — avoids masking double negations like "shall not assign without consent")
   - Deduplication: per (chunk_id, signal_group), keeps highest confidence
   - Claim confidence derived from evidence scores (clamped 0.80–0.92)

2. **Expanded seed queries** (`templates.py`)
   - 5 → 16 seed queries covering legal synonyms and related concepts
   - 5 → 10 filename hints (added: amendment, addendum, lease, service, subscription)

3. **Inclusive document routing** (`retriever.py`)
   - Two-tier routing: primary (type/filename match) + safety tier
   - Safety tier always includes: docs classified as "other", unclassified docs, docs with `needs_review=True`
   - A document is only excluded if it has a confident non-matching classification AND non-matching filename
   - Prevents false negatives from misclassified contracts

4. **LLM claim augmentation** (`llm_claim_builder.py` + `tasks.py`)
   - Runs after regex: chunks with no regex hits go to LLM for paraphrased/unusual clause detection
   - `LLMClaimBuilder` class with DI for `StructuredLLMRunner`
   - Pydantic schema: `LLMClaimBatch` → `LLMClaimCandidate` (chunk_id, claim_key, claim_text, stance, evidence_quote, confidence, rationale)
   - **Anchor gate**: rejects claims with chunk_id not in input set
   - **Claim key gate**: rejects invalid claim keys
   - **Trust boundary**: LLM claims always get `verification_status: "needs_review"` and `source_workers: ["llm"]` — they expand recall, never auto-accept
   - Dedup: highest confidence per claim_key
   - Merge rules: regex claim wins on key conflict; LLM evidence appended; existing claim tagged `llm_augmented: true`
   - Prompt caching: system prompt uses `cache_control: ephemeral` (5-min TTL, ~10x cheaper on repeated calls)
   - Graceful degradation: LLM failure logs warning, regex claims stand
   - Gated by `settings.pe_diligence_investigation_llm_enabled` (default: off)
   - Max chunks configurable: `settings.pe_diligence_investigation_llm_max_chunks` (default: 30)
   - Rejected LLM claims audited via `add_audit_event(event_type="investigation.llm_claim_rejected")`

5. **Weighted coverage scoring** (`coverage.py`)
   - Document-type weighting: contracts = 3x, financials = 1.5x, others = 1x
   - Weighted formula: 0.35 contract coverage + 0.25 doc spread + 0.15 targeted spread + 0.25 evidence density
   - **Force weak**: if contracts exist but none have evidence hits → coverage capped at 0.39 (below "moderate")
   - Fallback: no classifications available → original unweighted scoring
   - New metrics: `contracts_total`, `contracts_with_hits`, `contract_coverage_ratio`

#### API Surface
- Base prefix: `/api/v1/pe/diligence`
- Endpoints: rooms, documents, analysis runs, checklist/findings/summary/audit, investigations, evidence search
- Room document responses expose: `document_type`, `classification_confidence`, `classification_needs_review`, `classification_signals`
- Analysis run responses expose: `verification_total`, `verification_verified`, `verification_needs_review`, `document_classification_total`, `document_classification_needs_review`, `document_type_counts`

---

## Validation Invariants (Must Hold)

1. **Provenance** — No uncited high-impact claim is auto-accepted. Missing/weak anchors force `needs_review`.
2. **Interpretation boundary** — LLM interpretation requires a valid anchor (rule_anchor_id for classification, chunk_id for investigation claims). No anchor → reject.
3. **Scoring** — Dual score (`interpretation_confidence` + `coverage_score`) is mandatory. High confidence + low coverage routes to review. Low confidence + high coverage routes to review.
4. **Explanation boundary** — Explanation generation reads only verified/canonical DB claims. LLM outputs never rendered directly as user-facing text.
5. **State/safety** — DB is source-of-truth. Every async exception path emits terminal error state + audit event. Retry is idempotent.

---

## Pipeline Flows

### Analysis Pipeline (current)
```
load_documents → document_classification (rule + LLM fallback)
  → [FUTURE: amendment_linking] → clause_extraction → numeric_reconciliation
  → checklist_mapping → risk_scoring → verification → summary → evidence spans
```

### Investigation Pipeline (current + planned)
```
load_context → soft_prereq_check → route_candidates → retrieve_targeted
  → coverage_gate (expand if weak) → build_claims (regex, 27 patterns)
  → llm_claim_augmentation (optional, unmatched chunks only)
  → [FUTURE: reconcile_amendments] → score_gate (dual-score matrix)
  → persist_evidence → conclusion
```

Stages update `InvestigationRun.progress_percent` for frontend polling.

---

## Next Up — Remaining Backlog

### Priority 1: Claim History & Review Workflow

#### T6. Preserve claim history across reruns
- Current: `replace_claims` deletes all claims then re-inserts — destroys user overrides on rerun
- Fix: soft-archive previous run's claims (`status = "archived"`), create new claims with `supersedes_claim_id` pointing to previous version, carry forward `verification_status` when claim_key matches
- Files: `investigations/repository.py`

#### T7. Review endpoints + override transitions
- Classification override, claim override, conflict disposition with immutable audit records
- Persist: reviewer, timestamp, previous/new value, reason
- Files: `api/diligence.py`, `api/diligence_investigations.py`, repositories

### Priority 2: Real-Time Progress & Observability

#### T8. SSE progress streaming for investigations
- Current: progress written to DB via `repo.update_run()` but no real-time push
- Fix: wire `JobProgressTracker` from `app/services/job_tracker.py` (Redis pub/sub → SSE)
- Add SSE endpoint: `GET /api/v1/pe/diligence/investigations/{id}/runs/{run_id}/stream`
- Follow existing pattern from PE workflow tasks
- Files: `investigations/tasks.py`, `api/diligence_investigations.py`

#### T9. Operational metrics + dashboards
- Emit: `needs_review_rate`, `missing_anchor_reject_rate`, `low_coverage_high_confidence_rate`, `conflict_rate`, `override_rate`
- Files: `app/utils/metrics.py`, decision points in tasks

### Priority 3: Document Graph — Amendment Detection & Claim Reconciliation

**The problem:** The pipeline is per-document blind. If Contract A says "consent required on CoC" and Amendment 1 deletes that section, the system reports the clause as `supported`. The reverse is also true: an amendment adding a restriction goes undetected if the original shows no risk.

**Design decision:** We do NOT build a full document graph platform (weighted NER scoring, embedding similarity, ML classifiers). That's what Evisort/Eigen built over years. Instead, we build three tiers — each independently useful — that solve the actual problem: **"when I find a clause, is it still in effect?"**

#### T10. Amendment Detection (Tier 1 — Analysis phase)

Detect whether a document IS an amendment. Extend the existing document classifier.

**Runs during:** `document_classification` stage of `run_diligence_analysis_task` — where `classify_documents()` already runs.

**How:**
- Add `"amendment"` as a new document type in `document_classifier.py` TYPE_PATTERNS
- Patterns: `amendment`, `first amendment`, `amended and restated`, `addendum`, `side letter`, `modification`, `supplement`, `joinder`, `restatement`
- Pure regex on filename + first ~4000 chars of text — cheap, deterministic, catches ~80%
- LLM fallback (existing `PEDiligenceClassificationAdapter` pattern) catches remaining ~20%
- Stored in `metadata_json`: `{"document_classification": {"document_type": "amendment", ...}}`

**Files:** `diligence/document_classifier.py`, `diligence/llm_adapter.py`

#### T11. Parent Document Matching (Tier 2 — Analysis phase)

For each detected amendment, find which contract in the VDR it amends.

**Runs during:** New `amendment_linking` stage in `run_diligence_analysis_task`, after `document_classification`.

**How:**
1. Filter documents classified as `amendment`
2. For each amendment, use LLM (reuse `StructuredLLMRunner` pattern) to extract parent reference:
   - Input: amendment text (first ~4000 chars) + list of all doc titles/filenames in room
   - Prompt: "This document is an amendment. Which document does it amend? Quote the reference sentence."
   - Output: `{parent_document_id, confidence, evidence_quote, amendment_type}`
3. `amendment_type` values: `modifies` | `supersedes` (amended & restated) | `supplements` | `references`
4. Stored in amendment doc's `metadata_json`:
   ```json
   {"amendment_link": {"parent_document_id": "...", "amendment_type": "modifies", "confidence": 0.87, "evidence_quote": "This First Amendment to the MSA dated...", "linked_by": "llm_v1"}}
   ```
5. Prompt caching: system prompt with room doc list uses `cache_control: ephemeral` — multiple amendments share cached context
6. No match: store `parent_document_id = null` with reason `"no_parent_matched"` — surface in UI

**Files:** New `diligence/amendment_linker.py`, modified `diligence/tasks.py`, `config.py`
**Config:** `pe_diligence_amendment_linking_enabled: bool = True`

#### T12. Claim Reconciliation (Tier 3 — Investigation phase)

When a claim's source document has a linked amendment, flag the claim for review. **Conservative: do NOT auto-resolve.**

**Runs during:** New `reconcile_amendments` stage in investigation task, after `llm_claim_augmentation`, before `score_gate`.
```
build_claims → llm_augmentation → [RECONCILE_AMENDMENTS] → score_gate → persist
```

**How:**
1. Build contract family map from room doc metadata:
   `{base_doc_id: [{amendment_doc_id, amendment_type, confidence}]}`
2. For each claim, check if its source document (via evidence span `source_document_id`) belongs to a family:
   - Claim from **base contract** + amendments exist → `needs_review`, reason `amendment_exists`
   - Claim from **amendment** + base also has claims → flag both, reason `amendment_overlap`
   - Amendment type is `supersedes` → flag base claims as `potentially_superseded`
3. All flagged claims get `verification_status: "needs_review"` — reconciler never auto-accepts or auto-rejects

**What this does NOT do (intentionally):**
- Does NOT parse section references ("Section 5.2 is deleted") — that's Tier 4
- Does NOT auto-flip claim stances — wrong link is worse than no link
- Does NOT require NER, embedding similarity, or weighted scoring

**Why this is enough:** The deal team sees "Claim X found in Contract A. Amendment 1 to Contract A exists. Please verify." The human reviewer resolves it in 30 seconds. Zero risk of incorrect auto-resolution.

**Files:** New `investigations/reconciler.py`, modified `investigations/tasks.py`
**Reason codes:** `amendment_exists`, `amendment_overlap`, `potentially_superseded`

#### T13. Section-Level Resolution (Tier 4 — Future)

Only build after Tier 3 is validated with real VDRs.
- Parse section references in amendments: "Section 5.2 is deleted", "Section 3 is amended to read..."
- Map to specific chunks/claims in the base contract
- Auto-suggest resolution (still `needs_review`, but with suggested stance)
- May use LLM to compare old clause text vs amendment replacement text

**Infrastructure already in place for all tiers:**
- `supersedes_claim_id` on `InvestigationClaim` — claim lineage ready
- `source_chunk_id` on evidence spans — trace claim → document → section
- `metadata_json` JSONB on `PEDiligenceRoomDocument` — store amendment links
- `StructuredLLMRunner` — reuse for parent matching LLM calls
- `PEDiligenceClassificationAdapter` — pattern template for amendment adapter
- Prompt caching (`cache_control: ephemeral`) — cheap repeated LLM calls

### Priority 4: Conclusion & Review Workflow

#### T14. LLM-generated conclusion with evidence citations
- Replace template `_build_conclusion` with LLM call that reads verified claims + evidence spans
- Generate narrative with inline citations: "Based on 3 contracts containing explicit CoC consent requirements (MSA with Acme Corp, License with Beta Inc), and Amendment 1 modifying the Acme MSA, change-of-control risk is HIGH..."
- Guard: explanation boundary invariant (reads only DB-persisted verified claims)
- Files: `investigations/tasks.py`

#### T15. Review endpoints + override transitions
- Classification override, claim override, conflict disposition with immutable audit records
- Persist: reviewer, timestamp, previous/new value, reason
- Files: `api/diligence.py`, `api/diligence_investigations.py`, repositories

### Priority 5: Pilot Readiness

#### T16. Preserve claim history across reruns
- Current: `replace_claims` deletes all claims then re-inserts — destroys user overrides
- Fix: soft-archive previous run's claims (`status = "archived"`), new claims with `supersedes_claim_id`, carry forward `verification_status` on matching `claim_key`
- Files: `investigations/repository.py`

#### T17. SSE progress streaming for investigations
- Wire `JobProgressTracker` from `app/services/job_tracker.py` (Redis pub/sub → SSE)
- Endpoint: `GET /api/v1/pe/diligence/investigations/{id}/runs/{run_id}/stream`
- Files: `investigations/tasks.py`, `api/diligence_investigations.py`

#### T18. Edge-case fixture suite + idempotency hardening
- Fixtures: amendment chains, conflicts, sparse evidence, missing metadata, rerun idempotency
- No duplicate claim/evidence writes, no orphaned in-progress states
- Files: `backend/tests/`, `investigations/tasks.py`, `diligence/tasks.py`

#### T19. Pilot acceptance runbook
- End-to-end VDR analysis + investigation on real/past deal
- Go/No-Go decision based on validation gates

---

## Validation Gates (Go/No-Go for Pilot)

### Functional
- Anchor-required interpretation enforced in analysis and investigation paths
- Dual-score gate active in all claim decisions
- LLM augmentation tested with paraphrased legal language
- Amendment detection: amendments classified correctly, parent docs linked
- Claim reconciler: claims from documents with amendments flagged for review
- No auto-resolution of amendment conflicts — always `needs_review`

### Quality
- Edge-case suite passes: amendment chains, conflicting amendments, duplicate clauses, sparse evidence, missing metadata, rerun idempotency
- No false negatives on known test VDRs with non-standard legal language
- Amendment linking handles: no match found, multiple candidate parents, "amended and restated" supersession

### Operational
- Dashboards live for review rates, rejection rates, coverage metrics
- SSE progress streaming functional for investigation runs
- Amendment linking audit trail: every link decision logged

### Business
- Internal pilot completes end-to-end investigation with:
  - clear canonical claim set, no silent contradictions
  - amendment relationships visible (which docs amend which)
  - claims from amended contracts flagged for verification
  - auditable override trail
  - confidence/coverage visibly separated
  - LLM-augmented claims flagged for review

---

## Scale Track (Post-Pilot)

- Service extraction: formalize diligence microservice interface, throughput/SLA targets
- Retrieval expansion: additional clause/table/entity extractors, improved contradiction detection
- Productization: version delta detection, export-ready diligence memo with evidence footnotes, VDR connector abstraction
- New investigation types: financial covenant analysis, IP/license exposure, employment/benefit obligations

---

## Implementation Quality Standards

### SOLID Principles (enforced per module)
- **Single Responsibility**: Each module does one thing. `amendment_linker.py` only links amendments — doesn't classify, doesn't reconcile. `reconciler.py` only flags claims — doesn't persist, doesn't build evidence.
- **Open/Closed**: `SIGNAL_REGISTRY` list is extensible (add patterns) without modifying `build_change_of_control_claims`. New investigation types add templates without touching claim adjudication. New amendment types add to `amendment_type` enum without modifying linker logic.
- **Dependency Inversion**: All LLM-dependent classes accept `StructuredLLMRunner` via constructor injection. Repository layer injected, never instantiated inside domain logic. Makes testing possible without DB or LLM.
- **Interface Segregation**: Pydantic schemas define clear input/output contracts per module. Repositories expose focused methods, not god-objects.

### Edge Case & Business Rule Discipline
- Every new module must handle: empty inputs, null/missing fields, LLM timeout/failure, zero-result scenarios
- Negation contexts (legal language): never auto-flip — lower confidence, route to review
- Confidence calibration: regex exact match (0.85-0.92), regex fuzzy (0.70-0.84), LLM (always needs_review regardless of score)
- Graceful degradation: if any optional stage fails (LLM augmentation, amendment linking), the pipeline continues with what it has and logs the failure

### Cross-Track Standards
1. **Versioning** — Every logic block includes version tags in metadata (replay + attribution)
2. **Testability** — Every ticket ships with deterministic fixtures and integration assertions
3. **Backward compatibility** — Additive API/schema changes only unless explicitly versioned
4. **Observability** — Every auto-review decision emits reason codes and audit events
5. **Layering** — Route handlers orchestrate I/O only; domain rules in service/tasks; data access in repository; composition over coupling
6. **LLM trust boundary** — LLM outputs always `needs_review`; regex/rule outputs can auto-accept if confidence thresholds met
7. **Prompt caching** — System prompts use `cache_control: ephemeral` for Anthropic 5-min cache (~10x cost reduction)
8. **Config gating** — Every optional feature has a `settings.*_enabled` toggle (default off for LLM features, on for rule features)
9. **Audit trail** — Every rejected LLM candidate, every override, every reconciliation decision gets an `add_audit_event` call

---

## Key Files Reference

| File | Role |
|------|------|
| `db_models_pe_diligence.py` | 11 ORM models (Room, Document, Analysis, Investigation, Claim, Evidence, Audit) |
| `diligence/tasks.py` | Analysis Celery task (classify → extract → verify → summarize) |
| `diligence/document_classifier.py` | Rule-based doc classification + LLM fallback |
| `diligence/llm_adapter.py` | Structured LLM adapter for classification |
| `diligence/verifier.py` | Deterministic finding verification |
| `investigations/tasks.py` | Investigation Celery task (route → retrieve → claims → LLM → score → persist) |
| `investigations/claim_builder.py` | 27-pattern regex claim builder with negation detection |
| `investigations/llm_claim_builder.py` | LLM claim augmentation (anchor-gated, always needs_review) |
| `investigations/coverage.py` | Document-type-weighted coverage scoring |
| `investigations/retriever.py` | Two-tier document routing + evidence retrieval |
| `investigations/templates.py` | Investigation templates (seed queries, filename hints) |
| `investigations/repository.py` | Investigation data access layer |
| `investigations/schemas.py` | Pydantic request/response models |
| `api/diligence.py` | Analysis API endpoints |
| `api/diligence_investigations.py` | Investigation API endpoints |
| `config.py` | Settings: `pe_diligence_investigation_llm_enabled`, `pe_diligence_investigation_llm_max_chunks` |
