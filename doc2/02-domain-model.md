# 02 — Domain Model

## 1. Glossary

| Term | Precise meaning in this system |
|---|---|
| **Subscription** | A recurring billing arrangement with one customer, on one plan, at one price, owned by one account manager. |
| **Owner** | The single account manager on `subscription.owner_id`. Always an AM, never a BA. |
| **Collaborator** | An additional AM granted edit + invoice-create rights on a subscription. Zero or more per subscription. |
| **Archived** | `subscription.archived_at IS NOT NULL`. Excluded from bulk generation. History fully preserved and readable. |
| **Billing period** | A closed date interval `[period_start, period_end]`, inclusive at both ends, derived from the subscription's `start_date` and `billing_cycle`. |
| **Invoice** | One charge for one subscription for one billing period. |
| **Overdue** | `status = 'issued' AND due_date < today`. Derived, never stored. |
| **Receivables** | The sum of `amount` over all `issued` invoices (overdue ones included — they are still owed). |
| **Credit note** | An immutable correcting record against a Paid invoice. Never mutates the invoice. |
| **Invoice event** | One append-only row in the invoice timeline. |
| **Alert** | The UI surfacing of an overdue invoice. Not a stored row — the *dismissal* is stored, the alert is computed. |

## 2. Entity map

```
                    ┌──────────────┐
                    │    User      │  role: billing_admin | account_manager
                    └──────┬───────┘
                  owner_id │            ┌──────────────────┐
                    (1..N) │            │  Collaborator    │  (M..N join)
                           │      ┌─────┤  subscription_id │
                           ▼      │     │  user_id         │
                    ┌──────────────┐    └──────────────────┘
                    │ Subscription │◄───┘
                    │  archived_at │
                    └──────┬───────┘
                  (1..N)   │
                           ▼
                    ┌──────────────┐        ┌────────────────┐
                    │   Invoice    │───────►│  CreditNote    │ (1..N)
                    │   status     │        │  reason,amount │
                    └──────┬───────┘        └────────────────┘
                (1..N)     │
             ┌─────────────┴──────────────┐
             ▼                            ▼
    ┌──────────────────┐        ┌──────────────────────┐
    │  InvoiceEvent    │        │  AlertDismissal      │  (0..1 per invoice)
    │  append-only     │        │  dismissed_for_due_date │
    └──────────────────┘        └──────────────────────┘
```

Cardinalities, stated for `docs/schema.md`:

- User → Subscription (ownership): **one-to-many**.
- User ↔ Subscription (collaboration): **many-to-many**, through the explicit `Collaborator` table.
- Subscription → Invoice: **one-to-many**.
- Invoice → CreditNote: **one-to-many**.
- Invoice → InvoiceEvent: **one-to-many**, append-only.
- Invoice → AlertDismissal: **one-to-one** (nullable). Modelled as its own table rather than a
  column on `invoices` because writing it must not require an UPDATE on an invoice that may be Paid
  and therefore immutable. This is the single most important structural consequence of Goal 4
  meeting Goal 10.

## 3. The invoice state machine (Goal 4)

```
                    issue (BA)              mark_paid (BA)
      ┌───────┐  ─────────────────►  ┌────────┐  ────────────────►  ┌──────┐
      │ DRAFT │                      │ ISSUED │                     │ PAID │
      └───┬───┘                      └────┬───┘                     └──┬───┘
          │                               │                            │
          │ void (BA, reason required)    │ void (BA, reason required) │  ✗ void  — rejected
          └───────────────┬───────────────┘                            │  ✗ edit  — rejected
                          ▼                                            │
                     ┌────────┐                                        ▼
                     │  VOID  │  terminal                     credit_note (BA)
                     └────────┘                               → new CreditNote row,
                                                                invoice untouched
```

### Transition table — the authoritative version

