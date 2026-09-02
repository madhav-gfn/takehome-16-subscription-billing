# 01 — Current State Audit

Audited at commit `0885834` (`chore: setup project documentation…`), working tree dirty with
line-ending noise only.

## 1. What actually exists and works

### Backend — `backend/`

| Piece | File | State |
|---|---|---|
| Entry point | `main.py` | Works. Loads `.env` from `backend/`, puts `backend/` on `sys.path`, defaults `DJANGO_SETTINGS_MODULE=src.config.settings`. |
| Settings | `src/config/settings.py` | Real settings. Postgres, DRF, SimpleJWT, CORS, `AUTH_USER_MODEL="accounts.User"`, `CONN_MAX_AGE=600`. |
| Test settings | `src/config/test_settings.py` | Overrides DB to in-memory SQLite. |
| URLs | `src/config/urls.py` | `/health/`, `/api/auth/…`, `/`. |
| User model | `src/accounts/models.py` | `User(AbstractBaseUser)`, UUID PK, unique email login, `role` enum, `db_table="users"`. Has `is_billing_admin` / `is_account_manager` properties. |
| Manager | `src/accounts/managers.py` | `create_user` / `create_superuser`. Superuser forced to `billing_admin`. |
| Auth API | `src/accounts/views.py`, `urls.py` | `POST /api/auth/register/`, `POST /api/auth/login/`, `POST /api/auth/refresh/`, `GET /api/auth/me/`. |
| JWT claims | `src/accounts/serializers.py` | `CustomTokenObtainPairSerializer` injects `role` and `email` into the token. |
| RLS middleware | `src/accounts/middleware.py` | `RLSTransactionMiddleware`: decodes the bearer token, wraps the request in `transaction.atomic()`, runs `SET LOCAL app.user_id` / `app.role`. Skips cleanly on non-Postgres. |
| DRF permissions | `src/accounts/permissions.py` | `IsBillingAdmin`, `IsAccountManager`, `IsBillingAdminOrReadOnly`, `IsOwnerOrCollaboratorOrAdmin`, `CanManageInvoiceLifecycle`. |
| FBV decorators | `src/accounts/decorators.py` | `login_required`, `role_required`, `billing_admin_required`. |
| RLS policies | `src/accounts/rls_policies.sql` | Hand-written SQL for five tables that **do not exist yet**. Never applied. |
| Seed | `management/commands/seed_users.py` | Creates the three demo users, idempotent, `--flush` flag. |
| Tests | `src/accounts/tests.py` | 43 tests across model, register, login, refresh, `/me`, RBAC, middleware, seed. SQLite-backed. |

### Frontend — `frontend/`

Vite 8 + React 19, React Compiler enabled via `@rolldown/plugin-babel`. `App.jsx` is still the
health-check probe hitting `http://localhost:8000/health/` with a hardcoded URL. No router, no auth,
no state management, no additional dependencies installed.

### Docs

`docs/architecture.md`, `schema.md`, `plan.md`, `decisions.md`, `ai-prompts.md` all exist and are
substantively filled for the auth slice. `SUBMISSION.md` has the goal checklist with 1 = Done and
2–10 = Not done. `docs/Billing System Development Research.pdf` is the research artifact.

## 2. Goal coverage today

| Goal | Status | Gap |
|---|---|---|
| 1 Accounts and roles | **Done** | Enforcement classes exist but guard nothing yet — no protected resource exists. |
| 2 Subscriptions | Not started | No model, no app. |
| 3 Invoices | Not started | No model. |
| 4 Lifecycle rules | Not started | No state machine. |
| 5 Collaborators | Not started | No join table. |
| 6 Finding invoices | Not started | No list endpoint, no pagination class. |
| 7 Bulk generate + CSV | Not started | No period maths. |
| 8 Dashboard | Not started | No aggregation endpoints. |
| 9 Immutable history | Not started | No event table. |
| 10 Overdue alerts | Not started | No dismissal model. |

Nine of ten goals are ahead. That is the honest baseline the schedule in
[11-git-and-sessions.md](11-git-and-sessions.md) is built from.

## 3. Defects and debt found in the audit

These are real problems in the tree right now. Each has a fix step in the build plan; the ID is
referenced from there.

### D-01 — Duplicate dead settings/urls/wsgi at `src/`
`src/settings.py`, `src/urls.py`, `src/wsgi.py` are leftovers from the pre-`config/` layout. They
are still tracked, still importable, and `src/settings.py` disagrees with the live one on almost
everything (SQLite, no `AUTH_USER_MODEL`, session middleware, `corsheaders` but no DRF). Anyone
reading the repo has to work out which one is live.
**Fix:** delete all three. `src/config/` is canonical. *(First step of Session 1 — it is a
one-line-of-thought change and makes every later diff readable.)*

### D-02 — Working tree is 192 lines of CRLF noise
`git diff` shows six files changed; every hunk is `\n` → `\r\n`. An editor rewrote line endings.
This will pollute the next commit and make the history look like churn.
**Fix:** add `.gitattributes` with `* text=auto eol=lf`, then `git checkout -- .` to discard. Do
this *before* any real work so the first billing commit is clean.

