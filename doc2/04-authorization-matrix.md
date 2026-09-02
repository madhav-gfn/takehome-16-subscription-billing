# 04 — Authorization

## 1. The division of labour

Three layers. Each answers a different question, and the boundaries matter because overlapping them
is how you get a system where nobody can say where a rule lives.

| Layer | Question it answers | Failure mode it produces |
|---|---|---|
| **DRF permissions** | Is this *role* allowed to attempt this *action* at all? | 403 with an explanatory message |
| **Service layer** | Is this action legal for this *object* in its current *state*? | 409 / 400 with a domain error code |
| **PostgreSQL RLS** | Which *rows* may this session see or write? | Row invisible, or `0 rows updated` |

The rule I hold to: **RLS never produces user-facing error messages.** If RLS is the thing that
stops a request, a layer above should already have stopped it with a better message. RLS firing
means a bug in the layer above — it is the seatbelt, not the steering.

The corollary is that RLS is never load-bearing for UX, so it can be strict without making the API
hostile.

## 2. Role × action matrix

`own` = AM owns the subscription. `collab` = AM is a collaborator. `other` = neither.

| # | Action | BA | AM (own) | AM (collab) | AM (other) |
|---|---|---|---|---|---|
| 1 | List subscriptions | all | own+collab only | own+collab only | — |
| 2 | View subscription | ✓ any | ✓ | ✓ | ✗ 404 |
| 3 | Create subscription | ✓ (any owner) | ✓ (self as owner) | — | — |
| 4 | Edit subscription | ✓ | ✓ | ✓ | ✗ 404 |
| 5 | Archive subscription | ✓ | ✗ 403 | ✗ 403 | ✗ 404 |
| 6 | Restore subscription | ✓ | ✗ 403 | ✗ 403 | ✗ 404 |
| 7 | Add collaborator | ✓ | ✗ 403 | ✗ 403 | ✗ 404 |
| 8 | Remove collaborator | ✓ | ✗ 403 | ✗ 403 | ✗ 404 |
| 9 | List invoices | all | own+collab | own+collab | — |
| 10 | View invoice | ✓ any | ✓ | ✓ | ✗ 404 |
| 11 | Create invoice | ✓ | ✓ | ✓ | ✗ 404 |
| 12 | Edit Draft invoice | ✓ | ✓ | ✓ | ✗ 404 |
| 13 | Change due date (Draft/Issued) | ✓ | ✓ | ✓ | ✗ 404 |
| 14 | **Issue** invoice | ✓ | ✗ 403 | ✗ 403 | ✗ 404 |
| 15 | **Mark paid** | ✓ | ✗ 403 | ✗ 403 | ✗ 404 |
| 16 | **Void** | ✓ | ✗ 403 | ✗ 403 | ✗ 404 |
| 17 | **Credit note** | ✓ | ✗ 403 | ✗ 403 | ✗ 404 |
| 18 | Add note | ✓ | ✓ | ✓ | ✗ 404 |
| 19 | View timeline | ✓ | ✓ | ✓ | ✗ 404 |
| 20 | Bulk generate | ✓ | ✗ 403 | ✗ 403 | — |
| 21 | Export receivables CSV | ✓ | ✓ (own+collab rows) | ✓ | — |
| 22 | Dashboard | ✓ (all data) | ✓ (own+collab data) | ✓ | — |
| 23 | View alerts | ✓ (all) | ✓ (own+collab) | ✓ | — |
| 24 | Dismiss alert | ✓ | ✗ 403 | ✗ 403 | ✗ 404 |

Rows 14–17 and 20 are the exact list Goal 1 spells out as forbidden to account managers. Rows 5–8
and 24 complete it from Goals 2, 5 and 10.

### 404 vs 403 — the deliberate choice

An AM acting on a subscription they cannot see gets **404, not 403**. A 403 confirms the resource
exists, which leaks the customer list across account managers. A 404 does not. This falls out
naturally because the queryset is already RLS- and ORM-scoped, so `get_object_or_404` finds nothing.

An AM acting on a subscription they *can* see but attempting an admin-only action gets **403** with
a message naming the role required. They already know the object exists; hiding the reason would
just be unhelpful.

That distinction is worth stating out loud in `docs/decisions.md` — it is the kind of thing a
reviewer asks about, and "it happened to work that way" is a bad answer.

## 3. Where each check is implemented

