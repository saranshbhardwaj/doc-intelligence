# Doc Intelligence — Claude Reference

## Overview
Financial document RAG platform for private equity and real estate.
- **PE vertical**: CIM extraction, investment memo analysis, multi-doc comparison workflows
- **RE vertical**: Excel template filling from PDF documents (rent rolls, appraisals)

Deployed on **Railway** (API + workers). Local dev via Docker Compose.

---

## Repository Layout
```
/
├── backend/
│   ├── app/
│   │   ├── api/             # FastAPI route handlers
│   │   ├── core/            # Embedding, parsing, RAG, LLM
│   │   ├── repositories/    # Data access layer (12 repos)
│   │   ├── schemas/         # Pydantic models
│   │   ├── services/        # Job tracker, pub/sub, beta limits
│   │   ├── utils/           # Logging, metrics, notifications
│   │   ├── verticals/       # PE & RE vertical logic
│   │   ├── db_models*.py    # SQLAlchemy ORM models (7 files)
│   │   └── config.py        # All settings (env-driven, pydantic-settings)
│   ├── migrations/          # Alembic migrations
│   ├── scripts/             # One-time maintenance scripts
│   ├── docker-compose.yml
│   ├── Dockerfile           # API container
│   └── Dockerfile.worker    # Celery worker container
└── frontend/
    └── src/
        ├── api/             # Axios API clients (13 files)
        ├── components/      # Reusable UI (chat, pdf, workflows, shadcn/ui)
        ├── pages/           # Route-level pages
        ├── store/           # Zustand state (index.js + slices/)
        ├── utils/           # Frontend utilities
        └── verticals/       # PE & RE vertical UI
```

---

## Tech Stack
| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI (Python) |
| Task queue | Celery + Redis |
| Database | PostgreSQL + pgvector (local Docker, Supabase in prod) |
| Storage | Cloudflare R2 (S3-compatible) |
| Frontend | React + Vite (ports 5174) |
| Auth | WorkOS AuthKit (RS256 JWT, `PyJWT` + `PyJWKClient` on backend) |
| LLM | Anthropic Claude (via `llm_client.py`) |
| Embedding | OpenAI `text-embedding-3-small` (768d) |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` (CrossEncoder, ~1.5GB on API service) |
| Document parsing | Azure Document Intelligence only |
| Monitoring | Prometheus + Grafana |

---

## Docker Services (`backend/docker-compose.yml`)
| Container | Role |
|-----------|------|
| `docint-api` | FastAPI on port 8000 |
| `docint-worker1`, `docint-worker2` | Celery `critical` queue (workflows, extractions) |
| `docint-worker3` | Celery `default` queue (document indexing) |
| `docint-beat` | Celery Beat scheduler |
| `docint-postgres` | PostgreSQL + pgvector |
| `docint-redis` | Redis (broker + pub/sub) |
| `docint-prometheus` / `docint-grafana` | Monitoring |

**Run locally from `backend/`:**
```bash
docker compose up --build -d
docker compose exec api alembic upgrade head
# After embedding model change:
docker compose exec api python scripts/reembed_all_chunks.py
```

---

## Key Config (`backend/app/config.py`)
| Setting | Value | Notes |
|---------|-------|-------|
| `embedding_provider` | `"openai"` | Was `"sentence-transformer"` (removed Feb 2026) |
| `embedding_dimension` | `768` | Matryoshka reduction |
| `rag_reranker_model` | `"cross-encoder/ms-marco-MiniLM-L-6-v2"` | CrossEncoder, loads on API service (~1.5GB RAM) |
| `use_redis_cache` | `True` | Always Redis, never file cache |
| `cache_ttl` | `48` hours | Extraction result cache TTL |
| `max_pages_per_extraction` | `150` | Guard for extraction pipeline |
| `default_pages_limit` | `100` | Fallback if user.pages_limit is None |
| `chat_conversation_char_budget` | `15_000` | Triggers summarization when history exceeds this |
| `azure_doc_model` | `"prebuilt-layout"` | Azure DI model |

**Required env vars:**
- `OPENAI_API_KEY` — on both API and worker services
- `AZURE_DOC_INTELLIGENCE_API_KEY` + `AZURE_DOC_INTELLIGENCE_ENDPOINT`
- `SUPABASE_DATABASE_URL` — production only
- Workers: `USE_CELERY=true`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`

---

## Document Parsing
- **Only Azure Document Intelligence** — handles digital and scanned PDFs natively
- Removed Feb 2026: PyMuPDF (`pymupdf_parser.py`), Google Document AI (`google_documentai_parser.py`)
- No tier-based parser logic — all users use Azure DI
- Factory: `backend/app/core/parsers/parser_factory.py`

