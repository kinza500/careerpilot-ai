# Deployment

Two supported targets: **local** (Docker Compose, one command) and **managed**
(Vercel + Render + Supabase) for a public live URL.

---

## A. Local — Docker Compose

Prerequisites: Docker + Docker Compose.

```bash
# 1. configure the backend
cp backend/.env.example backend/.env

# 2. generate the two required secrets and paste them into backend/.env
python -c "from cryptography.fernet import Fernet; print('CV_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(48))"
# also set OPENAI_API_KEY=... (or LLM_PROVIDER=ollama)
# optional: TAVILY_API_KEY=... enables live company research (degrades gracefully without it)
# optional: JOOBLE_API_KEY=... / SERPAPI_KEY=... add supplemental job sources
# required for Gmail draft/send-detection/reply-detection/calendar features:
#   GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET (see "Google OAuth setup" below)

# 3. bring the whole stack up
docker compose up --build
```

- Frontend: http://localhost:3000
- API + docs: http://localhost:8000/docs
- The schema and RLS policies are applied automatically on first boot from
  `backend/sql/001_init.sql`.

Fully-local / no external API: uncomment the Ollama lines in `.env`, add an
`ollama` service, and set `LLM_PROVIDER=ollama`. No CV text then leaves your box.

---

## Google OAuth setup (Gmail + Calendar features)

1. In [Google Cloud Console](https://console.cloud.google.com), create a
   project → **APIs & Services → Credentials** → create an **OAuth 2.0 Client
   ID** (Web application).
2. Add an **Authorized redirect URI** matching `GOOGLE_REDIRECT_URI` (e.g.
   `http://localhost:8000/auth/google/callback` for local, or your deployed
   API's `/auth/google/callback` for a live URL).
3. Enable the **Gmail API** and **Google Calendar API** for the project.
4. On the **OAuth consent screen**, the app requests `gmail.compose`,
   `gmail.readonly`, and `calendar.events` — Google classifies these as
   sensitive/restricted scopes.

**Two ways to run this, depending on your goal:**

- **Testing mode (no verification needed)** — add each real user's Google
  account under **Test users** (cap: 100). Fast to set up, but refresh tokens
  expire after **7 days** for unverified apps, so users must reconnect Gmail
  weekly. Fine for a demo, presentation, or small closed group.
- **Published + verified** — required for public signup with persistent
  (non-expiring) Gmail access. Basic verification takes roughly a few days to
  a couple of weeks; because Gmail scopes are *restricted* (not just
  sensitive), Google also requires an additional security assessment (CASA),
  which realistically adds **weeks to a couple of months** depending on your
  usage tier. Budget for this early if a public launch is the goal — see
  [`docs/SECURITY.md`](SECURITY.md) for what scopes are requested and why.

---

## B. Managed — live URL (Vercel + Render + Supabase)

### 1. Database — Supabase
1. Create a project. In the SQL editor, paste and run
   `backend/sql/001_init.sql`. (Supabase Postgres already has `pgvector`.)
2. Grab the **connection string** (use the pooler for serverless). Convert it to
   the asyncpg scheme for the backend:
   `postgresql+asyncpg://USER:PASSWORD@HOST:PORT/postgres`.

### 2. Redis — Upstash
Create a free Redis DB and copy its URL → `REDIS_URL`.

### 3. Backend + worker — Render
1. Push this repo to GitHub.
2. In Render, **New → Blueprint**, point at `render.yaml`.
3. Fill the `sync:false` secrets: `DATABASE_URL`, `CV_ENCRYPTION_KEY`,
   `OPENAI_API_KEY`, `TAVILY_API_KEY` (optional), `JOOBLE_API_KEY` /
   `SERPAPI_KEY` (optional), `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` /
   `GOOGLE_REDIRECT_URI` (for Gmail/Calendar — see "Google OAuth setup"
   above), `REDIS_URL`, `FRONTEND_ORIGIN` (your Vercel URL).
4. Deploy. Note the API URL, e.g. `https://careerpilot-api.onrender.com`, and
   update `GOOGLE_REDIRECT_URI` (both here and in Google Cloud Console) to
   point at this live domain's `/auth/google/callback`.

> Free Render services sleep after ~15 min idle (30–60 s cold start). Warm the
> service manually before a demo — do **not** self-ping, which can trigger
> suspension.

### 4. Frontend — Vercel
1. **New Project** → import the repo → set **Root Directory** to `frontend`.
2. Env var: `NEXT_PUBLIC_API_URL = https://careerpilot-api.onrender.com`.
3. Deploy. Then set the backend's `FRONTEND_ORIGIN` to the Vercel URL and
   redeploy the backend so CORS matches.

### 5. Verify
- `GET https://<api>/health` → `{"status":"ok"}`
- Open the Vercel URL, register, upload a resume, search, prepare an application.
- Connect Gmail (top right) and confirm the status badge shows no "limited
  permissions" warning — if it does, a required scope wasn't granted; click
  reconnect. Test drafting an application and confirm the Gmail draft appears
  with the expected attachments.

---

## CI
`.github/workflows/ci.yml` compiles the backend and builds the frontend on every
push/PR. Extend it with `pytest` and Vercel/Render deploy hooks as needed.
