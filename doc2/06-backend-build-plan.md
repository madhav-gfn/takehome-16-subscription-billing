# 06 — Backend Build Plan

Ordered steps. Each has files, acceptance criteria, and a commit message. The order is chosen so
that **every step ends with a green test run and a working server** — no step leaves the tree in a
state where the next one has to be finished before anything runs.

## Target file layout

```
backend/src/billing/
├── __init__.py
├── apps.py                    # label = "billing"  (D-09)
├── enums.py                   # InvoiceStatus, BillingCycle, EventType
├── models.py                  # 6 models
├── db.py                      # rls_session()  (D-06)
├── periods.py                 # billing period arithmetic
├── errors.py                  # DomainError hierarchy + DRF exception handler
├── querysets.py               # visible_subscriptions / visible_invoices / active_alerts
├── permissions.py             # IsBillingAdmin, IsSubscriptionMember, …
├── filters.py                 # InvoiceFilterSet, SubscriptionFilterSet
├── pagination.py              # DefaultPagination (page_size 25, max 100)
├── serializers.py
├── services/
│   ├── __init__.py
│   ├── invoices.py            # create / edit / the 4 transitions / credit notes / notes
│   ├── subscriptions.py       # create / edit / archive / restore / collaborators
│   ├── bulk.py                # bulk generation
│   ├── dashboard.py           # the 6 aggregates
│   └── alerts.py              # active-alert predicate + dismissal
├── views/
│   ├── __init__.py
│   ├── subscriptions.py
│   ├── invoices.py
│   ├── dashboard.py
│   ├── alerts.py
│   └── exports.py
├── urls.py
├── management/commands/
│   ├── seed_demo.py
│   └── apply_rls.py           # re-apply policies against an existing DB
├── migrations/
│   ├── 0001_initial.py
│   ├── 0002_search_indexes.py
│   ├── 0003_rls.py
│   └── 0004_immutability.py
└── tests/
    ├── __init__.py, factories.py, test_periods.py, test_models.py,
    ├── test_subscriptions_api.py, test_invoice_lifecycle.py, test_permissions.py,
    ├── test_invoice_search.py, test_bulk.py, test_dashboard.py, test_alerts.py,
    ├── test_audit.py, test_export.py
    └── test_rls.py            # Postgres-only
```

**Services, not fat models or fat views.** Every business rule lives in `services/`. Views parse
input, call one service function, and serialise the result. Models hold data, constraints and
trivial derived properties. The reason is Goal 4: the same transition can be reached from a view, a
bulk run, a management command and a test, and it must behave identically from all four. A
`@transaction.atomic` service function is the only thing that guarantees that.

---

## Step 0 — Cleanup (D-01, D-02, D-10) · ~15 min

`[DELETE]` `backend/src/settings.py`, `backend/src/urls.py`, `backend/src/wsgi.py`
`[NEW]` `.gitattributes` → `* text=auto eol=lf`, plus `*.png binary` and `*.pdf binary`
`[NEW]` `backend/.env.example` — every key from `.env`, all values blank or obviously fake
`[MODIFY]` `backend/requirements.txt` — add `python-dateutil>=2.9`, `django-filter>=24.3`

Then `git checkout -- .` to discard the CRLF churn.

**Accept:** `python main.py check` clean; `git status` clean; `git ls-files` no longer lists the
three deleted files.
**Commit:** `chore: remove duplicate settings modules and normalise line endings`

---

## Step 1 — App skeleton, enums, period arithmetic · ~45 min

`[NEW]` `apps.py` with `label = "billing"`, `name = "src.billing"`
`[NEW]` `enums.py`:
```python
class InvoiceStatus(models.TextChoices):
    DRAFT="draft"; ISSUED="issued"; PAID="paid"; VOID="void"
    # lifecycle ordering for Goal 6's ordering=status
    @classmethod
    def sort_order(cls): return {cls.DRAFT:0, cls.ISSUED:1, cls.PAID:2, cls.VOID:3}
```
`[NEW]` `periods.py` — `period_for_index`, `current_period`, `next_uninvoiced_period`, `NET_DAYS=14`
`[NEW]` `tests/test_periods.py`
`[MODIFY]` `settings.py` — add `"src.billing"` and `"django_filters"` to `INSTALLED_APPS`

**Period arithmetic is written test-first.** It is pure, it has no dependencies, and every downstream
money bug traces back to it. The table it must satisfy:

