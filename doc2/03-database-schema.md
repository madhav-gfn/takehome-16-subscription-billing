# 03 — Database Schema

Target: PostgreSQL 15+. All billing tables live in the new `src.billing` app (Django label
`billing`). The existing `users` table from `src.accounts` is unchanged.

## 1. Table: `subscriptions`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `UUID` | no | `uuid4()` | PK |
| `customer_name` | `VARCHAR(255)` | no | | Goal 2; searched by Goal 6 |
| `billing_email` | `VARCHAR(255)` | no | | Goal 2; searched by Goal 6. Validated as an email, not unique — one customer can hold several subscriptions |
| `plan_name` | `VARCHAR(100)` | no | | Free text, not an FK. See §7 |
| `billing_cycle` | `VARCHAR(10)` | no | | `monthly` \| `annual` |
| `price` | `NUMERIC(12,2)` | no | | `CHECK (price > 0)` |
| `start_date` | `DATE` | no | | Anchors all period arithmetic |
| `owner_id` | `UUID` | no | | FK → `users(id)` `ON DELETE PROTECT` |
| `archived_at` | `TIMESTAMPTZ` | yes | `NULL` | Non-null ⇒ archived |
| `created_at` | `TIMESTAMPTZ` | no | `now()` | |
| `updated_at` | `TIMESTAMPTZ` | no | `now()` | `auto_now` |

Constraints and indexes:
```sql
CHECK (price > 0)
CHECK (billing_cycle IN ('monthly','annual'))
CREATE INDEX idx_sub_owner        ON subscriptions(owner_id);
CREATE INDEX idx_sub_archived     ON subscriptions(archived_at) WHERE archived_at IS NULL;
CREATE INDEX idx_sub_customer_trgm ON subscriptions USING gin (customer_name gin_trgm_ops);
CREATE INDEX idx_sub_email_trgm    ON subscriptions USING gin (billing_email gin_trgm_ops);
```
The two trigram indexes require `CREATE EXTENSION IF NOT EXISTS pg_trgm;` in the migration. They
exist for Goal 6's substring search (`ILIKE '%term%'`, which no B-tree index can serve). At a few
hundred subscriptions a sequential scan would be fine — they are there because the brief asks what
breaks at 100× and this is the honest answer to that for search. If the extension is unavailable on
the chosen host, the migration degrades to skipping them; the query is unchanged.

`ON DELETE PROTECT` on `owner_id`: deleting a user who owns subscriptions must fail loudly. There is
no user-deletion endpoint, so this is a guard against a future mistake, not a workflow.

## 2. Table: `collaborators`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `UUID` | no | PK |
| `subscription_id` | `UUID` | no | FK → `subscriptions(id)` `ON DELETE CASCADE` |
| `user_id` | `UUID` | no | FK → `users(id)` `ON DELETE CASCADE` |
| `added_by_id` | `UUID` | yes | FK → `users(id)` `ON DELETE SET NULL`. Who granted access — a BA |
| `created_at` | `TIMESTAMPTZ` | no | |

```sql
UNIQUE (subscription_id, user_id)
CREATE INDEX idx_collab_sub_user ON collaborators(subscription_id, user_id);  -- RLS subquery
CREATE INDEX idx_collab_user     ON collaborators(user_id);                   -- "my subscriptions"
```

Two indexes, not one. `idx_collab_sub_user` serves the RLS `EXISTS` check (given a subscription,
is this user on it). `idx_collab_user` serves Goal 5's "one list of every subscription where they
are owner or collaborator" (given a user, which subscriptions). The composite cannot serve the
second — its leading column is the wrong one.

`CASCADE` on both FKs: a collaborator row is pure access-grant metadata with no historical value.
Contrast with `owner_id`, which is PROTECTed because it is part of the subscription's identity.