---

## Document Pipeline (Library Indexing)
```
Upload → Parse (Azure DI) → Chunk → Embed (OpenAI 768d) → Store (pgvector)
```
Celery chain on `default` queue (worker3):
```
parse_document_for_indexing_task
  → chunk_document_for_indexing_task
  → embed_chunks_task
  → store_vectors_task
```
File: `backend/app/services/tasks/document_processor.py`

> All RAG chat and workflows use documents **already indexed** in the Library.

---

## RAG / Chat Pipeline

### Core files
| File | Role |
|------|------|
| `backend/app/core/rag/rag_service.py` | Main orchestrator |
| `backend/app/core/rag/hybrid_retriever.py` | Semantic (pgvector) + keyword (FTS/BM25) search |
| `backend/app/core/rag/reranker.py` | CrossEncoder reranking |
| `backend/app/core/rag/prompt_builder.py` | Prompt assembly; `build_split()` for prompt caching |
| `backend/app/core/rag/memory.py` | Conversation history summarization |
| `backend/app/core/rag/comparison_retriever.py` | Multi-doc comparison retrieval |
| `backend/app/core/rag/comparison_flow.py` | Comparison chat flow |
| `backend/app/core/rag/workflow_retriever.py` | Workflow-specific retrieval |
| `backend/app/core/chat/llm_service.py` | Summarization, compression, key fact extraction |
| `backend/app/core/llm/llm_client.py` | Anthropic API wrapper |

### Flow
```
User message
  → Query understanding / enhancement
  → Hybrid retrieval (semantic + BM25)
  → CrossEncoder reranking (top-N per section, ms-marco-MiniLM)
  → Budget enforcement
  → Prompt builder → build_split() → (system_prompt, user_content)
  → LLM stream (system_prompt sent with cache_control: ephemeral for Anthropic prompt caching)
  → Persist message + citations
```

### Prompt caching
`llm_client.stream_chat(user_content, system_prompt=system_prompt)` sends the system prompt with `cache_control: {"type": "ephemeral"}` (Anthropic 5-min cache, ~10x cheaper cache hits).

### Chat summarization
Triggered when `len(conversation_history_chars) > chat_conversation_char_budget (15_000)`.
Implemented in `memory.py` → calls `llm_service.py` for summarization.
`stream_chat()` yields dicts `{"type": "chunk", "text": str}` | `{"type": "usage", "data": {...}}` — NOT raw strings.

---

## SSE / Real-Time Progress Pattern

Used for workflows, template fill runs, and document indexing.

### Flow
```
Celery task → JobProgressTracker → Redis Pub/Sub → SSE endpoint → Frontend EventSource
```

### Key files
| File | Role |
|------|------|
| `backend/app/services/job_tracker.py` | `JobProgressTracker` — throttled DB updates + SSE publish |
| `backend/app/services/pubsub.py` | Redis Pub/Sub wrapper |
| `backend/app/api/jobs.py` | `GET /api/jobs/{job_id}/stream` — SSE endpoint |
| `frontend/src/api/sse-utils.js` | Frontend EventSource wrapper with reconnection |

### JobProgressTracker behavior
- Throttles DB commits: 0.75s min interval + 3% progress delta
- Channel: `job:progress:<job_id>`
- Events: `progress`, `error`, `complete`, `end`
- **Always call `tracker.mark_error()` in every exception path** — otherwise frontend stays stuck in "processing" state
- Publish failures are logged (not silently swallowed) but don't break task logic

---

## Private Equity Vertical

### Structure
```
backend/app/verticals/private_equity/
├── api/               # extraction.py, workflows.py
├── extraction/        # tasks/tasks.py, llm_service.py, prompts.py
└── workflows/         # tasks/tasks.py, map_reduce.py
```

### Workflow pipeline (Celery `critical` queue)
1. `prepare_context_task` — Retrieves and ranks chunks per section
2. `generate_artifact_task` — Runs LLM to produce section summaries / metrics
3. `map_reduce.py` — Aggregates per-section results

> Both tasks call `tracker.mark_error()` in their exception handlers to ensure SSE error events propagate to frontend.

---

## Real Estate Vertical

### Structure
```
backend/app/verticals/real_estate/
├── api/templates.py             # Template CRUD + fill run management
└── template_filling/
    ├── tasks.py                 # Celery task chain
    ├── llm_service.py           # LLM prompting for field detection/mapping/extraction
    ├── excel_handler.py         # openpyxl read/write
    └── excel/mapping_coordinator.py
```