| From | Action | To | Who | Preconditions | Rejection when violated |
|---|---|---|---|---|---|
| draft | `issue` | issued | BA only | — | 403 for AM; 409 from any other state |
| issued | `mark_paid` | paid | BA only | — | 403 for AM; 409 from draft/void/paid |
| draft | `void` | void | BA only | `reason` non-empty | 400 if reason missing |
| issued | `void` | void | BA only | `reason` non-empty | 400 if reason missing |
| paid | `void` | — | — | **never allowed** | 409 `INVOICE_PAID_CANNOT_VOID` |
| void | any transition | — | — | **terminal** | 409 `INVOICE_VOID_IS_TERMINAL` |
| paid | `credit_note` | (unchanged) | BA only | `reason` non-empty, `0 < amount`, cumulative credit ≤ invoice amount | 400 / 409 |

### Field mutability by state

| Field | draft | issued | paid | void |
|---|---|---|---|---|
| `billing_period_start` / `_end` | editable | **locked** | locked | locked |
| `amount` | editable | **locked** | locked | locked |
| `due_date` | editable | **editable** | locked | locked |
| `status` | via transitions | via transitions | frozen | frozen |
| `void_reason` | — | — | — | set once at void |

"Issuing locks its billing period and amount" (Goal 4) is exactly the `issued` column. "A Paid
invoice is immutable: no field on it can be changed" is exactly the `paid` column.

### Who may act

- **Edit a Draft invoice** (period, amount, due date): BA, or the subscription's owner AM, or a
  collaborator AM.
- **Change due date on an Issued invoice**: same set. Goal 3 says "change its due date until it is
  *Paid*" — that includes Issued, and it deliberately survives the Goal 4 lock on period and amount.
- **issue / mark_paid / void / credit_note**: BA only, on any subscription. Goal 1 is explicit.
- **Add a note**: BA, owner AM, or collaborator AM — on an invoice in any state, including Paid.
  A note is an event, not a field, so it does not violate Paid immutability.

## 4. Billing period arithmetic (Goal 7)

Periods are generated from `subscription.start_date`, never from the calendar month. A subscription
starting 2025-03-15 on a monthly cycle bills 15th→14th, not 1st→end-of-month.

```
period_index n (0-based), monthly:
    period_start = start_date + relativedelta(months=n)
    period_end   = start_date + relativedelta(months=n+1) - 1 day

annual:
    period_start = start_date + relativedelta(years=n)
    period_end   = start_date + relativedelta(years=n+1) - 1 day
```

`relativedelta` clamps month-end correctly: 2025-01-31 + 1 month = 2025-02-28. Two consequences
worth being deliberate about:

- A subscription starting Jan 31 produces periods Jan 31→Feb 27, Feb 28→Mar 30, Mar 31→Apr 29.
  Periods stay contiguous and never overlap, which is the property that matters. Alignment drift
  after a clamp is accepted; the alternative (re-anchoring to the 31st) creates gaps.
- `python-dateutil` becomes a dependency. It is the standard tool and hand-rolling month
  arithmetic is a reliable way to ship an off-by-one into a money path.

**Current period** = the unique `n` where `period_start ≤ today ≤ period_end`. Computed directly:

```python
def current_period(start_date, cycle, today):
    if today < start_date:
        return None            # not started yet
    n = months_between(start_date, today) // (1 if cycle == MONTHLY else 12)
    # then correct n by ±1 to handle month-end clamping edge cases, verified by
    # asserting period_start <= today <= period_end before returning
```

The implementation lives in `src/billing/periods.py` and is unit-tested against a table of
month-end and leap-year cases before anything calls it. See [08](08-testing-plan.md) §2.

**Due date** for a generated invoice: `period_start + NET_DAYS`, `NET_DAYS = 14`, a module constant.
Not configurable — the brief does not ask for payment terms, and a constant is honest about that.

## 5. Invariants

These are the statements that must be true of the database at all times. Each is enforced at the
layer named, and each has a test.