| start_date | cycle | as_of | expected period |
|---|---|---|---|
| 2025-03-15 | monthly | 2025-03-15 | 2025-03-15 → 2025-04-14 |
| 2025-03-15 | monthly | 2025-04-14 | 2025-03-15 → 2025-04-14 (last day inclusive) |
| 2025-03-15 | monthly | 2025-04-15 | 2025-04-15 → 2025-05-14 |
| 2025-01-31 | monthly | 2025-02-15 | 2025-01-31 → 2025-02-27 (clamped) |
| 2025-01-31 | monthly | 2025-03-01 | 2025-02-28 → 2025-03-30 |
| 2024-02-29 | annual | 2025-03-01 | 2025-02-28 → 2026-02-27 (leap-year source) |
| 2025-09-01 | monthly | 2025-06-20 | `None` — not started (A-13) |
| 2025-06-20 | monthly | 2025-06-20 | first period starts today |

Plus a property test: for any start date and any as_of ≥ start, consecutive periods are **contiguous
and non-overlapping** — `period(n).end + 1 day == period(n+1).start` for n in 0..24. That single
assertion catches every clamping mistake at once.

**Accept:** `test_periods.py` green, ~20 assertions, no DB.
**Commit:** `feat(billing): add app skeleton and billing period arithmetic`

---

## Step 2 — Models and migration 0001 · ~1 h

`[NEW]` `models.py` — all six models per [03](03-database-schema.md), `CheckConstraint`s in
`Meta.constraints`, the partial unique index in `Meta.indexes`/`constraints`
`[NEW]` `migrations/0001_initial.py` (generated, then reviewed by hand)
`[NEW]` `tests/factories.py`, `tests/test_models.py`

Derived properties on `Invoice` — cheap and used everywhere:
```python
@property
def is_overdue(self):        # mirrors the SQL annotation exactly
    return self.status == InvoiceStatus.ISSUED and self.due_date < timezone.localdate()
@property
def credited_total(self):    # prefer the annotated version in list contexts
    return self.credit_notes.aggregate(t=Sum("amount"))["t"] or Decimal("0.00")
```
The Python `is_overdue` and the SQL annotation must agree; `test_models.py` asserts both against the
same fixtures. Two definitions of overdue drifting apart would put a wrong badge next to a correct
filter, which is the worst kind of bug because it looks like a UI glitch.

**Accept:** `migrate` runs against real Postgres; `makemigrations --check --dry-run` clean; model
tests green.
**Commit:** `feat(billing): add subscription, invoice, credit note and audit models`

---

## Step 3 — RLS + immutability migrations, `rls_session` · ~1 h 15

`[NEW]` `db.py` — `rls_session()` (D-06)
`[NEW]` `migrations/0002_search_indexes.py`, `0003_rls.py`, `0004_immutability.py`
`[NEW]` `management/commands/apply_rls.py` — idempotent re-apply for a DB migrated before this
`[NEW]` `tests/test_rls.py` — the 12 scenarios in [04](04-authorization-matrix.md) §5
`[DELETE]` `src/accounts/rls_policies.sql` — superseded; leaving a stale copy guarantees someone
applies the buggy version
`[MODIFY]` `src/accounts/middleware.py` — roll back on `>= 400`, not `>= 500` (D-07)

`test_rls.py` must run against Postgres. It gets `@skipUnless(connection.vendor == "postgresql")`
so a SQLite run skips it loudly rather than passing vacuously, and CI/local runs use the default
settings so it actually executes.

**Accept:** all 12 RLS scenarios pass against Postgres; R-10 (anonymous) returns 0 rows with no
error, proving D-03 fixed; R-8 (BA cannot edit an event) passes, proving Goal 9.
**Commit:** `feat(billing): enforce row-level security and immutability at the database tier`

This is the highest-value commit in the project for the interview. Its message body should say what
it fixes and why RLS cannot express OLD-vs-NEW rules.

---

## Step 4 — Errors, querysets, permissions · ~45 min

`[NEW]` `errors.py` — `DomainError` base with `code`/`message`/`http_status`, the eight concrete
subclasses, the DRF exception handler, and the trigger-message → HTTP mapping
`[NEW]` `querysets.py`, `permissions.py`, `pagination.py`
`[MODIFY]` `settings.py` — point `EXCEPTION_HANDLER` at the new handler