```
src/billing/permissions.py
    IsBillingAdmin                     # rows 5-8, 14-17, 20, 24
    IsSubscriptionMember               # rows 2,4,10-13,18,19 — object-level
    CanCreateInvoiceForSubscription    # row 11

src/billing/services/invoice_lifecycle.py
    issue() / mark_paid() / void() / add_credit_note() / edit_draft() / change_due_date()
    # every state precondition, every I-* invariant, every event emission

src/billing/querysets.py
    visible_subscriptions(user) -> QuerySet
    visible_invoices(user)      -> QuerySet
    # the ORM-level scoping that produces the 404s, mirroring RLS exactly
```

**`visible_subscriptions` and RLS say the same thing twice, on purpose.** The ORM filter is what
makes the API behave correctly and testable on SQLite; RLS is what makes it true even if someone
later writes a view that forgets the filter. When they disagree, RLS wins and the symptom is a
missing row — which the RLS test suite exists to catch.

```python
def visible_subscriptions(user):
    qs = Subscription.objects.all()
    if user.role == Role.BILLING_ADMIN:
        return qs
    return qs.filter(Q(owner_id=user.id) | Q(collaborators__user_id=user.id)).distinct()
```

`.distinct()` is required — the collaborator join duplicates rows. Forgetting it produces duplicate
entries in the Goal 5 list and inflates the Goal 6 pagination count. It is a one-word bug with a
visible symptom, so it gets an explicit test.

## 4. RLS policies — the rewrite

Replaces `src/accounts/rls_policies.sql` wholesale (defects D-03, D-04, D-05). Ships as
`billing/migrations/0003_rls.py`. The full text lives in the migration; the shape and the reasoning
are here.

### Preamble

```sql
ALTER TABLE subscriptions     ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions     FORCE  ROW LEVEL SECURITY;
-- …same for collaborators, invoices, credit_notes, invoice_events, alert_dismissals
```

`FORCE` matters: Django connects as the table owner, and without `FORCE` the owner bypasses RLS
entirely, making every policy decorative. This is the single line that decides whether the
defence-in-depth story is real.

### Two helper functions

Every policy needs the current actor. Repeating the `NULLIF(...)::uuid` incantation twenty times is
how D-03 happened; two `STABLE` functions make each policy readable and fix the cast in one place.

```sql
CREATE OR REPLACE FUNCTION app_user_id() RETURNS uuid AS $$
    SELECT NULLIF(current_setting('app.user_id', true), '')::uuid;
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION app_role() RETURNS text AS $$
    SELECT coalesce(current_setting('app.role', true), 'anonymous');
$$ LANGUAGE sql STABLE;
```

`NULLIF` is the D-03 fix: an anonymous request sets `app.user_id = ''`, and `''::uuid` raises
rather than denying. `NULL::uuid` compares to NULL, which is falsy in a policy — a clean deny.

`STABLE` (not `IMMUTABLE`) lets the planner cache the value within a statement while still
re-reading it per statement. `IMMUTABLE` would be wrong and could be constant-folded across a
session.

```sql
-- Membership test, used by almost every policy. One place to get it right.
CREATE OR REPLACE FUNCTION app_can_reach_subscription(sub_id uuid) RETURNS boolean AS $$
    SELECT EXISTS (
        SELECT 1 FROM subscriptions s
        WHERE s.id = sub_id
          AND (s.owner_id = app_user_id()
               OR EXISTS (SELECT 1 FROM collaborators c
                          WHERE c.subscription_id = s.id AND c.user_id = app_user_id()))
    );
$$ LANGUAGE sql STABLE SECURITY DEFINER;
```

`SECURITY DEFINER` is required here and is the subtlest thing in this file. Without it, the inner
`SELECT` on `subscriptions` is itself filtered by the subscriptions policies, and the invoice
policy's membership check becomes recursive. With it, the function runs as its owner and sees all
rows — which is safe because it returns only a boolean about the caller's own access.

### `subscriptions`

```sql
CREATE POLICY sub_admin_all ON subscriptions FOR ALL
    USING (app_role() = 'billing_admin') WITH CHECK (app_role() = 'billing_admin');

CREATE POLICY sub_am_select ON subscriptions FOR SELECT
    USING (app_role() = 'account_manager'
           AND (owner_id = app_user_id()
                OR EXISTS (SELECT 1 FROM collaborators c
                           WHERE c.subscription_id = subscriptions.id
                             AND c.user_id = app_user_id())));

-- A-01: an AM may only create subscriptions they own.
CREATE POLICY sub_am_insert ON subscriptions FOR INSERT
    WITH CHECK (app_role() = 'account_manager' AND owner_id = app_user_id());

-- Archiving and owner reassignment are blocked by trg_sub_guard_archive,
-- not here (D-04). See the note below.
CREATE POLICY sub_am_update ON subscriptions FOR UPDATE
    USING (app_role() = 'account_manager'
           AND (owner_id = app_user_id()
                OR EXISTS (SELECT 1 FROM collaborators c
                           WHERE c.subscription_id = subscriptions.id
                             AND c.user_id = app_user_id())))
    WITH CHECK (app_role() = 'account_manager');
```

