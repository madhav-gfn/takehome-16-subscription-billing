# 13 — Risks, Open Questions and the Decision Queue

## 1. Risk register

Ordered by expected cost. Each has a trigger to watch for and a response decided in advance, so the
response is not invented under time pressure.

### R1 — The host will not allow `FORCE ROW LEVEL SECURITY`
**Likelihood** low · **Impact** severe · **Cost if it lands late** an entire session

Without `FORCE`, Django connects as the table owner and bypasses every policy, making the whole RLS
layer decorative — while still appearing to work. Silent failure of the exact thing
`docs/decisions.md` sells hardest.

*Trigger:* the §3 step-2 probe in [10](10-deployment-plan.md) fails.
*Response:* switch to Neon or Render Postgres, both of which grant the needed rights. This is why
the probe runs before anything else is deployed, and why deployment is Session 5 rather than 7.

### R2 — Time. 16 hours of plan against a 12-hour guide
**Likelihood** high · **Impact** moderate

*Trigger:* any session ending more than 30 minutes over.
*Response:* take the next item off the cut list in [11](11-git-and-sessions.md) §7 immediately, and
record it in `SUBMISSION.md` the same session. The failure mode to avoid is not "ran over" — it is
leaving three goals half-finished. The brief says explicitly that eight goals done well beats ten
done badly.

### R3 — Period arithmetic has an off-by-one
**Likelihood** moderate · **Impact** high

Month-end clamping, leap years, inclusive-vs-exclusive period ends. A bug here produces overlapping
or gapped billing periods, which is the worst class of bug in a billing system — it corrupts data
that later becomes immutable.

*Response:* `periods.py` is written test-first with the table in [06](06-backend-build-plan.md) §
Step 1, including the contiguity property test over 24 consecutive periods. It is the first thing
built after the skeleton, and nothing depends on it until it is green.

### R4 — Management commands silently do nothing under RLS (D-06)
**Likelihood** high without the fix · **Impact** high

`seed_demo` reports success while inserting nothing, and it will most likely be discovered on the
deployed database at the end of Session 5.

*Response:* `rls_session()` built in Session 1, and the seed verified against real Postgres locally
in Step 10 rather than only on SQLite.

### R5 — SQLite-only test runs hide RLS and trigger regressions
**Likelihood** high · **Impact** moderate

The fast runner becomes the only runner and the Postgres suite rots.

*Response:* the two guards in [08](08-testing-plan.md) §3 — visible skips plus a banner on the
SQLite settings module — and "full suite green" in the per-session closing ritual.

### R6 — Trigger exceptions surface as 500s
**Likelihood** moderate · **Impact** moderate

A `RAISE EXCEPTION` becomes `django.db.utils.InternalError`. Goal 4 requires "a message explaining
why", and a 500 is the opposite of that.

*Response:* the service layer checks first and returns clean 409s; the exception handler maps known
trigger messages as a backstop and logs at `error`, since a trigger firing means a service bug.

### R7 — The per-request transaction interacts badly with a pooler
**Likelihood** moderate · **Impact** moderate

`CONN_MAX_AGE=600` plus Supabase's transaction pooler produces "prepared statement already exists"
errors with psycopg2 — confusing, intermittent, and easy to misdiagnose as an application bug.

*Response:* use the session pooler (port 5432). Documented in [10](10-deployment-plan.md) §3 with
the reasoning, so the choice is not mistaken for an accident.

### R8 — N+1 queries in the list endpoints
**Likelihood** high without guards · **Impact** low locally, high on a free tier

A free-tier database with 50ms latency turns 50 extra queries into 2.5 seconds.

*Response:* `assertNumQueries` at two data sizes on all three list endpoints
([08](08-testing-plan.md) §5), which tests the property rather than pinning a number.

### R9 — Frontend and backend disagree about "overdue"
**Likelihood** moderate · **Impact** low but embarrassing

A badge that says overdue next to a filter that excludes the row.

*Response:* `is_overdue` and `days_overdue` are computed **only** in SQL and sent to the client. The
client has no date comparison logic anywhere ([07](07-frontend-build-plan.md) §1).

### R10 — Cold start read as a broken deployment
**Likelihood** high · **Impact** low

*Response:* noted in `SUBMISSION.md` in the brief's own terms, plus the explicit "waking the
backend" message after 5 seconds in the client.

### R11 — Generated code I cannot explain
**Likelihood** moderate · **Impact** severe — the brief names it as the most common way to fail

*Response:* every non-obvious construct — `SECURITY DEFINER`, the partial unique index, the
savepoint-per-subscription pattern, `select_for_update` in `transition()` — is explained in a doc or
a commit body, written at the time. If I cannot write the explanation, the code does not land.

## 2. Open questions

Answered with a default so nothing blocks, but flagged for a second look.

**Q1 — Should an account manager be able to void their own draft invoice?**
*Default: no.* Goal 1 lists void among the AM-forbidden actions without qualification. It does mean
an AM who creates a wrong draft must ask an admin to void it, which is mildly awkward but is what
the brief says. Worth raising in conversation as a place where the spec and workflow pull apart —
noticing it is more valuable than quietly "fixing" it.

**Q2 — Should bulk generation catch up missed periods, or only the current one?**
*Default: current period only.* Goal 7 says "the current period's invoices". Back-filling would
change the report's shape (one subscription could generate several invoices) and is not asked for.
Noted in `docs/architecture.md` under what was not built.

