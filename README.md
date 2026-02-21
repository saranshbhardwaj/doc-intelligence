# Doc Intelligence

AI-powered document intelligence for Private Equity and Real Estate.
Extract structured data, run AI workflows, and generate deal documents — in minutes.

## Features

- **Smart Extraction** — PDFs & Excel → structured JSON/Excel output
- **AI Chat** — Ask questions across your document library
- **PE Workflows** — Investment memos, red flags, deal screening
- **RE Workflows** — Underwriting, property analysis, template fill
- **Invite-only access** — Controlled rollout with admin allowlist

## Architecture

| Layer | Technology | Host |
|-------|------------|------|
| Frontend | React + Vite + shadcn/ui + Tailwind | Vercel |
| Backend | FastAPI + Python 3.11 (Docker) | Railway |
| Database | PostgreSQL + pgvector | Supabase |
| Auth | Clerk | — |
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
| `CLERK_SECRET_KEY` | Yes | Clerk backend secret |
| `SUPABASE_DATABASE_URL` | Yes | Supabase Supavisor pooler URL (**not** `DATABASE_URL` — Railway reserves that name for its own managed DB) |
| `ADMIN_API_KEY` | Yes | Secret for admin-only endpoints |
| `AZURE_DOC_INTEL_KEY` | No | Azure Document Intelligence OCR key |
| `AZURE_DOC_INTEL_ENDPOINT` | No | Azure Document Intelligence endpoint URL |

### Frontend
| Variable | Description |
|---|---|
| `VITE_API_URL` | Backend URL (Railway service URL) |
| `VITE_CLERK_PUBLISHABLE_KEY` | Clerk publishable key |

## Access Control (Invite-Only)

New signups start with `status = "pending_approval"` and see an "Access Pending" page until approved.
Only emails in the `allowed_emails` table are automatically activated on signup.

**Seed your email after running migrations:**
```sql
INSERT INTO allowed_emails (id, email)
VALUES (gen_random_uuid()::text, 'you@example.com');
```

**Admin API** (requires `X-Admin-Key` header):

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/admin/allowed-emails` | List all allowed emails |
| `POST` | `/api/admin/allowed-emails` | Add emails (also activates existing users) |
| `DELETE` | `/api/admin/allowed-emails/{email}` | Remove an email |
| `GET` | `/api/admin/pending-users` | List users awaiting approval |
| `POST` | `/api/admin/activate-user` | Manually activate a user by ID |

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
   - Clerk Dashboard → allowed origins
   - Railway env var `CORS_ORIGINS`

## Status

Active Development — MVP deployed
