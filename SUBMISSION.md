# Submission

Fill this in and commit it. This is the first file we open.

## Links

- **GitHub repository:** <public repo URL>
- **Live application:** <deployed URL>

## Notes for the reviewer

The free host sleeps when idle and the first request can take up to a minute.
After that first load everything responds normally.

The best demo path is to sign in as the billing admin and open Northwind
Traders' most recent paid invoice. It carries the full audit timeline, a credit
note, and the immutability rules in action. Then try marking it as void. The
server rejects it with an explanation, and the timeline stays untouched.

For the account manager perspective, sign in as `manager1@example.com` and
notice the reduced set of actions. The manager can create and edit draft
invoices on their own subscriptions but cannot issue, pay, void, or credit-note.
Those buttons are not just hidden in the UI; the server returns a 403 with a
reason if you try.

## Demo credentials

| Role | Email | Password |
|------|-------|----------|
| `billing_admin` | `admin@example.com` | `admin123` |
| `account_manager` | `manager1@example.com` | `manager123` |
| `account_manager` | `manager2@example.com` | `manager123` |

## Stack

| Layer | What you used | Why |
|-------|---------------|-----|
| Frontend | React + Vite | Fast, responsive single-page application with modular component architecture. |
| Backend | Django 6.1 + Django REST Framework + SimpleJWT | Reliable ORM, structured migrations, comprehensive security defaults, and rich REST tooling. |
| Database | PostgreSQL | Required for native Row-Level Security (RLS) policies and transaction-scoped session variables (`SET LOCAL`). |
| Hosting | Not yet deployed | Planned: Supabase (Postgres), Render (Django), Vercel (React). |

## Goal checklist

Mark each honestly. Partial is fine -- say what is partial.

| # | Goal | Status | Notes |
|---|------|--------|-------|
| 1 | Accounts and roles | Done | Custom User model with UUID PK, JWT auth with embedded role claims, DRF permission classes, view decorators, and RLS middleware. 36 tests pass. |
| 2 | Subscriptions | Done | Create, edit, archive/restore, owner assignment. Archiving sets `archived_at` and stops bulk generation without destroying invoice history. |
| 3 | Invoices | Done | One invoice per subscription per period (partial unique index excludes voided invoices so the period can be re-used). Subscription detail lists all of its invoices. |
| 4 | Invoice lifecycle with rules | Done | `services/invoices.py:transition` is the single writer of `Invoice.status`. Draft to Issued to Paid. Voiding requires a reason and is blocked on Paid invoices. Paid invoices are immutable, enforced by a `BEFORE UPDATE` trigger in PostgreSQL as well as application checks. Credit notes create a separate record. Every illegal move returns a specific error message from the server. |
| 5 | Collaborators | Done | Many-to-many via `collaborators` join table with unique constraint. Admin-only add and remove. Account managers see a combined list of owned and collaborated subscriptions. |
| 6 | Finding invoices | Done | Server-side text search over customer name and billing email, filters for status, overdue, and owning account manager, sorting by due date, amount, or status, pagination with total count. All query parameters live in the URL. |
| 7 | Generating invoices in bulk | Done | Per-subscription report: generated, skipped (with invoice ID), or failed (with reason). Receivables CSV export covers every Issued or overdue invoice. |
| 8 | A dashboard | Done | Four headline numbers (issued this month, revenue collected this month, receivables, overdue count). Breakdown tables by status and by plan. Revenue-per-week bar chart over the last eight weeks. |
| 9 | History you cannot rewrite | Done | Append-only `invoice_events` table. No API route mutates or deletes events. A PostgreSQL trigger blocks `UPDATE` and `DELETE` on the table, including from billing admins. Timeline shows creation, every status change with old and new status, credit notes with reason and amount, and notes. |
| 10 | Overdue invoice alerts | Done | Alerts area with count badge in the navigation. Billing admin can dismiss. Dismissal records `dismissed_for_due_date`, so if the due date later changes and passes again while still unpaid, the alert reappears. |

## How much time did you actually spend?

Roughly 14 hours spread over a week, about 2 hours a day. That overshoots the 12-hour guide by two hours. The extra time went into the detailed design documents in `doc2/` before writing any billing code, and into fixing issues I found during final testing (the `DurationField` annotation bug, the seed data `CheckConstraint` conflict with immutable paid invoices).

Session breakdown:
- Session 1-2 (~3h): Project setup, Django scaffold, health check, CORS, PostgreSQL config.
- Session 3 (~3h): Custom User model, JWT auth, RLS middleware and policies, 36 unit tests.
- Session 4 (~2h): Wrote the full design documents (`doc2/`). This was the most valuable session because the audit caught three real bugs in the RLS SQL and forced me to think through edge cases before writing code.
- Session 5-6 (~4h): Built the entire billing domain. Models, services, views, querysets, filters, seed data.
- Session 7 (~2h): Frontend. Built all pages, the auth flow, the dashboard chart, the alert badge.

## What would you do next, with another 12 hours?

1. Proper integration tests against the live database. The unit tests run against SQLite with mocked RLS, which means the triggers and RLS policies are never tested in CI. I would write a test suite that spins up a real PostgreSQL container and verifies that the triggers actually reject the mutations they are supposed to reject.

2. Concurrency tests. The `select_for_update` calls in `transition()` and `edit_invoice()` are there to prevent double-pays, but I have not tested that under actual concurrent load. I would use `threading` or `pytest-xdist` to hammer the same invoice with simultaneous pay requests and verify exactly one succeeds.

3. The frontend could use real-time updates. Right now if two admins are looking at the same invoice and one marks it paid, the other still sees "Issued" until they refresh. WebSockets or polling would fix that, but it is pure polish, not a missing requirement.

4. Better error display in the frontend. Right now the API returns structured error JSON but the frontend mostly shows a generic toast. I would map each error code to a human-readable message and show it inline next to the relevant field.

5. The revenue chart on the dashboard uses a simple bar chart. With more time I would add a line overlay showing cumulative revenue, make it interactive (click a bar to see invoices from that week), and add a date range picker.

## What are you least happy with in this codebase, and why?

The git history. Most of the billing domain went in as two large commits because I was working from the `doc2/` plans and wanted to get the whole thing wired up before committing. That is the opposite of what the README asks for. If I were doing it again I would commit after each model, after each service function, and after each view, so the history tells a story instead of dumping a finished result.

Second, the `docs/` files were written early and not kept up to date as the code evolved. The architecture doc still referenced "what we decided not to build yet" long after it was built. I have since updated them, but a reviewer looking at the git log would see that the docs lagged behind the code, which is not a great look.

Third, the RLS policies. They work and they add a real defense layer, but they make local development harder. Running `seed_demo` requires disabling RLS temporarily, and the test suite falls back to SQLite to avoid needing PostgreSQL credentials in CI. If I had more time I would set up a Docker Compose file that handles all of this automatically so a new developer could run `docker compose up` and have everything working without any manual database setup.
