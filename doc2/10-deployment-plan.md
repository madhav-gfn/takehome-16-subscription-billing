# 10 — Deployment Plan

Requirement: a working live URL, free tiers only, seeded with demo data, secrets in environment
variables, cold-start behaviour noted in `SUBMISSION.md`.

## 1. Choice

| Layer | Service | Why this one |
|---|---|---|
| Database | **Supabase** (managed Postgres) | Free tier gives a real Postgres with superuser-ish rights — needed for `CREATE EXTENSION pg_trgm` and for `FORCE ROW LEVEL SECURITY`. Neon is an equally fine alternative. |
| Backend | **Render** web service | Free tier runs a Python web service with a shell for one-off commands. The shell matters: seeding and migrating need it. |
| Frontend | **Vercel** static | Zero-config Vite build, instant deploys, no cold start. |

This is the combination the brief itself suggests. Choosing it costs nothing in marks and saves an
hour of evaluating alternatives — an hour better spent on Goals 4 and 9. That reasoning goes in
`docs/decisions.md`, because "I took the suggested option deliberately" and "I didn't think about
it" look the same in a repo unless one is written down.

**The RLS constraint drives the database choice.** A host that does not allow `FORCE ROW LEVEL
SECURITY` or grants only a restricted role would silently disable the entire second security layer.
That is checked *first*, before anything else is deployed — see §3 step 2.

## 2. Deploy order

Database → backend → frontend. Each needs the previous one's connection details, so any other order
means redeploying.

## 3. Steps

### 1. Supabase project
Create the project, note the connection string. Use the **session pooler** port (5432) rather than
the transaction pooler (6543).

Why: `RLSTransactionMiddleware` uses `SET LOCAL` inside an explicit transaction, which is safe under
transaction pooling in principle — that is exactly what `SET LOCAL` is for. But Django's
`CONN_MAX_AGE=600` plus a transaction pooler is a combination that produces confusing "prepared
statement already exists" failures with psycopg2. Session pooling with `CONN_MAX_AGE` is the boring,
working configuration. Documented in `docs/architecture.md` alongside the note that a production
system at scale would use PgBouncer in transaction mode *and* set `CONN_MAX_AGE=0`.

### 2. Verify RLS is actually available — before anything else
```sql
CREATE TABLE _rlscheck (id int);
ALTER TABLE _rlscheck ENABLE ROW LEVEL SECURITY;
ALTER TABLE _rlscheck FORCE  ROW LEVEL SECURITY;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
DROP TABLE _rlscheck;
```
All four must succeed. If `FORCE` fails, the host is wrong and the choice changes now rather than
after the backend is wired up. If only `pg_trgm` fails, migration `0002_search_indexes` is made
conditional and the loss is noted in `docs/schema.md` — search still works, just without the index.

### 3. Render web service
- Root directory `backend/`
- Build: `pip install -r requirements.txt`
- Start: `gunicorn src.config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 60`
- `gunicorn` is added to `requirements.txt`. The dev server is not a deployment.

Environment variables (all set in the Render dashboard, none in the repo):
```
DJANGO_SECRET_KEY        <64 random chars, freshly generated — not the dev value>
DJANGO_DEBUG             False
DJANGO_ALLOWED_HOSTS     <service>.onrender.com
CORS_ALLOWED_ORIGINS     https://<project>.vercel.app
DB_NAME DB_USER DB_PASSWORD DB_HOST DB_PORT   from Supabase
DB_CONN_MAX_AGE          600
JWT_SECRET_KEY           <a different 64 random chars>
JWT_ACCESS_TOKEN_LIFETIME_HOURS   24
JWT_REFRESH_TOKEN_LIFETIME_DAYS   7
```

`JWT_SECRET_KEY` is distinct from `DJANGO_SECRET_KEY`. They already can be — `settings.py` falls
back rather than requiring it — and separating them means rotating the Django key does not sign out
every user, and a leak of one does not compromise the other.

