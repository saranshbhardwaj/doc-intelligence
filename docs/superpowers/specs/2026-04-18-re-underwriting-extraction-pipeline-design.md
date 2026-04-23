# RE Underwriting Extraction Pipeline — Design Spec
**Date:** 2026-04-18  
**Branch:** sb/re-underwriting  
**Status:** Approved for implementation

---

## 1. Problem Statement

The current RE underwriting extraction pipeline has several critical bugs and design gaps:

1. **Celery chain is broken** — `chain(list_of_tasks, merge_task)` runs extract tasks sequentially and only passes the last task's output to merge. Multi-doc extraction silently drops all but the last document.

2. **Large data passed through Redis** — the API fetches all document chunks, joins them into a raw text string, and passes it as the Celery task payload. A 100-page OM can be 200KB+ through Redis. Redis has a default 512MB max but broker throughput degrades badly with large messages.

3. **N+1 DB calls in the API** — loops `get_by_id` + `get_chunks_for_document` per document in the request handler.

4. **No document size guard** — all chunks concatenated into one string in a single LLM call regardless of size.

5. **Wrong document slot labels** — the wizard UI conflated T-12 and Rent Roll, and the third slot ("Supplemental Docs") had `doc_type=t12` on the backend.

---

## 2. Document Slots

Three fixed slots. OM is the only required document.

| Slot | `doc_type` | Required | What we extract |
|---|---|---|---|
| Offering Memorandum | `om` | Yes | Purchase price, unit mix, cap rate, hold/exit assumptions, deal terms, property name/address |
| T-12 / T-6 | `t12` | No | Trailing 12 or 6 months actual GPR, vacancy, all expense line items, NOI |
| Rent Roll | `rent_roll` | No | Current unit occupancy, per-unit rents, sizes, lease expirations |

**What to extract:** financially relevant data + property name/address for wizard pre-fill. No location demographics, market narrative, or qualitative content — those don't feed the calculator.

---

## 3. Celery Message Design — Keep Payloads Small

**Rule: never pass document content through Celery/Redis. Pass IDs only.**

The API endpoint passes `document_id` + `doc_type` per slot. Each Celery task opens its own DB session and fetches the chunks it needs.

```
API payload to Celery (tiny, ~200 bytes per doc):
{
  "run_id": "uuid",
  "job_id": "uuid",
  "doc_type": "om",
  "document_id": "uuid"   ← ID only, no content
}

Task fetches chunks from DB itself:
  chunks = doc_repo.get_chunks_for_document(document_id)
```

The merge task similarly receives only the extracted structured results (small Pydantic dicts, not raw text). Raw chunk content never travels through Redis.

---

## 4. Extraction Architecture

### 4.1 Per-Document Extraction (Parallel)

Each document is extracted independently in parallel using Celery `chord` + `group`. This fixes the broken chain bug.

```python
chord(
    group(
        re_extract_per_doc_task.s(om_payload),
        re_extract_per_doc_task.s(t12_payload),
        re_extract_per_doc_task.s(rent_roll_payload),
    ),
    chain(
        re_merge_extractions_task.s(),
        re_detect_discrepancies_task.s(),
        re_calculate_underwriting_task.s(),
    )
)
```

The chord callback is a `chain` — Celery requires the callback to be a single signature. The merge task receives `list[ExtractedDocResult]` — one per doc.

### 4.2 Two-Tier Extraction Per Document

Each task fetches its chunks, measures total chars, then branches:

```
chunks = doc_repo.get_chunks_for_document(document_id)
total_chars = sum(len(c.content) for c in chunks)

if total_chars <= re_uw_full_text_max_chars (80,000):
    → direct_extract(chunks)       # one LLM call
else:
    → map_reduce_extract(chunks)   # Phase 1 batches + Phase 2 reduce
```

**Direct path** — build context string with citation headers, one LLM call, fill per-doc Pydantic model.

**Map-reduce path** — triggered for docs exceeding 80K chars (typically long OMs). Two phases:

