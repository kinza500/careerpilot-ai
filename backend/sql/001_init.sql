-- CareerPilot AI — schema, pgvector, and Row-Level Security (RLS)
--
-- CONFIDENTIALITY MODEL
-- ---------------------
-- Every row that can contain candidate data carries a `user_id`. RLS policies
-- restrict every SELECT/INSERT/UPDATE/DELETE to rows where
--     user_id = current_setting('app.current_user_id')::uuid
-- The backend sets that GUC per-request (SET LOCAL app.current_user_id = ...)
-- inside the same transaction as the query, using the id from the verified JWT.
--
-- This is defence-in-depth: even if application code forgets a WHERE clause,
-- the database itself will not return another user's rows. Raw CV bytes are
-- additionally encrypted at rest by the application before they ever reach
-- `resumes.ciphertext`, so the DB never stores plaintext resumes.
--
-- Works identically on plain Postgres (docker-compose) and Supabase Postgres.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "vector";     -- pgvector
CREATE EXTENSION IF NOT EXISTS "citext";     -- case-insensitive email

-- Dedicated, NON-superuser role the API connects as. A superuser (or a role
-- with BYPASSRLS) would ignore RLS, defeating the whole model. In docker we
-- create this role; on Supabase use the anon/authenticated pattern instead.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'careerpilot_app') THEN
    CREATE ROLE careerpilot_app LOGIN PASSWORD 'app_pw_change_me' NOBYPASSRLS;
  END IF;
END$$;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         citext UNIQUE,          -- citext requires the citext ext; fallback below
    password_hash text        NOT NULL,
    full_name     text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    -- Gmail draft-creation integration (gmail.compose scope only). The refresh
    -- token is Fernet-encrypted by the app before it ever reaches this column,
    -- same treatment as resume ciphertext.
    google_refresh_token_enc bytea,
    google_email              text
);

-- Encrypted resume blobs. `ciphertext` is AES-GCM output produced by the app;
-- the DB never sees plaintext. `sha256` lets us dedupe without decrypting.
CREATE TABLE IF NOT EXISTS resumes (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename     text NOT NULL,
    mime_type    text NOT NULL,
    ciphertext   bytea NOT NULL,          -- encrypted original bytes
    sha256       text  NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- Structured, machine-readable skill profile (Resume Understanding Agent output).
CREATE TABLE IF NOT EXISTS skill_profiles (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    resume_id    uuid REFERENCES resumes(id) ON DELETE SET NULL,
    profile      jsonb NOT NULL,          -- {skills, experience, education, ...}
    embedding    vector(384),             -- all-MiniLM-L6-v2 dim; local & private
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- Discovered job listings, scoped per user (a user's search history is private).
CREATE TABLE IF NOT EXISTS jobs (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source       text,
    external_id  text,
    title        text NOT NULL,
    company      text,
    location     text,
    remote       boolean,
    salary       text,
    url          text,
    company_url  text,
    description  text,
    -- Only ever a real address JobSpy found written in the posting text
    -- itself (never invented) — most listings won't have one.
    contact_email text,
    embedding    vector(384),
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, source, external_id)
);

-- Ranked matches with explainable reasoning (Matching & Ranking Agent output).
CREATE TABLE IF NOT EXISTS matches (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id       uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    profile_id   uuid NOT NULL REFERENCES skill_profiles(id) ON DELETE CASCADE,
    score        double precision NOT NULL,
    reasoning    text,
    factors      jsonb,                   -- {skills, experience, salary, location, growth}
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, job_id, profile_id)
);

-- Application lifecycle. Nothing is ever "sent" without status flipping to
-- 'approved' via an explicit human-in-the-loop action.
CREATE TABLE IF NOT EXISTS applications (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id         uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    -- Which resume/profile version produced this application — a user may
    -- replace their resume many times, and past applications should keep
    -- pointing at the one actually used, not silently follow the latest.
    profile_id     uuid REFERENCES skill_profiles(id) ON DELETE SET NULL,
    status         text NOT NULL DEFAULT 'draft'
                     CHECK (status IN ('draft','review','approved','submitted','rejected')),
    tailored_resume text,
    cover_letter    text,
    outreach_email  text,
    critic_notes    jsonb,
    -- Company research brief (bullet points) shown to the user alongside the
    -- generated documents, so the effort behind the cover letter is visible
    -- rather than assumed. _grounded is false when Tavily was unavailable and
    -- the LLM had to write it without any real web search.
    company_research          text,
    company_research_grounded boolean NOT NULL DEFAULT false,
    -- [{"title": str, "url": str}, ...] — real URLs straight from Tavily's
    -- own results, never LLM-generated, so there's no risk of a hallucinated link.
    company_research_sources  jsonb,
    -- Gmail thread continuity: set when the application email is drafted via
    -- Gmail, so a later follow-up can reply into the same conversation
    -- instead of starting a new one.
    gmail_thread_id  text,
    gmail_message_id text,
    -- Detected via gmail.readonly — true once a SENT-labelled message shows
    -- up in gmail_thread_id, i.e. the user actually sent the draft
    -- themselves from Gmail. CareerPilot still never sends anything itself.
    email_sent boolean NOT NULL DEFAULT false,
    -- A reply landed on gmail_thread_id (INBOX label) — checked opportunistically
    -- for ANY application with a thread, not gated behind the 14-day follow-up
    -- wait like followup_status='responded' is, so the Applications list can
    -- reflect a reply the moment it actually arrives.
    reply_received boolean NOT NULL DEFAULT false,
    -- Suggested interview slot extracted from the reply's own text — only a
    -- suggestion; never written to the calendar until the user confirms it
    -- (see calendar_event_id). _checked prevents re-running the LLM
    -- extraction on every load once a reply has already been evaluated once.
    interview_schedule         jsonb,
    interview_schedule_checked boolean NOT NULL DEFAULT false,
    calendar_event_id          text,
    -- Follow-up: generated once 14 days pass with no response tracked;
    -- 'saved'/'drafted' once the user acts on the prompt, 'sent' once a
    -- gmail.readonly check confirms it was actually sent, 'responded' when a
    -- reply arrives — either way it's no longer re-surfaced every load.
    followup_email  text,
    followup_status text CHECK (followup_status IS NULL OR followup_status IN ('saved','drafted','sent','responded')),
    -- The follow-up's own thread (equals gmail_thread_id when threaded into
    -- the original, or a fresh thread otherwise) + how many SENT messages
    -- already existed in it when drafted — sent-detection looks for growth
    -- past this baseline, not just ">0", since the original may already be sent.
    followup_gmail_thread_id  text,
    followup_sent_baseline    integer NOT NULL DEFAULT 0,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, job_id)
);

