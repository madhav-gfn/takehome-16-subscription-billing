# Decisions

Log the decisions that actually shaped this codebase — the ones where a real alternative existed and
you picked one. At least five entries. For each: what you chose, what you rejected, and why. At least
one entry must be a decision you later reversed — say what changed your mind. It can be any entry
below, not necessarily the last one; add a **Later reversed:** line to whichever one it is.

## Decision 1
Tech Stack

- **Chose:** Django for complete backend, ReactJS (Vite) for frontend, PostgreSQL for database.
- **Rejected:** Flask, Next.js, MongoDB, Node.js.
- **Why:** Django provides battle-tested ORM, structured migrations, security defaults, and rich ecosystem (DRF). PostgreSQL is mandatory for native Row-Level Security (RLS) support to enforce database-tier tenant/role isolation.

## Decision 2
Authentication Library & Token Strategy

- **Chose:** `djangorestframework-simplejwt` with custom claims (`role`, `email`, `user_id`) embedded directly in the JWT payload and a 24-hour access token lifecycle.
- **Rejected:** Standalone custom PyJWT handling without DRF, Django session cookies, and short-lived tokens requiring silent refresh token storage.
- **Why:** Embedding `role` and `user_id` inside the JWT payload enables our `RLSTransactionMiddleware` to extract claims and set PostgreSQL session variables instantly on every request without an extra database lookup. SimpleJWT integrates seamlessly with Django REST Framework serializers and view permissions.
- **Later reversed:** Initially designed a custom lightweight PyJWT helper without DRF dependencies to keep dependencies minimal. Reversed this decision to use `djangorestframework-simplejwt` so we have standard DRF integration, built-in password validation, clean token refresh endpoints, and unified serializer validation across all API routes.

## Decision 3
Multi-Layer Authorization & Defense-in-Depth

- **Chose:** Defense-in-depth architecture combining application-layer RBAC (DRF permissions like `IsBillingAdmin`, view decorators) with database-tier PostgreSQL Row-Level Security (RLS) policies.
- **Rejected:** Application-only permission checks (middleware or view decorators alone).
- **Why:** The specification strictly mandates that role distinctions must be server-enforced, not merely hidden in the UI. Application-level checks provide user-friendly error messages (e.g. HTTP 403 Forbidden with explanatory JSON), while PostgreSQL RLS provides an impenetrable database boundary: even if a developer makes a bug in an API endpoint, an Account Manager query physically cannot read or modify cross-tenant or unowned subscriptions.

## Decision 4
User Identification & Primary Key Architecture

- **Chose:** Custom `AbstractBaseUser` model (`accounts.User`) with `UUIDField` as primary key and `email` as the sole unique login identifier.
- **Rejected:** Default Django `auth.User` with auto-incrementing integer IDs and username requirements.
- **Why:** PostgreSQL RLS policies cast `current_setting('app.user_id')::UUID`. Using native UUID primary keys avoids awkward string/integer type casting in SQL policies and prevents ID enumeration attacks. Email is the natural login identifier for business billing workflows.

## Decision 5
Session Variable Injection & Connection Pool Safety

- **Chose:** `SET LOCAL app.user_id` and `SET LOCAL app.role` executed within a per-request `transaction.atomic()` block in `RLSTransactionMiddleware`, coupled with Django's `CONN_MAX_AGE=600`.
- **Rejected:** Session-scoped `SET app.user_id = ...` without `LOCAL`, or passing credentials in application query parameters.
- **Why:** `SET LOCAL` is strictly scoped to the active database transaction. Once the transaction commits or rolls back, the session variables are automatically purged. This prevents state leakage across requests when using connection pooling (such as PgBouncer in transaction mode or Django persistent connections).

## Decision 6
Where rules that compare a new value to an old value are enforced

- **Chose:** PostgreSQL `BEFORE UPDATE` triggers for paid-invoice immutability, the issued-invoice
  amount and period lock, append-only audit rows, and the restriction that only a billing admin may
  archive a subscription or change its owner.
- **Rejected:** Expressing those rules in RLS `WITH CHECK` clauses, which is what I originally wrote.
- **Why:** An RLS policy only ever sees the resulting row. It has no `OLD`, so a rule of the form
  "this column must not change" is not expressible in one at all.
- **Later reversed:** I wrote `AND (archived_at IS NOT DISTINCT FROM archived_at)` in
  `rls_policies.sql` believing it stopped account managers from archiving. It compares the column to
  itself, is always true, and enforces nothing. Auditing that file before applying it also turned up
  two further problems: `current_setting('app.user_id', true)::UUID` raises on anonymous requests,
  where the middleware sets the variable to the empty string, and `FORCE ROW LEVEL SECURITY` means
  management commands — which run with no session variables set — see and write nothing, silently.
  All three fail quietly rather than loudly, which is why testing had not caught them. The general
  rule I now hold to: RLS decides which rows a session may touch; triggers decide what may change
  about a row.
