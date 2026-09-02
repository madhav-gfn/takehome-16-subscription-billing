# 05 — API Contract

Base URL: `/api/`. Every endpoint below requires `Authorization: Bearer <access>` except the auth
endpoints marked public. All request and response bodies are JSON; the CSV export is the sole
exception.

## 1. Conventions

**Money** is serialised as a **string**, never a JSON number: `"amount": "199.00"`. A JSON number
becomes an IEEE double in every JS client, and `0.1 + 0.2` in a billing system is not a joke you
want in production. DRF's `DecimalField` does this by default with `COERCE_DECIMAL_TO_STRING=True`
(the default) — the plan is to leave it alone and say why.

**Dates** are `YYYY-MM-DD`. **Timestamps** are ISO-8601 UTC with `Z`.

**Errors** always have the same shape:
```json
{ "error": { "code": "INVOICE_PAID_IMMUTABLE",
             "message": "This invoice is paid and cannot be changed. Issue a credit note instead.",
             "field": null } }
```
`code` is stable and machine-readable; `message` is written for a human and is what the UI shows
verbatim; `field` is set for per-field validation failures, null otherwise. Goal 4's "rejected by
the server with a message explaining why" is this `message`, and the UI never invents its own.

**Status codes**
| Code | Used for |
|---|---|
| 200 | Successful read or update |
| 201 | Resource created |
| 400 | Malformed body or field validation failure |
| 401 | Missing/invalid/expired token |
| 403 | Authenticated but the role forbids this action |
| 404 | Resource does not exist *or* is invisible to this viewer (see [04](04-authorization-matrix.md) §2) |
| 409 | The action is illegal **for this object's current state** — the invoice lifecycle's home |
| 422 | Not used. 400 covers validation; using both invites inconsistency |

**Pagination envelope** (Goal 6 requires the total):
```json
{ "count": 137, "next": "…?page=3", "previous": "…?page=1", "results": [ … ] }
```
Standard DRF `PageNumberPagination`, `page_size=25`, `?page_size=` capped at 100.

## 2. Auth — already built

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/api/auth/register/` | public | `{email, password, role}` → 201 + tokens |
| POST | `/api/auth/login/` | public | `{email, password}` → `{access, refresh}` |
| POST | `/api/auth/refresh/` | public | `{refresh}` → `{access}` |
| GET | `/api/auth/me/` | required | `{id, email, role, is_active, …}` |

One addition needed by the frontend and by Goal 2 (choosing an owner) and Goal 5 (choosing a
collaborator):

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/api/auth/users/?role=account_manager` | required | Minimal list `[{id, email, role}]`. Needed to populate owner and collaborator pickers. Returns only `id`, `email`, `role` — no timestamps, nothing else. Available to both roles: an AM needs to see who owns what in the Goal 6 filter-by-owner control. |

## 3. Subscriptions (Goals 2, 5)

### `GET /api/subscriptions/`
Scoped per [04](04-authorization-matrix.md) §2 row 1. Paginated.

Query params:
| Param | Values | Meaning |
|---|---|---|
| `search` | text | `ILIKE` over `customer_name` and `billing_email` |
| `archived` | `true`\|`false`\|`all` | Default `false` — active only |
| `owner` | user UUID | Filter by owning AM |
| `plan` | text | Exact plan name |
| `ordering` | `customer_name`, `-created_at`, `price`, `start_date` (± `-`) | Default `-created_at` |

Each result carries a computed `invoice_summary` so the list can show useful numbers without N+1:
```json
{ "id": "…", "customer_name": "Northwind Traders", "billing_email": "ap@northwind.test",
  "plan_name": "Pro", "billing_cycle": "monthly", "price": "199.00",
  "start_date": "2025-03-15", "archived_at": null,
  "owner": { "id": "…", "email": "manager1@example.com" },
  "collaborators": [ { "id": "…", "email": "manager2@example.com" } ],
  "invoice_summary": { "total": 6, "draft": 1, "issued": 2, "paid": 3, "void": 0,
                       "outstanding": "398.00" } }
```
`invoice_summary` comes from a single annotated aggregate on the queryset, not a per-row query.
`collaborators` uses `prefetch_related`. Both are checked with `assertNumQueries` in the test suite —
a list endpoint that quietly goes N+1 is the most common way this kind of app gets slow.

