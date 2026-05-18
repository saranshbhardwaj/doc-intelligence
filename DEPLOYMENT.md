# Deployment Guide

Production stack: **Vercel** (frontend) + **Railway** (API + workers) + **Supabase** (PostgreSQL) + **WorkOS** (auth).

---

## Services Overview

| Service | Platform | URL |
|---------|----------|-----|
| Frontend | Vercel | `https://www.LatticeBlu.com` |
| Backend API | Railway (`api` service) | Railway-generated URL |
| Celery Workers | Railway (`worker1`, `worker2`, `worker3`) | — |
| Database | Supabase PostgreSQL | — |
| Auth | WorkOS AuthKit | `https://dashboard.workos.com` |
| Notifications | Gmail SMTP (app password) | — |

---

## Environment Variables

### Railway — API service

| Variable | Notes |
|----------|-------|
| `SUPABASE_DATABASE_URL` | **Pooler URL** — port 6543. See gotchas below. |
| `WORKOS_CLIENT_ID` | From WorkOS dashboard → API Keys |
| `WORKOS_API_KEY` | From WorkOS dashboard → API Keys |
| `OPENAI_API_KEY` | Required on both API and workers |
| `ANTHROPIC_API_KEY` | Claude LLM |
| `AZURE_DOC_INTELLIGENCE_API_KEY` | Document parsing |
| `AZURE_DOC_INTELLIGENCE_ENDPOINT` | Document parsing |
| `CLOUDFLARE_R2_ACCOUNT_ID` | File storage |
| `CLOUDFLARE_R2_ACCESS_KEY_ID` | File storage |
| `CLOUDFLARE_R2_SECRET_ACCESS_KEY` | File storage |
| `CLOUDFLARE_R2_BUCKET_NAME` | File storage |
| `CELERY_BROKER_URL` | Redis URL |
| `CELERY_RESULT_BACKEND` | Redis URL |
| `GMAIL_SENDER` | e.g. `saranshbhardwaj@gmail.com` |
| `GMAIL_APP_PASSWORD` | Gmail app password (not account password) |
| `ADMIN_NOTIFICATION_EMAIL` | Where sign-up alerts go |
| `CORS_ORIGINS` | `https://www.LatticeBlu.com,https://LatticeBlu.com` |
| `PORT` | `8000` |

### Railway — Worker services (`worker1`, `worker2`, `worker3`)

Same as API, plus:

| Variable | Value |
|----------|-------|
| `USE_CELERY` | `true` |

### Vercel — Frontend

| Variable | Notes |
|----------|-------|
| `VITE_WORKOS_CLIENT_ID` | Same `client_01...` value as Railway `WORKOS_CLIENT_ID` |
| `VITE_API_BASE_URL` | Railway API public URL (e.g. `https://api.LatticeBlu.com`) |

---

## WorkOS Configuration

1. **Redirect URIs** (Authentication → Redirects):
   - `https://www.LatticeBlu.com/callback`
   - `https://LatticeBlu.com/callback`
   - `http://localhost:5174/callback` (local dev)

2. **CORS Allowed Origins** (Authentication → Sessions):
   - `https://www.LatticeBlu.com`
   - `https://LatticeBlu.com`
   - `http://localhost:5174`

3. **JWT Template** (Authentication → Sessions → JWT template):
   Must add these custom claims (claim namespace `urn:myapp:`):
   ```json
   {
     "urn:myapp:org_id": "{{organization.id}}",
     "urn:myapp:org_role": "{{organization_membership.role}}",
     "urn:myapp:email": "{{user.email}}"
   }
   ```
   Without this, the backend throws 401 "Could not extract org_id from token".

4. **Social Connections** (Google OAuth):
   - Configured under WorkOS → Social Connections → Google
   - Uses Google Cloud Console OAuth client ID + secret
   - This is for "Sign in with Google" — **not related to Gmail SMTP notifications**
   - Authorized redirect URI in Google Cloud Console: `https://auth.workos.com/sso/oauth2/callback`

---

## Supabase

**Connection strings** (Settings → Database):

- **Pooler URL** (port 6543) — use for `SUPABASE_DATABASE_URL` in Railway:
  ```
  postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
  ```
- **Direct URL** (port 5432) — use only for running Alembic migrations:
  ```
  postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres
  ```

---

## Running Migrations

Alembic migrations must use the **direct connection** (port 5432), not the pooler.

```bash
# From local machine with backend Docker running
SUPABASE_DATABASE_URL="postgresql://postgres.[ref]:[password]@[host]:5432/postgres" \
  docker compose exec api alembic upgrade head
```

Or via Railway CLI:
```bash
railway run --service api alembic upgrade head
```

---

## Admin Setup (first deploy or new environment)

After first login, grant your account admin access:

```sql
UPDATE users
SET tier = 'admin', pages_limit = 10000, allowed_verticals = '["real_estate", "private_equity"]'
WHERE email = 'saranshbhardwaj@gmail.com';
```

Admin tier bypasses all `require_vertical()` checks in the backend.

---

## Deploy Checklist

- [ ] Code pushed to `main` — Vercel and Railway auto-deploy
- [ ] Run `alembic upgrade head` if schema changed (use direct DB URL)
- [ ] `PORT=8000` set in Railway API service settings
- [ ] WorkOS redirect URIs include production domain
- [ ] WorkOS JWT template has `urn:myapp:org_id`, `urn:myapp:org_role`, `urn:myapp:email` claims
- [ ] `VITE_WORKOS_CLIENT_ID` in Vercel matches `WORKOS_CLIENT_ID` in Railway (same value)
- [ ] `SUPABASE_DATABASE_URL` in Railway uses pooler URL (port 6543), no `?pgbouncer=true`

---

## Known Gotchas

### Supabase connection
- Use port **6543** (pooler) in Railway — Railway has IPv6 routing issues with the direct connection
- Strip `?pgbouncer=true` from the URL — that parameter is Prisma-specific and breaks SQLAlchemy/psycopg

### Railway port
- Railway default health check port is 8080, but the app binds to 8000
- Must explicitly set `PORT=8000` in Railway service variables

### WorkOS — both www and non-www
- Add **both** `www.LatticeBlu.com` and `LatticeBlu.com` to WorkOS redirect URIs and CORS origins
- Vercel serves on `www` but redirects from bare domain — WorkOS sees the original domain

### Stale user rows (Clerk migration)
- If migrating from Clerk, old rows in the `users` table have Clerk user IDs
- WorkOS login with the same email will fail with a unique constraint violation (silent 500)
- Fix: delete the old row from Supabase, then log in again with WorkOS

### WorkOS — session persistence on page refresh (`devMode={true}`)
- Without a custom auth domain, WorkOS stores the refresh token **in memory only** in production. Memory is wiped on every page refresh → users get logged out.
- Fix: `devMode={true}` on `AuthKitProvider` in [frontend/src/main.jsx](frontend/src/main.jsx) — this stores the refresh token in `localStorage` instead, surviving refreshes.
- The proper long-term fix is a custom auth domain (`auth.LatticeBlu.com`) so WorkOS can set an httpOnly cookie on `.LatticeBlu.com`. WorkOS charges $99/month for custom domains — not worth it for early beta.
- `devMode={true}` is explicitly documented by WorkOS as the recommended approach without a custom domain.

### Gmail SMTP
- Uses Gmail app password — generate at Google Account → Security → App Passwords
- This is separate from Google OAuth (which is for "Sign in with Google" in WorkOS)
