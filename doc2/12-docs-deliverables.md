# 12 — The Graded Docs

Five files under `docs/` plus `SUBMISSION.md` are graded directly, and the brief says the record of
thinking is what separates submissions — the app is "the evidence for that judgement, not the
deliverable in itself". This file plans them like features.

The key move: **each doc is assembled from material generated during the work**, not written from
memory at the end. Every session's closing ritual ([11](11-git-and-sessions.md) §5) feeds them.

## 1. `docs/architecture.md`

Must answer: the moving pieces, how they talk, where each runs, one request path end to end, and
what was deliberately not built.

Current state: good, and accurate for the auth slice. Needs the billing domain added.

| Section | Change | Source |
|---|---|---|
| Moving pieces | Add `src.billing` — models, services, views split; state that all rules live in `services/` and why | [06](06-backend-build-plan.md) |
| Moving pieces | Add the frontend properly: routes, API client, token refresh, and the "client never re-implements a rule" principle | [07](07-frontend-build-plan.md) §1 |
| Where each runs | Replace "Production Target / TBD" with the real Supabase + Render + Vercel URLs | [10](10-deployment-plan.md) |
| Request path | **Replace `GET /api/auth/me/` with `POST /api/invoices/{id}/pay/`** | below |
| Not built | Rewrite entirely | below |

### The request path to use

`GET /api/auth/me/` is a poor choice — it touches one table and demonstrates nothing about the
system. `POST /api/invoices/{id}/pay/` traverses every layer that matters:

```
Browser: POST /api/invoices/{id}/pay/  ·  Authorization: Bearer <jwt>
  → CorsMiddleware  → SecurityMiddleware  → CommonMiddleware
  → RLSTransactionMiddleware
        decodes the JWT (no DB hit — role and user_id are claims)
        opens transaction.atomic()
        SET LOCAL app.user_id / app.role
  → router → InvoiceViewSet.pay
  → DRF JWTAuthentication loads request.user (1 query, RLS-filtered)
  → IsBillingAdmin → 403 LIFECYCLE_ADMIN_ONLY for an account manager
  → services.invoices.transition(invoice, PAID, actor)
        SELECT … FOR UPDATE                  (re-read under a row lock)
        _assert_allowed(issued → paid)       (409 InvalidTransition otherwise)
        UPDATE invoices SET status, paid_at  (RLS WITH CHECK + trg_invoice_guard)
        INSERT INTO invoice_events           (append-only)
  → serialise → 200
  → middleware commits; SET LOCAL discarded with the transaction
```

Annotate each step with what would stop a *bad* request there. That single diagram answers the
defence-in-depth question before it is asked.

### "What we decided not to build"

Not a list of unfinished work — a list of considered choices. Each with a reason, and where useful
the trigger that would change the answer:

- **No `plans` table** — plan is a string. Revisit when plans carry their own price or features.
- **No async workers.** Bulk generation is synchronous. At the brief's scale it is sub-second; at
  20k subscriptions it needs chunking and a job record. Documented, not built.
- **No email.** A reminder-email stretch goal was skipped; nothing in the ten goals sends mail.
- **No soft delete anywhere.** Subscriptions archive, invoices void, nothing is deleted.
- **No refresh-token blacklist.** `ROTATE_REFRESH_TOKENS` is on, blacklisting is off. Logout is
  client-side token disposal. Honest limitation: a stolen refresh token stays valid until expiry.
- **No multi-tenancy.** Roles, not tenants. RLS is doing tenant-shaped work for a single-tenant app,
  which is the honest description of it.
- **No frontend tests.** [08](08-testing-plan.md) §1 has the reasoning.

## 2. `docs/schema.md`

Must answer: every column and type, one-to-many vs many-to-many, DB vs app constraints, deliberate
denormalisation, and what breaks first at 100×.

Current state: a good design sketch, all marked "planned". Becomes a description of what exists.

| Section | Source |
|---|---|
| All six tables, column by column | [03](03-database-schema.md) §1–6 verbatim |
| Relationships | [02](02-domain-model.md) §2 |
| DB vs app constraints | [02](02-domain-model.md) §5 — the invariant table has an "enforced by" column already |
| Denormalisation | [03](03-database-schema.md) §3 — `issued_at`/`paid_at`, with cost and mitigation. Also §7, plans as strings |
| 100× | [03](03-database-schema.md) §10 |

Two things to preserve when rewriting:

- **The invariant table with its enforcement column** is the single most useful artefact for the
  "database vs application" question. It answers it as a table rather than as prose.
- **Say that `alert_dismissals` is a separate table because writing it must not UPDATE a possibly-
  immutable invoice.** That is a structural consequence of two goals colliding, and noticing it is
  the kind of thing the brief is looking for.

The 100× section should include the one thing that *doesn't* break — the 8-week chart stays a
bounded range scan. A risk list where everything is a risk is not analysis.

## 3. `docs/plan.md`

Must answer: how the work split into sessions, the order and why, estimated vs actual, and what was
cut when short.

Current state: honest but thin, plus a large pasted auth plan.

**Restructure:**

1. **How I split the work** — the seven sessions and the reasoning for the order
   ([11](11-git-and-sessions.md) §5): RLS first because retrofitting it is a rewrite; deploy in
   Session 5 because hosting fails unpredictably; frontend last because it cannot precede its API.
2. **Estimated vs actual** — a per-session table, filled in *at the end of each session*:

   | Session | Planned | Est. | Actual | Notes |
   |---|---|---|---|---|
   | 1 | Models, RLS, triggers | 2:15 | | |

   The Notes column is the valuable one. "RLS `SECURITY DEFINER` on the membership function took 40
   minutes to work out — the recursive-policy failure mode is not obvious" is worth more than any
   number in the row.
