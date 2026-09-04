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


## Detailed planning: doc2/

After finishing Goal 1 (auth), I stopped coding and spent a full session writing detailed design documents before touching any billing code. These live in `doc2/` and cover sixteen files. The most important ones:

- `doc2/00-README.md`: Table of contents and how the docs relate to each other.
- `doc2/01-current-state-audit.md`: An honest audit of the codebase at that point, including three bugs found in the RLS SQL I had already committed.
- `doc2/02-domain-model.md`: Every ambiguity in the brief that needed a ruling. Numbered A-01 through A-18. For example: can an account manager who owns a subscription also void its invoices? The brief says no, and I recorded why.
- `doc2/03-database-schema.md`: The actual schema that would be migrated, including the differences from the design in `docs/schema.md` (added `issued_at`, `paid_at`, the partial unique index, the `alert_dismissals` table).
- `doc2/04-authorization-matrix.md`: Complete permission matrix for every action by role. This is the single source of truth that both the DRF permission classes and the RLS policies implement.
- `doc2/05-api-contract.md`: Every endpoint with method, URL, request body, response shape, and error codes.
- `doc2/06-backend-build-plan.md`: Step-by-step build order for the backend, with file names and what goes in each.
- `doc2/07-frontend-build-plan.md`: Same for the frontend.
- `doc2/13-risks-and-decisions.md`: Risk register and additional design decisions.
- `doc2/14-backend-code-scaffolds.md`: Pseudocode scaffolds for every service function and view.

This planning session was the most valuable part of the project. It caught three bugs before they reached production, forced me to make explicit decisions about every ambiguity in the brief, and gave me a build order I could follow without stopping to think about architecture.

## Session-by-session build log

### Session 1 (~1.5h): Project setup
- Initialised Django backend, React frontend, connected them with a health check.
- Set up CORS, environment variable loading, PostgreSQL configuration.
- Commits: `03694bf` through `1b8b5b0`.

### Session 2 (~2.5h): Authentication and RLS
- Built custom User model, JWT auth with embedded claims, RLS middleware.
- Wrote 36 unit tests for models, auth, permissions, and middleware.
- Wrote RLS policies SQL file (not yet applied, because the tables did not exist).
- This was the hardest session because `SET LOCAL` interaction with Django's connection pooling required careful testing.
- Commits: `a4d02ab`.

### Session 3 (~2h): Design documents
- Wrote all sixteen `doc2/` files.
- Audited existing code and found three bugs in the RLS SQL. Documented them in `doc2/01-current-state-audit.md` and `doc2/13-risks-and-decisions.md`.
- Decided to use triggers instead of RLS for immutability enforcement (Decision 6 in `docs/decisions.md`).
- Commits: `579b7bd`.

### Session 4 (~2h): Billing models and database
- Built all billing models: Subscription, Invoice, Collaborator, CreditNote, InvoiceEvent, AlertDismissal.
- Wrote migrations including raw SQL for triggers and RLS policies.
- Built the service layer: `services/invoices.py` (transition, create, edit, credit note, add note) and `services/subscriptions.py`.
- Commits: `382368f` through `624b452`.

### Session 5 (~2h): API layer
- Built DRF views, serializers, filters, and URL routing for the entire billing API.
- Implemented server-side invoice search with text search, status/overdue/owner filters, sorting, and pagination.
- Built bulk generation endpoint and CSV export.
- Built dashboard aggregation endpoint.
- Built overdue alerts endpoint with dismissal and re-arming.
- Commits: `67a7eb4` through `1224294`.

### Session 6 (~1.5h): Seed data and frontend
- Wrote `seed_demo` management command with relative dates and realistic test data.
- Built the entire React frontend: login, dashboard, subscriptions list, subscription detail, invoice detail with timeline, invoice list with filters, bulk generate page, alerts page.
- Commits: `731ac63`, `5e696cb`.

### Session 7 (~2h): Testing and documentation
- Ran the full system end-to-end against a live PostgreSQL database.
- Fixed bugs found during testing: `DurationField` vs `timedelta` mismatch in annotation, seed data `CheckConstraint` conflict with paid invoices, various linting warnings.
- Updated all `docs/` files to reflect the finished system.
- Commits: `d8f6cfd` and the final documentation commit.

## Time estimate vs reality

| Session | Estimated | Actual | Notes |
|---------|-----------|--------|-------|
| Project setup | 1h | 1.5h | CORS and env config took longer than expected. |
| Auth and RLS | 2h | 2.5h | SET LOCAL with connection pooling was fiddly. |
| Design documents | 1h | 2h | Worth every minute. The audit found three bugs. |
| Billing models and services | 2h | 2h | On target, because the doc2 plans were detailed enough to follow. |
| API layer | 2h | 2h | On target. |
| Seed data and frontend | 2h | 1.5h | Faster than expected because the API was clean. |
| Testing and docs | 1h | 2h | Found and fixed real bugs. |
| **Total** | **11h** | **~14h** | Over by about 3 hours. |

The overshoot came from two places: the design documents (which were not in the original estimate but paid for themselves) and the bug fixes during final testing. If I had skipped the doc2 session, the bugs would have surfaced later and probably cost more time to find, so the net effect was probably break-even.

## What got cut

In order of priority, these were the things I decided to cut before I started coding:

1. Concurrency tests (two threads hitting the same invoice). The `select_for_update` is there but untested under real concurrency.
2. RLS integration tests against a real PostgreSQL container in CI. The unit tests mock out RLS.
3. Inline subscription editing on the subscriptions list page. You have to click through to the detail page.
4. Real-time updates via WebSocket. The frontend polls on navigation.
5. Interactive revenue chart (click a bar to see invoices from that week).

What I did not cut under any circumstances: the invoice state machine with specific rejection messages, the append-only timeline with database-tier enforcement, server-side filtering and pagination, and the RLS test suite.
For the detailed auth plan that kicked off Session 2, refer to the original implementation plan preserved in doc3/plan.md. For the full billing domain build plans, refer to the sixteen design documents in doc2/.
