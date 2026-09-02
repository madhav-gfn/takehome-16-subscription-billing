# 11 — Git Strategy and Session Schedule

## 1. Why this file exists

The brief is unusually direct about git:

> *"A repository whose entire history is a single 'initial commit' containing a finished app scores
> zero on git history, and it colours how we read everything else in your submission."*

and about pacing:

> *"Budget about 12 hours total, spent roughly 2 hours a day across a week."*

Both are graded. Neither is achievable retroactively — you cannot fake an incremental history at the
end, and a reviewer reading commit timestamps can see a week compressed into one night. So the
schedule is a real constraint on the plan, not a wish.

## 2. Commit conventions

Conventional Commits, already the pattern in the existing history (`feat:`, `chore:`).

```
<type>(<scope>): <imperative summary under 72 chars>

<body — why, not what. The diff shows what.>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`.
Scopes: `billing`, `accounts`, `frontend`, `deploy`, `docs`.

**Rules I hold to:**

1. **One logical change per commit.** A commit that adds a model *and* an endpoint *and* fixes a
   typo cannot be read or reverted.
2. **Every commit leaves the tree working.** `python main.py check` passes and the test suite is
   green. A history of broken intermediate states tells a reviewer nothing about the order I built
   in, only that I committed carelessly.
3. **The body explains the decision** whenever there was one. Especially for the RLS commit, the
   denormalisation commit and anything reversed. These bodies become raw material for
   `docs/decisions.md`.
4. **Reversals are committed as reversals**, with a message saying what changed my mind. The brief
   asks for at least one reversed decision in `docs/decisions.md`; a matching commit is the evidence.
5. **Docs commit with the code they describe**, not in a batch at the end. `docs/plan.md`'s
   "estimated vs actual" is only honest if written the same day.

Example of a body that earns its place:

```
feat(billing): enforce row-level security and immutability at the database tier

Replaces the hand-written rls_policies.sql, which had three defects:

- Casts of current_setting('app.user_id') to UUID raised on anonymous
  requests, where the middleware sets the variable to ''. Now wrapped in
  NULLIF, so an anonymous session denies cleanly instead of 500ing.
- The anti-archiving clause compared archived_at to itself and enforced
  nothing. An RLS policy has no OLD row, so this rule is not expressible
  in RLS at all — it moves to a BEFORE UPDATE trigger.
- The AM insert policy pinned owner_id to the caller without saying why.
  Now explicit and documented as ruling A-01.

The general lesson, applied throughout: any rule comparing a new value to
a previous value belongs in a trigger, never in a policy.
```

## 3. Branching

Work happens on `main`. Given a solo project on a 12-hour budget, feature branches would add merge
noise and hide the linear build order the brief wants to read. No rebasing or squashing of pushed
commits — the mess is the record.

The exception: anything experimental that might be abandoned goes on a short branch and is merged
with `--no-ff` if it works, so the exploration is visible.

## 4. Push cadence

Push at the end of every session. A local-only history is not a public repository, and the brief
asks for commits "as the work actually happens".

## 5. The schedule

Seven sessions of roughly two hours. The backend build plan alone estimates 12:30 and the frontend
7:45 — **20 hours of work against a 12-hour budget.** That conflict is resolved here, explicitly,
rather than discovered at hour 11.

### How it is resolved

1. **Auth is already done** (~2h of the budget already spent and committed).
2. **The backend estimates are padded** with test-writing that partly overlaps implementation. Real
   throughput on steps 5–9 is closer to 70% of the estimate once the patterns are established.
3. **The frontend is deliberately plain.** No component library, no test harness, hand-written CSS.
   F8 polish is the first thing cut.
4. **Some things are cut before starting, not abandoned halfway.** The cut list is §7, and it is
   decided now so that nothing is left half-finished — the brief is explicit that "doing 8 goals well
   beats doing 10 goals badly".

### Session plan

| # | Focus | Steps | Est. | Ends with |
|---|---|---|---|---|
| **1** | Foundation | Backend 0–3 | 2:15 | Models, migrations, RLS, triggers, RLS tests green on Postgres |
| **2** | Subscriptions | Backend 4–5 | 2:15 | Goals 2 + 5 complete and tested via the API |
| **3** | Invoice lifecycle | Backend 6 | 2:00 | Goals 3 + 4 + 9 complete — the heart of the brief |
| **4** | Query + bulk | Backend 7–8 | 2:00 | Goals 6 + 7 complete |
| **5** | Dashboard, alerts, seed, **deploy** | Backend 9–10, deploy §3 | 2:30 | Goals 8 + 10 complete; **live URL working with seeded data** |
| **6** | Frontend core | F0–F4 | 2:30 | Login, subscriptions, invoices, invoice detail — the app is usable |
| **7** | Frontend rest + docs | F5–F8, docs | 2:30 | Dashboard, alerts, bulk UI; all five docs and `SUBMISSION.md` complete; final deploy |
| | | | **16:00** | |

