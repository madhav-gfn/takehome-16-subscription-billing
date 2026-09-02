"""Row-level security policies.

Replaces src/accounts/rls_policies.sql, which had three defects (see
doc2/01-current-state-audit.md, D-03/D-04/D-05):

  * Casts of current_setting('app.user_id') to UUID raised on anonymous
    requests, where the middleware sets the variable to ''. Now wrapped in
    NULLIF, so an anonymous session denies cleanly instead of 500ing.
  * The anti-archiving clause compared archived_at to itself and enforced
    nothing. An RLS policy has no OLD row, so that rule is not expressible in
    RLS at all — it lives in a trigger (migration 0003).
  * The account-manager INSERT policy pinned owner_id without saying why. It is
    now explicit and documented as ruling A-01.

The general rule this file follows: RLS decides which ROWS a session may
touch; triggers decide what may CHANGE about a row.

NOTE for future data migrations: anything here that reads or writes billing
tables must wrap itself in src.billing.db.rls_session(), or FORCE ROW LEVEL
SECURITY will silently deny it.
"""

from django.db import migrations

FORWARD = r"""
-- ---------------------------------------------------------------- helpers --
-- Repeating the NULLIF cast in twenty policies is how the original bug
-- happened. Two STABLE functions fix it in one place.

CREATE OR REPLACE FUNCTION app_user_id() RETURNS uuid AS $$
    SELECT NULLIF(current_setting('app.user_id', true), '')::uuid;
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION app_role() RETURNS text AS $$
    SELECT coalesce(current_setting('app.role', true), 'anonymous');
$$ LANGUAGE sql STABLE;

-- SECURITY DEFINER is required, and is the subtlest thing in this file.
-- Without it the inner SELECT on subscriptions is itself filtered by the
-- subscriptions policies, and the invoice policies' membership check becomes
-- recursive. With it the function runs as its owner and sees all rows, which
-- is safe because it returns only a boolean about the caller's own access.
CREATE OR REPLACE FUNCTION app_can_reach_subscription(sub_id uuid)
RETURNS boolean AS $$
    SELECT EXISTS (
        SELECT 1 FROM subscriptions s
        WHERE s.id = sub_id
          AND (s.owner_id = app_user_id()
               OR EXISTS (SELECT 1 FROM collaborators c
                          WHERE c.subscription_id = s.id
                            AND c.user_id = app_user_id()))
    );
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- ------------------------------------------------------------------ enable --
-- FORCE matters: Django connects as the table owner, and without it the owner
-- bypasses RLS entirely, making every policy below decorative.

ALTER TABLE subscriptions     ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions     FORCE  ROW LEVEL SECURITY;
ALTER TABLE collaborators     ENABLE ROW LEVEL SECURITY;
ALTER TABLE collaborators     FORCE  ROW LEVEL SECURITY;
ALTER TABLE invoices          ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices          FORCE  ROW LEVEL SECURITY;
ALTER TABLE credit_notes      ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_notes      FORCE  ROW LEVEL SECURITY;
ALTER TABLE invoice_events    ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoice_events    FORCE  ROW LEVEL SECURITY;
ALTER TABLE alert_dismissals  ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_dismissals  FORCE  ROW LEVEL SECURITY;

-- ----------------------------------------------------------- subscriptions --

CREATE POLICY sub_admin_all ON subscriptions FOR ALL
    USING (app_role() = 'billing_admin')
    WITH CHECK (app_role() = 'billing_admin');

CREATE POLICY sub_am_select ON subscriptions FOR SELECT
    USING (app_role() = 'account_manager'
           AND (owner_id = app_user_id()
                OR EXISTS (SELECT 1 FROM collaborators c
                           WHERE c.subscription_id = subscriptions.id
                             AND c.user_id = app_user_id())));

-- Ruling A-01: an account manager may only create subscriptions they own.
CREATE POLICY sub_am_insert ON subscriptions FOR INSERT
    WITH CHECK (app_role() = 'account_manager' AND owner_id = app_user_id());

-- WITH CHECK cannot pin owner_id here: "NEW.owner_id must equal OLD.owner_id"
-- needs an OLD row, which a policy does not have, and the naive
-- `owner_id = app_user_id()` would block collaborators from editing at all.
-- Owner reassignment and archiving are both guarded by trg_sub_guard.
CREATE POLICY sub_am_update ON subscriptions FOR UPDATE
    USING (app_role() = 'account_manager'
           AND (owner_id = app_user_id()
                OR EXISTS (SELECT 1 FROM collaborators c
                           WHERE c.subscription_id = subscriptions.id
                             AND c.user_id = app_user_id())))
    WITH CHECK (app_role() = 'account_manager');

-- No DELETE policy for account managers: nothing is ever deleted.

-- ----------------------------------------------------------- collaborators --
-- Only the admin policy covers INSERT/DELETE, so Goal 5's "only a billing
-- admin can add or remove a collaborator" is enforced in the database, not
-- merely in a view.

CREATE POLICY collab_admin_all ON collaborators FOR ALL
    USING (app_role() = 'billing_admin')
    WITH CHECK (app_role() = 'billing_admin');

CREATE POLICY collab_am_select ON collaborators FOR SELECT
    USING (app_role() = 'account_manager'
           AND app_can_reach_subscription(subscription_id));

-- ---------------------------------------------------------------- invoices --

CREATE POLICY inv_admin_all ON invoices FOR ALL
    USING (app_role() = 'billing_admin')
    WITH CHECK (app_role() = 'billing_admin');

CREATE POLICY inv_am_select ON invoices FOR SELECT
    USING (app_role() = 'account_manager'
           AND app_can_reach_subscription(subscription_id));

CREATE POLICY inv_am_insert ON invoices FOR INSERT
    WITH CHECK (app_role() = 'account_manager'
                AND status = 'draft'
                AND app_can_reach_subscription(subscription_id));

-- The WITH CHECK is Goal 1's hardest requirement, enforced in the database:
-- the row an account manager produces must still be draft or issued, so they
-- can never move an invoice to paid or void by any route, including a
-- hand-crafted UPDATE. Freezing amount and period on an issued invoice is an
-- OLD-vs-NEW rule, so it lives in trg_invoice_guard instead.
CREATE POLICY inv_am_update ON invoices FOR UPDATE
    USING (app_role() = 'account_manager'
           AND status IN ('draft','issued')
           AND app_can_reach_subscription(subscription_id))
    WITH CHECK (app_role() = 'account_manager'
                AND status IN ('draft','issued'));

-- ------------------------------------------------------------ credit notes --

CREATE POLICY cn_admin_all ON credit_notes FOR ALL
    USING (app_role() = 'billing_admin')
    WITH CHECK (app_role() = 'billing_admin');

CREATE POLICY cn_am_select ON credit_notes FOR SELECT
    USING (app_role() = 'account_manager'
           AND EXISTS (SELECT 1 FROM invoices i
                       WHERE i.id = credit_notes.invoice_id
                         AND app_can_reach_subscription(i.subscription_id)));

-- ---------------------------------------------------------- invoice events --
-- evt_admin_all grants FOR ALL, which nominally includes UPDATE and DELETE.
-- Goal 9 forbids that "including by billing admins" — trg_events_append_only
-- is what actually forbids it. The policy stays FOR ALL for INSERT's sake.

CREATE POLICY evt_admin_all ON invoice_events FOR ALL
    USING (app_role() = 'billing_admin')
    WITH CHECK (app_role() = 'billing_admin');

CREATE POLICY evt_am_select ON invoice_events FOR SELECT
    USING (app_role() = 'account_manager'
           AND EXISTS (SELECT 1 FROM invoices i
                       WHERE i.id = invoice_events.invoice_id
                         AND app_can_reach_subscription(i.subscription_id)));

CREATE POLICY evt_am_insert ON invoice_events FOR INSERT
    WITH CHECK (app_role() = 'account_manager'
                AND event_type IN ('created','field_changed','note_added')
                AND EXISTS (SELECT 1 FROM invoices i
                            WHERE i.id = invoice_events.invoice_id
                              AND app_can_reach_subscription(i.subscription_id)));

-- -------------------------------------------------------- alert dismissals --

CREATE POLICY dis_admin_all ON alert_dismissals FOR ALL
    USING (app_role() = 'billing_admin')
    WITH CHECK (app_role() = 'billing_admin');

CREATE POLICY dis_am_select ON alert_dismissals FOR SELECT
    USING (app_role() = 'account_manager'
           AND EXISTS (SELECT 1 FROM invoices i
                       WHERE i.id = alert_dismissals.invoice_id
                         AND app_can_reach_subscription(i.subscription_id)));
"""

