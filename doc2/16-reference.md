# 16 — Reference

Consolidated lookups: dependencies, environment variables, commands, and the full endpoint index.
Everything here appears somewhere in docs 03–15; this file is the single place to check it from.

---

## 1. Dependencies

### `backend/requirements.txt` — final

```
Django>=5.2
djangorestframework>=3.15.2
djangorestframework-simplejwt>=5.3.1
django-cors-headers==4.9.0
django-filter>=24.3          # NEW — Goal 6 filtering
psycopg2-binary>=2.9.9
python-dotenv==1.0.1
python-dateutil>=2.9         # NEW — relativedelta, period arithmetic
PyJWT>=2.9.0
gunicorn>=22.0               # NEW — production server
freezegun>=1.5               # NEW — dev only; time travel in alert tests
```

`freezegun` is a test dependency in a single requirements file. Splitting into
`requirements-dev.txt` is correct practice and costs a step in the Render build for one package —
noted as a knowing simplification rather than left unexplained.

### `frontend/package.json` — additions

```
react-router-dom  ^7      # routing + URL-driven filter state
recharts          ^2      # the Goal 8 8-week chart
```

Two runtime dependencies total, on top of React. No UI kit, no state library, no form library, no
date library — reasoning in [07](07-frontend-build-plan.md) §2.

---

## 2. Environment variables

### `backend/.env.example` (committed; `.env` stays gitignored)

```bash
# Django
DJANGO_SECRET_KEY=            # 64 random chars; distinct from JWT_SECRET_KEY
DJANGO_DEBUG=True             # False in production
DJANGO_ALLOWED_HOSTS=*        # the real host in production, never *

# CORS — the frontend origin(s)
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# PostgreSQL
DB_NAME=billing
DB_USER=postgres
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=5432
DB_CONN_MAX_AGE=600

# JWT — deliberately separate from DJANGO_SECRET_KEY so rotating one does not
# sign out every user, and a leak of one does not compromise the other.
JWT_SECRET_KEY=
JWT_ACCESS_TOKEN_LIFETIME_HOURS=24
JWT_REFRESH_TOKEN_LIFETIME_DAYS=7
```

### `frontend/.env.example`

```bash
VITE_API_BASE_URL=http://localhost:8000
```

Vite inlines `VITE_*` at **build** time, so changing it in production requires a redeploy, not a
restart.

### Production values

| Variable | Render (backend) | Vercel (frontend) |
|---|---|---|
| `DJANGO_DEBUG` | `False` | — |
| `DJANGO_ALLOWED_HOSTS` | `<service>.onrender.com` | — |
| `CORS_ALLOWED_ORIGINS` | `https://<project>.vercel.app` | — |
| `DB_*` | from Supabase, session pooler port 5432 | — |
| `DJANGO_SECRET_KEY` / `JWT_SECRET_KEY` | fresh, distinct, 64 chars each | — |
| `VITE_API_BASE_URL` | — | `https://<service>.onrender.com` |

---

## 3. Commands

```bash
# --- backend, from backend/ ------------------------------------------------
python main.py check                       # config sanity
python main.py check --deploy              # production warnings
python main.py makemigrations billing
python main.py makemigrations --check --dry-run   # CI guard: nothing missing
python main.py migrate
python main.py migrate billing zero        # tear down billing (RLS test reset)
python main.py runserver

python main.py seed_users                  # the 3 published demo users
python main.py seed_demo                   # full dataset, idempotent
python main.py seed_demo --flush           # wipe and reseed
python main.py apply_rls                   # re-apply policies to an existing DB

# tests — fast loop (SQLite, RLS SKIPPED)
python main.py test src --settings=src.config.test_settings
# tests — full (real Postgres, RLS + triggers included). Before every commit
# touching models, migrations or services.
python main.py test src
python main.py test src.billing.tests.test_invoice_lifecycle -v 2

# --- frontend, from frontend/ ----------------------------------------------
npm install
npm run dev            # http://localhost:5173
npm run build          # must be clean before deploying
npm run preview
npm run lint

# --- production ------------------------------------------------------------
gunicorn src.config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 60
```

### Pre-commit checklist

```bash
python main.py test src                    # full suite, Postgres
python main.py makemigrations --check --dry-run
grep -rn "float(" src/billing/             # must be empty — money is Decimal
grep -rn "\.status = " src/billing/        # exactly one hit: transition()
```