### `POST /api/subscriptions/`
Body: `{customer_name, billing_email, plan_name, billing_cycle, price, start_date, owner_id}`

- BA: `owner_id` required, must be an AM (A-02).
- AM: `owner_id` optional; if given it must equal the caller's own id, else **403**
  `SUBSCRIPTION_OWNER_MUST_BE_SELF` (A-01). If omitted, defaults to the caller.
- `price` must parse as a decimal > 0 with ≤ 2 dp — 400 `INVALID_PRICE` otherwise.
- `billing_cycle` ∈ {monthly, annual} — 400 otherwise.

→ 201 with the full object.

### `GET /api/subscriptions/{id}/`
Full detail. Includes `collaborators`, `owner`, and `invoices` — every invoice for the subscription,
newest period first, because Goal 3 says "Opening a subscription shows all of its invoices". Not
paginated: a subscription's invoice count is bounded by its age in months, so a few dozen at most.

### `PATCH /api/subscriptions/{id}/`
Partial update of `customer_name`, `billing_email`, `plan_name`, `billing_cycle`, `price`,
`start_date`, `owner_id`.

- `owner_id` changeable by BA only — 403 `OWNER_CHANGE_ADMIN_ONLY` for an AM.
- `archived_at` is **not** writable here. Archiving has its own endpoints so it is an explicit,
  auditable act rather than a field someone can null out by accident.
- Editing an archived subscription → 409 `SUBSCRIPTION_ARCHIVED` (A-16).
- Changing `start_date` or `billing_cycle` when invoices already exist → allowed, with a warning in
  the response: `{"warnings": ["Existing invoices keep their original periods."]}`. Rejecting it
  would leave no way to fix a typo in a start date; silently re-basing history would be worse.

### `POST /api/subscriptions/{id}/archive/`  — BA only
No body. → 200 with the updated subscription. Already archived → 409 `ALREADY_ARCHIVED`.

### `POST /api/subscriptions/{id}/restore/` — BA only
Not archived → 409 `NOT_ARCHIVED`.

### `POST /api/subscriptions/{id}/collaborators/` — BA only (Goal 5)
Body `{user_id}`.
- User must exist and be an `account_manager` → 400 `COLLABORATOR_MUST_BE_AM`.
- User is already the owner → 400 `OWNER_CANNOT_BE_COLLABORATOR`.
- Already a collaborator → 409 `ALREADY_COLLABORATOR`.
→ 201.

### `DELETE /api/subscriptions/{id}/collaborators/{user_id}/` — BA only
→ 204. Not a collaborator → 404.

## 4. Invoices (Goals 3, 4, 6, 9)

### `GET /api/invoices/` — the Goal 6 endpoint
Scoped to visible subscriptions. Everything below happens in SQL; the browser filters nothing.

| Param | Values | Meaning |
|---|---|---|
| `search` | text | `ILIKE '%term%'` over `subscription.customer_name` **and** `subscription.billing_email` |
| `status` | `draft`\|`issued`\|`paid`\|`void`, repeatable | `?status=draft&status=issued` → OR |
| `overdue` | `true`\|`false` | `true` ⇒ `status='issued' AND due_date < today` (A-07) |
| `owner` | user UUID | Owning AM of the invoice's subscription |
| `subscription` | UUID | Single subscription |
| `due_before` / `due_after` | date | Range |
| `ordering` | `due_date`, `amount`, `status`, `created_at`, each ± `-` | Default `-due_date` |
| `page`, `page_size` | int | |

`ordering=status` sorts by the **lifecycle order** draft → issued → paid → void, not alphabetically
(which would give draft, issued, paid, void — coincidentally the same, but only by luck; a future
status like `partially_paid` would break it). Implemented with an explicit `Case/When` ordering
annotation so the intent is in the code, not in the alphabet.

`overdue=true` combined with `status=paid` returns an empty set rather than an error — the filters
compose as AND, and an empty result is the truthful answer.

