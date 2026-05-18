# Doc Intelligence

AI-powered CRE underwriting for real estate teams.
Extract deal data, analyze assumptions, and generate underwriting outputs in minutes.

## Features

- **Smart Extraction** — PDFs & Excel → structured JSON/Excel output
- **AI Chat** — Ask questions across your document library
- **PE Workflows** — Investment memos, red flags, deal screening
- **RE Workflows** — Underwriting, property analysis, template fill
- **Closed beta** — Real Estate vertical open to invited users; PE access granted by admin

## Architecture

| Layer | Technology | Host |
|-------|------------|------|
| Frontend | React + Vite + shadcn/ui + Tailwind | Vercel |
| Backend | FastAPI + Python 3.11 (Docker) | Railway |
| Database | PostgreSQL + pgvector | Supabase |
| Auth | WorkOS AuthKit | — |
| AI | Anthropic Claude (claude-sonnet-4-6) | — |

## Local Development

### Backend
```bash
cd backend
pip install -r requirements.txt
# Set env vars (see below)
uvicorn main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Environment Variables

### Backend
| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `WORKOS_CLIENT_ID` | Yes | WorkOS client ID |
| `WORKOS_API_KEY` | Yes | WorkOS API key |
| `SUPABASE_DATABASE_URL` | Yes | Supabase Supavisor pooler URL (**not** `DATABASE_URL` — Railway reserves that name for its own managed DB) |
| `NOTIFICATION_EMAIL` | No | Gmail address to receive new signup notifications |
| `GMAIL_APP_PASSWORD` | No | Gmail app password for signup notifications |
| `AZURE_DOC_INTEL_KEY` | No | Azure Document Intelligence OCR key |
| `AZURE_DOC_INTEL_ENDPOINT` | No | Azure Document Intelligence endpoint URL |

### Frontend
| Variable | Description |
|---|---|
| `VITE_API_URL` | Backend URL (Railway service URL) |
| `VITE_WORKOS_CLIENT_ID` | WorkOS client ID (for AuthKit) |

## Access Control

New users who sign up immediately receive **active** status with **Real Estate** vertical access — no approval step required. The admin receives an email notification on each new sign-up.

**Vertical access** is controlled per-user via the `allowed_verticals` JSONB column:
- New sign-ups: `["real_estate"]`
- To grant PE access: update via `PATCH /api/admin/users/{user_id}/limits` or directly in the DB

**Admin API** (requires admin tier):

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/admin/pending-users` | List users with pending_approval status |
| `POST` | `/api/admin/activate-user` | Manually activate a user by ID |
| `PATCH` | `/api/admin/users/{user_id}/limits` | Update a user's limits and vertical access |

## Deployment

### 1. Database (Supabase)
1. Create a Supabase project and note the connection strings
2. Run migrations from `backend/`: `alembic upgrade head`
3. Use the **Supavisor (pooler)** connection string for `SUPABASE_DATABASE_URL` — not the direct connection — to avoid Railway IPv6 routing issues

### 2. Backend (Railway)
1. Connect GitHub repo → set root directory to `/backend`
2. Set all backend env vars (especially `SUPABASE_DATABASE_URL` — not `DATABASE_URL`)
3. Railway auto-deploys on push to `main`

### 3. Frontend (Vercel)
1. Connect GitHub repo → set root directory to `/frontend`
2. Set `VITE_API_URL` and `VITE_CLERK_PUBLISHABLE_KEY` env vars
3. Add Vercel domain to:
   - WorkOS Dashboard → redirect URIs
   - Railway env var `CORS_ORIGINS`

## Status

Active Development — MVP deployed
