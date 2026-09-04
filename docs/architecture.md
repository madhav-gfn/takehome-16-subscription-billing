# Architecture

## Current project shape

The project is structured as a decoupled full-stack application:
- **Backend (`backend/`)**: Django 6.1 with Django REST Framework (DRF) and `djangorestframework-simplejwt`. The entry point is [backend/main.py](../backend/main.py), loading settings from [backend/src/config/settings.py](../backend/src/config/settings.py) and routing through [backend/src/config/urls.py](../backend/src/config/urls.py).
- **Frontend (`frontend/`)**: React application bundled with Vite.
- **Database**: PostgreSQL with Row-Level Security (RLS) policies and transaction-scoped session variables.

## Moving pieces

1. **Authentication & Identity (`src.accounts`)**:
   - Custom `User` model (`accounts.User`) with UUID primary key, `email` unique login, and `role` (`billing_admin` vs `account_manager`).
   - JWT token generation & verification with custom claims (`role`, `email`, `user_id`) embedded in the token payload.
   - Endpoints for user registration (`/api/auth/register/`), login (`/api/auth/login/`), token refresh (`/api/auth/refresh/`), and current user profile (`/api/auth/me/`).

2. **Defense-in-Depth Authorization**:
   - **Layer 1 (Application RBAC)**: DRF permission classes (`IsBillingAdmin`, `IsOwnerOrCollaboratorOrAdmin`, `CanManageInvoiceLifecycle`) and function decorators (`@login_required`, `@role_required`, `@billing_admin_required`) returning explicit HTTP 401/403 responses.
   - **Layer 2 (Database RLS)**: `RLSTransactionMiddleware` extracts claims from JWT, wraps each request in a `transaction.atomic()` block, and executes `SET LOCAL app.user_id` and `SET LOCAL app.role`. PostgreSQL RLS policies enforce row isolation even if application logic is bypassed.

3. **Database Layer**:
   - PostgreSQL database configured with connection pooling (`CONN_MAX_AGE=600`) and health checks.
   - Raw SQL RLS policies in [rls_policies.sql](../backend/src/accounts/rls_policies.sql) for `subscriptions`, `invoices`, `collaborators`, `credit_notes`, and `invoice_events`.
   - Covering indexes on foreign keys to prevent sequential scans during RLS subquery evaluation.

## Where each piece runs

- **Local Development**:
  - Django server running on `http://127.0.0.1:8000` via `python main.py runserver`.
  - PostgreSQL database running on `localhost:5432` (`billing` database).
  - React frontend dev server running on `http://localhost:5173` via `npm run dev`.
- **Production Target**:
  - Web Server: Render / VM running Django WSGI.
  - Database: Managed PostgreSQL (e.g., Supabase / Neon / Render Postgres) with transaction-mode pooling (PgBouncer).
  - Frontend: Vercel / Netlify static hosting.

## Representative request path

Here is the end-to-end lifecycle of an authenticated request (e.g. `GET /api/auth/me/` or fetching subscriptions):

```
Client (React / Browser)
  │
  │ HTTP Request: GET /api/auth/me/
  │ Header: "Authorization: Bearer <JWT_TOKEN>"
  ▼
1. Django Middleware Pipeline:
   ├─ CorsMiddleware (validates CORS origins)
   ├─ CommonMiddleware / SecurityMiddleware
   └─ RLSTransactionMiddleware:
        ├─ Extracts token from header and decodes payload without DB hit
        ├─ Reads user_id = "f683bf3a-..." and role = "billing_admin"
        ├─ Begins atomic DB transaction: transaction.atomic()
        └─ Executes:
             SET LOCAL app.user_id = 'f683bf3a-...';
             SET LOCAL app.role = 'billing_admin';
  ▼
2. URL Routing (`src.config.urls` -> `src.accounts.urls`):
   └─ Resolves to `MeView.as_view()`
  ▼
3. DRF View & Authentication:
   ├─ JWTAuthentication verifies signature and loads User instance
   ├─ Permission Check: IsAuthenticated (passes)
   └─ Handler: executes `UserSerializer(request.user).data`
  ▼
4. Database Query (under RLS):
   ├─ Query runs against PostgreSQL within the active transaction
   └─ PostgreSQL applies RLS filters using current_setting('app.role') and ('app.user_id')
  ▼
5. Middleware Transaction Cleanup:
   ├─ Transaction commits successfully
   └─ SET LOCAL variables are automatically cleared, resetting connection state
  ▼
Client receives HTTP 200 OK + User JSON Payload
```

## What we decided not to build

