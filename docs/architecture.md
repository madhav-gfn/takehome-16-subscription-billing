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

## What we decided not to build yet

- **Subscription and Invoice Domain Models**: Next milestone after authentication and authorization foundations are solid.
- **Frontend Dashboard / UI Views**: Frontend will be built on top of the tested API endpoints.
- **Async Workers / Celery**: In-request processing is sufficient for the scope; bulk invoice operations can be executed synchronously within transactions.