-- Adaptive memory: liked/rejected/applied signals feed future ranking.
CREATE TABLE IF NOT EXISTS memory_events (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind         text NOT NULL,           -- liked | rejected | applied | preference
    payload      jsonb NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- Mock interview sessions — scoped to an application (not a bare job), so
-- each session can be grounded in the real job description, tailored resume,
-- and company research already gathered for that specific application.
CREATE TABLE IF NOT EXISTS interview_sessions (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    application_id uuid NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    status         text NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress','completed')),
    -- [{"role": "interviewer" | "candidate", "content": text}, ...] in order.
    transcript     jsonb NOT NULL DEFAULT '[]',
    feedback       jsonb,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_resumes_user       ON resumes(user_id);
CREATE INDEX IF NOT EXISTS idx_profiles_user      ON skill_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_user          ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_matches_user       ON matches(user_id);
CREATE INDEX IF NOT EXISTS idx_applications_user  ON applications(user_id);
CREATE INDEX IF NOT EXISTS idx_memory_user        ON memory_events(user_id);
CREATE INDEX IF NOT EXISTS idx_interview_user        ON interview_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_interview_application ON interview_sessions(application_id);
-- Approximate NN indexes for semantic search (cosine).
CREATE INDEX IF NOT EXISTS idx_jobs_embedding
    ON jobs USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ---------------------------------------------------------------------------
-- Row-Level Security
-- ---------------------------------------------------------------------------

-- Helper: read the per-request user id set by the backend.
CREATE OR REPLACE FUNCTION app_current_user() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid
$$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['resumes','skill_profiles','jobs','matches','applications','memory_events','interview_sessions']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY;', t);  -- applies to table owner too
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I;', t);
    EXECUTE format($f$
      CREATE POLICY tenant_isolation ON %I
        USING (user_id = app_current_user())
        WITH CHECK (user_id = app_current_user());
    $f$, t);
  END LOOP;
END$$;

-- `users` gets a narrower policy: a session may read/update only its own row,
-- but INSERT (registration) must be allowed before a session exists, so the
-- backend performs registration in a short transaction WITHOUT the app role's
-- RLS by using a dedicated auth path. For simplicity we let the app role
-- select its own row; lookups by email during login use a SECURITY DEFINER fn.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS self_read ON users;
CREATE POLICY self_read ON users
    USING (id = app_current_user())
    WITH CHECK (id = app_current_user());

-- Login/registration need to bypass RLS in a controlled way. These SECURITY
-- DEFINER functions run as the table owner and are the ONLY way to look up a
-- user by email or create one, keeping the surface tiny and auditable.
CREATE OR REPLACE FUNCTION auth_lookup_user(p_email text)
RETURNS TABLE (id uuid, email text, password_hash text, full_name text)
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
  SELECT id, email::text, password_hash, full_name FROM users WHERE email = p_email;
$$;

CREATE OR REPLACE FUNCTION auth_create_user(p_email text, p_hash text, p_name text)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE new_id uuid;
BEGIN
  INSERT INTO users (email, password_hash, full_name)
  VALUES (p_email, p_hash, p_name)
  RETURNING id INTO new_id;
  RETURN new_id;
END;
$$;

-- Grants for the app role.
GRANT USAGE ON SCHEMA public TO careerpilot_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO careerpilot_app;
GRANT EXECUTE ON FUNCTION auth_lookup_user(text)         TO careerpilot_app;
GRANT EXECUTE ON FUNCTION auth_create_user(text,text,text) TO careerpilot_app;
GRANT EXECUTE ON FUNCTION app_current_user()             TO careerpilot_app;
