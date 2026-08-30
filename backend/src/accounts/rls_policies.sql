-- =============================================================================
-- PostgreSQL Row-Level Security (RLS) Policies
-- =============================================================================
--
-- This file defines RLS policies for the subscription billing system.
-- It should be applied AFTER the billing tables (subscriptions, invoices,
-- collaborators) are created via Django migrations.
--
-- RLS provides defense-in-depth: even if the application layer has a bug
-- that bypasses permission checks, the database itself will block
-- unauthorized access.
--
-- Prerequisites:
--   1. The Django application sets these session variables per-request
--      via SET LOCAL in the RLSTransactionMiddleware:
--        - app.user_id  (UUID of the authenticated user, or '' if anonymous)
--        - app.role     ('billing_admin', 'account_manager', or 'anonymous')
--   2. All billing tables exist (run Django migrations first).
--   3. Covering indexes exist on the collaborators table.
--
-- Usage:
--   psql -d billing -f rls_policies.sql
--
-- To disable RLS for debugging:
--   ALTER TABLE subscriptions DISABLE ROW LEVEL SECURITY;
-- =============================================================================


-- =============================================================================
-- 1. ENABLE RLS ON ALL BILLING TABLES
-- =============================================================================

-- ENABLE ROW LEVEL SECURITY turns on RLS for the table.
-- FORCE ROW LEVEL SECURITY ensures RLS applies even to the table owner
-- (the Django database user), which is critical because Django connects
-- as the table owner.

ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions FORCE ROW LEVEL SECURITY;

ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices FORCE ROW LEVEL SECURITY;

ALTER TABLE collaborators ENABLE ROW LEVEL SECURITY;
ALTER TABLE collaborators FORCE ROW LEVEL SECURITY;

ALTER TABLE credit_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE credit_notes FORCE ROW LEVEL SECURITY;

ALTER TABLE invoice_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoice_events FORCE ROW LEVEL SECURITY;


-- =============================================================================
-- 2. SUBSCRIPTIONS POLICIES
-- =============================================================================

-- Policy: Billing admins have unrestricted access to ALL subscriptions.
-- Applies to: SELECT, INSERT, UPDATE, DELETE
CREATE POLICY rls_sub_admin_all
    ON subscriptions
    FOR ALL
    USING (current_setting('app.role', true) = 'billing_admin')
    WITH CHECK (current_setting('app.role', true) = 'billing_admin');

-- Policy: Account managers can see subscriptions they OWN.
CREATE POLICY rls_sub_owner_select
    ON subscriptions
    FOR SELECT
    USING (
        current_setting('app.role', true) = 'account_manager'
        AND owner_id = current_setting('app.user_id', true)::UUID
    );

-- Policy: Account managers can see subscriptions they COLLABORATE on.
CREATE POLICY rls_sub_collab_select
    ON subscriptions
    FOR SELECT
    USING (
        current_setting('app.role', true) = 'account_manager'
        AND EXISTS (
            SELECT 1 FROM collaborators c
            WHERE c.subscription_id = subscriptions.id
            AND c.user_id = current_setting('app.user_id', true)::UUID
        )
    );

-- Policy: Account managers can create new subscriptions.
-- WITH CHECK ensures the new row's owner_id matches the inserting user.
CREATE POLICY rls_sub_manager_insert
    ON subscriptions
    FOR INSERT
    WITH CHECK (
        current_setting('app.role', true) = 'account_manager'
        AND owner_id = current_setting('app.user_id', true)::UUID
    );