- **Async Workers / Celery**: In-request processing is sufficient for the scope; bulk invoice operations execute synchronously within transactions. At 200 customers, the bulk-generate endpoint finishes in under a second.
- **WebSocket push**: The frontend polls on navigation rather than receiving live updates. Two admins viewing the same invoice will not see each other's changes until one of them refreshes. This is fine for the stated scenario.

---

## Final architecture (4 September 2026)

Everything above was written during the initial scaffold phase. Below is the actual finished system.

### Billing domain (`src.billing`)

The billing app is the core of the system. It is split into layers:

- **Models** (`models.py`): Subscription, Invoice, Collaborator, CreditNote, InvoiceEvent, AlertDismissal. All use UUID primary keys. Financial amounts are `DECIMAL(12, 2)`. The Invoice model has `issued_at` and `paid_at` denormalised from the event trail so dashboard aggregations are indexed range scans instead of joins.
- **Enums** (`enums.py`): `BillingCycle`, `InvoiceStatus`, `EventType`, and `ALLOWED_TRANSITIONS` (the FSM adjacency map).
- **Services** (`services/invoices.py`, `services/subscriptions.py`): All business rules live here, not in views or serializers. `transition()` is the only function in the codebase that writes `Invoice.status`. This single-writer property is what makes "every status change writes exactly one event" true by construction. `create_invoice()` checks for period collisions. `add_credit_note()` enforces the paid-only rule and the running total cap.
- **Querysets** (`querysets.py`): `visible_to(user)` returns only the invoices/subscriptions a given user is allowed to see. Annotations for `is_overdue`, `days_overdue`, and `credited_total` are computed in SQL so filtering and sorting work server-side.
- **Views** (`views.py`): Thin DRF views that delegate to services. Each view checks permissions via DRF permission classes, then calls the appropriate service function. Views never write to the database directly.
- **Filters** (`filters.py`): Django-filter backend for the invoice list. Supports text search (`search`), status, overdue flag, owner, sorting by due date / amount / status, and pagination.
- **Errors** (`errors.py`): Domain-specific exception classes (`InvoicePaidImmutable`, `InvalidTransition`, `VoidReasonRequired`, etc.) that map to HTTP 409 Conflict responses with human-readable messages.

### Database tier enforcement

Two things are enforced at the database level, not just in application code:

1. **Immutability trigger** (`0003_rls_and_triggers.py`): A `BEFORE UPDATE` trigger on the `invoices` table prevents any column change on a paid invoice. This means even a raw SQL `UPDATE` against the database cannot silently modify a paid invoice. The trigger raises a PostgreSQL exception with an explanatory message.
2. **Append-only audit trail** (`0003_rls_and_triggers.py`): A trigger on `invoice_events` blocks all `UPDATE` and `DELETE` operations. The timeline is physically write-once.

### Request path: marking an invoice as paid

```
Client (React)
  |
  | POST /api/invoices/{id}/pay/
  | Header: "Authorization: Bearer <JWT>"
  v
1. RLSTransactionMiddleware:
   - Decodes JWT, extracts user_id and role
   - Opens transaction.atomic()
   - SET LOCAL app.user_id = '...';
   - SET LOCAL app.role = 'billing_admin';

2. URL routing -> InvoiceViewSet.pay()

3. DRF permission check: CanManageInvoiceLifecycle
   - Verifies user is billing_admin (account managers cannot pay)
   - Returns 403 with explanation if not

4. services.invoices.transition(invoice, 'paid', actor):
   - SELECT ... FOR UPDATE (row lock prevents double-pay)
   - Checks ALLOWED_TRANSITIONS: issued -> paid is valid
   - Sets invoice.status = 'paid', invoice.paid_at = now()
   - Calls save(update_fields=['status', 'paid_at', 'updated_at'])
   - PostgreSQL immutability trigger: passes (status was not 'paid' before)
   - Creates InvoiceEvent(type=status_changed, old='issued', new='paid')
   - Append-only trigger: allows INSERT, would block UPDATE/DELETE

5. Transaction commits
   - SET LOCAL variables cleared automatically

6. Response: 200 OK with serialised invoice
```

### The detailed design documents in `doc2/`

Before writing any billing code, I wrote a comprehensive set of design documents covering the domain model, database schema, authorization matrix, API contract, build plans, testing strategy, seed data, and deployment. The full list is in `doc2/00-README.md`. The most important ones:

- `doc2/02-domain-model.md`: Every ambiguity in the brief that I had to rule on, numbered and recorded.
- `doc2/04-authorization-matrix.md`: The complete permission matrix for every action by role.
- `doc2/05-api-contract.md`: Every endpoint, its method, URL, request body, and response shape.
- `doc2/13-risks-and-decisions.md`: Risk register and design decisions made before coding.