## 3. Table: `invoices`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `UUID` | no | `uuid4()` | PK |
| `subscription_id` | `UUID` | no | | FK → `subscriptions(id)` `ON DELETE PROTECT` |
| `period_start` | `DATE` | no | | |
| `period_end` | `DATE` | no | | |
| `amount` | `NUMERIC(12,2)` | no | | `CHECK (amount > 0)` |
| `due_date` | `DATE` | no | | |
| `status` | `VARCHAR(10)` | no | `'draft'` | `draft`\|`issued`\|`paid`\|`void` |
| `void_reason` | `TEXT` | yes | `NULL` | Required iff status is void |
| `issued_at` | `TIMESTAMPTZ` | yes | `NULL` | Set on the draft→issued transition |
| `paid_at` | `TIMESTAMPTZ` | yes | `NULL` | Set on the issued→paid transition |
| `created_by_id` | `UUID` | yes | | FK → `users(id)` `ON DELETE SET NULL` |
| `created_at` | `TIMESTAMPTZ` | no | `now()` | |
| `updated_at` | `TIMESTAMPTZ` | no | `now()` | |

```sql
CHECK (amount > 0)
CHECK (period_start <= period_end)
CHECK (status IN ('draft','issued','paid','void'))
CHECK ((status = 'void') = (void_reason IS NOT NULL AND length(trim(void_reason)) > 0))

CREATE UNIQUE INDEX uq_invoice_period
    ON invoices(subscription_id, period_start, period_end)
    WHERE status <> 'void';                            -- I-4, partial

CREATE INDEX idx_inv_sub          ON invoices(subscription_id);
CREATE INDEX idx_inv_status_due   ON invoices(status, due_date);   -- overdue + Goal 6 sort
CREATE INDEX idx_inv_due          ON invoices(due_date);
CREATE INDEX idx_inv_paid_at      ON invoices(paid_at) WHERE paid_at IS NOT NULL;
CREATE INDEX idx_inv_issued_at    ON invoices(issued_at) WHERE issued_at IS NOT NULL;
```

`ON DELETE PROTECT` on `subscription_id`: invoice history outlives everything. Subscriptions are
archived, never deleted, and there is no delete endpoint for either.

### The `issued_at` / `paid_at` denormalisation

Both are derivable from `invoice_events` (A-08, A-09). They are stored anyway, and this is the one
deliberate denormalisation in the schema — `docs/schema.md` asks for exactly this and this is the
entry.

*Why:* the dashboard's "issued this month" and "revenue collected this month" would otherwise be a
join to `invoice_events` filtered on `new_status`, aggregated by month, on every dashboard load.
With the columns, both are an indexed range scan on `invoices`.
*What it costs:* two columns that can theoretically disagree with the event trail.
*How that is prevented:* the transition service is the only code that writes `status`, and it writes
the column and the event in the same statement block inside one transaction. The event trail remains
the source of truth; these are a cache of it. A `manage.py verify_invoice_timestamps` check command
(Session 6, if time permits) re-derives both from events and reports drift.

## 4. Table: `credit_notes`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `UUID` | no | PK |
| `invoice_id` | `UUID` | no | FK → `invoices(id)` `ON DELETE PROTECT` |
| `amount` | `NUMERIC(12,2)` | no | `CHECK (amount > 0)` |
| `reason` | `TEXT` | no | `CHECK (length(trim(reason)) > 0)` |
| `created_by_id` | `UUID` | yes | FK → `users(id)` `ON DELETE SET NULL` |
| `created_at` | `TIMESTAMPTZ` | no | |

```sql
CREATE INDEX idx_cn_invoice ON credit_notes(invoice_id);
```
Immutable: no UPDATE or DELETE policy, plus the trigger in §5.

## 5. Table: `invoice_events`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `UUID` | no | PK |
| `invoice_id` | `UUID` | no | FK → `invoices(id)` `ON DELETE PROTECT` |
| `event_type` | `VARCHAR(32)` | no | Closed set — see [02](02-domain-model.md) §7 |
| `old_status` | `VARCHAR(10)` | yes | Only on `status_changed` |
| `new_status` | `VARCHAR(10)` | yes | Only on `status_changed` |
| `actor_id` | `UUID` | yes | FK → `users(id)` `ON DELETE SET NULL` — the row survives the user |
| `details` | `JSONB` | no | Default `{}` |
| `created_at` | `TIMESTAMPTZ` | no | |