| # | Invariant | Enforced by |
|---|---|---|
| I-1 | `amount > 0` on every invoice | DB `CHECK` |
| I-2 | `price > 0` on every subscription | DB `CHECK` |
| I-3 | `period_start <= period_end` | DB `CHECK` |
| I-4 | At most one **non-void** invoice per `(subscription, period_start, period_end)` | DB partial `UNIQUE` index |
| I-5 | `status = 'void'` ⟺ `void_reason` is non-empty | DB `CHECK` |
| I-6 | A Paid invoice's fields never change | DB `BEFORE UPDATE` trigger + service layer |
| I-7 | An Issued invoice's `amount` and period never change | DB trigger + service layer |
| I-8 | `invoice_events` rows are never updated or deleted | DB trigger + `REVOKE` + absence of an RLS UPDATE/DELETE policy |
| I-9 | `credit_notes` rows are never updated or deleted | Same as I-8 |
| I-10 | Sum of credit notes against an invoice ≤ that invoice's amount | Service layer, inside a `SELECT … FOR UPDATE` on the invoice |
| I-11 | `collaborator.user_id` references a user whose role is `account_manager` | Service layer (a DB check would need a trigger for a cross-table condition; not worth it) |
| I-12 | `subscription.owner_id` references an `account_manager` | Service layer, same reasoning |
| I-13 | Every status change writes exactly one `invoice_event` | Service layer — the transition function is the only writer of `status` |
| I-14 | An archived subscription generates no new invoices | Service layer (bulk generation filters `archived_at IS NULL`) |

I-4 is a **partial** unique index — `WHERE status <> 'void'`. Voiding an invoice must free the
period so a corrected one can be generated. That is the whole point of voiding a wrong draft.

## 6. Ambiguity rulings

The brief leaves these genuinely open. Each is ruled here so the code has one answer, and each
lands in `docs/decisions.md` with its reasoning.

**A-01 — Can an AM create a subscription owned by a different AM?**
No. An AM may only create subscriptions they own. A BA may name any AM as owner.
*Why:* otherwise an AM could hand a subscription to a colleague and lose their own access to it, or
manufacture work for someone else. It also makes the RLS INSERT policy expressible in one line.

**A-02 — Can a BA own a subscription?**
No. `owner_id` must point to a user with role `account_manager`. Goal 2 says "an owning account
manager", which is a role constraint, not a suggestion. BAs reach everything by role, not ownership.

**A-03 — Is a Void invoice editable?**
No. Void is terminal and fully immutable. The brief only forbids editing Paid invoices explicitly,
but a void carries a reason and stands as a record; letting it be edited would undermine the same
principle Goal 9 exists to protect.

**A-04 — Can a credit note be issued against a Draft or Issued invoice?**
No. Paid only. Goal 4 frames the credit note as the correction mechanism *for a Paid invoice*,
because Draft and Issued invoices have their own correction paths (edit, and void-and-reissue).
Allowing credit notes everywhere would give two ways to do the same thing with different audit trails.

**A-05 — May a credit note exceed the invoice amount?**
No — individually or cumulatively (I-10). A credit larger than the charge is a refund, which is a
different concept the brief does not ask for.

**A-06 — Does a credit note reduce "revenue collected"?**
The dashboard reports **gross collected** (sum of Paid invoice amounts in the window) and shows
**total credited** as a separate figure beside it. Netting them into one number hides information
the finance team in the scenario specifically lost when they were on spreadsheets. The dashboard
labels both explicitly.

**A-07 — Exactly what counts as overdue?**
`status = 'issued' AND due_date < today`. Draft is not overdue (never sent). Paid is not overdue.
Void is not overdue. `due_date == today` is not yet overdue — the customer has the day.

**A-08 — What is "invoices issued this month"?**
The count of invoices whose *first* transition into `issued` happened this calendar month — read
from `invoice_events`, not from current status. An invoice issued in March and paid in April still
counts as issued in March. This is the answer that survives the follow-up question in an interview.

**A-09 — What is "revenue collected this month"?**
Sum of `amount` over invoices whose transition to `paid` happened this calendar month, read from
`invoice_events.created_at`. Requires the event trail to be trustworthy, which Goal 9 guarantees.
An indexed `paid_at` column on `invoices` is denormalised from that event for query speed — see
[03](03-database-schema.md) §3.