- **Phase 1 (Map):** Batch chunks by char budget (not fixed count — see §7). Each batch → LLM → `CondensedBatchExtraction` (list of `{field, value, citations, source_text}`). Schema-agnostic: "extract all financially relevant data." Chunk types handled differently in the prompt: KV pairs = highest confidence, tables = high-confidence numeric, narratives = contextual.
- **Phase 2 (Reduce):** All condensed batch results → single LLM call → per-doc Pydantic model. Schema fitting happens only here.

Phase 2 output is small structured JSON — safe to pass back through Redis to the merge task.

### 4.3 Chunk Types

Three types already in DB (`is_tabular`, `section_type`):

| Type | `is_tabular` | Extraction priority |
|---|---|---|
| KV pair | False, `section_type="key_value"` | Highest — already structured |
| Table | True | High — numeric financial data, bbox per table |
| Narrative | False, `section_type="narrative"` | Lower — contextual, may overlap with others |

When all three contain the same value, KV pair > table > narrative in Phase 2.

---

## 5. Citation Format

Reuses existing `[S1:pN]` format (Source index, page number) used across template filling and chat. Each chunk has `chunk_metadata.bbox` + `page_number` already stored — the citation token maps back to these for UI highlighting via `CitationBadge.jsx` and `CitationDrawer.jsx`.

Chunks are prefixed before sending to LLM:
```
[S1:p12] (Table Chunk — Financial Summary)
Unit Type | Count | Avg Rent | Total SF
...

[S1:p14] (KV Pair)
Gross Potential Rent: $485,000/year
```

Phase 1 condensed output preserves citations:
```json
{
  "field": "gross_potential_rent_annual",
  "value": "485000",
  "citations": ["[S1:p12]", "[S1:p14]"],
  "source_text": "GPR $485,000/yr per rent roll summary table"
}
```

These flow through to `run.field_citations` JSONB — no new citation infrastructure needed.

---

## 6. Per-Document Pydantic Schemas

Three separate extraction schemas. All fields `Optional[...]` with `None` default.

### `OMExtraction`
```python
purchase_price, closing_cost_pct, capex_reserve_per_unit,
num_units, rentable_sqft, year_built, name, address,
gpr_annual_projected, vacancy_pct_projected, noi_projected,
mgmt_fee_pct, exit_cap_rate, hold_period_years, selling_cost_pct,
target_irr, target_cash_on_cash, target_equity_multiple,
ltv_pct, interest_rate_pct, amortization_years, loan_term_years
```

### `T12Extraction`
```python
gpr_annual_actual, vacancy_credit_loss_pct_actual,
other_income_annual, property_tax_annual, insurance_annual,
mgmt_fee_pct_actual, payroll_annual, repairs_maintenance_annual,
utilities_annual, marketing_annual, other_opex_annual,
noi_actual, period_months  # 12 or 6 — used to annualise T-6 figures (× 12/period_months)
```

### `RentRollExtraction`
```python
num_units_actual, physical_occupancy_pct,
lease_records: list[LeaseRecord],  # existing schema
rent_growth_pct
```

---

## 7. Config Values to Add

```python
# RE Underwriting extraction
re_uw_full_text_max_chars: int = 80_000         # below → direct single call per doc
re_uw_map_reduce_max_chars_per_batch: int = 20_000  # hard char cap per Phase 1 batch
re_uw_discrepancy_threshold_pct: float = 0.10   # flag if sources differ by > 10%
re_uw_task_soft_time_limit_seconds: int = 600   # 10 min → SoftTimeLimitExceeded → mark_error
re_uw_stale_job_timeout_minutes: int = 20       # periodic_cleanup() sweeps runs stuck here
```

**Char-budget batching** (not fixed chunk count — at ~500 tokens/chunk × 4 chars = ~2,000 chars/chunk, 15 chunks ≈ 30K chars which exceeds the 20K guard):