```sql
CREATE INDEX idx_evt_invoice_time ON invoice_events(invoice_id, created_at);
CREATE INDEX idx_evt_status_time  ON invoice_events(new_status, created_at)
    WHERE event_type = 'status_changed';   -- serves A-08 / A-09 verification
```

`actor_id` is `SET NULL` rather than `PROTECT` because the event must outlive the actor, and the
timeline renders "(deleted user)" rather than refusing to delete a user forever. The `details`
payload can carry a snapshot of the actor's email at event time if that becomes a real concern —
not built now, noted as the extension point.

## 6. Table: `alert_dismissals`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `UUID` | no | PK |
| `invoice_id` | `UUID` | no | FK → `invoices(id)` `ON DELETE CASCADE`, `UNIQUE` |
| `dismissed_for_due_date` | `DATE` | no | The due date the dismissal was made against — the whole mechanism (A-10) |
| `dismissed_by_id` | `UUID` | yes | FK → `users(id)` `ON DELETE SET NULL` |
| `dismissed_at` | `TIMESTAMPTZ` | no | |

`UNIQUE (invoice_id)` — one dismissal row per invoice, overwritten (upserted) on each new dismissal.
It records *the most recent* dismissal, which is all A-10's rule needs.

Separate table, not a column on `invoices`: writing a dismissal must not UPDATE the invoice, because
an invoice can be immutable (I-6/I-7) while still being dismissible. Putting the flag on `invoices`
would force the immutability trigger to carve out an exception, and every carve-out in an
immutability rule is a place the rule later leaks.

## 7. Plans are strings, not a table

`plan_name` is `VARCHAR(100)` free text. There is no `plans` table.

*Why:* the brief says "a plan name" and "a price as an exact decimal amount" as fields on the
subscription — the price lives on the subscription, so a plan carries no data of its own. A `plans`
table would be a lookup with one column, and it would add a join to the Goal 8 "breakdown by plan"
query for no gain.
*What it costs:* nothing prevents "Pro" and "pro " coexisting as distinct plans in the by-plan
breakdown. Mitigated by trimming on write and by the seed data using a fixed set; the frontend
offers a datalist of existing plan names.
*What would change the answer:* per-plan default pricing, plan-level features, or plan changes with
proration (a stretch goal). Recorded in `docs/decisions.md` as a decision with a named trigger for
revisiting it.

## 8. Immutability triggers

RLS controls *which rows* you can touch. It cannot express "this column may not change from its
previous value", because a policy has no `OLD`. Triggers do. Migration `0003_immutability.py`:

```sql
-- Paid and Void invoices are frozen entirely (I-6, A-03).
-- Issued invoices freeze period and amount but not due_date (I-7, Goal 3).
CREATE OR REPLACE FUNCTION billing_guard_invoice_update() RETURNS trigger AS $$
BEGIN
    IF OLD.status IN ('paid','void') THEN
        IF ROW(NEW.*) IS DISTINCT FROM ROW(OLD.*) THEN
            RAISE EXCEPTION 'invoice % is % and immutable', OLD.id, OLD.status
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    IF OLD.status = 'issued' AND NEW.status = 'issued' THEN
        IF NEW.amount       IS DISTINCT FROM OLD.amount
        OR NEW.period_start IS DISTINCT FROM OLD.period_start
        OR NEW.period_end   IS DISTINCT FROM OLD.period_end THEN
            RAISE EXCEPTION 'issued invoice % has a locked period and amount', OLD.id
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_invoice_guard BEFORE UPDATE ON invoices
    FOR EACH ROW EXECUTE FUNCTION billing_guard_invoice_update();
```

```sql
-- Append-only tables (I-8, I-9, A-18). Blocks BAs and superusers alike.
CREATE OR REPLACE FUNCTION billing_block_write() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% rows are append-only and cannot be % ',
        TG_TABLE_NAME, lower(TG_OP) USING ERRCODE = 'check_violation';
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_events_append_only BEFORE UPDATE OR DELETE ON invoice_events
    FOR EACH ROW EXECUTE FUNCTION billing_block_write();
CREATE TRIGGER trg_cn_append_only BEFORE UPDATE OR DELETE ON credit_notes
    FOR EACH ROW EXECUTE FUNCTION billing_block_write();
```

