# 08 — Testing Plan

## 1. What is worth testing here, and what is not

The brief scores judgement, not coverage percentage. So the tests target the places where being
wrong is expensive and where being right is not obvious:

**Heavily tested:** the invoice state machine, period arithmetic, RLS, the alert re-arming rule,
bulk generation idempotence, visibility scoping.
**Lightly tested:** serialiser field lists, URL routing, CRUD happy paths (one test each).
**Not tested:** Django itself, DRF's pagination, React components. No frontend test harness is set
up — with 12 hours total, a Vitest setup buys less than the same 40 minutes spent on the RLS suite
or on the alert rule. Stated in `docs/plan.md` as a cut, with that reasoning, rather than left as a
silent gap.

## 2. Test layout

```
src/billing/tests/
├── factories.py               # plain functions, not factory_boy
├── test_periods.py            # pure, no DB — the fastest and most valuable file
├── test_models.py             # constraints, derived properties
├── test_subscriptions_api.py  # Goals 2, 5
├── test_invoice_lifecycle.py  # Goals 3, 4 — the 4×5 matrix
├── test_audit.py              # Goal 9
├── test_invoice_search.py     # Goal 6
├── test_bulk.py               # Goal 7
├── test_export.py             # Goal 7
├── test_dashboard.py          # Goal 8
├── test_alerts.py             # Goal 10
├── test_permissions.py        # the whole matrix from doc 04
└── test_rls.py                # Postgres-only
```

`factories.py` uses plain builder functions (`make_subscription(owner=..., **kw)`) rather than
`factory_boy`. Twelve fixtures do not justify a dependency and its own learning surface, and plain
functions read more clearly in a test than a DSL does.

## 3. The two runners

```bash
# Fast loop — SQLite, skips RLS. Used constantly while building.
python main.py test src --settings=src.config.test_settings

# Full — real Postgres, includes RLS and triggers. Before every commit that
# touches models, migrations or services.
python main.py test src
```

The split exists because RLS and triggers are Postgres-only and a SQLite run cannot exercise them.
The danger of a two-runner setup is that the fast one becomes the only one that ever runs and the
slow one silently rots. Two guards:

1. `test_rls.py` uses `@skipUnless(connection.vendor == "postgresql", ...)`, so a SQLite run prints
   skips rather than passing quietly.
2. `test_settings.py` gains a module-level banner printed on load:
   `"SQLite test settings — RLS and trigger tests are SKIPPED. Run without --settings for the full suite."`

## 4. Goal → test mapping

Every goal, and where its proof lives. This table goes into `docs/plan.md` more or less as-is — it
is the answer to "how do you know it works".

| Goal | Test file | The tests that actually prove it |
|---|---|---|
| **1** Roles | `test_permissions.py` | All 24 matrix rows × both roles. Every AM-forbidden action asserted as 403 **at the API**, not at the permission class — the brief says server-enforced, so the test hits the endpoint. |
| **1** (depth) | `test_rls.py` | R-4, R-5, R-6: an AM cannot pay, issue or add collaborators even via raw SQL. |
| **2** Subscriptions | `test_subscriptions_api.py` | Create with all seven fields; edit; archive is BA-only; restore; A-01 owner rule; **archived subscription keeps its invoices and they stay readable**. |
| **3** Invoices | `test_invoice_lifecycle.py` | Invoice belongs to exactly one subscription; owner AM and collaborator AM can both create; stranger AM 404s; subscription detail returns all invoices. |
| **4** Lifecycle | `test_invoice_lifecycle.py` | The 4×5 matrix. Every illegal move asserts a **specific error code and a 409**, not just "not 200". |
| **4** (DB depth) | `test_rls.py` R-9 | A BA cannot mutate a paid invoice even by raw `UPDATE`. |
| **5** Collaborators | `test_subscriptions_api.py` | Many-to-many both ways; only BA adds/removes; the combined owner+collaborator list is correct **and free of duplicates** (the `.distinct()` bug). |
| **6** Finding | `test_invoice_search.py` | Each filter alone; filters combined; count reflects filters not page size; both sort directions; **search hits customer name and billing email separately**; scoping holds under every filter. |
| **7** Bulk | `test_bulk.py` | All three outcomes in one run; idempotent second run; a void invoice's period regenerates (A-14); archived skipped; per-subscription isolation on failure. |
| **7** CSV | `test_export.py` | Exact header row; only issued invoices; a comma in a customer name is quoted; amounts unrounded; scoping holds. |
| **8** Dashboard | `test_dashboard.py` | Each headline figure against a hand-computed fixture; 8 buckets including zeros; A-08 (issued-this-month uses `issued_at`, not current status); AM scoping. |
| **9** History | `test_audit.py` | Every action emits exactly the right events; **a BA cannot UPDATE or DELETE an event** (trigger); notes are allowed on paid invoices; no route exists to mutate the timeline. |
| **10** Alerts | `test_alerts.py` | The A-10 narrative test; badge count == list length; AM-scoped; dismiss is BA-only; a paid invoice never alerts regardless of due date. |

