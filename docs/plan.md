# Plan

## Work split

I planned the work in a straightforward sequence based on the assignment requirements:

1. Set up the backend foundation.
2. Validate the project structure and Django startup.
3. Define the domain model for users, subscriptions, and invoices.
4. Build auth and role enforcement.
5. Implement subscription and invoice operations.
6. Add server-side filtering, bulk generation, and reporting.
7. Add audit history and overdue alert logic.
8. Write the documentation and submission artifacts.

This order matters because the business rules depend on the data model and role structure. It is better to stabilize the backend shell before adding billing logic.

## What we built so far

- Django backend initialized under `backend/`
- project configuration and URL routing created
- Django system check passes successfully
- project structure cleaned up and aligned with the current folder layout

## What is next

- create the core billing app models
- implement user roles and server-side permission checks
- add subscriptions and invoices with invoice lifecycle rules
- create invoice search/filter/query logic
- add reporting endpoints and alerts
- document decisions and final architecture once the logic exists

## Time estimate vs reality

The backend scaffolding took far less time than the full billing logic will take. The foundation was roughly a few hours, which was accurate for setup. The full domain implementation and business rule enforcement will be more involved and likely exceed the initial estimate if done properly.

## What we cut or deferred

- A frontend was intentionally deferred.
- Deployment work was deferred until the backend logic is stable.
- Complex stretch features were deferred. The priority is correctness for the required billing rules, not extra features.
- A stronger production database and deployment environment will come after the core business model is working and tested.


## plan for auth
```
# JWT-Based RBAC Authentication & Authorization with PostgreSQL RLS

Build a defense-in-depth auth system with two layers: application-level JWT middleware and database-level Row-Level Security (RLS) policies on PostgreSQL.

## Audit Summary — Current State

| Layer | Status | Details |
|-------|--------|---------|
| Backend | Early scaffold | Django 5.1 with a health endpoint. No apps, no models, no auth. SQLite DB. |
| Frontend | Bare Vite+React | Default boilerplate, no routing, no auth context |
| Database | SQLite (dev) | No tables beyond Django defaults, no migrations |
| Auth | None | No user model, no JWT, no RBAC, no RLS |

The project is essentially a blank shell — the entire auth system will be built from scratch.

---

## User Review Required

> [!IMPORTANT]
> **PostgreSQL is a prerequisite.** The plan assumes you will set up a PostgreSQL instance (local or hosted) **before** execution begins. The `.env` will need `DATABASE_URL` or individual `DB_*` variables. I will not create or modify the PG instance itself.

> [!IMPORTANT]
> **Django vs. raw SQL for RLS.** Django's ORM does not natively support `SET LOCAL` session variables or RLS policies. We will use **raw SQL migrations** for RLS policy creation, and a **custom database backend / middleware** to inject `SET LOCAL` at the start of each request's transaction. This is non-trivial but necessary for defense-in-depth.

> [!WARNING]
> **Bypassing Django's built-in `auth.User`.** Django's default `User` model uses session-based auth. We will replace it with a **custom `User` model** (`AUTH_USER_MODEL`) that stores `role` and uses `UUID` primary keys — required for RLS `current_setting('app.user_id')::UUID` patterns. This must be done **before** the first `migrate`.

---

## Open Questions

> [!IMPORTANT]
> **1. JWT Library:** Should we use **`djangorestframework-simplejwt`** (requires DRF) or **`PyJWT`** (lightweight, manual token handling)? I recommend `PyJWT` + manual middleware to avoid pulling in all of DRF for just auth, but if you plan to use DRF for the rest of the API, `simplejwt` is more ergonomic. **Which do you prefer?**

> [!IMPORTANT]
> **2. Password Hashing:** Django's built-in `make_password` / `check_password` (uses PBKDF2 by default) is battle-tested. Should we use that, or do you prefer `bcrypt` / `argon2`?

> [!IMPORTANT]
> **3. Token Refresh Strategy:** Should we implement a refresh token flow (access + refresh token pair, with the refresh token stored in httpOnly cookie or DB), or keep it simple with a single JWT access token with a longer expiry?

> [!IMPORTANT]
> **4. Connection Pooling:** The spec mentions PgBouncer for safe `SET LOCAL` handling. For development, are you planning to set up PgBouncer, or should we just use Django's direct connections for now and document PgBouncer as a production concern?

---

## Proposed Changes

### Component 1: Custom User Model & Django App

This is the foundation — a new `accounts` Django app with a custom `User` model using UUID PKs and a `role` field.

#### [NEW] [`backend/src/accounts/__init__.py`](file:///d:/takehome-16-subscription-billing/backend/src/accounts/__init__.py)
Empty init file for the accounts app.

#### [NEW] [`backend/src/accounts/apps.py`](file:///d:/takehome-16-subscription-billing/backend/src/accounts/apps.py)
Django app config: `name = "src.accounts"`, `default_auto_field = "django.db.models.BigAutoField"`.

#### [NEW] [`backend/src/accounts/models.py`](file:///d:/takehome-16-subscription-billing/backend/src/accounts/models.py)
Custom User model:
```python
class Role(models.TextChoices):
    BILLING_ADMIN = "billing_admin", "Billing Admin"
    ACCOUNT_MANAGER = "account_manager", "Account Manager"