### D-03 — `current_setting(...)::UUID` blows up on anonymous requests
`rls_policies.sql` casts `current_setting('app.user_id', true)::UUID`. The middleware sets that
variable to `''` for unauthenticated requests. `''::uuid` raises
`invalid input syntax for type uuid: ""` — a 500, not a clean deny, on every anonymous request that
touches a protected table.
**Fix:** every cast becomes `NULLIF(current_setting('app.user_id', true), '')::uuid`. A NULL
comparison yields NULL, which is falsy in a policy — a clean deny.

### D-04 — The anti-archiving RLS check is a tautology
```sql
AND (archived_at IS NOT DISTINCT FROM archived_at)
```
This compares the column to itself. It is always true and enforces nothing. RLS `WITH CHECK` sees
only the *new* row — there is no `OLD` in a policy, so this rule is not expressible in RLS at all.
**Fix:** enforce "only a BA may change `archived_at`" in a `BEFORE UPDATE` trigger, which does have
`OLD` and `NEW`. See [03](03-database-schema.md) §5.

### D-05 — RLS INSERT policy contradicts Goal 2
`rls_sub_manager_insert` requires `owner_id = current_setting('app.user_id')`, but Goal 2 says a
subscription is created *with* an owning account manager — which for a BA is someone else.
The BA path is covered by `rls_sub_admin_all`, so it works by accident, but the intent is unstated.
**Fix:** make the rule explicit and documented (ruling A-01 in [02](02-domain-model.md)): an AM may
only create subscriptions owned by themselves; a BA may name any AM as owner.

### D-06 — Management commands run with no RLS role and see nothing
`FORCE ROW LEVEL SECURITY` applies to the table owner, which is the Django DB user. Outside a
request there is no middleware, so `app.role` is unset, `current_setting('app.role', true)` returns
NULL, every policy evaluates falsy, and `seed_demo` inserts nothing and reads nothing. This will
look like a mystifying silent failure.
**Fix:** an `rls_session(role, user_id)` context manager in `src/billing/db.py`, used by every
management command and every test that touches billing tables. See [04](04-authorization-matrix.md) §6.

### D-07 — Only 5xx rolls the request transaction back
The middleware calls `transaction.set_rollback(True)` when `status_code >= 500`. But DRF converts a
raised `ValidationError` into a 400 *response*, so the transaction commits — and any writes made
before the validation failure are persisted. In a billing system that is exactly the class of bug
that produces half-written invoices.
**Fix:** roll back on `status_code >= 400`. Nothing that returns a 4xx should be persisting.

### D-08 — RLS is completely untested
`test_settings.py` swaps in SQLite, and the middleware short-circuits on `connection.vendor !=
"postgresql"`. So the entire second layer of the defence-in-depth story — the part
`docs/decisions.md` sells hardest — has zero test coverage.
**Fix:** a Postgres-backed `src/billing/tests/test_rls.py` that sets session vars directly and
asserts row visibility, run under the default settings. See [08](08-testing-plan.md) §4.

### D-09 — `IsOwnerOrCollaboratorOrAdmin` references a model that does not exist
It does `apps.get_model("billing", "Collaborator")` inside a `try/except LookupError` that returns
`False`. Once the app exists the label must match. The app will be `src.billing`, whose Django app
*label* is `billing`, so the lookup will resolve — but this is load-bearing and undocumented.
**Fix:** set `label = "billing"` explicitly in `BillingConfig` and delete the `try/except` once the
model is real, so a genuine lookup failure is loud instead of silently denying.

### D-10 — No `.env.example`
`.env` is correctly gitignored and untracked (verified), and it contains a real local Postgres
password. But there is no committed template, so nobody — including a reviewer — can tell what
variables the app needs.
**Fix:** commit `backend/.env.example` with every key and no values. Also required by the hosting
section of the brief.

### D-11 — Demo passwords are weaker than the validator
`AUTH_PASSWORD_VALIDATORS` requires 8 characters; `admin123` is exactly 8 and only passes because
`set_password()` bypasses validators. It works, but registering that same password through the API
would be a coin flip on the rule. Harmless, noted so it is not mistaken for a bug later.
**Fix:** none required. Keep the credentials as published in `SUBMISSION.md`.

## 4. What the audit changes about the plan

Three things:

1. **Session 1 opens with cleanup** (D-01, D-02, D-10). Ten minutes, and every later diff reads clearly.
2. **The RLS SQL gets rewritten, not extended.** D-03, D-04 and D-05 mean the existing file is not
   a foundation to build on. It moves into a real migration with the casts fixed and the archiving
   rule relocated to a trigger. [04](04-authorization-matrix.md) §4 has the replacement in full.
3. **RLS gets a Postgres test suite** (D-08). Without it the defence-in-depth claim in
   `docs/decisions.md` is a claim, not a fact — and the brief says the interview will ask about
   exactly this kind of claim.