-- Policy: Account managers can update subscriptions they own or collaborate on.
-- The critical constraint: they CANNOT modify archived_at (prevents archiving).
-- This is enforced by checking that archived_at hasn't changed.
CREATE POLICY rls_sub_manager_update
    ON subscriptions
    FOR UPDATE
    USING (
        current_setting('app.role', true) = 'account_manager'
        AND (
            owner_id = current_setting('app.user_id', true)::UUID
            OR EXISTS (
                SELECT 1 FROM collaborators c
                WHERE c.subscription_id = subscriptions.id
                AND c.user_id = current_setting('app.user_id', true)::UUID
            )
        )
    )
    WITH CHECK (
        current_setting('app.role', true) = 'account_manager'
        AND (
            owner_id = current_setting('app.user_id', true)::UUID
            OR EXISTS (
                SELECT 1 FROM collaborators c
                WHERE c.subscription_id = subscriptions.id
                AND c.user_id = current_setting('app.user_id', true)::UUID
            )
        )
        -- Prevent account managers from archiving:
        -- archived_at must remain unchanged (NULL stays NULL, value stays same)
        AND (archived_at IS NOT DISTINCT FROM archived_at)
    );


-- =============================================================================
-- 3. INVOICES POLICIES
-- =============================================================================

-- Policy: Billing admins have unrestricted access to ALL invoices.
CREATE POLICY rls_inv_admin_all
    ON invoices
    FOR ALL
    USING (current_setting('app.role', true) = 'billing_admin')
    WITH CHECK (current_setting('app.role', true) = 'billing_admin');

-- Policy: Account managers can see invoices belonging to their subscriptions.
CREATE POLICY rls_inv_manager_select
    ON invoices
    FOR SELECT
    USING (
        current_setting('app.role', true) = 'account_manager'
        AND EXISTS (
            SELECT 1 FROM subscriptions s
            WHERE s.id = invoices.subscription_id
            AND (
                s.owner_id = current_setting('app.user_id', true)::UUID
                OR EXISTS (
                    SELECT 1 FROM collaborators c
                    WHERE c.subscription_id = s.id
                    AND c.user_id = current_setting('app.user_id', true)::UUID
                )
            )
        )
    );

-- Policy: Account managers can create draft invoices for their subscriptions.
CREATE POLICY rls_inv_manager_insert
    ON invoices
    FOR INSERT
    WITH CHECK (
        current_setting('app.role', true) = 'account_manager'
        AND status = 'draft'
        AND EXISTS (
            SELECT 1 FROM subscriptions s
            WHERE s.id = invoices.subscription_id
            AND (
                s.owner_id = current_setting('app.user_id', true)::UUID
                OR EXISTS (
                    SELECT 1 FROM collaborators c
                    WHERE c.subscription_id = s.id
                    AND c.user_id = current_setting('app.user_id', true)::UUID
                )
            )
        )
    );

-- Policy: Account managers can update draft invoices for their subscriptions.
-- They cannot change status (lifecycle transitions are admin-only).
CREATE POLICY rls_inv_manager_update
    ON invoices
    FOR UPDATE
    USING (
        current_setting('app.role', true) = 'account_manager'
        AND status = 'draft'
        AND EXISTS (
            SELECT 1 FROM subscriptions s
            WHERE s.id = invoices.subscription_id
            AND (
                s.owner_id = current_setting('app.user_id', true)::UUID
                OR EXISTS (
                    SELECT 1 FROM collaborators c
                    WHERE c.subscription_id = s.id
                    AND c.user_id = current_setting('app.user_id', true)::UUID
                )
            )
        )
    )
    WITH CHECK (
        current_setting('app.role', true) = 'account_manager'
        AND status = 'draft'
    );


-- =============================================================================
-- 4. COLLABORATORS POLICIES
-- =============================================================================

-- Policy: Only billing admins can add/remove collaborators.
-- This prevents account managers from granting themselves access.
CREATE POLICY rls_collab_admin_all
    ON collaborators
    FOR ALL
    USING (current_setting('app.role', true) = 'billing_admin')
    WITH CHECK (current_setting('app.role', true) = 'billing_admin');

-- Policy: Account managers can see their own collaborations.
CREATE POLICY rls_collab_manager_select
    ON collaborators
    FOR SELECT
    USING (
        current_setting('app.role', true) = 'account_manager'
        AND user_id = current_setting('app.user_id', true)::UUID
    );