class User(AbstractBaseUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["role"]

    objects = UserManager()  # custom manager for create_user / create_superuser
```
- UUID PK is critical — RLS policies cast `current_setting('app.user_id')` to `UUID`.
- No `username` field — email is the sole login identifier.
- `AbstractBaseUser` gives us `password` field + `set_password()` / `check_password()` for free.

#### [NEW] [`backend/src/accounts/managers.py`](file:///d:/takehome-16-subscription-billing/backend/src/accounts/managers.py)
Custom `UserManager(BaseUserManager)` with `create_user(email, password, role)` and `create_superuser(...)` methods.

---

### Component 2: JWT Token Utilities

Stateless token generation and verification — no Django sessions involved.

#### [NEW] [`backend/src/accounts/jwt_utils.py`](file:///d:/takehome-16-subscription-billing/backend/src/accounts/jwt_utils.py)
```python
def generate_tokens(user) -> dict:
    """Generate access + refresh token pair."""
    access_payload = {
        "user_id": str(user.id),
        "email": user.email,
        "role": user.role,
        "type": "access",
        "iat": now,
        "exp": now + ACCESS_TOKEN_LIFETIME,  # e.g. 15 min
        "jti": uuid4().hex,
    }
    refresh_payload = {
        "user_id": str(user.id),
        "type": "refresh",
        "iat": now,
        "exp": now + REFRESH_TOKEN_LIFETIME,  # e.g. 7 days
        "jti": uuid4().hex,
    }
    return {
        "access": jwt.encode(access_payload, SECRET_KEY, algorithm="HS256"),
        "refresh": jwt.encode(refresh_payload, SECRET_KEY, algorithm="HS256"),
    }

def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises jwt.InvalidTokenError on failure."""
    return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
```
- `role` is embedded directly in the access token — the middleware reads it without a DB query.
- `jti` (JWT ID) allows future token blacklisting if needed.
- Separate `type` field prevents refresh tokens being used as access tokens.

#### [NEW] [`backend/src/accounts/jwt_settings.py`](file:///d:/takehome-16-subscription-billing/backend/src/accounts/jwt_settings.py)
Centralized JWT configuration pulled from env vars:
- `JWT_SECRET_KEY` (falls back to `DJANGO_SECRET_KEY`)
- `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` (default: 30)
- `JWT_REFRESH_TOKEN_LIFETIME_DAYS` (default: 7)
- `JWT_ALGORITHM` (default: "HS256")

---

### Component 3: Authentication Middleware

Intercepts every request, extracts the JWT from the `Authorization: Bearer <token>` header, validates it, and attaches the authenticated user context to the request object.

#### [NEW] [`backend/src/accounts/middleware.py`](file:///d:/takehome-16-subscription-billing/backend/src/accounts/middleware.py)
```python
class JWTAuthenticationMiddleware:
    """
    Reads Bearer token from Authorization header.
    On success: sets request.user_id, request.user_role, request.user_email.
    On failure or absence: sets request.user_id = None (anonymous).
    Does NOT enforce auth — individual views/decorators decide if auth is required.
    """
    def __call__(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = decode_token(token)
                if payload.get("type") != "access":
                    raise InvalidTokenError("Not an access token")
                request.user_id = payload["user_id"]
                request.user_role = payload["role"]
                request.user_email = payload["email"]
            except (InvalidTokenError, KeyError):
                request.user_id = None
                request.user_role = None
        else:
            request.user_id = None
            request.user_role = None
        return self.get_response(request)
```

---

### Component 4: Authorization Decorators

Reusable decorators for view-level RBAC enforcement.

#### [NEW] [`backend/src/accounts/decorators.py`](file:///d:/takehome-16-subscription-billing/backend/src/accounts/decorators.py)
```python
def login_required(view_func):
    """Rejects unauthenticated requests with 401."""

def role_required(*allowed_roles):
    """Rejects requests from users whose role is not in allowed_roles with 403.
    Returns: {"error": "Forbidden", "message": "..."} explaining why."""

def billing_admin_required(view_func):
    """Shorthand for role_required(Role.BILLING_ADMIN)."""

def owner_or_collaborator_required(view_func):
    """For subscription-scoped endpoints: checks request.user_id is
    the subscription owner or a collaborator. Billing admins pass automatically.
    Account managers without ownership/collaboration get 403."""
```
Each decorator returns a JSON response with an explanatory message on rejection — never a silent redirect.

---

### Component 5: Auth API Views (Login / Register / Refresh / Me)

#### [NEW] [`backend/src/accounts/views.py`](file:///d:/takehome-16-subscription-billing/backend/src/accounts/views.py)

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `POST /api/auth/register/` | POST | None | Create a new user (email, password, role). Returns tokens. |
| `POST /api/auth/login/` | POST | None | Email + password login. Returns access + refresh tokens. |
| `POST /api/auth/refresh/` | POST | None | Exchange a valid refresh token for a new access token. |
| `GET /api/auth/me/` | GET | Required | Returns the current user's profile (id, email, role). |

Request/response validation is done manually (no DRF serializers) — parse `json.loads(request.body)`, validate fields, return `JsonResponse`.

#### [NEW] [`backend/src/accounts/urls.py`](file:///d:/takehome-16-subscription-billing/backend/src/accounts/urls.py)
```python
urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.login, name="login"),
    path("refresh/", views.refresh, name="refresh"),
    path("me/", views.me, name="me"),
]
```

---

### Component 6: PostgreSQL Database Configuration

Switch from SQLite to PostgreSQL in Django settings.

#### [MODIFY] [`backend/src/config/settings.py`](file:///d:/takehome-16-subscription-billing/backend/src/config/settings.py)

Changes:
1. **Database engine**: `django.db.backends.postgresql` with env-driven config (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`).
2. **`AUTH_USER_MODEL`**: Set to `"accounts.User"`.
3. **`INSTALLED_APPS`**: Add `"src.accounts"`.
4. **Middleware**: Add `"src.accounts.middleware.JWTAuthenticationMiddleware"` after `CommonMiddleware`.
5. **Remove** session-related middleware (`SessionMiddleware`, `AuthenticationMiddleware`) since we use stateless JWT — or keep them for Django admin access only.
6. **JWT settings**: Add `JWT_SECRET_KEY`, `JWT_ACCESS_TOKEN_LIFETIME`, `JWT_REFRESH_TOKEN_LIFETIME` from env.

#### [MODIFY] [`backend/src/config/urls.py`](file:///d:/takehome-16-subscription-billing/backend/src/config/urls.py)
Wire up the auth URLs:
```python
urlpatterns = [
    path("health/", health, name="health"),
    path("api/auth/", include("src.accounts.urls")),
]
```

#### [MODIFY] [`backend/.env`](file:///d:/takehome-16-subscription-billing/backend/.env)
Add PostgreSQL connection variables:
```
DB_NAME=subscription_billing
DB_USER=postgres
DB_PASSWORD=<your-password>
DB_HOST=localhost
DB_PORT=5432
JWT_SECRET_KEY=<long-random-secret>
```

#### [MODIFY] [`requirements.txt`](file:///d:/takehome-16-subscription-billing/requirements.txt)
Add:
```
psycopg2-binary==2.9.9
PyJWT==2.9.0
```

---

### Component 7: RLS Database Middleware (SET LOCAL)

This is the critical bridge between JWT auth and PostgreSQL RLS. Every request's DB transaction must have `app.user_id` and `app.role` set as session variables so RLS policies can read them.

#### [NEW] [`backend/src/accounts/db_rls_middleware.py`](file:///d:/takehome-16-subscription-billing/backend/src/accounts/db_rls_middleware.py)
```python
class RLSMiddleware:
    """
    After JWTAuthenticationMiddleware has parsed the token:
    1. Wraps the request in a DB transaction.
    2. Executes SET LOCAL app.user_id = '...'; SET LOCAL app.role = '...';
    3. All subsequent ORM queries in this request see the RLS-filtered data.
    4. Transaction commits on success, rolls back on exception.

    For unauthenticated requests (no valid JWT), sets app.role = 'anonymous'
    and app.user_id = '' — RLS policies will deny everything.
    """
    def __call__(self, request):
        user_id = getattr(request, "user_id", None) or ""
        role = getattr(request, "user_role", None) or "anonymous"

        with connection.cursor() as cursor:
            # SET LOCAL scopes the variable to the current transaction only.
            # This is critical for connection pooling safety.
            cursor.execute("SET LOCAL app.user_id = %s", [str(user_id)])
            cursor.execute("SET LOCAL app.role = %s", [role])

        response = self.get_response(request)
        return response
```

> [!WARNING]
> **`SET LOCAL` only works inside a transaction.** We need Django's `ATOMIC_REQUESTS = True` in the database config, or wrap this in `transaction.atomic()`. The plan uses `ATOMIC_REQUESTS = True` for simplicity.

---

### Component 8: RLS Policies (SQL Migration)

Raw SQL migration to enable RLS on all billing tables and create the policies. This migration runs **after** the model migrations.

#### [NEW] [`backend/src/accounts/migrations/0002_rls_policies.py`](file:///d:/takehome-16-subscription-billing/backend/src/accounts/migrations/0002_rls_policies.py)

This is a `RunSQL` migration with the following policies:

**Subscriptions table:**

| Policy | Target | Operation | Logic |
|--------|--------|-----------|-------|
| `rls_sub_admin_all` | `billing_admin` | ALL | `current_setting('app.role') = 'billing_admin'` |
| `rls_sub_owner_select` | `account_manager` | SELECT | `owner_id = current_setting('app.user_id')::UUID` |
| `rls_sub_collab_select` | `account_manager` | SELECT | `EXISTS (SELECT 1 FROM collaborators WHERE sub_id = id AND user_id = current_setting('app.user_id')::UUID)` |
| `rls_sub_owner_update` | `account_manager` | UPDATE | Owner/collaborator check + `archived_at IS NOT DISTINCT FROM` old value (prevents archiving) |
| `rls_sub_manager_insert` | `account_manager` | INSERT | `current_setting('app.role') IN ('billing_admin','account_manager')` — managers can create |

**Invoices table:**

| Policy | Target | Operation | Logic |
|--------|--------|-----------|-------|
| `rls_inv_admin_all` | `billing_admin` | ALL | Role check |
| `rls_inv_owner_select` | `account_manager` | SELECT | Join through subscription to check ownership/collaboration |
| `rls_inv_owner_insert` | `account_manager` | INSERT | Same join — managers can only create invoices for their subscriptions |

**Collaborators table:**

| Policy | Target | Operation | Logic |
|--------|--------|-----------|-------|
| `rls_collab_admin_all` | `billing_admin` | ALL | Only admins can INSERT/DELETE collaborators |
| `rls_collab_manager_select` | `account_manager` | SELECT | Managers can see collaborations they're part of |

**Supporting SQL:**
```sql
-- Enable RLS on each table (RLS is off by default)
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE collaborators ENABLE ROW LEVEL SECURITY;

-- Force RLS even for table owners (the Django DB user)
ALTER TABLE subscriptions FORCE ROW LEVEL SECURITY;
ALTER TABLE invoices FORCE ROW LEVEL SECURITY;
ALTER TABLE collaborators FORCE ROW LEVEL SECURITY;
```

**Critical index for RLS performance:**
```sql
-- Covering index to prevent sequential scans in the collaborators subquery
CREATE INDEX idx_collaborators_sub_user ON collaborators(subscription_id, user_id);
CREATE INDEX idx_subscriptions_owner ON subscriptions(owner_id);
CREATE INDEX idx_invoices_subscription ON invoices(subscription_id);
```

---

### Component 9: Seed Data Management Command

#### [NEW] [`backend/src/accounts/management/commands/seed_users.py`](file:///d:/takehome-16-subscription-billing/backend/src/accounts/management/commands/seed_users.py)
Creates demo users for testing:
```
| Role            | Email                    | Password   |
|-----------------|--------------------------|------------|
| Billing Admin   | admin@example.com        | admin123   |
| Account Manager | manager1@example.com     | manager123 |
| Account Manager | manager2@example.com     | manager123 |
```

---

### Component 10: File Structure Summary

After implementation, the `backend/src/accounts/` directory will look like:

```
backend/src/accounts/
├── __init__.py
├── apps.py
├── models.py              # User model with UUID PK + role
├── managers.py            # UserManager
├── jwt_utils.py           # Token generation + decoding
├── jwt_settings.py        # Centralized JWT config
├── middleware.py           # JWT auth middleware
├── db_rls_middleware.py    # SET LOCAL middleware for RLS
├── decorators.py          # @login_required, @role_required, etc.
├── views.py               # Login, register, refresh, me
├── urls.py                # Auth URL routing
├── management/
│   └── commands/
│       └── seed_users.py  # Demo data seeding
└── migrations/
    ├── 0001_initial.py    # Auto-generated model migration
    └── 0002_rls_policies.py  # Raw SQL RLS policies
```

---

## Verification Plan

### Automated Tests

#### [NEW] [`backend/src/accounts/tests.py`](file:///d:/takehome-16-subscription-billing/backend/src/accounts/tests.py)
Test cases covering:

1. **Registration**: Valid registration returns tokens; duplicate email returns 400; missing fields return 400.
2. **Login**: Correct credentials return tokens; wrong password returns 401; non-existent user returns 401.
3. **Token validation**: Expired tokens return 401; malformed tokens return 401; refresh tokens cannot be used as access tokens.
4. **Token refresh**: Valid refresh token returns new access token; expired refresh token returns 401.
5. **`/me` endpoint**: Returns correct user data with valid token; returns 401 without token.
6. **Role enforcement (Application layer)**:
   - Billing admin can access admin-only endpoints → 200
   - Account manager accessing admin-only endpoint → 403 with explanatory message
   - Account manager accessing own subscription → 200
   - Account manager accessing another's subscription → 403
7. **RLS enforcement (Database layer)**:
   - Direct ORM query with `app.role = 'account_manager'` set → only sees own/collaborated subscriptions
   - Direct ORM query with `app.role = 'billing_admin'` → sees all subscriptions
   - Account manager cannot see or modify subscriptions they don't own/collaborate on even if application middleware is bypassed

```bash
cd backend && python main.py test src.accounts
```

### Manual Verification

1. Start the Django dev server, hit `POST /api/auth/register/` and `POST /api/auth/login/` with curl/Postman.
2. Use the returned JWT to hit `GET /api/auth/me/` — confirm user data.
3. Attempt to hit a billing-admin-only endpoint with an account_manager JWT — confirm 403.
4. Verify RLS by connecting directly to PostgreSQL and running `SET LOCAL app.role = 'account_manager'; SET LOCAL app.user_id = '<manager-uuid>'; SELECT * FROM subscriptions;` — confirm only owned/collaborated rows are returned.

```