### 4. Migrate and seed, via the Render shell
```bash
python main.py migrate
python main.py seed_demo
```
`migrate` applies `0003_rls` and `0004_immutability` along with everything else. **`seed_demo` will
insert nothing if `rls_session` was not wired up** (D-06) — this is where that defect would surface,
in production, at the worst moment. It is why Step 10 of the build plan verifies the seed against
real Postgres locally rather than SQLite.

Verify against §7 of [09](09-seed-data-plan.md) before touching the frontend.

### 5. Vercel
- Root directory `frontend/`, framework preset Vite, build `npm run build`, output `dist`
- Environment: `VITE_API_BASE_URL = https://<service>.onrender.com`
- Vite inlines `VITE_*` at build time, so changing it requires a redeploy, not just a restart.

### 6. Close the CORS loop
Set Render's `CORS_ALLOWED_ORIGINS` to the actual Vercel URL and restart. `CSRF_TRUSTED_ORIGINS`
follows it automatically in the current settings. A wildcard here would be lazy and visible.

### 7. End-to-end check
Log in as each of the three published users on the live URL and walk §7 of
[09](09-seed-data-plan.md). Then, with DevTools open, confirm the invoice list's network request
carries the filter query params — the visible proof that Goal 6 filters server-side.

## 4. Free-tier cold start

Render's free web services sleep after ~15 minutes idle and take **30–60 seconds** to wake. The
brief explicitly asks for this to be noted so a slow first load is not read as a broken deployment.

Two mitigations:
1. `SUBMISSION.md` says it plainly, in the Notes section, in the brief's own terms.
2. The frontend shows a specific message when a request exceeds 5 seconds: *"Waking the backend —
   free hosting sleeps when idle. This can take up to a minute on the first request."* A generic
   spinner for 45 seconds reads as broken; a spinner that explains itself reads as considered.

Deliberately **not** doing: an external cron pinging the service to keep it warm. It is against the
spirit of a free tier, and the honest note is better than the trick.

## 5. Production settings to verify

`python main.py check --deploy` with `DEBUG=False`, and act on:

| Setting | Value | Note |
|---|---|---|
| `DEBUG` | `False` | Via env, verified in the deployed `/health/` response |
| `ALLOWED_HOSTS` | the Render host | Not `*`. The current default is `*` and must be overridden in production |
| `SECURE_SSL_REDIRECT` | `True` when not DEBUG | Render terminates TLS |
| `SECURE_PROXY_SSL_HEADER` | `("HTTP_X_FORWARDED_PROTO","https")` | Required behind Render's proxy, otherwise the redirect loops |
| `SECURE_HSTS_SECONDS` | `31536000` when not DEBUG | |
| `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` | `True` | Little effect — the API is stateless — but free |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` | Django default |

These land in `settings.py` behind `if not DEBUG:` so local development is unaffected. The
`SECURE_PROXY_SSL_HEADER` line is the one that causes an infinite redirect if forgotten — worth
knowing before spending twenty minutes on it.

## 6. `/health/` upgrade

The current endpoint returns a static payload, so it cannot distinguish "the process is up" from
"the app works". It becomes:
```json
{ "status": "ok", "service": "django", "debug": false,
  "database": "ok", "migrations": "applied", "time": "2025-09-01T12:00:00Z" }
```
`database` runs `SELECT 1`; `migrations` checks for unapplied migrations. Returns 503 if either
fails. Render's health check points at it, so a failed deploy fails visibly rather than serving 500s.

## 7. If deployment fails

The brief: *"If you cannot get it hosted, submit anyway and record in SUBMISSION.md what you tried
and where it broke."*

The fallback is a `docker-compose.yml` (Postgres + backend + frontend) plus a README section so a
reviewer can run it in one command, and a `SUBMISSION.md` entry naming the exact failure — the
service, the error, and what was tried. A specific failure report reads far better than a vague
apology, and the compose file is ~30 minutes of work that also makes local setup easier for anyone
else.

**Deployment happens in Session 5, not Session 7.** Deploying early, with a partially finished app,
is deliberate: hosting problems are unpredictable and discovering a `FORCE ROW LEVEL SECURITY`
restriction on the final evening would be unrecoverable. Once the pipeline works, later sessions
redeploy for free. This is the single highest-value scheduling decision in the plan and it goes in
`docs/plan.md` as such.