Sixteen hours against a twelve-hour guide. The brief calls twelve "a size guide so you know how much
to attempt", not a hard limit, and says explicitly *"pace yourself, stop when you're tired"*. The
honest position — recorded in `docs/plan.md` — is that this plan is 30% over the guide and the cut
list exists to bring it back if the early sessions run long. Pretending it fits in twelve would make
the "estimated vs actual" section fiction, which is precisely the section the brief asks to be true.

### Why this order

- **RLS in Session 1, not last.** It touches every table and constrains every query. Retrofitting it
  onto a finished app means rewriting every test and discovering that management commands are
  silently broken. Building on it from the start means every later feature is written correctly the
  first time.
- **Deploy in Session 5, not Session 7.** Hosting fails in unpredictable ways and free tiers have
  undocumented restrictions (see [10](10-deployment-plan.md) §3 step 2). Finding out that the
  database will not allow `FORCE ROW LEVEL SECURITY` on the final evening would be unrecoverable;
  finding out in Session 5 costs an hour and a different provider.
- **Frontend last.** It cannot be built against an API that does not exist, and building it against
  a changing API means building it twice. The cost is that the app is unusable-by-hand until Session
  6 — mitigated by curl and by the seed data.
- **Docs continuously, finalised in Session 7.** Each session ends with 10 minutes updating
  `docs/plan.md` (what was estimated, what it took), `docs/decisions.md` (anything decided) and
  `docs/ai-prompts.md` (prompts used, including the bad ones). Writing these from memory at the end
  is both worse and, given the brief's framing, transparently so.

### Per-session closing ritual — 10 minutes, non-negotiable

1. Full Postgres test suite green.
2. Update `docs/plan.md` with actual vs estimated for the session.
3. Append any decision made to `docs/decisions.md` while the reasoning is fresh.
4. Append prompts used to `docs/ai-prompts.md`, **including the ones that produced bad output**.
5. Update the `SUBMISSION.md` goal checklist honestly.
6. Commit and push.

Step 4 is the one that will feel skippable and is not. The brief asks for prompts "including the
ones that produced bad output and what you changed afterwards", and reconstructing those a week
later produces a sanitised fiction that is worth less than nothing.

## 6. Expected commit shape

Roughly 30 commits across 7 sessions, 3–6 per session. Enough to show the order of work; not so many
that the history is noise.

Session 1's sequence, as an illustration:
```
chore: remove duplicate settings modules and normalise line endings
feat(billing): add app skeleton and billing period arithmetic
feat(billing): add subscription, invoice, credit note and audit models
feat(billing): enforce row-level security and immutability at the database tier
fix(accounts): roll back the request transaction on 4xx, not only 5xx
docs: record the session 1 plan-vs-actual and the RLS trigger decision
```

## 7. The cut list

Decided in advance. If a session overruns, cuts come **in this order**, and each is recorded in
`SUBMISSION.md` as a partial with the reason:

1. **Concurrency tests** ([08](08-testing-plan.md) §6). Valuable, but the `select_for_update` they
   verify is visible in the code and defensible in conversation without them.
2. **The `verify_invoice_timestamps` check command.** The denormalisation risk is documented; the
   drift-checker is belt-and-braces.
3. **The 8-week chart** → a table. Goal 8 says "charts", so this is a genuine partial and is
   described as one.
4. **Inline subscription editing** → a separate edit page.
5. **`docker-compose.yml`** — only if deployment already succeeded, since it exists as the fallback.
6. **The `pg_trgm` indexes.** Purely a performance measure at this data size; the search still works.

**Never cut, in any circumstance:** the invoice state machine and its rejection messages (Goal 4),
the append-only timeline (Goal 9), server-side filtering (Goal 6), or the RLS test suite. Those four
are what the submission is actually being read for.

## 8. What a reviewer should be able to see in the history

Stated as a target, because it is the thing being graded:

- Auth built first, then the domain model, then rules, then queries, then UI — a defensible order.
- One commit that fixes three real defects in my own earlier RLS work, with the reasoning in the body.
- At least one reversal, committed as such.
- Docs updated alongside code throughout, not in a single final `docs:` commit.
- Timestamps spread across several days, not one long night.