**A-10 — When exactly does a dismissed alert return? (Goal 10)**
Dismissal stores the due date it was dismissed against:
`AlertDismissal(invoice, dismissed_for_due_date, dismissed_by, dismissed_at)`.
An invoice's alert is **active** when:
```
status = 'issued'
AND due_date < today
AND (no dismissal row  OR  dismissal.dismissed_for_due_date <> invoice.due_date)
```
Walk the scenario in the brief: invoice overdue → alert shows → BA dismisses, storing
`dismissed_for_due_date = 2025-04-01` → alert gone. BA extends the due date to 2025-05-01 → still
gone, because it is no longer overdue at all. 2025-05-02 arrives, still unpaid → overdue again, and
`dismissed_for_due_date (04-01) <> due_date (05-01)` → **the alert returns.** Exactly the rule.
Storing a boolean `dismissed` flag instead would fail this; storing `dismissed_at` and comparing to
a due-date-change timestamp would work but needs a second timestamp and is harder to explain.

**A-11 — Who can dismiss an alert?**
BA only. Goal 10 says "A billing admin can dismiss the alert" and says nothing about AMs. AMs see
the alerts for their own subscriptions but get no dismiss control.

**A-12 — Whose alerts appear in whose badge?**
The alert list is scoped exactly like the invoice list: a BA sees all, an AM sees alerts on
subscriptions they own or collaborate on. The badge count matches the list the viewer can see.

**A-13 — What does bulk generation do with a subscription that has not started yet?**
Reported as `skipped`, reason `"subscription has not started (starts YYYY-MM-DD)"`. Not `failed` —
nothing went wrong. Goal 7's three outcomes are generated / skipped / failed, and "no period exists
today" is a legitimate skip.

**A-14 — What does bulk generation do when the existing invoice for the period is Void?**
Generates a new one. I-4's partial unique index permits it, and this is the intended recovery path
after voiding a mistake. The report says `generated`.

**A-15 — Are invoices for archived subscriptions still visible and payable?**
Yes. Archiving stops *generation* only (Goal 2: "without destroying its invoice history"). Existing
invoices on an archived subscription can still be issued, paid and voided by a BA.

**A-16 — Can an archived subscription be edited?**
No, other than restoring it. Editing a stopped arrangement has no meaning and invites confusion
about whether it will resume billing. Restore first, then edit.

**A-17 — Timezone for "today", "this month", "last eight weeks".**
UTC throughout, via `timezone.localdate()` with `TIME_ZONE="UTC"`. Documented in
`docs/architecture.md` as a deliberate simplification: a real multi-region billing system would
anchor to the customer's timezone, and getting that wrong quietly is worse than not doing it.

**A-18 — Are notes editable or deletable?**
No. A note is an `invoice_event` and Goal 9 says nothing in the timeline can be edited or deleted,
"including by billing admins". Enforced by trigger, not by convention.

## 7. Event taxonomy (Goal 9)

Every row in `invoice_events` has an `event_type` from this closed set. `details` is JSONB, shaped
per type, so the timeline renderer can be a simple dispatch.

| `event_type` | Emitted when | `details` shape |
|---|---|---|
| `created` | Invoice row is created | `{"amount": "…", "period_start": "…", "period_end": "…", "due_date": "…", "source": "manual"\|"bulk"}` |
| `status_changed` | Any transition | `{}` — `old_status` / `new_status` are first-class columns |
| `voided` | Transition to void | `{"reason": "…"}` — emitted **in addition to** `status_changed`, so the reason has a home |
| `field_changed` | A Draft edit or a due-date change | `{"changes": {"due_date": {"from": "…", "to": "…"}}}` |
| `credit_note_issued` | Credit note created | `{"credit_note_id": "…", "amount": "…", "reason": "…"}` |
| `note_added` | Someone leaves a note | `{"text": "…"}` |

Every event carries `actor_id` (nullable only for system-generated events, of which there are
currently none — bulk generation records the BA who triggered it) and `created_at`.

`old_status` / `new_status` are real columns rather than JSONB keys because Goal 9 names them
specifically ("every status change with the old and new status and who made it") and because the
dashboard queries them (A-08, A-09). Indexing a JSONB key for that would be needless work.
