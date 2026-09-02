"""Immutability and archive-guard triggers.

RLS controls which rows a session may touch. It cannot express "this column may
not change from its previous value", because a policy has no OLD row. Triggers
do. Every OLD-vs-NEW rule in the system lives here.

A trigger firing is a 500 by default, which is not an acceptable API response.
The service layer checks the same conditions first and returns a clean 409;
these are the net beneath it. src.billing.errors maps the messages below back
to the right status and logs the miss, because a trigger firing means a
service-layer bug.
"""

from django.db import migrations

FORWARD = r"""
-- Paid and Void invoices are frozen entirely (I-6, ruling A-03).
-- Issued invoices freeze period and amount but NOT due_date, because Goal 3
-- allows changing the due date "until it is Paid".
CREATE OR REPLACE FUNCTION billing_guard_invoice_update() RETURNS trigger AS $$
BEGIN
    IF OLD.status IN ('paid','void') THEN
        IF ROW(NEW.*) IS DISTINCT FROM ROW(OLD.*) THEN
            RAISE EXCEPTION 'invoice % is % and immutable', OLD.id, OLD.status
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    IF OLD.status = 'issued' AND NEW.status = 'issued' THEN
        IF NEW.amount       IS DISTINCT FROM OLD.amount
        OR NEW.period_start IS DISTINCT FROM OLD.period_start
        OR NEW.period_end   IS DISTINCT FROM OLD.period_end THEN
            RAISE EXCEPTION 'issued invoice % has a locked period and amount', OLD.id
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_invoice_guard BEFORE UPDATE ON invoices
    FOR EACH ROW EXECUTE FUNCTION billing_guard_invoice_update();


-- Append-only tables (I-8, I-9, ruling A-18). Blocks billing admins and the
-- table owner alike, which is exactly what Goal 9 asks for.
CREATE OR REPLACE FUNCTION billing_block_write() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% rows are append-only and cannot be %',
        TG_TABLE_NAME, lower(TG_OP) USING ERRCODE = 'check_violation';
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_events_append_only BEFORE UPDATE OR DELETE ON invoice_events
    FOR EACH ROW EXECUTE FUNCTION billing_block_write();

CREATE TRIGGER trg_credit_notes_append_only BEFORE UPDATE OR DELETE ON credit_notes
    FOR EACH ROW EXECUTE FUNCTION billing_block_write();


-- Only a billing admin may archive/restore a subscription or reassign its
-- owner. This is the rule the original RLS attempted with
-- `archived_at IS NOT DISTINCT FROM archived_at`, which compared the column to
-- itself and enforced nothing (defect D-04).
CREATE OR REPLACE FUNCTION billing_guard_subscription_update() RETURNS trigger AS $$
BEGIN
    IF NEW.archived_at IS DISTINCT FROM OLD.archived_at
       AND coalesce(current_setting('app.role', true), '') <> 'billing_admin' THEN
        RAISE EXCEPTION 'only a billing admin can archive or restore a subscription'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF NEW.owner_id IS DISTINCT FROM OLD.owner_id
       AND coalesce(current_setting('app.role', true), '') <> 'billing_admin' THEN
        RAISE EXCEPTION 'only a billing admin can reassign a subscription'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sub_guard BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION billing_guard_subscription_update();
"""

REVERSE = r"""
DROP TRIGGER IF EXISTS trg_sub_guard ON subscriptions;
DROP TRIGGER IF EXISTS trg_credit_notes_append_only ON credit_notes;
DROP TRIGGER IF EXISTS trg_events_append_only ON invoice_events;
DROP TRIGGER IF EXISTS trg_invoice_guard ON invoices;
DROP FUNCTION IF EXISTS billing_guard_subscription_update();
DROP FUNCTION IF EXISTS billing_block_write();
DROP FUNCTION IF EXISTS billing_guard_invoice_update();
"""


class Migration(migrations.Migration):
    dependencies = [("billing", "0002_rls")]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]