```sql
-- Only a billing admin may change archived_at. Replaces the tautological
-- RLS clause found in the audit (D-04).
CREATE OR REPLACE FUNCTION billing_guard_archive() RETURNS trigger AS $$
BEGIN
    IF NEW.archived_at IS DISTINCT FROM OLD.archived_at
       AND coalesce(current_setting('app.role', true), '') <> 'billing_admin' THEN
        RAISE EXCEPTION 'only a billing admin can archive or restore a subscription'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sub_guard_archive BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION billing_guard_archive();
```

A trigger firing is a **500 by default** — a `django.db.utils.InternalError`. That is not an
acceptable API response. The service layer checks the same conditions first and returns a clean
409 with an explanation; the trigger is the net beneath it, and if it ever fires it means a service
bug. `src/billing/errors.py` maps `check_violation` and `insufficient_privilege` from these triggers
to a 409/403 rather than letting a 500 escape. See [05](05-api-contract.md) §7.

## 9. Migration order

| Migration | Contents | Notes |
|---|---|---|
| `billing/0001_initial.py` | All six tables, FKs, `CHECK`s, B-tree indexes | Standard `makemigrations` output, then hand-edited to add the `CheckConstraint`s via `Meta.constraints` |
| `billing/0002_search_indexes.py` | `CREATE EXTENSION pg_trgm`, the two GIN indexes | Separate because the extension may need elevated rights on a managed host; isolating it means a failure here does not block the schema |
| `billing/0003_rls.py` | `ENABLE`/`FORCE ROW LEVEL SECURITY` + every policy | `RunSQL` with a real `reverse_sql` that drops each policy |
| `billing/0004_immutability.py` | The three trigger functions and their triggers | `RunSQL` with `DROP TRIGGER`/`DROP FUNCTION` reverse |

Every `RunSQL` gets a working `reverse_sql`. An irreversible migration is a migration you cannot
develop against, and `migrate billing zero` is how the RLS test suite resets.

`CheckConstraint` goes in `Meta.constraints` rather than raw SQL wherever Django can express it, so
`makemigrations --check` stays meaningful and the constraint is visible in the model file next to
the field it guards.

## 10. What breaks first at 100× data

For `docs/schema.md`. At 100× this is ~20k subscriptions and ~500k–1M invoices. Ranked by what
actually gives way first:

1. **The invoice list's `COUNT(*)` for pagination (Goal 6).** Postgres has no shortcut for an exact
   count of a filtered set; it scans every matching row on every page load. At 500k invoices with a
   loose filter this dominates the request. *Fix when it hurts:* keyset pagination for the rows plus
   an approximate count from `EXPLAIN`, with the exact count only when the filter is narrow.
2. **Substring search on customer name and email.** `ILIKE '%term%'` cannot use a B-tree. The GIN
   trigram indexes in §1 are the fix and are already in the plan — without them this is #1.
3. **The RLS collaborator `EXISTS` subquery.** Evaluated per candidate row for every AM query. The
   composite index makes each probe an index-only scan; without it, this is a sequential scan of
   `collaborators` per row, which is quadratic in disguise.
4. **The 8-week revenue chart (Goal 8).** `date_trunc('week', paid_at)` over a growing table.
   Survives on `idx_inv_paid_at` because the window is bounded to 8 weeks, so it stays a range scan
   regardless of table size. This one scales fine — worth saying so rather than listing everything
   as a risk.
5. **Bulk generation (Goal 7).** One pass over active subscriptions, one INSERT each, in a single
   transaction. At 20k subscriptions that transaction is long enough to matter for lock contention
   and would need chunking into batches with a per-batch commit, plus a job record so the report
   survives a timeout. At the brief's stated few hundred customers it is a sub-second operation, so
   it stays synchronous and the chunking is documented rather than built.
6. **The per-request transaction from `RLSTransactionMiddleware`.** Every request holds a connection
   for its full duration. At 100× traffic this exhausts the pool before anything else in this list
   becomes visible. *Fix:* PgBouncer in transaction mode, already the documented production stance.
