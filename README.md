# Money Clarity OS

Personal finance dashboard with secure multi-user support, Gmail OAuth, and persistent storage.

**Stack:** Streamlit UI → FastAPI backend → Supabase (Postgres + Storage + Auth)

---

## Table of Contents

1. [Architecture](#architecture)
2. [Quick Start — Local Development](#quick-start--local-development)
3. [Supabase Setup](#supabase-setup)
4. [Google OAuth Setup](#google-oauth-setup)
5. [Environment Variables](#environment-variables)
6. [Database Migrations](#database-migrations)
7. [Running Tests](#running-tests)
8. [API Reference](#api-reference)
9. [Security & RLS Verification](#security--rls-verification)
10. [Deployment](#deployment)
11. [Key Rotation](#key-rotation)
12. [Manual QA Checklist](#manual-qa-checklist)
13. [Roadmap / Scalability Notes](#roadmap--scalability-notes)

---

## Architecture

```
Browser (Streamlit)
  │  auth: Supabase JWT (email OTP or Google OAuth)
  │  API calls: Authorization: Bearer <access_token>
  ▼
FastAPI backend  (/upload, /parse, /gmail/connect, /gmail/sync, /summary)
  │  JWT verification: HS256 with SUPABASE_JWT_SECRET
  │  Encryption: AES-256-GCM for files + Gmail tokens
  ▼
Supabase
  ├── Auth         — identity provider (Google + email OTP)
  ├── Postgres     — statements, monthly_summaries, uploads, gmail_accounts
  │   └── RLS      — auth.uid() = user_id on all tables
  ├── Storage      — encrypted raw statement files
  └── Realtime     — optional: push summary updates to Streamlit
```

### Data flow: Upload → Parse → Summary

```
1. User uploads CSV/XLSX  →  POST /upload
     File bytes AES-256-GCM encrypted → Supabase Storage
     Upload record inserted into `uploads` table

2. Client calls POST /parse with upload_id
     File retrieved + decrypted from Storage
     Transactions parsed + categorized → inserted into `statements`
     DB trigger fires → `monthly_summaries` auto-updated

3. Any page load / login calls GET /summary
     Returns pre-aggregated monthly totals from `monthly_summaries`
     Data is there on every subsequent login — persistent, per-user
```

### Login / Logout

```
Login:
  User enters email → Supabase sends OTP → user enters code
  → Supabase returns session.access_token + refresh_token
  → Stored in st.session_state["sb_session"]
  → All FastAPI calls include Authorization: Bearer <access_token>

OR: Sign in with Google → Supabase handles OAuth → same result

Logout:
  supabase.auth.sign_out()  ← invalidates server-side session
  + st.session_state cleared ← clears client-side
  → User sees login page immediately
```

---

## Quick Start — Local Development

### Prerequisites

- Python 3.11+
- A Supabase project (free tier works)
- Google Cloud project with OAuth credentials

### 1. Clone and install

```bash
git clone <repo>
cd moneyclarity
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your real values (see sections below)

mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with Supabase public keys
```

### 3. Run migrations

```bash
psql $DATABASE_URL -f migrations/001_initial_schema.sql
psql $DATABASE_URL -f migrations/002_rls_policies.sql
psql $DATABASE_URL -f migrations/003_triggers.sql
```

Or paste each file into the Supabase Dashboard → SQL Editor.

### 4. Start the backend

```bash
uvicorn backend.main:app --reload --port 8000
```

### 5. Start Streamlit

```bash
streamlit run dashboard.py
```

Open http://localhost:8501 — you'll see the login page.

---

## Supabase Setup

1. **Create a project** at [supabase.com](https://supabase.com)

2. **Enable Google Auth provider**
   - Supabase Dashboard → Authentication → Providers → Google
   - Enter your Google Client ID and Client Secret
   - Copy the Callback URL shown (e.g. `https://xxx.supabase.co/auth/v1/callback`)
   - Add it as an Authorized Redirect URI in Google Console

3. **Create Storage bucket**
   - Dashboard → Storage → New bucket → name: `statements`
   - Set to **private** (not public)

4. **Copy credentials**
   - Dashboard → Project Settings → API
   - Copy: `Project URL`, `anon key`, `service_role key`, `JWT Secret`

5. **Set redirect URL** (for email OTP)
   - Dashboard → Authentication → URL Configuration
   - Site URL: `http://localhost:8501` (dev) or your production URL

---

## Google OAuth Setup

**For Gmail connect (server-side, `/gmail/connect`):**

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a project (or use existing)
3. Enable the **Gmail API**: APIs & Services → Library → Gmail API → Enable
4. Create OAuth credentials: Credentials → Create → OAuth Client ID → Web application
5. Add Authorized Redirect URI: `http://localhost:8000/gmail/callback`
6. Copy Client ID and Client Secret to `.env`

**Required scopes:**
- `https://www.googleapis.com/auth/gmail.readonly`
- `openid`
- `email`
- `profile`

**For Supabase Google login (user authentication):**

1. Use the same Google project
2. Add the Supabase callback URL as an Authorized Redirect URI:
   `https://YOUR_PROJECT_REF.supabase.co/auth/v1/callback`

---

## Environment Variables

| Variable | Where used | Description |
|---|---|---|
| `SUPABASE_URL` | backend + frontend | Your Supabase project URL |
| `SUPABASE_ANON_KEY` | frontend only | Public key, safe for client |
| `SUPABASE_SERVICE_ROLE_KEY` | backend only | **Never expose to browser** |
| `SUPABASE_JWT_SECRET` | backend only | From Settings → API → JWT Secret |
| `GOOGLE_CLIENT_ID` | backend | From Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | backend | From Google Cloud Console |
| `OAUTH_REDIRECT_URL` | backend | `http://localhost:8000/gmail/callback` |
| `ENCRYPTION_SECRET` | backend | Base64-encoded 32-byte key |
| `DATABASE_URL` | backend (optional) | Direct Postgres connection string |
| `ANTHROPIC_API_KEY` | frontend | For statement anonymizer |

Generate an encryption key:
```bash
python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

---

## Database Migrations

Apply in order:

```bash
# 1. Tables
psql $DATABASE_URL -f migrations/001_initial_schema.sql

# 2. Row Level Security policies
psql $DATABASE_URL -f migrations/002_rls_policies.sql

# 3. Monthly summary trigger
psql $DATABASE_URL -f migrations/003_triggers.sql
```

**Verify RLS is enabled:**
```sql
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
AND tablename IN ('uploads', 'statements', 'monthly_summaries', 'gmail_accounts');
-- All rows should show rowsecurity = true
```

---

## Running Tests

```bash
# All tests
pytest

# With coverage report
pytest --cov=backend --cov-report=html

# Specific test file
pytest tests/test_rls.py -v
```

The tests mock Supabase and Google API — no real credentials needed.

---

## API Reference

All endpoints (except `/health`) require:
```
Authorization: Bearer <supabase_access_token>
```

### `POST /upload`
Upload and encrypt a bank statement file.

```
Content-Type: multipart/form-data
Body: file (required), metadata (optional JSON string)

Response 200:
{
  "upload_id": "uuid",
  "storage_path": "user_id/upload_id/filename.csv",
  "status": "uploaded"
}
```

### `POST /parse`
Parse a previously uploaded file into transactions.

```
Content-Type: application/json
Body: {"upload_id": "uuid"}

Response 200:
{
  "upload_id": "uuid",
  "parsed_rows": 150,
  "inserted": 150,
  "month_range": ["2024-01", "2024-06"]
}
```

### `GET /gmail/connect`
Get Google OAuth URL.

```
Response 200:
{"auth_url": "https://accounts.google.com/o/oauth2/auth?..."}
```

### `GET /gmail/callback`
Called by Google after OAuth consent. Stores encrypted tokens.

```
Query: code=..., state=...
Response: HTML success page (closes itself)
```

### `GET /gmail/status`
```
Response 200:
{"connected": true, "gmail_user_id": "user@gmail.com", "last_synced_at": "2024-01-15T10:00:00Z"}
```

### `POST /gmail/sync`
Trigger Gmail sync.

```
Body (optional): {"since": "2024-01-01"}

Response 200:
{
  "status": "completed",
  "new_files": 3,
  "transactions_imported": 87,
  "errors": []
}
```

### `GET /summary`
Get monthly aggregates.

```
Query: ?month=2024-01 (optional)

Response 200:
[
  {
    "month": "2024-01",
    "income": 85000.0,
    "expense": 42000.0,
    "net": 43000.0,
    "categories": {
      "Food & Dining": 8500.0,
      "Transport": 3200.0
    }
  }
]
```

---

## Security & RLS Verification

### Confirm RLS blocks cross-user access

Test with two different JWTs in the Supabase SQL editor:

```sql
-- Set session as User A
SET request.jwt.claims = '{"sub": "user-a-uuid", "role": "authenticated"}';
SELECT * FROM statements;  -- Only User A's rows

-- Switch to User B
SET request.jwt.claims = '{"sub": "user-b-uuid", "role": "authenticated"}';
SELECT * FROM statements;  -- Only User B's rows (User A's are invisible)
```

### Verify encrypted storage

All files in Supabase Storage bucket `statements` are AES-256-GCM encrypted before upload. The stored content starts with `v1:` (key_id prefix). Downloading raw bytes from Storage returns ciphertext, not plaintext.

### Confirm clean logout

```python
# In Python / Streamlit:
supabase.auth.sign_out()
# ↑ This invalidates the refresh token server-side in Supabase Auth.
# The access_token will still be valid until its exp, but the refresh_token
# cannot produce new tokens. The user's session is effectively terminated.
```

---

## Deployment

### Railway (recommended for backend)

1. Create a new Railway project
2. Add service → Deploy from GitHub
3. Set `Start Command`: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
4. Add all environment variables from `.env` in Railway dashboard
5. Railway auto-assigns a URL — set `OAUTH_REDIRECT_URL` to `https://<railway-url>/gmail/callback`

### Render

1. New Web Service → connect GitHub repo
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables

### Fly.io

```bash
fly launch
fly secrets set SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... (all vars)
fly deploy
```

### Streamlit Cloud (frontend)

1. Push repo to GitHub
2. [share.streamlit.io](https://share.streamlit.io) → New app → select `dashboard.py`
3. Add secrets in Streamlit Cloud UI (same as `.streamlit/secrets.toml`)
4. Set `BACKEND_URL` to your Railway/Render/Fly URL

### Production checklist

- [ ] `ENVIRONMENT=production` set on backend
- [ ] `SUPABASE_SERVICE_ROLE_KEY` is NOT in any frontend env or Streamlit secrets
- [ ] `ENCRYPTION_SECRET` stored as a secret (not in repo)
- [ ] `OAUTH_REDIRECT_URL` matches the registered redirect URI in Google Console
- [ ] CORS origins updated to production Streamlit URL
- [ ] Supabase Storage bucket is private
- [ ] RLS verified (see above)

---

## Key Rotation

When rotating the `ENCRYPTION_SECRET`:

1. Generate new key:
   ```bash
   python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
   ```

2. Set both keys in env (old → new):
   ```
   ENCRYPTION_KEYS=v1:<old_b64_key>,v2:<new_b64_key>
   ENCRYPTION_SECRET=<new_b64_key>
   ```

3. Run the rotation script:
   ```bash
   python scripts/rotate_encryption_keys.py
   ```
   This re-encrypts all `gmail_accounts` tokens with the new key.

4. Once confirmed, remove the old key:
   ```
   ENCRYPTION_KEYS=v2:<new_b64_key>
   ```

---

## Manual QA Checklist

### Authentication
- [ ] Sign in with email OTP — magic link arrives, 6-digit code works
- [ ] Sign in with Google — redirects to Google, returns to app logged in
- [ ] Sign out — returns to login page, session cleared
- [ ] Refresh page while logged in — stays logged in (session persists)
- [ ] Expired token — automatic refresh or graceful logout

### Upload & Parse
- [ ] Upload CSV statement — success message, upload_id returned
- [ ] Upload XLSX statement — parses correctly
- [ ] Upload invalid file type — 400 error shown
- [ ] Parse endpoint — transactions appear in Supabase `statements` table
- [ ] `monthly_summaries` table updated automatically (trigger fires)
- [ ] Log out and log back in — `/summary` returns previously uploaded data

### Gmail Integration
- [ ] Click "Connect Gmail" — redirects to Google consent screen
- [ ] Authorize — success page shown, returns to app
- [ ] `/gmail/status` shows `connected: true`
- [ ] `/gmail/sync` — fetches attachments, imports transactions
- [ ] Log out and log back in — Gmail still connected, data persists

### RLS
- [ ] Create two test users in Supabase
- [ ] Upload statement as User A
- [ ] Log in as User B — `/summary` returns empty (User A's data not visible)

### Data Persistence
- [ ] Upload data → log out → log back in → `/summary` shows same data
- [ ] Gmail sync → log out → log back in → synced transactions visible

---

## Roadmap / Scalability Notes

| Feature | MVP (current) | Scale path |
|---|---|---|
| Background sync | FastAPI BackgroundTasks (in-process) | Celery + Redis worker |
| Encryption key storage | Env var | AWS KMS / GCP KMS |
| DB access | Supabase REST (supabase-py) | asyncpg direct connection |
| Realtime updates | Poll on page load | Supabase Realtime subscription |
| Rate limiting | None | Upstash Redis rate limiter |
| Gmail sync schedule | Manual trigger | Celery Beat nightly cron |

### Enable Supabase Realtime (optional)

```sql
-- Run in Supabase SQL Editor
ALTER PUBLICATION supabase_realtime ADD TABLE monthly_summaries;
```

Then in Streamlit:
```python
supabase.realtime.channel("summaries") \
    .on("postgres_changes", {"event": "UPDATE", "schema": "public", "table": "monthly_summaries"},
        lambda payload: st.rerun()) \
    .subscribe()
```