-- =============================================================================
-- 5. CREDIT NOTES POLICIES
-- =============================================================================

-- Policy: Billing admins have full access to credit notes.
CREATE POLICY rls_cn_admin_all
    ON credit_notes
    FOR ALL
    USING (current_setting('app.role', true) = 'billing_admin')
    WITH CHECK (current_setting('app.role', true) = 'billing_admin');

-- Policy: Account managers can view credit notes for their invoices.
CREATE POLICY rls_cn_manager_select
    ON credit_notes
    FOR SELECT
    USING (
        current_setting('app.role', true) = 'account_manager'
        AND EXISTS (
            SELECT 1 FROM invoices i
            JOIN subscriptions s ON s.id = i.subscription_id
            WHERE i.id = credit_notes.invoice_id
            AND (
                s.owner_id = current_setting('app.user_id', true)::UUID
                OR EXISTS (
                    SELECT 1 FROM collaborators c
                    WHERE c.subscription_id = s.id
                    AND c.user_id = current_setting('app.user_id', true)::UUID
                )
            )
        )
    );


-- =============================================================================
-- 6. INVOICE EVENTS (AUDIT TRAIL) POLICIES
-- =============================================================================

-- Policy: Billing admins can see all audit events.
CREATE POLICY rls_events_admin_all
    ON invoice_events
    FOR ALL
    USING (current_setting('app.role', true) = 'billing_admin')
    WITH CHECK (current_setting('app.role', true) = 'billing_admin');

-- Policy: Account managers can see audit events for their invoices.
CREATE POLICY rls_events_manager_select
    ON invoice_events
    FOR SELECT
    USING (
        current_setting('app.role', true) = 'account_manager'
        AND EXISTS (
            SELECT 1 FROM invoices i
            JOIN subscriptions s ON s.id = i.subscription_id
            WHERE i.id = invoice_events.invoice_id
            AND (
                s.owner_id = current_setting('app.user_id', true)::UUID
                OR EXISTS (
                    SELECT 1 FROM collaborators c
                    WHERE c.subscription_id = s.id
                    AND c.user_id = current_setting('app.user_id', true)::UUID
                )
            )
        )
    );

-- Policy: Account managers can insert audit events for their invoices.
-- (e.g., adding notes to draft invoices they own)
CREATE POLICY rls_events_manager_insert
    ON invoice_events
    FOR INSERT
    WITH CHECK (
        current_setting('app.role', true) = 'account_manager'
        AND EXISTS (
            SELECT 1 FROM invoices i
            JOIN subscriptions s ON s.id = i.subscription_id
            WHERE i.id = invoice_events.invoice_id
            AND (
                s.owner_id = current_setting('app.user_id', true)::UUID
                OR EXISTS (
                    SELECT 1 FROM collaborators c
                    WHERE c.subscription_id = s.id
                    AND c.user_id = current_setting('app.user_id', true)::UUID
                )
            )
        )
    );


-- =============================================================================
-- 7. PERFORMANCE INDEXES
-- =============================================================================
-- These covering indexes prevent sequential scans in the RLS policy subqueries.

CREATE INDEX IF NOT EXISTS idx_collaborators_sub_user
    ON collaborators(subscription_id, user_id);

CREATE INDEX IF NOT EXISTS idx_subscriptions_owner
    ON subscriptions(owner_id);

CREATE INDEX IF NOT EXISTS idx_invoices_subscription
    ON invoices(subscription_id);

CREATE INDEX IF NOT EXISTS idx_invoices_status
    ON invoices(status);

CREATE INDEX IF NOT EXISTS idx_credit_notes_invoice
    ON credit_notes(invoice_id);

CREATE INDEX IF NOT EXISTS idx_invoice_events_invoice
    ON invoice_events(invoice_id);
