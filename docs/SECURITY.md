# Security & Confidentiality

CareerPilot AI is multi-user and handles resumes — sensitive personal
documents. Confidentiality is enforced in depth, at four independent layers, so
no single mistake exposes one user's CV to another.

## 1. Tenant isolation at the database (Row-Level Security)

Every table that can hold candidate data (`resumes`, `skill_profiles`, `jobs`,
`matches`, `applications`, `memory_events`) has RLS **enabled and forced**. The
policy on each is:

```sql
USING      (user_id = app_current_user())
WITH CHECK (user_id = app_current_user())
```

`app_current_user()` reads the GUC `app.current_user_id`, which the backend sets
**inside each request transaction** from the verified JWT:

```sql
SELECT set_config('app.current_user_id', '<uuid>', true);  -- true = transaction-local
```

Consequences:

- A query with a forgotten `WHERE user_id = …` still returns **only** the
  caller's rows — the database refuses the rest.
- If `app.current_user_id` is unset, `app_current_user()` is `NULL` and every
  policy fails closed (no rows).
- The API connects as `careerpilot_app`, a **non-superuser role created with
  `NOBYPASSRLS`**. Superusers ignore RLS, so the app must never connect as one.

Login and registration are the only operations that must reach across users
(look up by email / insert a new user). They go through two tiny, auditable
`SECURITY DEFINER` functions (`auth_lookup_user`, `auth_create_user`) instead of
a broad bypass.

## 2. CV encryption at rest

Raw resume bytes are **encrypted with Fernet (authenticated AES) before they are
written** to `resumes.ciphertext`. The database never stores plaintext. The key
lives in `CV_ENCRYPTION_KEY` (env / secret manager), never in the DB. Decryption
happens only in memory, only for the owning user, only when an agent needs the
text, and the plaintext reference is dropped promptly after parsing.

## 3. A model that does not train on your data

Free public LLM tiers (e.g. the consumer ChatGPT free/Plus tiers) may use
submitted prompts to improve their models — which is disqualifying for
confidential resumes. The default provider is therefore the **OpenAI API**,
which by default does **not** train on data submitted through the API and
retains it only for a short (~30-day) abuse-monitoring window (Zero Data
Retention is available for eligible enterprise endpoints). Anthropic's API
offers the same commercial no-train guarantee and can be selected instead. For a
fully local / air-gapped posture, set `LLM_PROVIDER=ollama` and no CV text
leaves the host at all — embeddings fall back to a local `sentence-transformers`
model in that mode specifically.

By default (OpenAI/Anthropic), embeddings use that same provider's API rather
than a local model — resume and job text used for semantic matching already
goes to that API for the LLM agents (resume understanding, matching reasoning,
writer/critic), so routing embeddings through it too doesn't cross a new trust
boundary, under the same no-training guarantee above.

> The distinction that matters for confidentiality is **API vs. consumer chat
> tier**, not which vendor: the API paths of OpenAI and Anthropic both exclude
> your data from training by default; the free consumer chat products do not.

## 4. Transport, access, and operational hygiene

- **Auth:** JWT bearer tokens (HS256), bcrypt-hashed passwords.
- **Downloads:** the decrypt endpoint runs inside the tenant session, so a user
  can only ever download their own resume.
- **No CV in logs:** request bodies are never logged; logging is limited to
  metadata.
- **Rate limiting & CORS:** `slowapi` limits abusive traffic; CORS is pinned to
  the configured frontend origin.
- **Secrets:** provided via env vars / Render + Vercel secret stores, never
  committed (`.env` is git-ignored; `.env.example` documents the shape).

## Human-in-the-loop

No outbound action is autonomous. Application drafts are stored as `review`; only
an explicit user approval flips them to `approved`. CareerPilot creates Gmail
**drafts**, never sends — the user reviews and clicks send in Gmail itself. The
same applies to follow-up emails and calendar events: an interview date/time
extracted from a reply is only ever suggested for the user to confirm or
dismiss; nothing is written to their calendar until they click confirm.

Gmail/Calendar access is OAuth-scoped to the minimum needed:
`gmail.compose` (create drafts, never send), `gmail.readonly` (detect whether
the user themselves sent a draft or received a reply — read-only, never
modifies or deletes mail), and `calendar.events` (create an event only after
explicit confirmation). Because these are Google-classified sensitive/
restricted scopes, an unverified app is capped at 100 manually-added test
users with 7-day-expiring refresh tokens — see
[`docs/DEPLOYMENT.md`](DEPLOYMENT.md) for what that means for going live.

## Hardening checklist before real production

- [ ] Rotate `careerpilot_app` password and all default secrets.
- [ ] Put the API behind TLS (Render/Vercel do this automatically).
- [ ] Consider envelope encryption (per-user data keys wrapped by a KMS).
- [ ] Add audit logging of access to `resumes`.
- [ ] Set short JWT lifetimes + refresh tokens for production.
