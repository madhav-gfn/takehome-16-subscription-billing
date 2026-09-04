# AI prompts

The prompts you actually used, in the order you used them, grouped by what you were trying to achieve. For each significant one: what you asked, what you got back, and what you had to correct.

Include at least one prompt that produced something wrong, and what you did about it.

If you did not use AI at all, say so here, and describe your process instead.

---

# 1.
## Domain Research & System Comparison
I was trying to gather knowledge about similar billing systems, operational patterns, and technologies or frameworks that can be used.

### Prompt
```
The scenario
Picture a small software company selling subscriptions to a couple hundred business customers, each on one of a handful of plans billed monthly or annually. Right now billing runs out of a spreadsheet: someone works out by hand which customers are due to be billed this period, types up an invoice in a document, and emails it out, hoping they remembered to update the row before moving to the next customer.
The result is predictable. A customer who cancelled last month gets invoiced anyway because nobody updated the spreadsheet in time. An invoice goes out with the wrong amount, someone "fixes" it by editing that same row and re-sending it, and afterward nobody can say which version the customer actually paid against. Finance cannot say how much revenue is actually outstanding right now without opening the spreadsheet and adding up unpaid rows by hand.
They want one system: billing admins keep the subscription list current and step in for anything that needs a judgment call, invoices for the current period generate themselves instead of being typed out one by one, and a paid invoice is never quietly edited after the fact — a correction leaves its own trail instead. Anyone should be able to tell what is overdue and what is still owed without opening a spreadsheet. That is the system you are building.
What it must do
Everything below is required. Several of the ten spell out exact rules — what happens on an illegal move, what a bulk action must report back, when a dismissed alert is allowed to reappear — and those specifics are the actual ask, not just the bold headline in front of them.
Accounts and roles. People sign in with an email and password, and there are at least two roles — a billing admin role and an account manager role. Billing admins create, edit and archive any subscription, and can issue, mark as paid, void or credit-note any invoice. Account managers create subscriptions and edit ones they own or collaborate on, and can create invoices for them, but cannot issue, mark an invoice as paid, void or credit-note an invoice, archive a subscription, or act on a subscription they do not own or collaborate on. The difference must be enforced on the server, not just hidden in the interface.
Subscriptions. Billing admins and account managers create subscriptions with a customer name, a billing email, a plan name, a billing cycle, a price as an exact decimal amount, a start date, and an owning account manager, and can edit them later. Subscriptions can be archived and restored. Archiving a subscription stops future invoices from being generated for it without destroying its invoice history.
Invoices. Every invoice belongs to exactly one subscription and carries a billing period's start and end date, an amount owed as an exact decimal amount, and a due date. A billing admin or the subscription's owning account manager can create an invoice for it, edit it freely while it is Draft, and change its due date until it is Paid. Opening a subscription shows all of its invoices.
An invoice lifecycle with rules. An invoice moves through Draft → Issued → Paid. Issuing an invoice locks its billing period and amount; an Issued invoice not yet Paid by its due date counts as overdue, though it stays Issued until it is actually paid or voided. An invoice can be marked Void, with a required reason, only while it is Draft or Issued — never once it is Paid. A Paid invoice is immutable: no field on it can be changed, and the only way to correct one is to issue a credit note against it, recording a reason and an exact decimal amount, which stands as its own record rather than altering the original invoice. Any other move must be rejected by the server with a message explaining why.
Collaborators. A subscription has one owning account manager, but any number of other account managers can be added to it as collaborators who can also edit it and create invoices for it, and an account manager can collaborate on any number of subscriptions. Only a billing admin can add or remove a collaborator. Every account manager can see one list of every subscription where they are the owner or a collaborator.
Finding invoices. One list shows invoices across every subscription the viewer can see, with a text search over customer name and billing email, filters for status, overdue and owning account manager, sorting by due date, amount or status, and pagination showing the total number of matches. All of this must happen on the server — do not load every invoice into the browser and filter there.
Generating invoices in bulk. A billing admin can bulk-generate the current period's invoices across every active subscription in a single action. The result is a per-subscription report: generated where no invoice exists yet for that period, skipped where one already does, or failed with a reason. Separately, export receivables — every Issued or overdue invoice with its subscription, amount and due date — as a CSV file.
A dashboard. A landing view shows headline numbers — invoices issued this month, revenue collected this month, receivables, and invoices overdue. It also breaks invoices down by status and by plan, and charts revenue collected per week over the last eight weeks.
History you cannot rewrite. Every invoice has a timeline showing when it was created, every status change with the old and new status and who made it, any credit notes issued against it with their reason and amount, and any notes left on it. Nothing in this timeline can be edited or deleted after the fact, including by billing admins.
Overdue invoice alerts. An invoice that counts as overdue appears in an alerts area, with a count badge visible in the navigation. A billing admin can dismiss the alert. If the due date later changes and then passes again while the invoice is still not Paid, the alert returns.
Stretch ideas (optional)
None of these are required, and none substitute for a goal above. If you finish all ten with time left over, pick whichever of these sounds most useful and build it:
Usage-based add-on charges on top of a plan's base price.
Proration when a subscription changes plan mid-cycle.
A customer-facing self-service billing portal.
Reminder emails for invoices approaching or past their due date.
Multi-currency billing.
Tax calculation by jurisdiction.
Automatic discounts for annual versus monthly billing.
Revenue reporting spread evenly across each invoice's billing period.
A trial period before a subscription's first invoice.


this is a breif about a project i am building can you do a deep research on the related projects that are there, the things that can be used to build it and give me a comprehensive report
```

