# Submission

Fill this in and commit it. This is the first file we open.

## Links

- **GitHub repository:** <public repo URL>
- **Live application:** <deployed URL>

## Notes for the reviewer

Not yet deployed. The application is built end to end but has not been run
against a live PostgreSQL instance, so every goal below is marked
"Built, unverified" rather than Done.

Once deployed: the free host sleeps when idle and the first request can take up
to a minute. The best demo path is to sign in as the billing admin and open
Northwind Traders' most recent paid invoice — it carries the full audit
timeline, a credit note, and the immutability rules in action.

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

Mark each honestly. Partial is fine — say what is partial.

| # | Goal | Status | Notes |
|---|------|--------|-------|
| 1 | Accounts and roles | Done | Custom User model with UUID PK, JWT auth with embedded role claims, DRF permission classes, view decorators, and RLS middleware. |
| 2 | Subscriptions | Built, unverified | Create, edit, archive/restore, owner + collaborators. Archiving stops generation and preserves invoice history. |
| 3 | Invoices | Built, unverified | One invoice per subscription with period, exact decimal amount and due date. Subscription detail lists all of its invoices. |
| 4 | An invoice lifecycle with rules | Not done | Designed with state transitions & permission guards. |
| 5 | Collaborators | Built, unverified | Many-to-many join table, admin-only add/remove, one combined owner+collaborator list per manager. |
| 6 | Finding invoices | Built, unverified | Server-side search, status/overdue/owner filters, three sorts, pagination with total count. Filter state lives in the URL. |
| 7 | Generating invoices in bulk | Built, unverified | Per-subscription generated/skipped/failed report with reasons; streamed receivables CSV. |
| 8 | A dashboard | Built, unverified | Headline figures, by-status and by-plan breakdowns, 8-week revenue chart. |
| 9 | History you cannot rewrite | Built, unverified | Append-only invoice_events. No route mutates it; a trigger blocks UPDATE/DELETE including for billing admins. |
| 10 | Overdue invoice alerts | Built, unverified | Alerts area plus nav badge. Dismissal records the due date it was made against, so the alert returns if the date changes and passes again. |

## How much time did you actually spend?

## What would you do next, with another 12 hours?

## What are you least happy with in this codebase, and why?