**Why `WITH CHECK` cannot pin `owner_id`.** The obvious rule — "an AM must not reassign a
subscription to someone else" — looks like `WITH CHECK (owner_id = app_user_id())`. That is wrong
twice over. It would block a *collaborator* from editing at all, since a collaborator is not the
owner; and what the rule actually means is "`NEW.owner_id` must equal `OLD.owner_id`", which a
policy cannot express because it has no `OLD`.

So owner reassignment is guarded exactly the way archiving is: `trg_sub_guard_archive` is extended
to also reject `NEW.owner_id IS DISTINCT FROM OLD.owner_id` when `app_role() <> 'billing_admin'`.

This is the same lesson as D-04, hit a second time from a different direction, and it generalises
into the rule this whole file follows: **any rule that compares a new value to a previous value
belongs in a trigger, never in a policy.** It is the non-obvious thing this build taught me about
RLS, and it is queued as decision 6 in [13](13-risks-and-decisions.md) §3.

No DELETE policy for AMs ⇒ deletion denied. Intentional: nothing is ever deleted.

### `collaborators`

```sql
CREATE POLICY collab_admin_all ON collaborators FOR ALL
    USING (app_role() = 'billing_admin') WITH CHECK (app_role() = 'billing_admin');

CREATE POLICY collab_am_select ON collaborators FOR SELECT
    USING (app_role() = 'account_manager' AND app_can_reach_subscription(subscription_id));
```

Only the admin policy covers INSERT/DELETE ⇒ Goal 5's "only a billing admin can add or remove a
collaborator" is enforced in the database, not merely in a view. An AM sees the full collaborator
list of any subscription they are on, so the UI can show who else is working the account — broader
than "only their own rows", and the right call for the feature.

### `invoices`

```sql
CREATE POLICY inv_admin_all ON invoices FOR ALL
    USING (app_role() = 'billing_admin') WITH CHECK (app_role() = 'billing_admin');

CREATE POLICY inv_am_select ON invoices FOR SELECT
    USING (app_role() = 'account_manager' AND app_can_reach_subscription(subscription_id));

-- AMs create drafts only. Lifecycle transitions are admin-only (Goal 1).
CREATE POLICY inv_am_insert ON invoices FOR INSERT
    WITH CHECK (app_role() = 'account_manager'
                AND status = 'draft'
                AND app_can_reach_subscription(subscription_id));

CREATE POLICY inv_am_update ON invoices FOR UPDATE
    USING (app_role() = 'account_manager'
           AND status IN ('draft','issued')          -- issued: due_date only, per Goal 3
           AND app_can_reach_subscription(subscription_id))
    WITH CHECK (app_role() = 'account_manager' AND status IN ('draft','issued'));
```

The `WITH CHECK` blocks an AM from writing `status = 'paid'` directly — the row they produce must
still be draft or issued. Combined with `USING`, an AM can never move an invoice into paid or void
by any route, including a hand-crafted `UPDATE`. That is Goal 1's hardest requirement, enforced in
the database.

Freezing amount and period on an issued invoice is again an OLD-vs-NEW rule ⇒ `trg_invoice_guard`,
not a policy.

### `credit_notes`, `invoice_events`, `alert_dismissals`

```sql
CREATE POLICY cn_admin_all ON credit_notes FOR ALL
    USING (app_role() = 'billing_admin') WITH CHECK (app_role() = 'billing_admin');
CREATE POLICY cn_am_select ON credit_notes FOR SELECT
    USING (app_role() = 'account_manager'
           AND EXISTS (SELECT 1 FROM invoices i WHERE i.id = credit_notes.invoice_id
                         AND app_can_reach_subscription(i.subscription_id)));

CREATE POLICY evt_admin_all ON invoice_events FOR ALL
    USING (app_role() = 'billing_admin') WITH CHECK (app_role() = 'billing_admin');
CREATE POLICY evt_am_select ON invoice_events FOR SELECT
    USING (app_role() = 'account_manager'
           AND EXISTS (SELECT 1 FROM invoices i WHERE i.id = invoice_events.invoice_id
                         AND app_can_reach_subscription(i.subscription_id)));
-- AMs insert note events on invoices they can reach.
CREATE POLICY evt_am_insert ON invoice_events FOR INSERT
    WITH CHECK (app_role() = 'account_manager'
                AND event_type = 'note_added'
                AND EXISTS (SELECT 1 FROM invoices i WHERE i.id = invoice_events.invoice_id
                              AND app_can_reach_subscription(i.subscription_id)));

CREATE POLICY dis_admin_all ON alert_dismissals FOR ALL
    USING (app_role() = 'billing_admin') WITH CHECK (app_role() = 'billing_admin');
CREATE POLICY dis_am_select ON alert_dismissals FOR SELECT
    USING (app_role() = 'account_manager'
           AND EXISTS (SELECT 1 FROM invoices i WHERE i.id = alert_dismissals.invoice_id
                         AND app_can_reach_subscription(i.subscription_id)));
```

