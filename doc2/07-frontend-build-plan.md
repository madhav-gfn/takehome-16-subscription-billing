# 07 — Frontend Build Plan

React 19 + Vite 8, already scaffolded. The frontend's job is to be an honest window onto the API and
nothing more.

## 1. The one rule

**The frontend never re-implements a business rule.** It does not decide whether an invoice can be
voided, whether a transition is legal, or what counts as overdue. It renders what the API tells it
and shows the API's error message when an action is refused.

The only permission logic in the client is *cosmetic*: hiding buttons a role cannot use, so the UI
is not littered with controls that always fail. Every one of those hidden actions is still enforced
server-side and still tested server-side. This is exactly the distinction Goal 1 draws ("enforced on
the server, not just hidden in the interface") and the client is built to make it obvious which side
of that line each thing is on.

A concrete consequence: `canIssue(invoice)` in the client is a one-liner
`user.role === 'billing_admin' && invoice.status === 'draft'`, and it is used **only** to set
`disabled`. There is no client-side transition table.

## 2. Dependencies to add

| Package | Why | Alternative rejected |
|---|---|---|
| `react-router-dom` | 8 routes with URL-driven state | Hand-rolled hash routing — Goal 6 needs filters in the URL and a hand-rolled router makes that tedious |
| `recharts` | The Goal 8 8-week bar chart | Chart.js (imperative, awkward in React 19); hand-rolled SVG (a day's work for one chart) |

That is all. No UI kit, no state library, no form library. `fetch` + `useState` + context is enough
for eight screens, and every dependency added here is time not spent on the ten goals. Styling is
hand-written CSS with custom properties — one `theme.css` holding colours, spacing and type scale,
so the app looks deliberate rather than default.

**Not adding TanStack Query**, despite it being the right tool for a bigger app: the caching and
invalidation rules would be a new thing to get right, and a small `useApi` hook covers loading,
error and refetch for these screens. Recorded in `docs/decisions.md` as a scope call, with the
trigger for reversing it (the moment two screens need to share and invalidate the same cached list).

## 3. Structure

```
frontend/src/
├── main.jsx                     # Router + AuthProvider
├── App.jsx                      # route table + AppShell
├── theme.css
├── api/
│   ├── client.js                # fetch wrapper: base URL, bearer, refresh-on-401, error unwrap
│   ├── auth.js  subscriptions.js  invoices.js  dashboard.js  alerts.js
├── auth/
│   ├── AuthContext.jsx          # user, login, logout, token storage
│   └── RequireAuth.jsx  RequireAdmin.jsx
├── hooks/
│   ├── useApi.js                # {data, loading, error, refetch}
│   ├── useQueryFilters.js       # filter state <-> URL search params
│   └── useAlertCount.js         # nav badge, polls /api/alerts/count/
├── components/
│   ├── AppShell.jsx  NavBar.jsx  AlertBadge.jsx
│   ├── Money.jsx  DateText.jsx  StatusPill.jsx  OverdueTag.jsx
│   ├── DataTable.jsx  Pagination.jsx  SearchInput.jsx  FilterBar.jsx
│   ├── Modal.jsx  ConfirmDialog.jsx  ReasonDialog.jsx
│   ├── ErrorBanner.jsx  EmptyState.jsx  Spinner.jsx
│   ├── Timeline.jsx  StatCard.jsx  RevenueChart.jsx  BreakdownTable.jsx
│   └── BulkResultTable.jsx
├── pages/
│   ├── LoginPage.jsx
│   ├── DashboardPage.jsx        # Goal 8
│   ├── SubscriptionsPage.jsx    # Goals 2, 5
│   ├── SubscriptionDetailPage.jsx  # Goals 2, 3, 5
│   ├── InvoicesPage.jsx         # Goal 6
│   ├── InvoiceDetailPage.jsx    # Goals 4, 9
│   ├── AlertsPage.jsx           # Goal 10
│   └── BulkGeneratePage.jsx     # Goal 7
└── lib/
    ├── money.js                 # format only — never arithmetic
    ├── dates.js                 # formatting, "12 days overdue"
    └── permissions.js           # cosmetic role checks, documented as such
```

**`lib/money.js` formats and never computes.** Amounts arrive as strings and are displayed as
strings. There is no place in the client where two money values are added — every total the UI shows
comes from the API. A `Number(amount)` anywhere in this codebase is a bug, and the file carries a
comment saying so.

## 4. `api/client.js`

```js
const BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
```
The hardcoded `http://localhost:8000/health/` in the current `App.jsx` goes away. `VITE_API_BASE_URL`
is set in `.env.development` and in the Vercel dashboard for production — required by the brief's
"never in the repository" rule, and it is the single change that makes the app deployable.

Responsibilities:
1. Attach `Authorization: Bearer <access>`.
2. On 401, attempt one refresh; on refresh failure, clear tokens and redirect to `/login`. Guarded
   by a single in-flight promise so five parallel 401s trigger one refresh, not five.
3. Unwrap the §1 error envelope into a thrown `ApiError` carrying `code`, `message`, `field`,
   `status` — so every screen can `catch (e) { setError(e.message) }` and show the server's words.

**Tokens live in `localStorage`.** The honest trade-off: `localStorage` is readable by any XSS on the
origin, and an httpOnly refresh cookie would be materially safer. It needs CSRF protection and a
same-site cookie story across two different hosting origins, which is real work for a demo app.
This goes in `docs/decisions.md` as a knowingly-accepted risk with the mitigation named — not
omitted, because a reviewer will ask, and "I didn't think about it" and "I chose it" score very
differently.

## 5. Screens

### `/login` — LoginPage
Email + password → `POST /api/auth/login/`, store tokens, `GET /api/auth/me/`, redirect to `/`.
Shows the three demo credential sets as clickable buttons that fill the form. A reviewer opening
a live URL should be one click from being inside each role.

### `/` — DashboardPage (Goal 8)
One `GET /api/dashboard/`. Layout:

```
┌────────────┬────────────┬────────────┬────────────┐
│ Issued     │ Collected  │ Receivables│ Overdue    │
│ this month │ this month │            │            │
│    14      │  £4,820.00 │  £3,980.00 │ 5 · £1,240 │
└────────────┴────────────┴────────────┴────────────┘
┌──────────────────────────┬──────────────────────────┐
│  By status               │  By plan                 │
│  draft 3 · issued 9 · …  │  Pro 22 · Starter 8 · …  │
└──────────────────────────┴──────────────────────────┘
┌───────────────────────────────────────────────────┐
│  Revenue collected, last 8 weeks   (bar chart)    │
└───────────────────────────────────────────────────┘
```
The overdue tile links to `/alerts`; each status row links to `/invoices?status=…`; each plan row
links to `/subscriptions?plan=…`. A dashboard whose numbers are not clickable makes the reader
retype what they just read.

### `/subscriptions` — SubscriptionsPage (Goals 2, 5)
Search box, archived toggle, owner filter, "New subscription" button. Table: customer, plan, cycle,
price, owner, collaborator count, invoice summary, status chip.
An AM sees only their own and collaborated rows — Goal 5's "one list", delivered by the API's
scoping rather than by a client-side filter.

### `/subscriptions/:id` — SubscriptionDetailPage (Goals 2, 3, 5)
Three sections:
1. **Details** — inline edit form. Archive / Restore buttons, BA only.
2. **Collaborators** — list with remove buttons and an add-picker, all BA-only. An AM sees the list
   read-only, which is useful (who else is on this account) and matches the RLS.
3. **Invoices** — every invoice for this subscription, newest period first, with a "New invoice"
   button. This is Goal 3's "Opening a subscription shows all of its invoices", literally.

### `/invoices` — InvoicesPage (Goal 6)
The filter bar is the screen:
```
[ search customer or email ] [status ▾] [☐ overdue only] [owner ▾] [sort ▾]
Showing 26–50 of 137                                   [‹ prev] [next ›]
```
**Every filter is a URL search param** via `useQueryFilters`. Three reasons, all of which matter for
this specific brief: a filtered view is shareable and bookmarkable; the back button works; and it
makes it self-evident to a reviewer that filtering is server-side, because the URL changes and a
request goes out. A screen recording of that is a better answer to "did you filter in the browser?"
than any assertion.

Search input is debounced 300 ms. Changing any filter resets to page 1 — forgetting that is how a
user ends up on page 7 of a 2-page result staring at an empty table.

### `/invoices/:id` — InvoiceDetailPage (Goals 4, 9)
```
┌──────────────────────────────────────────────────────────┐
│ Invoice · Northwind Traders            [ISSUED] [12d overdue]
│ Period 2025-06-15 → 2025-07-14   Amount £199.00
│ Due 2025-06-29                            [Edit due date]
├──────────────────────────────────────────────────────────┤
│ Actions:  [Issue] [Mark paid] [Void…] [Credit note…]     │
│           (disabled + tooltip when not permitted)         │
├──────────────────────────────────────────────────────────┤
│ Credit notes                                              │
│   £50.00 — "Overbilled one seat" — admin@ — 2025-07-02   │
├──────────────────────────────────────────────────────────┤
│ Timeline                              [Add note]          │
│   2025-06-15 09:00  created            manager1@          │
│   2025-06-15 09:31  draft → issued     admin@             │
│   2025-06-20 14:02  due date 06-29 → 07-15   admin@       │
│   2025-07-02 11:10  credit note £50.00  admin@            │
└──────────────────────────────────────────────────────────┘
```
Disabled buttons carry a `title` explaining *why* — "Only a billing admin can void an invoice",
"A paid invoice cannot be voided; issue a credit note". The user learns the rule from the UI, and
the server enforces it regardless.

Void and credit-note open `ReasonDialog`, which will not submit an empty reason. The server also
rejects it; the dialog just saves a round trip.

The timeline is strictly read-only. There is no edit affordance anywhere on it, because there is no
endpoint behind one (Goal 9).

### `/alerts` — AlertsPage (Goal 10)
Table of overdue invoices with days overdue and amount, each linking to its invoice. A "Dismiss"
button per row for BAs only. Dismissing removes the row optimistically and refreshes the badge.
The page carries a one-line explainer: *"Dismissed alerts return if the due date changes and passes
again while the invoice is unpaid."* — the rule, stated where the user acts on it.

### `/bulk-generate` — BulkGeneratePage (Goal 7), BA only
A confirm dialog naming how many active subscriptions will be considered, then the result table:
```
Northwind Traders   generated  2025-06-15 → 2025-07-14  £199.00   [view]
Contoso             skipped    An invoice already exists for this period  [view]
Fabrikam            skipped    Subscription has not started (starts 2025-09-01)
Adventure Works     failed     Could not determine a billing period
```
Outcome-coloured rows, a `7 generated · 4 skipped · 1 failed` summary line, and a "Download
receivables CSV" button alongside — the two halves of Goal 7 in one place. The CSV download attaches
the bearer token, so it is a `fetch` → `Blob` → object-URL download, not a bare `<a href>`.

## 6. Nav and the badge (Goal 10)

```
Billing   Dashboard  Subscriptions  Invoices  Alerts (5)  Bulk    admin@example.com [Sign out]
```
`Alerts (5)` is the count badge. `useAlertCount` fetches `/api/alerts/count/` on mount, on route
change, and after any action that could change it (issue, pay, void, due-date change, dismiss). No
polling timer — a 30-second interval on a demo app is wasted requests, and every state change that
can affect the count is already something the client initiated. Documented so it does not read as an
oversight.

The `Bulk` link renders only for BAs.

## 7. States every screen must handle

Written down because these are what get skipped when time runs short, and they are the difference
between "runs" and "finished":

| State | Treatment |
|---|---|
| Loading | Skeleton rows for tables, spinner for detail views. Never a blank screen. |
| Empty | `EmptyState` with a specific message and, where useful, the action — "No invoices match these filters. Clear filters." |
| Error | `ErrorBanner` showing the API's `message` verbatim, with a retry. Never "Something went wrong". |
| Forbidden | Should not be reachable (controls are hidden), but if it happens the 403 message renders in the banner. |
| Optimistic-then-failed | Roll back the local change and show the banner. Applies to alert dismissal. |

## 8. Build order

| # | Work | Est. | Unblocks |
|---|---|---|---|
| F0 | Deps, `theme.css`, `client.js`, `AuthContext`, router, `AppShell`, LoginPage | 1:00 | Everything |
| F1 | `DataTable`, `Pagination`, `StatusPill`, `Money`, `Modal`, `ErrorBanner`, `EmptyState` | 0:45 | All pages |
| F2 | SubscriptionsPage + DetailPage (Goals 2, 5) | 1:15 | |
| F3 | InvoicesPage with URL-driven filters (Goal 6) | 1:00 | |
| F4 | InvoiceDetailPage + timeline + action dialogs (Goals 3, 4, 9) | 1:15 | |
| F5 | DashboardPage + chart (Goal 8) | 0:45 | |
| F6 | AlertsPage + nav badge (Goal 10) | 0:30 | |
| F7 | BulkGeneratePage + CSV download (Goal 7) | 0:30 | |
| F8 | Empty/loading/error polish, responsive check, `npm run build` clean | 0:45 | |
| | **Frontend total** | **7:45** | |

Build order is deliberately *not* goal order. F2→F4 comes first because those screens are how the
backend gets exercised by hand; the dashboard and alerts are read-only views over data the earlier
screens create, so they are easier once real data exists.

## 9. Cut list, in the order things get cut

If time runs short, in this order:
1. **F8 polish** → keep loading and error states, drop responsive refinement.
2. **The chart** → `revenue_by_week` renders as a small table. Goal 8 says "charts revenue collected
   per week", so this is a genuine partial and `SUBMISSION.md` says so in those words.
3. **Inline subscription editing** → a separate edit page instead. Same capability, less polish.
4. **Never cut:** the invoice detail action buttons and the timeline. Goals 4 and 9 are the heart of
   the brief and the parts a reviewer will click first.