---

## 4. Endpoint index

Legend: **BA** billing admin only · **M** member (admin, owner or collaborator) · **A** any
authenticated user, results scoped to what they can see.

| Method | Path | Who | Goal | Spec |
|---|---|---|---|---|
| POST | `/api/auth/register/` | public | 1 | built |
| POST | `/api/auth/login/` | public | 1 | built |
| POST | `/api/auth/refresh/` | public | 1 | built |
| GET | `/api/auth/me/` | A | 1 | built |
| GET | `/api/auth/users/?role=` | A | 2, 5, 6 | [05](05-api-contract.md) §2 |
| GET | `/api/subscriptions/` | A | 2, 5 | [05](05-api-contract.md) §3 |
| POST | `/api/subscriptions/` | A | 2 | §3 · A-01 |
| GET | `/api/subscriptions/{id}/` | M | 2, 3 | §3 · includes all invoices |
| PATCH | `/api/subscriptions/{id}/` | M | 2 | §3 |
| POST | `/api/subscriptions/{id}/archive/` | BA | 2 | §3 |
| POST | `/api/subscriptions/{id}/restore/` | BA | 2 | §3 |
| POST | `/api/subscriptions/{id}/collaborators/` | BA | 5 | §3 |
| DELETE | `/api/subscriptions/{id}/collaborators/{user_id}/` | BA | 5 | §3 |
| GET | `/api/invoices/` | A | 6 | [05](05-api-contract.md) §4 |
| POST | `/api/invoices/` | M | 3 | §4 |
| GET | `/api/invoices/{id}/` | M | 3, 9 | §4 |
| PATCH | `/api/invoices/{id}/` | M | 3, 4 | §4 · state-dependent fields |
| POST | `/api/invoices/{id}/issue/` | BA | 4 | §4 |
| POST | `/api/invoices/{id}/pay/` | BA | 4 | §4 |
| POST | `/api/invoices/{id}/void/` | BA | 4 | §4 · reason required |
| POST | `/api/invoices/{id}/credit-notes/` | BA | 4 | §4 · paid only |
| POST | `/api/invoices/{id}/notes/` | M | 9 | §4 · any state |
| GET | `/api/invoices/{id}/timeline/` | M | 9 | §4 · read-only, no PATCH/DELETE route exists |
| POST | `/api/invoices/{id}/dismiss-alert/` | BA | 10 | [05](05-api-contract.md) §6 |
| POST | `/api/invoices/bulk-generate/` | BA | 7 | §5 |
| GET | `/api/exports/receivables.csv` | A | 7 | §5 |
| GET | `/api/dashboard/` | A | 8 | §6 |
| GET | `/api/alerts/` | A | 10 | §6 |
| GET | `/api/alerts/count/` | A | 10 | §6 |
| GET | `/health/` | public | — | [10](10-deployment-plan.md) §6 |

28 endpoints. Note what is **absent**: no DELETE on subscriptions, invoices, credit notes or events;
no PUT anywhere; no route that mutates the timeline. Those absences are the design.

---

## 5. Error code index

| Code | HTTP | Raised by |
|---|---|---|
| `VALIDATION_ERROR` | 400 | Any serialiser failure |
| `INVALID_PRICE` | 400 | Subscription create/update |
| `VOID_REASON_REQUIRED` | 400 | Void without a reason |
| `CREDIT_EXCEEDS_INVOICE` | 400 | Credit note breaching I-10 |
| `COLLABORATOR_MUST_BE_AM` | 400 | Adding a non-AM |
| `OWNER_CANNOT_BE_COLLABORATOR` | 400 | Adding the owner |
| `UNAUTHENTICATED` | 401 | Missing or expired token |
| `FORBIDDEN` | 403 | Any permission class |
| `LIFECYCLE_ADMIN_ONLY` | 403 | AM attempting issue/pay/void/credit |
| `SUBSCRIPTION_OWNER_MUST_BE_SELF` | 403 | A-01 |
| `OWNER_CHANGE_ADMIN_ONLY` | 403 | AM reassigning an owner |
| `NOT_FOUND` | 404 | Missing **or invisible** — same message either way |
| `INVALID_TRANSITION` | 409 | Illegal state move |
| `INVOICE_PAID_IMMUTABLE` | 409 | Editing a paid invoice |
| `INVOICE_PAID_CANNOT_VOID` | 409 | Voiding a paid invoice |
| `INVOICE_ISSUED_LOCKED` | 409 | Changing amount/period after issue |
| `INVOICE_VOID_IS_TERMINAL` | 409 | Any action on a void invoice |
| `CREDIT_NOTE_REQUIRES_PAID` | 409 | Credit note on a non-paid invoice |
| `PERIOD_ALREADY_INVOICED` | 409 | Duplicate period |
| `SUBSCRIPTION_ARCHIVED` | 409 | Editing/invoicing an archived subscription |
| `ALREADY_ARCHIVED` / `NOT_ARCHIVED` | 409 | Archive/restore |
| `ALREADY_COLLABORATOR` | 409 | Duplicate collaborator |
| `NOT_OVERDUE` | 409 | Dismissing a non-overdue alert |