**Q3 — What happens to invoices when a subscription's price changes?**
*Default: nothing.* Existing invoices keep their amount; future generated ones use the new price.
This is correct — an invoice is a record of what was charged, not a view of the current price. Worth
stating explicitly because the opposite behaviour would be a serious bug.

**Q4 — Should a credit note be visible in the receivables CSV?**
*Default: no.* Receivables are Issued invoices; credit notes apply to Paid ones, so they cannot
overlap by definition. Mentioned because it looks like a gap until you notice that.

**Q5 — Should the alert badge poll?**
*Default: no timer.* Refetch on route change and after any action that could change the count.
Reasoning in [07](07-frontend-build-plan.md) §6, recorded so it does not read as forgetfulness.

**Q6 — Should archived subscriptions appear in the dashboard's by-plan breakdown?**
*Default: yes for invoice-based figures, no for subscription counts.* Their invoices are real money
and belong in revenue; the subscription itself is not active. Fiddly, and worth one sentence in
`docs/schema.md` so the numbers can be reconciled by hand.

**Q7 — Is one dismissal row per invoice enough, or should dismissals be a history?**
*Default: one row, upserted.* A-10's rule only needs the most recent dismissal. A full history would
be more auditable and is one column of change away if it is ever wanted. Noted rather than built.

## 3. Decision queue for `docs/decisions.md`

Each is decided here; each needs the chosen / rejected / why write-up in the graded doc. Decisions
1–5 already exist from the auth phase.

| # | Decision | Chose | Rejected | Core reason |
|---|---|---|---|---|
| 6 | Where OLD-vs-NEW rules live | `BEFORE UPDATE` triggers | RLS `WITH CHECK` | A policy has no `OLD` row — the rule was not expressible where I first put it. **The reversal entry.** |
| 7 | Business-rule home | A `services/` layer | Fat models; fat views | One transition path shared by views, bulk runs, commands and tests |
| 8 | `issued_at` / `paid_at` | Denormalised onto `invoices` | Deriving from `invoice_events` | Dashboard aggregates become indexed range scans; single-writer discipline bounds the risk |
| 9 | Plans | A string field | A `plans` table | The plan carries no data of its own; price lives on the subscription |
| 10 | Invisible resources | 404 | 403 | A 403 confirms existence and leaks the customer list across account managers |
| 11 | Period uniqueness | Partial unique index `WHERE status <> 'void'` | Full unique index | Voiding must free the period so a corrected invoice can be generated |
| 12 | Token storage | `localStorage` | httpOnly refresh cookie | Cross-origin cookie + CSRF work outweighed the benefit at this scope. Accepted risk, mitigation named |
| 13 | Credits on the dashboard | Gross collected and credits shown separately | Netting them into one figure | Netting hides exactly the information the spreadsheet workflow lost |
| 14 | Bulk transaction shape | Savepoint per subscription | One all-or-nothing transaction | One bad subscription must not waste the run or hide the other results |
| 15 | Deploy timing | Session 5, app unfinished | Session 7, app finished | Hosting fails unpredictably; an unrecoverable discovery on the final evening is the risk being bought out |
| 16 | Frontend tests | None | Vitest + Testing Library | 40 minutes buys more as RLS tests than as component tests at this scope. A cut, stated as one |
| 17 | Frontend data layer | `fetch` + a small `useApi` hook | TanStack Query | Eight screens; the caching rules would be new surface. Trigger for reversal named |

## 4. Things I expect to be asked at interview

Preparing for these is part of the work, not extra. If any answer is thin, that is a signal to go
back to the code.

1. *"Walk me through what happens when an account manager tries to mark an invoice paid."*
   → Three refusals: the button is disabled, `IsBillingAdmin` returns 403 with a message, and the
   RLS `WITH CHECK` on `inv_am_update` rejects the row even by raw SQL. Test R-4 proves the third.
2. *"Why row-level security? Isn't that overkill for two roles?"*
   → Yes, arguably. Defence in depth against my own bugs in a money system, and it is the layer that
   still holds if a view forgets its filter. But it is tenant-shaped machinery on a single-tenant
   app, and I would not fight hard for it. Also in `SUBMISSION.md`'s "least happy with".
3. *"Show me a bug you found in your own work."*
   → The three RLS defects, particularly `archived_at IS NOT DISTINCT FROM archived_at`. Found by
   auditing, not by testing, because all three fail silently.
4. *"How do you know the audit trail cannot be edited?"*
   → No route exists, no RLS UPDATE/DELETE policy exists, and `trg_events_append_only` raises. Test
   R-8 does it as a billing admin, which is the case Goal 9 names.
5. *"Why is `alert_dismissals` its own table?"*
   → Because dismissing must not UPDATE an invoice that may be immutable. Goals 4 and 10 collide,
   and a column would have forced a hole in the immutability trigger.
6. *"What breaks first at 100×?"*
   → The exact-count pagination, before anything else. [03](03-database-schema.md) §10 ranks the
   rest, including the one thing that does not break.
7. *"What would you do differently?"*
   → Build `periods.py` and the RLS layer before the auth API rather than after, and delete the
   duplicate settings module the day it appeared instead of six commits later.