3. **What I cut and why** — from [11](11-git-and-sessions.md) §7, marking which cuts were actually
   made. Include the ones considered and *not* made.
4. **What I got wrong about the estimates** — the plan budgets 16 hours against a 12-hour guide, and
   said so in advance. Whether that was right, and where the estimates were worst.

Move the pasted auth plan to an appendix or drop it — `doc2/` is now the working-plan home, and the
graded doc should be readable.

## 4. `docs/decisions.md`

Must answer: at least five real decisions — chosen, rejected, why — including at least one reversed.

Current state: five solid entries, all from the auth phase. Needs the billing-phase decisions, which
are where the interesting trade-offs are. Target ten to twelve.

The queue, from [13](13-risks-and-decisions.md) §3:

| # | Decision | Reversed? |
|---|---|---|
| 6 | RLS cannot express OLD-vs-NEW; those rules moved to triggers | **Yes** — the strongest candidate |
| 7 | Services layer owns all business rules; models and views stay thin | |
| 8 | `issued_at`/`paid_at` denormalised from the event trail | |
| 9 | Plans are strings, not a table | |
| 10 | 404 rather than 403 for invisible resources | |
| 11 | Partial unique index on period, so voiding frees the period | |
| 12 | Tokens in `localStorage` — accepted risk, mitigation named | |
| 13 | Dashboard reports gross collected and credits separately, never netted | |
| 14 | Bulk generation uses a savepoint per subscription, not all-or-nothing | |
| 15 | Deployed in Session 5, before the app was finished | |

**Decision 6 is the reversal to lead with.** The story is complete and it is genuinely about
learning something: I wrote an RLS policy containing
`AND (archived_at IS NOT DISTINCT FROM archived_at)` believing it prevented account managers from
archiving. It compares a column to itself and is always true. The root cause is that an RLS policy
has no `OLD` row — the rule was not expressible where I put it. Reversed to a `BEFORE UPDATE`
trigger, and the general principle (any rule comparing new to old belongs in a trigger) was then
applied to owner reassignment and to the issued-invoice amount lock as well. Chosen, rejected, why,
what changed my mind, and what it generalised to — the entry writes itself, and it is true.

Decision 2 already carries a `Later reversed:` line (PyJWT → simplejwt), so the requirement is met
twice. Good.

## 5. `docs/ai-prompts.md`

Must answer: the prompts actually used, in order, grouped by intent, including at least one that
produced something wrong and what was done about it.

Current state: four entries, well-structured, with real corrections recorded. The format works —
keep it.

**Append per session, same day.** Each entry: what I was trying to do, the prompt, what came back,
what I corrected.

Entries this phase should include, at minimum:

- The domain-model and schema design prompt (this one — planning the billing domain).
- The RLS policy prompt, and the fact that **the output contained the tautological `archived_at`
  clause, the unguarded UUID cast, and no handling of management commands running outside a
  request** — three defects, found by auditing the SQL rather than by running it, since they fail
  silently. That is the strongest "produced something wrong" entry available and it is real.
- The period-arithmetic prompt, and whether the month-end clamping was right first time.
- Any prompt where the output was accepted and later turned out to need reversing.

The brief says *"Submitting generated code you cannot explain is the single most common way
candidates fail this round."* The defence is that every non-obvious line in the codebase is
explained in one of these docs. Two practices support that:

1. **Nothing lands without being understood.** `SECURITY DEFINER`, the partial unique index, the
   savepoint-per-subscription pattern — each is explained in a doc or a commit body, and each is
   there because I can say why.
2. **Record the corrections, not just the wins.** The corrections are the evidence of direction and
   verification, which is what is actually being assessed.

## 6. `SUBMISSION.md`

The first file opened. Currently accurate: Goal 1 Done, 2–10 Not done.

| Section | Plan |
|---|---|
| Links | Repo + live URL, both verified from a logged-out browser before submitting |
| Notes | Render's 30–60s cold start, in the brief's own terms. Plus one line pointing at the best demo path: *"Log in as the admin, open Northwind Traders' most recent paid invoice — it shows the full audit timeline, a credit note and the immutability rules."* |
| Demo credentials | Unchanged. `manager3` stays unpublished on purpose ([09](09-seed-data-plan.md) §2) |
| Stack | Fill in the real hosting row |
| Goal checklist | Updated at the end of **every** session, not at the end |
| Time spent | The real number, per session, from `docs/plan.md` |
| Next 12 hours | Concrete: the concurrency tests, chunked bulk generation with a job record, an httpOnly refresh cookie, frontend tests, usage-based add-ons |
| Least happy with | The one that must be honest — see below |

### "What are you least happy with"

A real answer scores; a humblebrag does not. The honest candidates, to be picked from what is true
at the end:

- Two settings modules survived far longer than they should have, and the duplicate `src/settings.py`
  disagreed with the live one for several commits. It was cleaned up, but it should never have
  existed.
- The RLS layer is genuinely good and genuinely more than this app needs. It is a role-based app, not
  a multi-tenant one, and RLS is tenant-shaped machinery. I would defend it as defence-in-depth, but
  a reviewer arguing it is over-engineering for a two-role system would not be wrong.
- No frontend tests at all. A deliberate cut, but it means the client's error handling is verified
  only by hand.
- `issued_at`/`paid_at` can theoretically drift from the event trail. The transition function is the
  only writer, but "only one place writes it" is a discipline guarantee, not a structural one.

Pick whichever is truest at the end and say it plainly. The brief is asking whether I can see my own
work clearly.
