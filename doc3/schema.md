# Schema

## Current state

The authentication and user schema (`users` table) is fully defined and migrated to PostgreSQL (`accounts.0001_initial`). The billing domain models (subscriptions, invoices, collaborators, credit notes, invoice events) are planned below along with their database-tier Row-Level Security (RLS) policies.

## Core tables

### Users (`users`)
*Status: Migrated and active in PostgreSQL*

- `id` — `UUID` (Primary Key, default `uuid.uuid4`)
- `email` — `VARCHAR(255)` (Unique, indexed, login identifier)
- `password` — `VARCHAR(128)` (PBKDF2 SHA256 hashed password)
- `role` — `VARCHAR(20)` (Enum: `billing_admin`, `account_manager`)
- `is_active` — `BOOLEAN` (Default `TRUE`)
- `last_login` — `TIMESTAMP WITH TIME ZONE` (Nullable)
- `created_at` — `TIMESTAMP WITH TIME ZONE` (Auto-now-add)
- `updated_at` — `TIMESTAMP WITH TIME ZONE` (Auto-now)

### Subscriptions (`subscriptions`)
*Status: Designed with RLS policies in `src/accounts/rls_policies.sql`*

- `id` — `UUID` (Primary Key)
- `customer_name` — `VARCHAR(255)`
- `billing_email` — `VARCHAR(255)`
- `plan_name` — `VARCHAR(100)`
- `billing_cycle` — `VARCHAR(20)` (`monthly` or `annual`)
- `price` — `DECIMAL(12, 2)` (Exact decimal representation for financial accuracy)
- `start_date` — `DATE`
- `owner_id` — `UUID` (Foreign Key -> `users.id`, indexed)
- `archived_at` — `TIMESTAMP WITH TIME ZONE` (Nullable; indicates archived state without destroying history)
- `created_at` — `TIMESTAMP WITH TIME ZONE`
- `updated_at` — `TIMESTAMP WITH TIME ZONE`

### Subscription Collaborators (`collaborators`)
*Status: Designed with RLS policies in `src/accounts/rls_policies.sql`*

- `id` — `UUID` (Primary Key)
- `subscription_id` — `UUID` (Foreign Key -> `subscriptions.id`, indexed)
- `user_id` — `UUID` (Foreign Key -> `users.id`, indexed)
- `created_at` — `TIMESTAMP WITH TIME ZONE`
- *Constraints*: Unique constraint on `(subscription_id, user_id)`

### Invoices (`invoices`)
*Status: Designed with RLS policies in `src/accounts/rls_policies.sql`*

- `id` — `UUID` (Primary Key)
- `subscription_id` — `UUID` (Foreign Key -> `subscriptions.id`, indexed)
- `billing_period_start` — `DATE`
- `billing_period_end` — `DATE`
- `amount` — `DECIMAL(12, 2)` (Exact decimal amount owed)
- `due_date` — `DATE`
- `status` — `VARCHAR(20)` (`draft`, `issued`, `paid`, `void`)
- `void_reason` — `TEXT` (Nullable; mandatory if status is `void`)
- `created_at` — `TIMESTAMP WITH TIME ZONE`
- `updated_at` — `TIMESTAMP WITH TIME ZONE`

### Credit Notes (`credit_notes`)
*Status: Designed with RLS policies in `src/accounts/rls_policies.sql`*

- `id` — `UUID` (Primary Key)
- `invoice_id` — `UUID` (Foreign Key -> `invoices.id`, indexed)
- `reason` — `TEXT` (Mandatory explanation)
- `amount` — `DECIMAL(12, 2)` (Exact decimal correction amount)
- `created_at` — `TIMESTAMP WITH TIME ZONE`

### Invoice Audit Events (`invoice_events`)
*Status: Designed with RLS policies in `src/accounts/rls_policies.sql`*

- `id` — `UUID` (Primary Key)
- `invoice_id` — `UUID` (Foreign Key -> `invoices.id`, indexed)
- `event_type` — `VARCHAR(50)` (`created`, `status_changed`, `due_date_changed`, `credit_note_issued`, `note_added`)
- `old_status` — `VARCHAR(20)` (Nullable)
- `new_status` — `VARCHAR(20)` (Nullable)
- `actor_id` — `UUID` (Foreign Key -> `users.id`)
- `details` — `JSONB` (Metadata: reasons, notes, amounts)
- `created_at` — `TIMESTAMP WITH TIME ZONE`