REVERSE = r"""
DROP POLICY IF EXISTS dis_am_select     ON alert_dismissals;
DROP POLICY IF EXISTS dis_admin_all     ON alert_dismissals;
DROP POLICY IF EXISTS evt_am_insert     ON invoice_events;
DROP POLICY IF EXISTS evt_am_select     ON invoice_events;
DROP POLICY IF EXISTS evt_admin_all     ON invoice_events;
DROP POLICY IF EXISTS cn_am_select      ON credit_notes;
DROP POLICY IF EXISTS cn_admin_all      ON credit_notes;
DROP POLICY IF EXISTS inv_am_update     ON invoices;
DROP POLICY IF EXISTS inv_am_insert     ON invoices;
DROP POLICY IF EXISTS inv_am_select     ON invoices;
DROP POLICY IF EXISTS inv_admin_all     ON invoices;
DROP POLICY IF EXISTS collab_am_select  ON collaborators;
DROP POLICY IF EXISTS collab_admin_all  ON collaborators;
DROP POLICY IF EXISTS sub_am_update     ON subscriptions;
DROP POLICY IF EXISTS sub_am_insert     ON subscriptions;
DROP POLICY IF EXISTS sub_am_select     ON subscriptions;
DROP POLICY IF EXISTS sub_admin_all     ON subscriptions;

ALTER TABLE alert_dismissals  DISABLE ROW LEVEL SECURITY;
ALTER TABLE invoice_events    DISABLE ROW LEVEL SECURITY;
ALTER TABLE credit_notes      DISABLE ROW LEVEL SECURITY;
ALTER TABLE invoices          DISABLE ROW LEVEL SECURITY;
ALTER TABLE collaborators     DISABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions     DISABLE ROW LEVEL SECURITY;

DROP FUNCTION IF EXISTS app_can_reach_subscription(uuid);
DROP FUNCTION IF EXISTS app_role();
DROP FUNCTION IF EXISTS app_user_id();
"""


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql=FORWARD, reverse_sql=REVERSE, hints={"postgres_only": True}
        ),
    ]