Result rows are flattened for the list view, avoiding a nested fetch per row:
```json
{ "id": "…", "subscription_id": "…", "customer_name": "Northwind Traders",
  "billing_email": "ap@northwind.test", "plan_name": "Pro",
  "owner_email": "manager1@example.com",
  "period_start": "2025-06-15", "period_end": "2025-07-14",
  "amount": "199.00", "due_date": "2025-06-29", "status": "issued",
  "is_overdue": true, "days_overdue": 12,
  "credited_total": "0.00", "created_at": "2025-06-15T09:00:00Z" }
```
`is_overdue` is annotated in SQL, not computed in Python — otherwise `?overdue=true` and the
displayed badge could disagree, and sorting by it would be impossible.

### `POST /api/invoices/`
Body `{subscription_id, period_start, period_end, amount, due_date}`.
Permitted for BA, owner AM, collaborator AM (Goal 3).
- Subscription not visible → 404.
- Archived subscription → 409 `SUBSCRIPTION_ARCHIVED`. Goal 2 stops *generation*; manual creation on
  a stopped arrangement is equally meaningless.
- Overlapping non-void invoice for the same period → 409 `PERIOD_ALREADY_INVOICED` with the
  offending invoice's id in `details`.
- `period_start > period_end` → 400.
- `amount <= 0` → 400.
- Always created as `draft`. Status is not accepted in the body at all — a client cannot create an
  already-issued invoice.
→ 201. Emits a `created` event.

### `GET /api/invoices/{id}/`
Full detail including `subscription` (nested summary), `credit_notes[]`, and `timeline[]` (Goal 9,
oldest first). Also `credited_total` and `net_amount` (`amount - credited_total`).

### `PATCH /api/invoices/{id}/`
The state machine's mutability table ([02](02-domain-model.md) §3) in endpoint form.

| Invoice state | Accepted fields | Otherwise |
|---|---|---|
| draft | `period_start`, `period_end`, `amount`, `due_date` | — |
| issued | `due_date` only | any other field → 409 `INVOICE_ISSUED_LOCKED` |
| paid | none | 409 `INVOICE_PAID_IMMUTABLE` |
| void | none | 409 `INVOICE_VOID_IS_TERMINAL` |

Emits one `field_changed` event carrying every changed field with from/to values. One event per
request, not one per field — the timeline should read as a list of actions someone took, not a list
of column writes.

### Lifecycle transitions — all BA-only (Goal 4)

| Endpoint | From | To | Body | Errors |
|---|---|---|---|---|
| `POST /api/invoices/{id}/issue/` | draft | issued | — | 409 `INVALID_TRANSITION` from issued/paid/void |
| `POST /api/invoices/{id}/pay/` | issued | paid | — | 409 `INVALID_TRANSITION`; from draft the message names issuing as the missing step |
| `POST /api/invoices/{id}/void/` | draft, issued | void | `{reason}` required, non-empty | 400 `VOID_REASON_REQUIRED`; 409 `INVOICE_PAID_CANNOT_VOID` from paid |
| `POST /api/invoices/{id}/credit-notes/` | paid only | (unchanged) | `{amount, reason}` | 409 `CREDIT_NOTE_REQUIRES_PAID`; 400 `CREDIT_EXCEEDS_INVOICE` |

Each returns 200 with the updated invoice (or 201 with the credit note). Each emits its events
inside the same transaction as the state change.

The error messages, written out, because these are the ones a reviewer will actually try:

```
INVALID_TRANSITION (draft → pay)
  "An invoice must be issued before it can be marked paid. This invoice is still a draft."
INVOICE_PAID_CANNOT_VOID
  "This invoice has been paid and cannot be voided. Issue a credit note against it instead."
INVOICE_PAID_IMMUTABLE
  "This invoice is paid and cannot be changed. Issue a credit note to correct it."
INVOICE_ISSUED_LOCKED
  "This invoice has been issued, so its billing period and amount are locked. You can still
   change its due date."
CREDIT_NOTE_REQUIRES_PAID
  "Credit notes can only be issued against paid invoices. This invoice is {status} — edit or
   void it instead."
CREDIT_EXCEEDS_INVOICE
  "A credit note of {amount} would bring total credits to {total}, which is more than the
   invoice amount of {invoice_amount}."
LIFECYCLE_ADMIN_ONLY  (403)
  "Only a billing admin can issue, mark paid, void or credit-note an invoice."
```