```python
batches, current, current_chars = [], [], 0
for chunk in chunks:
    n = len(chunk.content)
    if current_chars + n > settings.re_uw_map_reduce_max_chars_per_batch and current:
        batches.append(current)
        current, current_chars = [], 0
    current.append(chunk)
    current_chars += n
if current:
    batches.append(current)
```

Extraction model reuses `synthesis_llm_model` (Haiku 4.5).

---

## 8. Merge & Conflict Resolution

Industry-standard CRE underwriting priority:

| Field group | Wins | Rationale |
|---|---|---|
| GPR, vacancy %, all expenses, NOI | **T-12** | Verified actuals beat seller projections |
| Current occupancy, per-unit rents, lease expirations | **Rent Roll** | Most current point-in-time data |
| Purchase price, exit cap, hold period, selling costs, LTV, interest rate | **OM** | Deal terms — not historical |
| Mgmt fee % | T-12 if present, else OM | T-12 shows actual cost |
| Num units, rentable sqft | Rent Roll if present, else OM | Rent roll is authoritative |

Discrepancy detection flags any field where two sources differ by > 10%. Stored in `run.discrepancies`, surfaced via `DiscrepancyBanner.jsx`.

---

## 9. Task Pipeline (Updated)

```
API: POST /api/v1/re/underwriting/runs
  → validate OM doc_id present
  → create UnderwritingRun (status=extracting)
  → create JobState
  → start_re_underwriting_chain(run_id, [{doc_id, doc_type}, ...], job_id)
     ↑ NO chunk fetching here — IDs only

Celery (critical queue):
  chord(
    group(re_extract_per_doc_task × N docs),   # each fetches own chunks from DB
    chain(
      re_merge_extractions_task,               # receives list[ExtractedDocResult] — small JSON
      re_detect_discrepancies_task,
      re_calculate_underwriting_task,          # calculator → stress tests → verdict → store
    )
  )

SSE: GET /api/v1/jobs/{job_id}/stream
  → frontend polls via streamJobProgress() (15 min timeout, auto-reconnect)
```

Progress stages:
- `initialization` → 5%
- `extracting_om` / `extracting_t12` / `extracting_rent_roll` → 20–50%
- `merging` → 60%
- `discrepancy_detection` → 70%
- `calculating` → 80%
- `done` → 100%

---

## 10. Error Handling

**Task-level:**
- Every exception path calls `tracker.mark_error()` — existing pattern
- Task decorator: `soft_time_limit=600, acks_late=True, reject_on_worker_lost=True`
- `SoftTimeLimitExceeded` caught → `tracker.mark_error()` + `repo.update_status(run_id, "failed")`
- Non-required doc failure (T-12, rent roll): pipeline continues, missing doc logged as warning, merge works with available docs
- OM failure: run fails immediately

**Worker down:**
- `acks_late=True` + `reject_on_worker_lost=True` — Celery re-queues if worker crashes mid-task
- Stale sweep added to `lifespan.py`'s `periodic_cleanup()` (same pattern as uploaded file cleanup): finds `UnderwritingRun` records stuck in `status=extracting` for > `re_uw_stale_job_timeout_minutes` → marks them `failed` with `error_message="Job timed out — worker may have crashed"`

**Frontend:**
- SSE `streamJobProgress` already has 15-min absolute timeout and exponential backoff reconnect
- On `onError`: wizard shows inline error card (existing `DiscrepancyBanner` pattern), not `alert()`

---

## 11. Frontend Changes (Already Applied)

- Wizard doc slots corrected: OM → T-12/T-6 → Rent Roll (labels, subtitles, `doc_type` keys)
- State key order fixed: `{ om, t12, rent_roll }` (was `{ om, rent_roll, t12 }`)

---

## 12. Out of Scope

- Additional asset types beyond `self_storage`
- Audited financial statements as a separate slot (upload as T-12 slot)
- RAG retrieval for extraction (map-reduce chosen instead)
- Frontend result page changes
- `get_chunks_for_documents(ids[])` batch method on `DocumentRepository` — single-doc fetch per task is one query, acceptable