`evt_admin_all` grants a BA `FOR ALL`, which nominally includes UPDATE and DELETE. Goal 9 forbids
that "including by billing admins" — and `trg_events_append_only` is what actually forbids it. The
policy stays `FOR ALL` for INSERT's sake; the trigger is the enforcement. That is the correct
split: RLS decides *rows*, triggers decide *operations*.

## 5. Attack scenarios the RLS suite must prove closed

Each becomes a test in `test_rls.py`, written as raw SQL against a real Postgres so it bypasses
every Python-side check.

| # | Scenario | Expected |
|---|---|---|
| R-1 | AM session `SELECT * FROM subscriptions` | Only owned + collaborated rows |
| R-2 | AM session `UPDATE subscriptions SET archived_at = now()` on an owned row | Trigger raises `insufficient_privilege` |
| R-3 | AM session `UPDATE subscriptions SET owner_id = <self>` on a collaborated row | Trigger raises |
| R-4 | AM session `UPDATE invoices SET status='paid'` on an owned invoice | 0 rows (WITH CHECK fails) |
| R-5 | AM session `INSERT INTO invoices (…, status) VALUES (…, 'issued')` | Policy rejects |
| R-6 | AM session `INSERT INTO collaborators …` | Policy rejects |
| R-7 | AM session `DELETE FROM invoice_events WHERE …` | Trigger raises |
| R-8 | **BA** session `UPDATE invoice_events SET details='{}'` | Trigger raises — proves "including by billing admins" |
| R-9 | BA session `UPDATE invoices SET amount=1 WHERE status='paid'` | Trigger raises |
| R-10 | Anonymous session (`app.user_id=''`, `app.role='anonymous'`) `SELECT * FROM subscriptions` | 0 rows, **no error** — the D-03 regression test |
| R-11 | AM session `SELECT * FROM invoices` where a collaborator was just removed | Row disappears immediately |
| R-12 | AM session `UPDATE invoices SET due_date=…` on an owned **issued** invoice | Succeeds — proves Goal 3 was not over-restricted |

R-10 and R-12 are the two most valuable tests in the file: one is the bug the audit found, the other
guards against fixing it too enthusiastically.

## 6. `rls_session` — running outside a request (D-06)

Management commands and tests have no middleware, so `app.role` is unset and `FORCE ROW LEVEL
SECURITY` denies everything silently. Every non-request DB path goes through this:

```python
# src/billing/db.py
from contextlib import contextmanager
from django.db import connection, transaction

@contextmanager
def rls_session(role, user_id=""):
    """Run a block with RLS session variables set, as a request would.

    Required for management commands, data migrations and tests — outside a
    request there is no middleware, so app.role is unset and FORCE ROW LEVEL
    SECURITY denies everything without an error message.
    """
    if connection.vendor != "postgresql":
        yield                                   # SQLite test runs are unaffected
        return
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("SET LOCAL app.role = %s", [role])
            cur.execute("SET LOCAL app.user_id = %s", [str(user_id or "")])
        yield
```

Used by `seed_demo` (`with rls_session("billing_admin", admin.id):`) and by every Postgres-backed
test. The failure it prevents — a seed command that reports success while inserting nothing — is
exactly the sort of thing that costs an hour of confused debugging at the worst moment.

**Data migrations are the trap.** A future data migration that touches billing tables will hit the
same wall. `0003_rls.py` gets a comment saying so, pointing at `rls_session`.

## 7. What is deliberately *not* enforced in RLS

Stated plainly, because "we have RLS" invites the assumption that it covers everything:

- **State-machine legality** (draft→paid directly). Service layer + trigger. RLS has no concept of a
  transition, only of a resulting row.
- **Credit-note total ≤ invoice amount** (I-10). Needs an aggregate over sibling rows under a lock;
  a policy cannot take a lock.
- **Owner/collaborator must be an account_manager** (I-11, I-12). Cross-table role check; would need
  yet another trigger for little gain, since only the API creates these rows.
- **Rate limiting, anything about who a user is.** Out of scope entirely.