## 5. The tests worth writing out in advance

### The A-10 narrative (Goal 10)
```python
@freeze_time("2025-06-01")
def test_dismissed_alert_returns_when_due_date_passes_again(self):
    inv = make_invoice(due_date=date(2025, 6, 10), status="issued")

    with freeze_time("2025-06-11"):
        assert self.alert_ids() == [inv.id]                   # overdue, alerting
        self.admin_post(f"/api/invoices/{inv.id}/dismiss-alert/")
        assert self.alert_ids() == []                          # dismissed

        self.admin_patch(f"/api/invoices/{inv.id}/", {"due_date": "2025-06-20"})
        assert self.alert_ids() == []                          # no longer overdue

    with freeze_time("2025-06-21"):
        assert self.alert_ids() == [inv.id]                    # overdue again → returns
```
One test, reads like the sentence in the brief, and fails loudly if the dismissal is ever
simplified to a boolean flag.

### The lifecycle matrix (Goal 4)
```python
ILLEGAL = [
    ("draft",  "pay",         "INVALID_TRANSITION"),
    ("draft",  "credit_note", "CREDIT_NOTE_REQUIRES_PAID"),
    ("issued", "issue",       "INVALID_TRANSITION"),
    ("issued", "credit_note", "CREDIT_NOTE_REQUIRES_PAID"),
    ("paid",   "issue",       "INVALID_TRANSITION"),
    ("paid",   "pay",         "INVALID_TRANSITION"),
    ("paid",   "void",        "INVOICE_PAID_CANNOT_VOID"),
    ("void",   "issue",       "INVOICE_VOID_IS_TERMINAL"),
    ("void",   "pay",         "INVOICE_VOID_IS_TERMINAL"),
    ("void",   "void",        "INVOICE_VOID_IS_TERMINAL"),
    ("void",   "credit_note", "CREDIT_NOTE_REQUIRES_PAID"),
]
# subTest over the table: each asserts 409 and the exact code, and asserts the
# invoice's status is unchanged afterwards.
```
The second assertion matters as much as the first: a rejected transition that still wrote something
is worse than one that returned the wrong code.

### The N+1 guards
```python
def test_invoice_list_query_count_is_constant(self):
    make_invoices(5);  self.assertNumQueries(N, lambda: self.get("/api/invoices/"))
    make_invoices(50); self.assertNumQueries(N, lambda: self.get("/api/invoices/"))
```
Asserting the *same* count at two data sizes tests the actual property — constant queries — rather
than pinning a magic number that anyone will "fix" by editing it upward.

### The immutability trigger, bypassing the service layer
```python
def test_paid_invoice_cannot_be_updated_via_orm(self):
    inv = make_invoice(status="paid")
    with self.assertRaises(InternalError):
        Invoice.objects.filter(pk=inv.pk).update(amount=Decimal("1.00"))
```
Deliberately goes around every Python check to prove the database is the backstop. `.update()`
skips `save()`, signals and the service layer entirely — if this passes, the trigger is real.

## 6. Concurrency

Two tests using `TransactionTestCase` and threads:

- **Double mark-paid.** Two threads call `pay` on one invoice. Exactly one succeeds; exactly one
  `status_changed` event exists afterwards. Proves the `select_for_update()` in `transition()`.
- **Concurrent bulk generation.** Two threads run bulk-generate simultaneously. Every subscription
  ends with exactly one invoice for the period, and the loser reports `skipped`, not `failed`.
  Proves the partial unique index plus the `IntegrityError` handling.

These are slow and fiddly, and two is the right number. They exist because "what happens if two
admins click at once" is a fair interview question about a billing system, and having an actual
answer beats having an opinion.

## 7. What "done" means per session

No step in [06](06-backend-build-plan.md) is committed until:
1. The full Postgres suite is green (not just the SQLite one).
2. `makemigrations --check --dry-run` reports no missing migrations.
3. The new endpoints have been hit by hand once — curl or the UI — because a passing test on an
   endpoint nobody has looked at is a weak signal.

## 8. Coverage target

None set. A percentage would push effort toward serialisers and away from the state machine, which
is precisely backwards for this brief. What is tracked instead is the Goal → test table in §4: every
goal has named tests, and any goal whose row is thin is the next thing tested. That table, filled in
honestly, is a better artefact for `docs/plan.md` than a coverage badge.