**Accept:** unit tests asserting the envelope shape for each error class; `visible_*` tested for
BA / owner / collaborator / stranger, including the `.distinct()` duplicate case.
**Commit:** `feat(billing): add domain error envelope, visibility querysets and permissions`

---

## Step 5 — Subscriptions API (Goals 2, 5) · ~1 h 30

`[NEW]` `services/subscriptions.py`, `serializers.py` (subscription half), `views/subscriptions.py`,
`urls.py`, `filters.py` (subscription half)
`[MODIFY]` `src/config/urls.py` — `path("api/", include("src.billing.urls"))`
`[NEW]` `views/users.py` or extend `accounts` — `GET /api/auth/users/?role=`
`[NEW]` `tests/test_subscriptions_api.py`

**Accept:** matrix rows 1–8 covered by tests, both roles; archive/restore BA-only; collaborator
add/remove BA-only; A-01 owner rule enforced; `assertNumQueries` bound on the list endpoint.
**Commit:** `feat(billing): subscriptions CRUD, archive/restore and collaborators`

---

## Step 6 — Invoice lifecycle (Goals 3, 4, 9) · ~2 h

The core of the assignment. `services/invoices.py` is the file a reviewer will read most closely.

`[NEW]` `services/invoices.py`:
```python
@transaction.atomic
def transition(invoice, target, actor, *, reason=None):
    """The only function in the codebase that writes Invoice.status."""
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)   # re-read under lock
    _assert_allowed(invoice.status, target)      # raises InvalidTransition (409)
    old = invoice.status
    invoice.status = target
    if target == InvoiceStatus.ISSUED: invoice.issued_at = timezone.now()
    if target == InvoiceStatus.PAID:   invoice.paid_at   = timezone.now()
    if target == InvoiceStatus.VOID:   invoice.void_reason = _require_reason(reason)
    invoice.save(update_fields=[...])
    _event(invoice, EventType.STATUS_CHANGED, actor, old_status=old, new_status=target)
    if target == InvoiceStatus.VOID:
        _event(invoice, EventType.VOIDED, actor, details={"reason": reason})
    return invoice
```

Three things that are deliberate:
- **`select_for_update()`** — two concurrent "mark paid" clicks must not both succeed and write two
  events. The row lock makes the check-then-act atomic. Cheap, and the alternative is a double-pay
  that only shows up in the audit trail.
- **`update_fields`** — never write columns the transition did not touch; keeps the immutability
  trigger from seeing spurious diffs.
- **One function** owns status. Grep for `\.status =` and there is exactly one assignment in the
  codebase. That is the property that makes I-13 true by construction rather than by discipline.

Also in this step: `create_invoice`, `edit_invoice` (per-state field whitelist), `change_due_date`,
`add_credit_note` (with `select_for_update` on the invoice for the I-10 aggregate), `add_note`.

`[NEW]` `views/invoices.py`, `tests/test_invoice_lifecycle.py`, `tests/test_audit.py`

`test_invoice_lifecycle.py` is written as an exhaustive 4×5 matrix — every status × every action —
with the legal cells asserting success and the other cells asserting the specific error code.
Sixteen-ish rejections written as a parametrised table, not as sixteen hand-written tests.

**Accept:** the full matrix green; every event emitted exactly once (asserted by counting events,
not by trusting the code); a PATCH to a paid invoice returns 409 with `INVOICE_PAID_IMMUTABLE`; a
raw ORM `.save()` on a paid invoice raises from the trigger.
**Commit:** `feat(billing): invoice lifecycle with server-enforced transition rules and audit trail`

---

## Step 7 — Invoice search, filtering, pagination (Goal 6) · ~1 h

`[NEW]` `filters.py` (invoice half) — `django_filter` FilterSet, plus the `Case/When` status
ordering and the `is_overdue` SQL annotation
`[NEW]` `tests/test_invoice_search.py`

The annotation, since it is the crux:
```python
today = timezone.localdate()
qs = qs.annotate(
    is_overdue=Case(
        When(status=InvoiceStatus.ISSUED, due_date__lt=today, then=Value(True)),
        default=Value(False), output_field=BooleanField()),
    days_overdue=Case(
        When(status=InvoiceStatus.ISSUED, due_date__lt=today,
             then=ExtractDay(Value(today) - F("due_date"))),
        default=Value(0), output_field=IntegerField()),
)
```

