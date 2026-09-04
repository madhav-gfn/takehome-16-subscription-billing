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
Where rules that compare old and new values are enforced

- **Chose:** PostgreSQL `BEFORE UPDATE` triggers for paid-invoice immutability, the issued-invoice amount and period lock, the append-only audit trail, and the restriction that only a billing admin may archive a subscription or change its owner.
- **Rejected:** Expressing those rules in RLS `WITH CHECK` clauses, which is what I originally wrote.
- **Why:** An RLS policy only ever sees the resulting row. It has no `OLD`, so a rule like "this column must not change" cannot be expressed in one. I wrote `AND (archived_at IS NOT DISTINCT FROM archived_at)` in `rls_policies.sql` believing it stopped account managers from archiving. It compares the column to itself, is always true, and enforces nothing. Auditing that file before applying it also turned up two more problems: `current_setting('app.user_id', true)::UUID` raises on anonymous requests where the middleware sets the variable to the empty string, and `FORCE ROW LEVEL SECURITY` means management commands (which run with no session variables set) see and write nothing, silently. All three fail quietly. The general rule I settled on: RLS decides which rows a session may touch; triggers decide what may change about a row.
- **Later reversed:** The original RLS-only approach. Reversed to triggers after discovering the three bugs above during the `doc2/` audit session.

## Decision 7
Single-writer pattern for invoice status

- **Chose:** One function, `services/invoices.py:transition()`, is the only place in the entire codebase that assigns `Invoice.status`. Every caller goes through it.
- **Rejected:** Letting views or serializers set `status` directly and just validating transitions in a model `save()` override.
- **Why:** If status changes happen in multiple places, then the invariant "every status change produces exactly one audit event" depends on every caller remembering to also create the event. That is discipline, not structure. With a single writer, the invariant is true by construction. You can verify it with `grep -rn "\.status = " src/billing/` and you will find exactly one hit. This also makes concurrency safe because `transition()` uses `select_for_update()` to take a row lock before reading the current status, so two people clicking "mark as paid" at the same time will not both succeed.

## Decision 8
Alert re-arming via dismissed_for_due_date

- **Chose:** A separate `alert_dismissals` table with a `dismissed_for_due_date` column. The alert query filters for invoices where either no dismissal exists, or the dismissal's recorded due date does not match the invoice's current due date.
- **Rejected:** A boolean `alert_dismissed` column on the invoice itself.
- **Why:** Two problems with a boolean on the invoice. First, the brief says a paid invoice is immutable, so you cannot set a flag on it, which means dismissing an alert on a paid overdue invoice would require a hole in the immutability trigger. Every hole in an immutability rule is a place the rule eventually leaks. Second, a boolean does not carry enough information for re-arming. The brief says the alert should return if the due date "later changes and then passes again." With just a boolean, any due date change would need to reset the flag, and you would need another trigger or hook to detect that. With `dismissed_for_due_date`, the check is a simple comparison: `dismissed_for_due_date != invoice.due_date` means the world has changed since the dismissal, so the alert comes back.

## Decision 9
Seed data with relative dates

- **Chose:** The `seed_demo` management command generates invoices with dates relative to `today`, not hardcoded dates. The demo data always has some invoices due last month (overdue), some due this month (current), and some due next month (upcoming).
- **Rejected:** Hardcoded dates like `2026-08-01`.
- **Why:** Hardcoded dates rot. If someone reviews the submission a week after I submit it, every "current month" invoice would be in the past and the dashboard would show zero for "invoices issued this month." Relative dates mean the demo always looks fresh. The downside is that the seed data is not deterministic across runs on different dates, but for a demo that is fine.

## Decision 10
Dashboard aggregation: separate queries per section

- **Chose:** The dashboard endpoint runs four or five small queries (headline numbers, by-status breakdown, by-plan breakdown, weekly revenue), each filtered by indexed columns, and returns them as one JSON response.
- **Rejected:** One large query with multiple joins and subqueries, or client-side aggregation from the full invoice list.
- **Why:** A single mega-query is harder to read, harder to index, and harder to debug when one number is wrong. Separate queries mean each one can be optimised independently (the weekly revenue query uses `paid_at`, the headline numbers use `status` and `issued_at`), and if one is slow you can see it in the query log without untangling a join tree. The total round-trip cost of five simple queries is lower than one complex query with multiple aggregation levels, and the database is on localhost anyway so latency per query is sub-millisecond.