Each of these strings is a constant in `src/billing/errors.py` and each has a test asserting the
exact `code`. Testing the prose would make the tests brittle; testing the code makes them meaningful.

### `POST /api/invoices/{id}/notes/` (Goal 9)
Body `{text}`, non-empty. BA / owner AM / collaborator AM. Allowed in **any** state including paid —
a note is an event, not a field (A-18). → 201, emits `note_added`.

### `GET /api/invoices/{id}/timeline/`
The append-only timeline. Also embedded in the detail response; the standalone endpoint exists so
the UI can refresh just the timeline after an action.
```json
[ { "id": "…", "event_type": "status_changed", "old_status": "draft", "new_status": "issued",
    "actor": { "id": "…", "email": "admin@example.com" },
    "details": {}, "created_at": "2025-06-15T09:31:00Z" } ]
```
**There is no PATCH or DELETE on this resource, at any URL.** Not "returns 403" — the routes do not
exist, so the 405 comes from the router. Goal 9 is best served by there being nothing to call.

## 5. Bulk generation and export (Goal 7)

### `POST /api/invoices/bulk-generate/` — BA only
Body: `{}` or `{"as_of": "2025-06-20"}` (`as_of` defaults to today; it exists for testing and for
regenerating a period after a fix, and is echoed in the response).

Runs over every **non-archived** subscription visible to the caller — for a BA, all of them.

```json
{ "as_of": "2025-06-20",
  "summary": { "total": 12, "generated": 7, "skipped": 4, "failed": 1 },
  "results": [
    { "subscription_id": "…", "customer_name": "Northwind Traders",
      "outcome": "generated", "invoice_id": "…",
      "period_start": "2025-06-15", "period_end": "2025-07-14", "amount": "199.00" },
    { "subscription_id": "…", "customer_name": "Contoso",
      "outcome": "skipped", "reason": "An invoice already exists for 2025-06-01 – 2025-06-30",
      "invoice_id": "…" },
    { "subscription_id": "…", "customer_name": "Fabrikam",
      "outcome": "skipped", "reason": "Subscription has not started (starts 2025-09-01)" },
    { "subscription_id": "…", "customer_name": "Adventure Works",
      "outcome": "failed", "reason": "Could not determine a billing period for this subscription" }
  ] }
```

Exactly Goal 7's three outcomes, one row per subscription, every skip and failure carrying a reason
a human can act on.

**Transaction shape — the important design point.** Each subscription is generated in its **own**
nested `atomic()` block (savepoint). One subscription failing must not roll back the others; a bulk
action that is all-or-nothing turns one bad row into a wasted run and tells the operator nothing
about the other eleven. The outer request transaction still wraps everything, so the response and
the writes commit together.

```python
for sub in subscriptions:
    try:
        with transaction.atomic():          # savepoint per subscription
            result = generate_for(sub, as_of, actor)
    except DomainError as exc:
        result = {"outcome": "failed", "reason": str(exc)}
    results.append(result)
```
`IntegrityError` on `uq_invoice_period` from a concurrent run is caught and reported as `skipped`,
not `failed` — a race that lands on the correct end state is not an error.

Each generated invoice emits a `created` event with `details.source = "bulk"`, so the timeline
distinguishes bulk-generated invoices from hand-made ones.

### `GET /api/exports/receivables.csv` (Goal 7)
Every **Issued** invoice (overdue included — they are receivables) visible to the caller.
`Content-Type: text/csv`, `Content-Disposition: attachment; filename="receivables-YYYY-MM-DD.csv"`.

```csv
invoice_id,customer_name,billing_email,plan_name,owner_email,period_start,period_end,amount,due_date,days_overdue,status
5f1c…,Northwind Traders,ap@northwind.test,Pro,manager1@example.com,2025-06-15,2025-07-14,199.00,2025-06-29,12,issued
```