Full class definitions in [14](14-backend-code-scaffolds.md) §2.

---

## 6. Ruling index

Quick lookup for the 18 ambiguity rulings in [02](02-domain-model.md) §6.

| ID | Ruling |
|---|---|
| A-01 | AM creates only subscriptions they own; BA names any AM |
| A-02 | A BA cannot own a subscription |
| A-03 | Void is terminal and immutable |
| A-04 | Credit notes against Paid invoices only |
| A-05 | Credits never exceed the invoice, individually or cumulatively |
| A-06 | Collected and credited reported separately, never netted |
| A-07 | Overdue = issued AND due_date < today |
| A-08 | "Issued this month" reads `issued_at`, not current status |
| A-09 | "Collected this month" reads `paid_at` |
| A-10 | Dismissal stores `dismissed_for_due_date`; alert re-arms when it differs |
| A-11 | Only a BA dismisses |
| A-12 | Alerts scoped like invoices; badge matches the visible list |
| A-13 | Not-yet-started subscription → `skipped`, not `failed` |
| A-14 | A void invoice's period regenerates |
| A-15 | Archived subscriptions keep payable, visible invoices |
| A-16 | Archived subscriptions cannot be edited — restore first |
| A-17 | UTC everywhere |
| A-18 | Notes cannot be edited or deleted |

---

## 7. Defect index

From [01](01-current-state-audit.md) §3 — the eleven issues found in the existing tree.

| ID | Issue | Fixed in |
|---|---|---|
| D-01 | Duplicate dead `src/settings.py`, `urls.py`, `wsgi.py` | Step 0 |
| D-02 | 192 lines of CRLF churn in the working tree | Step 0 |
| D-03 | `''::uuid` raises on anonymous requests | Step 3 (`NULLIF`) |
| D-04 | `archived_at IS NOT DISTINCT FROM archived_at` is a tautology | Step 3 (trigger) |
| D-05 | RLS INSERT policy contradicts Goal 2 without saying so | Step 3 (A-01) |
| D-06 | Management commands see nothing under `FORCE RLS` | Step 3 (`rls_session`) |
| D-07 | Only 5xx rolls the request transaction back | Step 3 |
| D-08 | RLS entirely untested | Step 3 (`test_rls.py`) |
| D-09 | `IsOwnerOrCollaboratorOrAdmin` silently denies on `LookupError` | Step 4 (deleted) |
| D-10 | No `.env.example` | Step 0 |
| D-11 | Demo passwords at the validator boundary | none — noted only |

---

## 8. Invariant index

The fourteen statements that must always hold, from [02](02-domain-model.md) §5. Reproduced as a
checklist because this is the table `docs/schema.md`'s "database versus application constraints"
section is built from.

| ID | Invariant | Enforced by |
|---|---|---|
| I-1 | `amount > 0` | DB CHECK |
| I-2 | `price > 0` | DB CHECK |
| I-3 | `period_start <= period_end` | DB CHECK |
| I-4 | One non-void invoice per period | DB partial UNIQUE |
| I-5 | void ⟺ a reason exists | DB CHECK |
| I-6 | Paid invoices never change | trigger + service |
| I-7 | Issued amount and period never change | trigger + service |
| I-8 | Events are append-only | trigger + no RLS policy |
| I-9 | Credit notes are append-only | trigger + no RLS policy |
| I-10 | Credits ≤ invoice amount | service, under a row lock |
| I-11 | Collaborators are account managers | service |
| I-12 | Owners are account managers | service |
| I-13 | Every status change writes one event | service — one writer of `status` |
| I-14 | Archived subscriptions generate nothing | service |