**Accept:** each filter tested alone and in combination; `count` reflects filters not page size;
`ordering=status` produces lifecycle order; search matches on both customer name and billing email;
`assertNumQueries` bounded (proves no N+1 on the flattened rows); **an AM's result set never contains
another AM's invoice** — the test that ties Goal 6 back to Goal 1.
**Commit:** `feat(billing): server-side invoice search, filtering, sorting and pagination`

---

## Step 8 — Bulk generation and CSV export (Goal 7) · ~1 h 15

`[NEW]` `services/bulk.py`, `views/exports.py`
`[NEW]` `tests/test_bulk.py`, `tests/test_export.py`

**Accept:** a run over a fixture containing one generatable, one already-invoiced, one archived, one
not-yet-started and one broken subscription returns exactly the right outcome for each; re-running
immediately produces all-skipped (idempotence, the property Goal 7 is really testing); a failure in
one subscription does not roll back the others (asserted by checking the *other* invoices exist
after the run); CSV headers exact; amounts unquoted and unrounded; a customer name containing a
comma is properly quoted.
**Commit:** `feat(billing): bulk period invoice generation and receivables CSV export`

---

## Step 9 — Dashboard and alerts (Goals 8, 10) · ~1 h 15

`[NEW]` `services/dashboard.py`, `services/alerts.py`, `views/dashboard.py`, `views/alerts.py`
`[NEW]` `tests/test_dashboard.py`, `tests/test_alerts.py`

`test_alerts.py` must contain the A-10 walk-through as a single narrative test — overdue, dismiss,
extend the due date, advance time past the new date, assert the alert is back. That one test is the
entire proof of Goal 10's trickiest sentence, and it should read like the sentence.

Time travel via `freezegun` (add to requirements) rather than by mutating dates — the test then
reads as "on 2 May, …" instead of as arithmetic.

**Accept:** every headline figure asserted against a hand-computed fixture; `revenue_by_week` returns
exactly 8 buckets including zeros; an AM's dashboard excludes other AMs' data; the alert badge count
equals the alert list length under every fixture.
**Commit:** `feat(billing): dashboard aggregates and overdue alerts with re-arming dismissal`

---

## Step 10 — Seed data · ~45 min

`[NEW]` `management/commands/seed_demo.py` per [09](09-seed-data-plan.md)
`[MODIFY]` `management/commands/seed_users.py` — call it from `seed_demo`, keep it standalone

**Accept:** `python main.py seed_demo --flush` on an empty Postgres produces a database where every
screen has content and the dashboard has non-zero numbers in every tile; idempotent without
`--flush`; wrapped in `rls_session("billing_admin", …)` (D-06) — verified by actually running it,
since this is precisely where D-06 bites.
**Commit:** `feat(billing): seed a demo dataset covering every screen`

---

## Step 11 — Hardening pass · ~45 min

- `assertNumQueries` on all three list endpoints
- `select_related("subscription", "subscription__owner")` / `prefetch_related` audited everywhere
- `DEBUG=False` smoke run — catches anything relying on Django's debug error pages
- `python main.py check --deploy` and act on what is real (`SECURE_*`, `ALLOWED_HOSTS`)
- confirm no `float(` anywhere in a money path: `grep -rn "float(" src/billing/`
- confirm one status writer: `grep -rn "\.status = " src/billing/`

**Commit:** `perf(billing): eliminate N+1 queries and tighten production settings`

---

## Running total

| Step | Est. |
|---|---|
| 0 Cleanup | 0:15 |
| 1 Skeleton + periods | 0:45 |
| 2 Models | 1:00 |
| 3 RLS + triggers | 1:15 |
| 4 Errors/querysets/permissions | 0:45 |
| 5 Subscriptions API | 1:30 |
| 6 Invoice lifecycle | 2:00 |
| 7 Search | 1:00 |
| 8 Bulk + CSV | 1:15 |
| 9 Dashboard + alerts | 1:15 |
| 10 Seed | 0:45 |
| 11 Hardening | 0:45 |
| **Backend total** | **12:30** |

That is the entire 12-hour budget on the backend alone, with a frontend and a deployment still to
build. The schedule in [11](11-git-and-sessions.md) resolves this — it is a real conflict, not an
oversight, and the resolution (which steps get compressed, and what gets cut) is the interesting
part of `docs/plan.md`.