### Template fill pipeline
```
detect_fields_task          → LLM detects structured fields in PDF
auto_map_fields_task        → LLM maps PDF fields → Excel cells
extract_data_task           → LLM extracts values from PDF text
fill_excel_task             → openpyxl fills Excel with extracted values
```
Orchestrated by `start_fill_run_chain`.

### SSE for template fills
- `GET /api/templates/fill-runs/{fill_run_id}/progress` — SSE endpoint (same pub/sub pattern as workflows)
- Frontend: `streamTemplateFillProgress()` in `frontend/src/api/re-templates.js`
- Page: `frontend/src/verticals/real_estate/pages/TemplateFillPage.jsx`

---

## Frontend State (Zustand)

### Store structure (`frontend/src/store/`)
| Slice | File | Manages |
|-------|------|---------|
| Chat | `slices/chat/chatSlice.js` + action files | Sessions, messages, documents, comparisons |
| Extraction | `slices/extractionSlice.js` | PE extraction state |
| Workflow | `slices/workflowDraftSlice.js` | Workflow builder + execution + SSE |
| Template Fill | `slices/templateFillSlice.js` | Fill run data, PDF URL, cached workbook |
| User | `slices/userSlice.js` | User profile, dashboard data |
| Feedback | `slices/feedbackSlice.js` | Feedback modal |

**Selectors (index.js):**
- `useChatActions()` — all chat actions (must be explicitly listed in selector)
- `useTemplateFill()` / `useTemplateFillActions()`
- `useWorkflowDraft()` / `useWorkflowDraftActions()`

**Persistence:** `localStorage` key `"sand-cloud-storage"` — extraction IDs, drafts, indexing jobs.

---

## Frontend API Clients (`frontend/src/api/`)
| File | Covers |
|------|--------|
| `chat.js` | Chat, messages, sessions |
| `documents.js` | Document CRUD |
| `extraction.js` | Extraction API |
| `pe-workflows.js` | PE workflow APIs |
| `re-templates.js` | RE template APIs + SSE |
| `sse-utils.js` | SSE setup & reconnection |
| `users.js` | User endpoints |
| `client.js` | Axios instance (base URL, auth headers) |

---

## UI Conventions
- **Component library**: shadcn/ui (26 base components in `frontend/src/components/ui/`)
- **Styling**: Tailwind CSS with tokenized colors — always use semantic tokens, never raw hex or hardcoded color classes
  - Key tokens: `bg-background`, `bg-card`, `bg-muted`, `text-foreground`, `text-muted-foreground`
  - Error: `bg-destructive/10`, `border-destructive/30`, `text-destructive`
  - Success: `bg-green-500/10`, `text-green-600` (or `success` token)
  - Primary accent: `bg-primary/5`, `border-primary/20`, `text-primary`
- **Adding new color tokens**: Always follow this 3-step pattern:
  1. Define CSS variables in `frontend/src/index.css` under `:root {}` (light) and `.dark {}` using HSL components (no `hsl()` wrapper so opacity modifiers work)
  2. Register in `frontend/tailwind.config.js` under `theme.extend.colors` as `"hsl(var(--my-token))"`
  3. Use in components as `bg-my-token`, `text-my-token`, etc. — 
- **Error UI**: Inline error cards (shadcn `Alert` or custom div with `AlertCircle` icon), NOT browser `alert()`
- **Progress UI**: Inline progress with shadcn `Progress` component + status message
- **Icons**: lucide-react
- **Dark mode**: class-based (`darkMode: "class"` in tailwind config)
- **Whitespace**: Keep padding and margins minimal and compact. Avoid excessive vertical padding (e.g., `py-8`, `py-6` in small sections). Prefer `p-3`, `p-4`, `py-2`, `py-3` for compact UIs. Use `gap-2`, `gap-3` instead of `gap-4`, `gap-6` unless explicitly spacious design is requested.

---

## Database Migrations
Alembic migrations in `backend/migrations/versions/`.

Current head: `f3a4b5c6d7e8`
```
...→ a7fd572ad161 → b1c2d3e4f5a6 → c4d5e6f7a8b9 → d1e2f3a4b5c6 → e2f3a4b5c6d7 → f3a4b5c6d7e8 (HEAD)
```
- `a7fd572ad161`: Add beta limits & shadow credit lifecycle columns
- `b1c2d3e4f5a6`: Upgrade vector column 384d → 768d (Feb 2026)
- `c4d5e6f7a8b9`: Add PG tsvector trigger for hybrid FTS search; backfill (Feb 2026)
- `d1e2f3a4b5c6`: Fix job_states check constraint to include template_fill_run_id (Feb 2026)
- `e2f3a4b5c6d7`: Fix tsvector trigger function search_path (Supabase security lint)
- `f3a4b5c6d7e8`: Drop 9 duplicate ix_ indexes shadowing idx_ counterparts (Supabase perf lint)

