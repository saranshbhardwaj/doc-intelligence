# Doc Intelligence — promptfoo Evals

Evaluates the LLM stages of the template fill pipeline and RAG chat.
Test fixtures are exported from real runs stored in the database.

---

## Setup

```bash
npm install -g promptfoo
# or run without installing:
npx promptfoo eval
```

Set your API key (same one the backend uses):
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

---

## Provider Architecture

| Provider | Label | What it tests |
|----------|-------|---------------|
| `providers/extract_schema_fields.py` | `haiku-e2e-schema` | Schema field extraction (template fill) |
| `providers/extract_table_values.py` | `haiku-e2e-tables` | Table value extraction (template fill) |
| `providers/rag_chat.py` | `haiku-rag` | RAG generation — replays stored prompts, returns `{text, context}` |
| `providers/rag_retrieval.py` | `haiku-retrieval` | RAG retrieval — calls real pipeline, checks page recall |
| `providers/rag_comparison.py` | `haiku-rag-comparison` | Comparison generation — replays stored comparison prompts and derives judge context from the prompt itself |

**Why separate retrieval and generation evals?**
If retrieval degrades, generation metrics drop too — but you can't tell which broke.
Testing independently pinpoints the failure: `rag_retrieval` catches retrieval regressions,
`rag_generation` catches prompt/model regressions.

**Why custom Python providers instead of promptfoo's built-in Anthropic provider?**
- Anthropic requires streaming when `max_tokens > ~21k` — built-in provider would fail
- Schema/table providers use structured output (`output_format`) — requires custom parsing
- `rag_retrieval` calls the actual DB/vector pipeline, not an LLM

**Provider routing**: Each test case JSONL includes `"providers": ["label"]` so
promptfoo routes it to the correct provider — no cross-product between stages.

---

## Workflow

### Template Fill (extract_schema_fields, extract_table_values)

These have golden datasets already committed. Run immediately:

```bash
cd evals
npx promptfoo eval
```

### RAG Chat Eval (rag_generation + rag_retrieval + rag_comparison)

**Step 1 — Enable IO capture**

```bash
# In backend/.env or docker-compose env:
CAPTURE_LLM_IO_LOG=true
# Restart the API service
```

Fresh RAG golden exports should be captured after this implementation is deployed.
The exporter now skips older rows that do not include the current versioned RAG eval contract.

**Step 2 — Produce real data**

Open the app and use it normally with `CAPTURE_LLM_IO_LOG=true`:
- **Regular chat**: ask 3-5 factual questions about a document (note the session_id from the URL or DB)
- **Comparison chat**: compare 2 documents on a specific topic

Find the session_id:
```sql
SELECT metadata->>'session_id', COUNT(*) FROM llm_io_logs
WHERE stage IN ('rag_chat', 'rag_chat_comparison')
GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
```

**Step 3 — Export golden fixtures by session**

```bash
cd backend

# Generation eval (replays LLM call, checks faithfulness + citations)
python -m scripts.export_eval_dataset \
  --stage rag_generation \
  --session-id <UUID> \
  --golden \
  --output ../evals/datasets/golden/rag-chat

# Retrieval eval (calls real pipeline, checks page recall)
python -m scripts.export_eval_dataset \
  --stage rag_retrieval \
  --session-id <UUID> \
  --golden \
  --output ../evals/datasets/golden/rag-chat

# Comparison eval (replays comparison prompt, checks multi-doc coverage)
python -m scripts.export_eval_dataset \
  --stage rag_comparison \
  --session-id <UUID> \
  --golden \
  --output ../evals/datasets/golden/rag-chat
```

`--session-id` exports all QA pairs from that session — use instead of `--limit N`
so the golden set is curated by session, not random recency.
If a session contains rows with missing prompt-visible context or missing eval metadata,
those rows are skipped instead of being exported as weak golden fixtures.

**Step 4 — Activate in config**

Uncomment in `promptfooconfig.yaml`:
```yaml
tests:
  - datasets/golden/rag-chat/rag_generation.jsonl
  - datasets/golden/rag-chat/rag_retrieval.jsonl
  - datasets/golden/rag-chat/rag_comparison.jsonl
```

**Step 5 — Run**

```bash
cd evals
npx promptfoo eval
npx promptfoo view
```

### Retrieval Study: A0-A6 Switch Surface

`providers/rag_retrieval.py` accepts an optional `ablation_id` test var.
If omitted, it defaults to `A6` and runs the full production-style retrieval path.

Use these exact IDs in promptfoo dataset vars:

| `ablation_id` | System | Enabled | Disabled |
|---------------|--------|---------|----------|
| `A0` | Dense baseline | semantic retrieval only | keyword retrieval, phrase constraints, reranker, structured bypass, scope routing, guardrail |
| `A1` | Hybrid baseline | semantic + keyword + RRF | phrase constraints, structured bypass, scope routing, guardrail |
| `A2` | Hybrid + generic rerank | A1 + rerank all chunks | phrase constraints, structured bypass, scope routing, guardrail |
| `A3` | Hybrid + phrase-aware retrieval | A2 + `RetrievalQuery` lexical required and optional constraints | structured bypass, scope routing, guardrail |
| `A4` | Hybrid + selective reranking | A3 + structured bypass for BM25-matched table and key-value chunks | scope routing, guardrail |
| `A5` | A4 + scope-aware retrieval | A4 + document-scoped routing for named-entity queries | guardrail |
| `A6` | Full system | A5 + guardrail regeneration + confidence-aware reranker skip | nothing |

The retrieval provider consumes these dataset vars for research runs:

| Var | Required | Meaning |
|-----|----------|---------|
| `user_question` | yes | Raw user query |
| `document_ids` | yes if no `collection_id` | JSON array of candidate document UUIDs |
| `collection_id` | yes if no `document_ids` | Collection scope fallback |
| `query_understanding` | strongly recommended | Serialized production `QueryUnderstanding`; required for non-`A6` ablations on exported fixtures |
| `expected_pages` | yes for golden retrieval evals | JSON array of gold `{document_id, page}` pairs |
| `ablation_id` | no | One of `A0` through `A6`; defaults to `A6` |

Example retrieval test vars:

```json
{
  "user_question": "What is the 2024 property tax for Point Blank Portfolio?",
  "document_ids": "[\"110bce13-325a-4b56-8b2c-6d0cec61a23c\"]",
  "collection_id": "",
  "query_understanding": "{\"query_type\":\"data_extraction\",\"data_fields\":[\"property tax\"],\"scope_mode\":\"single_doc\",\"target_property_names\":[\"Point Blank Portfolio\"]}",
  "expected_pages": "[{\"document_id\":\"110bce13-325a-4b56-8b2c-6d0cec61a23c\",\"page\":18}]",
  "ablation_id": "A4"
}
```

For a reproducible A0-A6 sweep, export one golden retrieval dataset once, then run the same fixture set seven times with `ablation_id` changed per run.

### Benchmark Annotations

The exporter still accepts the legacy flat file in `annotations/rag-chat.json`, but it also accepts the structured benchmark schema in `annotations/rag-benchmark.schema.json`.
When a structured annotation is present, the exporter copies these promptfoo vars into retrieval and generation fixtures:

| Var | Meaning |
|-----|---------|
| `benchmark_question_id` | Stable benchmark row id |
| `benchmark_eval_slice` | One of `table_factual`, `narrative`, `entity_scoped`, `ambiguous_multi_doc` |
| `benchmark_scope_type` | Scope label for slice analysis |
| `benchmark_table_heavy` | JSON boolean for the table-heavy subset |
| `benchmark_target_entities` | JSON array of target entity names |
| `benchmark_target_document_ids` | JSON array of in-scope document ids |
| `benchmark_expected_answer_substrings` | JSON array of accepted answer surface forms |
| `benchmark_gold_evidence` | JSON array of gold evidence objects |
| `benchmark_numeric_targets` | JSON array of canonical numeric targets |
| `benchmark_table_labels` | JSON array of referenced table labels |

That gives you one exported dataset carrying both promptfoo assertions and the research metadata needed for Page Recall@K, Table Recall@K, Numeric Exact Match, Phrase Match Preservation Rate, Scope Error Rate, and table-heavy subset reporting.

Schema and example files:

- `annotations/rag-benchmark.schema.json`
- `annotations/rag-benchmark.sample.json`

---

## Regression Testing: Prompt Changes

Use this workflow before and after editing any prompt in `template_filling/prompts/`.

```bash
# 1. Save current baseline BEFORE making any changes
cd evals
npx promptfoo eval --output results/v1_baseline.json

# 2. Edit prompt (e.g. prompts/v1.py) or create prompts/v2.py

# 3. If you changed v1 in-place, just re-run and compare:
npx promptfoo eval --output results/v1_after.json
npx promptfoo view
# Both runs appear in the UI — compare pass rates, costs, values.

# 4. If you created a new version (v2.py), re-export with that version:
cd backend
python -m scripts.export_eval_dataset --golden --version v2 \
  --output ../evals/datasets/golden_v2

cd evals
npx promptfoo eval --tests datasets/golden_v2/extract_schema_fields.jsonl \
  --output results/v2.json
npx promptfoo view
```

Golden assertions fail if:
- `total_found` drops (fewer fields extracted = regression)
- A previously correct field value changes
- A previously correct table cell value changes
- RAG response fails the factual grounding rubric

---

## Prompt Comparison (Two Providers Side-by-Side)

To compare two prompt versions on the same test cases, register both as providers
in `promptfooconfig.yaml` (each with a different label) and remove the `providers`
filter from the test case JSONL so promptfoo runs both:

```yaml
providers:
  - id: file://providers/extract_schema_fields.py
    label: haiku-e2e-schema-v1
  - id: file://providers/extract_schema_fields.py
    label: haiku-e2e-schema-v2
```

Then set the `PROMPT_VERSION` env var (or a custom var) inside each provider
to select which prompt set to load. `npx promptfoo view` renders both side-by-side.

---

## Diagnosing Low Field Coverage

When fewer fields are mapped than expected, use the diagnostic script:

```bash
cd backend
python -m scripts.analyze_fill_coverage --fill-run-id <uuid>
```

Output groups the 235 YAML schema fields into:

| Status | Meaning |
|--------|---------|
| `ALIAS_MATCH` | Filled by deterministic alias matching (Stage 1, no LLM) |
| `FOUND` | LLM extracted a non-null value |
| `NULL` | LLM looked but value is genuinely absent from PDF |
| `NOT_SENT` | Never included in an LLM request — routing/batching gap (bug!) |

For a machine-readable JSON report:
```bash
python -m scripts.analyze_fill_coverage --fill-run-id <uuid> --json > report.json
```

---

## Files

| File | Purpose |
|------|---------|
| `promptfooconfig.yaml` | Main config — providers, prompts, tests list |
| `providers/extract_schema_fields.py` | Template fill: schema field extraction (streaming + structured output) |
| `providers/extract_table_values.py` | Template fill: table value extraction (streaming, JSON output) |
| `providers/rag_chat.py` | RAG generation: replays stored prompts, returns `{text, context}` |
| `providers/rag_retrieval.py` | RAG retrieval: calls real hybrid retrieval + reranker pipeline |
| `providers/rag_comparison.py` | RAG comparison: replays stored comparison prompts |
| `.gitignore` | Ignores `datasets/` but tracks `datasets/golden/` |
| `datasets/golden/` | Committed regression baselines (JSONL, one file per stage) |
| `datasets/` | Generated fixtures from latest runs (gitignored) |
| `results/` | Saved eval results for comparison (gitignored) |

---

## Assertions Reference

| Assertion | Stage | What it checks |
|-----------|-------|---------------|
| `is-json` | all structured | Output is valid JSON |
| `javascript: results !== undefined` | all structured | Structural shape present |
| `javascript: total_found >= N` | schema fields | **Golden**: field count floor (finding more is OK, fewer = regression) |
| `javascript: coverage_rate_90pct` | schema fields | **Golden**: at least 90% of reference count extracted |
| `javascript: field_id === value` | schema fields | **Golden**: specific field value unchanged |
| `javascript: table_rows >= N` | tables | **Golden**: row count floor per table |
| `javascript: table_cells_filled >= N` | tables | **Golden**: filled cell count floor per table |
| `javascript: String(r.values[col]) === val` | tables | **Golden**: specific cell value (String() coerces number → string) |
| `javascript: JSON.parse(output).chunk_count >= 1` | rag_retrieval | Retrieved at least one chunk |
| `retrieval/page_recall_80` | rag_retrieval | **Golden**: ≥80% of golden page+doc pairs appear in results (stable across re-indexing) |
| `javascript: JSON.parse(output).text.length > 50` | rag_generation | Response is non-trivial |
| `javascript: /\[D\d+:p\d+\]/.test(...)` | rag_generation | Response contains at least one citation |
| `context-faithfulness` | rag_generation / rag_comparison | LLM response is grounded in provided context |
| `answer-relevance` | rag_generation / rag_comparison | Response addresses the question |
| `llm-rubric` | rag_generation | **Golden**: factually grounded, cites, no hallucinations |
| `comparison/multi_doc_reference` | rag_comparison | References Document A/B or [D1/D2] |
| `comparison/structured_output` | rag_comparison | Contains table, bullets, or headers |
| `llm-rubric` | rag_comparison | **Golden**: balanced coverage of both docs, no hallucination |
| `cost < 0.10` | all | Per-call cost guard (Haiku pricing) |
| `latency < 30000` | all | Per-call latency guard (30 s) |

### Judge LLM (context-faithfulness, answer-relevance, llm-rubric)

`context-faithfulness`, `answer-relevance`, and `llm-rubric` all require a judge LLM.
The default config now uses Claude Haiku as the judge so the eval stack can run off the same Anthropic credentials as the backend. For stricter golden promotion, you can override it with a stronger judge model:
```yaml
evaluateOptions:
  rubricModel: "anthropic:claude-sonnet-4-5-20250929"
```
If you prefer OpenAI for judging, set `OPENAI_API_KEY` in `evals/.env` and swap the rubric model.

### context-faithfulness with {text, context} output

The `rag_generation` and `rag_comparison` providers return JSON `{"text": ..., "context": ...}`.
promptfoo reads `vars.context` for context-based metrics. The `transform` in `defaultTest`
strips markdown fences from JSON output — harmless on prose text since the regex won't match.
For both RAG providers, `context` should come from the stored prompt, not from metadata snapshots.
