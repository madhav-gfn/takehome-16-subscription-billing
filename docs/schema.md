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

## Final schema (4 September 2026)

Everything above was the design written before migration. Below is what actually got migrated and is running in PostgreSQL.

### What changed from the original design

- `invoices` uses `period_start` and `period_end`, not `billing_period_start` / `billing_period_end`. Shorter names, same purpose.
- `invoices` gained `issued_at` and `paid_at` (timestamps), denormalised from the event trail so the dashboard does not need to join `invoice_events` for monthly aggregations.
- `invoices` gained `created_by` (FK to users). Needed to show who created the invoice in the timeline.
- `collaborators` gained `added_by` (FK to users). Records which billing admin granted the access.
- `credit_notes` gained `created_by` (FK to users). Records who issued the credit note.
- A sixth table, `alert_dismissals`, was added for overdue alert dismissal. It is separate from `invoices` because recording a dismissal must not UPDATE an invoice that may be immutable.

### Alert Dismissals (`alert_dismissals`)
*Status: Migrated and active*

- `id` -- `UUID` (Primary Key)
- `invoice_id` -- `UUID` (OneToOne FK -> `invoices.id`, CASCADE)
- `dismissed_for_due_date` -- `DATE` (the due date at the time of dismissal; if the invoice's due date later changes and passes again, the alert reappears)
- `dismissed_by_id` -- `UUID` (FK -> `users.id`, SET NULL)
- `dismissed_at` -- `TIMESTAMP WITH TIME ZONE`

### Constraints actually in the database

Beyond the ones listed in the original design above:

**CHECK constraints:**
- `sub_price_positive`: `price > 0` on subscriptions
- `inv_amount_positive`: `amount > 0` on invoices
- `inv_period_ordered`: `period_start <= period_end`
- `inv_void_has_reason`: status is void if and only if void_reason is not null
- `cn_amount_positive`: `amount > 0` on credit_notes

**Partial unique index:**
- `uq_invoice_period`: unique on `(subscription_id, period_start, period_end)` where status is not void. This means voiding an invoice frees the period so a corrected one can be generated.

**Triggers (raw SQL in migration `0003_rls_and_triggers`):**
- `trg_invoice_immutable`: BEFORE UPDATE on `invoices`. If the existing status is `paid`, rejects the update with an error message. This is the database-tier enforcement of Goal 4's immutability rule.
- `trg_invoice_events_append_only`: BEFORE UPDATE OR DELETE on `invoice_events`. Always rejects. The timeline is physically write-once.

### Updated denormalization

Two deliberate denormalizations exist in the final schema:

1. `invoices.issued_at` and `invoices.paid_at` duplicate information that could be derived from `invoice_events` (by finding the status_changed event where new_status is "issued" or "paid"). The duplicate exists so the dashboard query "revenue collected this month" is `SELECT SUM(amount) FROM invoices WHERE paid_at >= '2026-09-01'` instead of a subquery join against the events table. The service function `transition()` writes both the invoice field and the event in the same transaction, so they cannot drift.

2. `alert_dismissals.dismissed_for_due_date` duplicates the invoice's `due_date` at the moment of dismissal. This is the re-arming mechanism: the alert query checks `WHERE dismissed_for_due_date != invoice.due_date OR dismissal IS NULL`, so changing the due date and having it pass again causes the alert to return even though the admin previously dismissed it.

### Updated scaling risks

At 100x volume (20,000 customers, ~240,000 invoices/year), three new concerns would appear:

4. **Bulk generation throughput**: The current implementation loops through subscriptions in Python and creates invoices one at a time inside a single transaction. At 20,000 subscriptions this could hit statement timeout. Mitigation: batch the loop into chunks of 500 with separate transactions, or move to a `INSERT ... SELECT` pattern.
5. **Audit trail growth**: Every status change creates an event row. At 240k invoices with an average of 3 events each, that is 720k rows/year. Not a problem for PostgreSQL, but the `idx_evt_invoice_time` index would need periodic `REINDEX` on high-write workloads.
6. **RLS policy cost on the invoice list page**: The `visible_to` queryset does a subquery against `collaborators` for account managers. With 20,000 subscriptions and many collaborator rows, this subquery could become expensive. Mitigation: materialise the user-to-subscription mapping into a flat table refreshed on collaborator changes.