> Switching embedding models requires: new migration (alter vector column) + `reembed_all_chunks.py`

---

## DB Models (`backend/app/`)
| File | Contains |
|------|---------|
| `db_models.py` | Core models (JobState, etc.) |
| `db_models_chat.py` | `DocumentChunk` (Vector(768)), `Message`, `ChatSession`, `Citation` |
| `db_models_documents.py` | Document metadata |
| `db_models_feedback.py` | Feedback |
| `db_models_templates.py` | Template definitions, fill runs |
| `db_models_users.py` | User profiles, permissions, beta limits |
| `db_models_workflows.py` | Workflow definitions, runs |

---

## Important File Paths (Quick Reference)
| File | Purpose |
|------|---------|
| `backend/app/config.py` | All settings |
| `backend/app/core/parsers/parser_factory.py` | Returns Azure DI parser |
| `backend/app/core/embeddings/factory.py` | Returns OpenAI embedding provider |
| `backend/app/core/embeddings/openai_provider.py` | 768d embedding implementation |
| `backend/app/core/llm/llm_client.py` | Anthropic streaming client (prompt caching support) |
| `backend/app/core/rag/rag_service.py` | Main RAG orchestrator |
| `backend/app/core/rag/prompt_builder.py` | `build_split()` for prompt caching |
| `backend/app/core/rag/memory.py` | Char-budget-based summarization |
| `backend/app/core/chat/llm_service.py` | Summarization helpers |
| `backend/app/services/job_tracker.py` | SSE progress tracker |
| `backend/app/services/pubsub.py` | Redis pub/sub |
| `backend/app/api/jobs.py` | SSE streaming endpoint |
| `backend/app/services/tasks/document_processor.py` | Library indexing Celery tasks |
| `backend/app/verticals/private_equity/workflows/tasks/tasks.py` | PE workflow Celery tasks |
| `backend/app/verticals/private_equity/extraction/tasks/tasks.py` | PE extraction Celery tasks |
| `backend/app/verticals/real_estate/template_filling/tasks.py` | RE template fill Celery tasks |
| `backend/scripts/reembed_all_chunks.py` | One-time re-embed script |
| `frontend/src/store/index.js` | Zustand store (all slices + selectors) |
| `frontend/src/api/sse-utils.js` | SSE EventSource wrapper |
| `frontend/src/pages/WorkflowSimplePage.jsx` | Workflow execution page |
| `frontend/src/verticals/real_estate/pages/TemplateFillPage.jsx` | Template fill page |

---

## Deployment (Railway)
- Separate Railway services: `api` + 3+ `worker` services
- Env vars per service in Railway dashboard
- `OPENAI_API_KEY` required on both API and worker services
- Database: Supabase (`SUPABASE_DATABASE_URL`)
- Workers: `USE_CELERY=true`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`

---

## Common Gotchas
- **Avoid N+1 DB/API patterns**: Never loop individual queries/API calls when a batch alternative exists. Use batch endpoints, JOINs, or `include_documents`-style flags. Example: `listCollections(getToken, { includeDocuments: true })` instead of listing then fetching each.
- **`stream_chat()` yields dicts**, not strings: `{"type": "chunk", "text": str}` or `{"type": "usage", "data": {...}}`. Always check `item["type"] == "chunk"` before appending.
- **Zustand selectors**: Actions must be **explicitly listed** in `useChatActions()` / other selectors in `store/index.js` to be accessible via `actions.*`.
- **SSE error propagation**: Every Celery task exception path must call `tracker.mark_error()` — otherwise frontend stays stuck in "processing" state indefinitely.
- **Reranker loads on the API service** (~1.5GB RAM): used for RAG/chat. worker-critical has reranking disabled (configurable via `config.py`). Config changes require API container restart.
- **Embedding model change**: Requires DB migration (alter vector column dimension) + full re-embed of all chunks via script.
- **Chat error display**: Error in `isProcessing` block disappears when processing stops — keep error state in separate block.
- **No `alert()`**: Always use inline shadcn error components.

## Important
- The code you write will be reviewed by Codex and senior engineer, so be mindful of it while designing and writring code.