### What you got
`docs/Billing System Development Research.pdf` reference knowledge artifact.

### What you corrected
It is a reference knowledge document, so no code edits were required.

---

# 2.
## Backend to Frontend Connectivity Test
Connecting the basic Django backend to the React frontend to verify CORS and health status.

### Prompt
```
We have a basic frontend working and basic backend working I want to connect both of them, just show the health endpoint of backend visible on frontend
```

### What you got
Working CORS setup, health check endpoint, and frontend connection verification (`image.png`, commit `1b8b5b079f105ffe4936a44c2d6a89dab6d07549`).

### What you corrected
Nothing.

---

# 3.
## Environment Configuration
Setting up `.env` loading and path resolution in Django.

### Prompt
```
Set up env config and resolution in backend
```

### What you got
Working `.env` parsing via `python-dotenv` and settings loader (commit `42c873692ddb8f715f0a3598cba1afc33c5fbf41`).

### What you corrected
Nothing.

---

# 4.
## Authentication, Authorization & PostgreSQL Row-Level Security (RLS)
Designing and implementing the complete JWT-based RBAC system with defense-in-depth PostgreSQL Row-Level Security.

### Prompt
```
1. Accounts and roles. People sign in with an email and password, and there are at least two
roles — a billing admin role and an account manager role. Billing admins create, edit and archive any
subscription, and can issue, mark as paid, void or credit-note any invoice. Account managers create
subscriptions and edit ones they own or collaborate on, and can create invoices for them, but cannot
issue, mark an invoice as paid, void or credit-note an invoice, archive a subscription, or act on a
subscription they do not own or collaborate on. The difference must be enforced on the server, not
just hidden in the interface.

our goal is to build a JWT based, RBAC Authentication and authorization system, plan everything in accordance with below text:
Server-Side Authorization and Row-Level Security...
we will use postgres SQL, audit the project, keep your scope to building this auth only and after you are done with the plan i will setup the post gres
```

### What you got
- Implementation plan with 4 architectural design questions (JWT library, password hashing, token strategy, connection pooling).
- Custom `User` model (`accounts.User`) with UUID primary key and explicit `role` enum.
- `djangorestframework-simplejwt` token pair serializer embedding `role`, `email`, and `user_id` into JWT claims.
- `RLSTransactionMiddleware` setting transaction-scoped `SET LOCAL app.user_id` and `SET LOCAL app.role` inside `transaction.atomic()`.
- DRF permission classes (`IsBillingAdmin`, `IsOwnerOrCollaboratorOrAdmin`, `CanManageInvoiceLifecycle`) and view decorators.
- API endpoints: `/api/auth/register/`, `/api/auth/login/`, `/api/auth/refresh/`, `/api/auth/me/`.
- PostgreSQL RLS policies SQL file (`src/accounts/rls_policies.sql`) for subscriptions, invoices, collaborators, credit notes, and invoice events.
- Management command `seed_users` for demo data.
- Automated test suite with 36 tests across models, auth, permissions, and middleware.

### What you corrected
- **Initial dependency conflict / unpinned Django**: SimpleJWT initially pulled Django 6.1 which triggered an uninstallation of 5.1.1 during pip install. Adjusted `requirements.txt` to use `>=` version specifiers (`Django>=5.2`, `djangorestframework>=3.15.2`, `djangorestframework-simplejwt>=5.3.1`, `psycopg2-binary>=2.9.9`, `PyJWT>=2.9.0`) so pip dependency resolution succeeded cleanly.
- **Test execution environment**: PostgreSQL required credentials not initially present in the test runner environment. Created `test_settings.py` overriding the test DB engine to SQLite with an automatic fallback check in `RLSTransactionMiddleware` to verify all 36 unit tests pass before applying migrations to the live PostgreSQL instance.

---

# 5.
## Planning the Remaining Nine Goals
Auth was done and I needed a build plan for the rest of the system before writing any more code.

### Prompt
```
i want you to create a doc2 folder and put all the plans there, we gonna hyper detailed
plans here, put the files in doc folder as it is there, it is just there for reference,
read the docs, read the README tooo
```
Followed by:
```
so does it have all the detailed plans to implement the whole thing
```