Streamed via `StreamingHttpResponse` with a generator over `.iterator()`. At a few hundred rows this
is unnecessary; it costs three extra lines and means the endpoint does not need rewriting when the
row count grows. Amounts are written with `str(Decimal)` — never `%f`.

Accepts the same `search` / `owner` / `overdue` filters as the invoice list, so "export what I am
looking at" works. Shares one filter class with the list endpoint, so the two can never drift.

## 6. Dashboard and alerts (Goals 8, 10)

### `GET /api/dashboard/`
All figures scoped to what the viewer can see (A-12), so an AM gets their own book of business.

```json
{ "as_of": "2025-06-20",
  "headline": {
    "invoices_issued_this_month": 14,
    "revenue_collected_this_month": "4820.00",
    "credits_issued_this_month": "150.00",
    "receivables": "3980.00",
    "invoices_overdue": 5,
    "overdue_amount": "1240.00" },
  "by_status": [ { "status": "draft", "count": 3, "amount": "597.00" }, … ],
  "by_plan":   [ { "plan_name": "Pro", "count": 22, "amount": "4378.00" }, … ],
  "revenue_by_week": [ { "week_start": "2025-04-28", "amount": "980.00" }, … ] }
```

- `invoices_issued_this_month` — count where `issued_at` falls in the current calendar month (A-08).
- `revenue_collected_this_month` — sum of `amount` where `paid_at` falls in it (A-09).
- `credits_issued_this_month` — shown alongside, never netted off (A-06).
- `receivables` — sum of `amount` over all `issued` invoices, no date bound.
- `revenue_by_week` — exactly 8 entries, oldest first, **including zero weeks**. A chart that skips
  empty weeks silently rescales its own x-axis and misleads; the backend emits the zeros so the
  frontend cannot get this wrong.

Implementation: one query per section (six total), each a single aggregate. Not one query overall —
a six-way FULL OUTER JOIN to save five round trips on a page that loads once is the wrong trade.

### `GET /api/alerts/` (Goal 10)
Overdue invoices with an active alert, per A-10's rule. Scoped to the viewer.
```json
{ "count": 5,
  "results": [ { "invoice_id": "…", "customer_name": "…", "amount": "199.00",
                 "due_date": "2025-06-01", "days_overdue": 19,
                 "dismissible": true } ] }
```
`dismissible` is `true` only for a BA (A-11), so the UI does not render a button that will 403.

### `GET /api/alerts/count/`
`{"count": 5}`. A dedicated endpoint because the nav badge polls it, and the badge should not pull
the full list. Same predicate as `/api/alerts/`, shared in one queryset function so the badge can
never disagree with the list.

### `POST /api/invoices/{id}/dismiss-alert/` — BA only
No body. Upserts an `AlertDismissal` with `dismissed_for_due_date = invoice.due_date` (the whole
mechanism). Invoice not currently overdue → 409 `NOT_OVERDUE`. → 200 `{"dismissed_for_due_date": …}`.

Does **not** write an `invoice_event`. Dismissing an alert is an operator convenience about their own
attention, not a fact about the invoice, and Goal 9's timeline should stay about the invoice.
A judgement call, recorded in `docs/decisions.md`.

## 7. Exception handling

A custom DRF exception handler in `src/billing/errors.py` produces the §1 envelope for everything:

1. `DomainError` subclasses (`InvalidTransition`, `ImmutableInvoice`, `PeriodAlreadyInvoiced`, …)
   carry `code`, `message`, `http_status` and render directly.
2. DRF `ValidationError` → 400, first field error surfaced in `field`.
3. `PermissionDenied` → 403 with the permission class's `message`.
4. `Http404` → 404 with a generic "not found or not visible to you" — the same message whether the
   row is missing or hidden, so the 404-not-403 choice is not undone by a chatty message.
5. `django.db.utils.InternalError` whose message matches a known trigger → mapped to the equivalent
   409/403. **If a trigger fires, it is a service-layer bug**, so it is also logged at `error` with
   the SQL state and the invoice id. The user gets a correct answer; I get a loud signal.

Wired via `REST_FRAMEWORK["EXCEPTION_HANDLER"]`, replacing the current default.