---

## Relationship plan

- **Users to Subscriptions (Ownership)**: One-to-Many (`users.id` -> `subscriptions.owner_id`).
- **Users to Subscriptions (Collaboration)**: Many-to-Many via explicit `collaborators` mapping table with unique constraint `(subscription_id, user_id)`.
- **Subscriptions to Invoices**: One-to-Many (`subscriptions.id` -> `invoices.subscription_id`).
- **Invoices to Credit Notes**: One-to-Many (`invoices.id` -> `credit_notes.invoice_id`).
- **Invoices to Audit Events**: One-to-Many (`invoices.id` -> `invoice_events.invoice_id`). Append-only timeline that cannot be edited or deleted.

---

## Database vs Application constraints

### Database Constraints (Enforced at DB tier)
- `email` uniqueness on `users`.
- Foreign key integrity across all related tables with `CASCADE` or `PROTECT`.
- Non-null constraints on financial amounts (`price`, `amount`), dates, and role fields.
- Decimal precision (`DECIMAL(12, 2)`) to avoid IEEE floating point inaccuracy.
- PostgreSQL Row-Level Security (RLS) policies enforcing row visibility and modification rules based on `current_setting('app.role')` and `current_setting('app.user_id')`.
- Covering indexes:
  - `idx_collaborators_sub_user` on `collaborators(subscription_id, user_id)`
  - `idx_subscriptions_owner` on `subscriptions(owner_id)`
  - `idx_invoices_subscription` on `invoices(subscription_id)`
  - `idx_invoices_status` on `invoices(status)`

### Application Logic Constraints (Enforced in Django/DRF)
- Only `billing_admin` users may invite/remove collaborators or archive subscriptions.
- FSM state transitions on invoices (`Draft -> Issued -> Paid`, `Draft/Issued -> Void`).
- Immutability of Paid invoices (no field modifications allowed; corrections only via credit notes).
- Due date changes permitted on Draft and Issued invoices, but forbidden on Paid/Void invoices.
- Rich HTTP 403 explanatory error messages for illegal actions.

---

## Denormalization decisions

The design stays strictly normalized to preserve auditability and financial data integrity:
- Subscription collaborator links live in a dedicated join table to keep permission history clear.
- Credit notes stand as independent records referencing the original invoice rather than mutating original invoice totals.
- Audit events are strictly append-only rows.

---

## Scaling risk at 100x volume

At 100x volume, the main bottlenecks and mitigations are:
1. **RLS Subquery Overhead**: Account manager queries that join `collaborators` across large datasets could force sequential scans. *Mitigation: Covering compound index `(subscription_id, user_id)`.*
2. **Invoice Filtering & Search**: Text search across customer name and billing email with status/due-date filters. *Mitigation: Server-side pagination, compound indexes on `(status, due_date)`, and PostgreSQL `pg_trgm` or Gin indexes on email/name if search becomes hot.*
3. **Dashboard Aggregations**: Dynamic grouping for 8-week revenue charts. *Mitigation: Aggregation queries filtered by indexed date ranges, or PostgreSQL materialized views refreshed periodically.*

---

## Status — 2 September 2026

`users` is the only table that exists in PostgreSQL. Migration `accounts.0001_initial` is applied.

Everything below "Core tables" from `subscriptions` onward is design, not schema — no migration has
been written for it and no RLS policy has been applied. `doc2/03-database-schema.md` carries the
version that will actually be migrated; it differs from the design above in four confirmed ways:

- `invoices` gains `issued_at` and `paid_at`, denormalised from the event trail so the dashboard's
  monthly figures are indexed range scans rather than joins against `invoice_events`.
- The uniqueness rule on `(subscription, period_start, period_end)` is a **partial** unique index
  excluding voided invoices, so voiding a wrong invoice frees the period for a corrected one.
- A sixth table, `alert_dismissals`, holds the overdue-alert dismissal. It is separate from
  `invoices` because recording a dismissal must not UPDATE an invoice that may be immutable.
- Immutability and the archive restriction move from RLS into `BEFORE UPDATE` triggers. See
  decision 6.