### What you got
`doc2/`, sixteen files: an audit of the existing tree, the domain model with the brief's ambiguities ruled on, the schema, the authorization matrix and RLS rewrite, the API contract, the backend and frontend build plans, testing, seed data, deployment, git and session scheduling, and code scaffolds.

The most useful output was not the plan itself. It was the audit. It found three real defects in the RLS SQL I had already written and committed (decision 6 in `docs/decisions.md`), plus the fact that `seed_demo` would have silently inserted nothing on the deployed database because of `FORCE ROW LEVEL SECURITY`.

### What you corrected
The first pass settled every decision but left the service layer, views, serializers, filters and the whole frontend as prose rather than code. I asked whether it was actually complete, and it was not. Three more files were needed to close that gap. Worth noting because "the plan looks thorough" and "someone could build from this without inventing anything" are not the same test, and only the second one matters.

---

# 6.
## Building the Billing Domain (Goals 2-10)
This was the main build phase. I gave the agent the `doc2/` plans and told it to implement them.

### Prompt
```
read the readme, read the doc2 completely and implement them
```

### What you got
- All billing models: Subscription, Invoice, Collaborator, CreditNote, InvoiceEvent, AlertDismissal.
- Migration `0003_rls_and_triggers.py` with raw SQL for immutability triggers and append-only enforcement.
- Service layer: `services/invoices.py` with `transition()`, `create_invoice()`, `edit_invoice()`, `add_credit_note()`, `add_note()`. `services/subscriptions.py` for archive/restore.
- `querysets.py` with `visible_to(user)` for RLS-aware filtering and SQL annotations for `is_overdue`, `days_overdue`, `credited_total`.
- DRF views, serializers, filters, and URL routing for the entire billing API.
- Bulk generation endpoint with per-subscription generated/skipped/failed report.
- Dashboard aggregation endpoint.
- Overdue alerts endpoint with dismissal and re-arming.
- `seed_demo` management command with relative dates.

### What you corrected
- The seed data command initially tried to create paid invoices and then update their status directly. This violated the `CheckConstraint` that requires `amount > 0` and the immutability trigger on paid invoices. I had to restructure the seed logic to create invoices as draft, then transition them through the correct lifecycle (draft to issued to paid) using the same `transition()` function that the API uses. This was the right fix because it proved the lifecycle rules work end-to-end.

---

# 7.
## Building the Frontend
The API was done and I needed a React frontend to demonstrate it.

### Prompt
```
read the doc2 folder completely, go through the API, go through the backend, and build
the frontend
```

### What you got
A complete React SPA: login page, dashboard with headline numbers and revenue chart, subscriptions list, subscription detail (with collaborators and invoice list), invoice detail (with timeline, status actions, and credit note form), invoice search page with filters, bulk generation page with per-subscription report, and alerts page with dismiss button and nav badge.

### What you corrected
Nothing structurally wrong. The frontend was built against a working API so the data shapes matched. A few minor issues surfaced later during browser testing:
- Unused `slow` prop in `common.jsx` caused a React warning. Removed it.
- Unused `authApi` import in `SubscriptionsPage.jsx`. Removed it.
- `AuthContext.jsx` had a sync `setState` in a `useEffect` cleanup path that triggered a React warning. Refactored the loading state initialization.

---

# 8.
## Final Testing and Bug Fixes
Running the full system end-to-end against a live PostgreSQL database and fixing what broke.

### Prompt
```
can you run this backend with venv and check if everything is right
```

### What you got
The agent set up the virtualenv, installed dependencies, ran migrations, seeded demo data, started the server, and tested every API endpoint. Two real bugs surfaced:

1. **DurationField vs timedelta mismatch (the prompt that produced something wrong):** The `days_overdue` annotation in `querysets.py` was originally written as an `IntegerField` output, computing `(today - due_date).days`. But Django's ORM expression for date subtraction produces a `DurationField` (a `timedelta` object), not an integer. The annotation silently returned `timedelta(days=5)` instead of `5`, which meant the `days_overdue` property on the model returned the wrong type. The template rendered it as "5 days, 0:00:00" instead of "5". The fix was to change the annotation's `output_field` to `DurationField()` and handle the conversion in the model property (check `hasattr(val, 'days')` and extract `.days`). This is the kind of bug that tests on SQLite would never catch because SQLite stores dates as text and Django's SQLite backend handles the subtraction differently.

2. **Seed data CheckConstraint violation:** The `seed_demo` command created paid invoices by setting `status='paid'` directly on the model, bypassing the `transition()` function. This skipped the `issued_at` and `paid_at` timestamps, and when a later update tried to save the invoice, the immutability trigger rejected it. The fix was to use `transition()` for all status changes in the seed data, which also proved the lifecycle works correctly end-to-end.

### What you corrected
Both bugs above. The DurationField one is worth highlighting because the AI-generated code looked correct at a glance (the date subtraction math was right), but the type system disagreement between Django's ORM and the model property caused a silent data corruption. It took manual testing against a real database to surface it.