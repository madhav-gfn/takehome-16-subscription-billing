# Submission

Fill this in and commit it. This is the first file we open.

## Links

- **GitHub repository:** <public repo URL>
- **Live application:** <deployed URL>

## Notes for the reviewer

<Anything we should know before opening the link — e.g. your host sleeps when idle and the first
request can take up to a minute.>

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
| Hosting | TBD (e.g. Render / Vercel / Supabase) | Free-tier cloud infrastructure for full-stack deployment. |

## Goal checklist

Mark each honestly. Partial is fine — say what is partial.

| # | Goal | Status | Notes |
|---|------|--------|-------|
| 1 | Accounts and roles | Done | Custom User model with UUID PK, JWT auth with embedded role claims, DRF permission classes, view decorators, and RLS middleware. |
| 2 | Subscriptions | Not done | Designed with schema & RLS policies; ready for implementation. |
| 3 | Invoices | Not done | Designed with schema & RLS policies; ready for implementation. |
| 4 | An invoice lifecycle with rules | Not done | Designed with state transitions & permission guards. |
| 5 | Collaborators | Not done | Designed with dedicated join table & admin-only assignment. |
| 6 | Finding invoices | Not done | Planned for server-side search/filter/pagination. |
| 7 | Generating invoices in bulk | Not done | Planned for bulk current-period generation & CSV export. |
| 8 | A dashboard | Not done | Planned for 8-week revenue chart & status breakdown. |
| 9 | History you cannot rewrite | Not done | Planned for append-only invoice audit events. |
| 10 | Overdue invoice alerts | Not done | Planned for dismissible alerts with badge counts. |

## How much time did you actually spend?

## What would you do next, with another 12 hours?

## What are you least happy with in this codebase, and why?
