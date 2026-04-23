-- Migration 002: Row Level Security policies
-- Ensures each user can only access their own data.
-- auth.uid() resolves to the Supabase JWT sub claim.

-- ─────────────────────────────────────────────────────────────────────────────
-- Enable RLS on all user-data tables
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE uploads          ENABLE ROW LEVEL SECURITY;
ALTER TABLE statements       ENABLE ROW LEVEL SECURITY;
ALTER TABLE monthly_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE gmail_accounts   ENABLE ROW LEVEL SECURITY;


-- ─────────────────────────────────────────────────────────────────────────────
-- uploads policies
-- ─────────────────────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS uploads_select_own ON uploads;
DROP POLICY IF EXISTS uploads_insert_own ON uploads;
DROP POLICY IF EXISTS uploads_update_own ON uploads;
DROP POLICY IF EXISTS uploads_delete_own ON uploads;

CREATE POLICY uploads_select_own ON uploads
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY uploads_insert_own ON uploads
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY uploads_update_own ON uploads
    FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY uploads_delete_own ON uploads
    FOR DELETE USING (auth.uid() = user_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- statements policies
-- ─────────────────────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS statements_select_own ON statements;
DROP POLICY IF EXISTS statements_insert_own ON statements;
DROP POLICY IF EXISTS statements_update_own ON statements;
DROP POLICY IF EXISTS statements_delete_own ON statements;

CREATE POLICY statements_select_own ON statements
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY statements_insert_own ON statements
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY statements_update_own ON statements
    FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE POLICY statements_delete_own ON statements
    FOR DELETE USING (auth.uid() = user_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- monthly_summaries policies
-- ─────────────────────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS summaries_select_own ON monthly_summaries;
DROP POLICY IF EXISTS summaries_insert_own ON monthly_summaries;
DROP POLICY IF EXISTS summaries_update_own ON monthly_summaries;

CREATE POLICY summaries_select_own ON monthly_summaries
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY summaries_insert_own ON monthly_summaries
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY summaries_update_own ON monthly_summaries
    FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- gmail_accounts policies (service_role bypasses RLS — fine for server writes)
-- ─────────────────────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS gmail_accounts_select_own ON gmail_accounts;
DROP POLICY IF EXISTS gmail_accounts_insert_own ON gmail_accounts;
DROP POLICY IF EXISTS gmail_accounts_update_own ON gmail_accounts;

CREATE POLICY gmail_accounts_select_own ON gmail_accounts
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY gmail_accounts_insert_own ON gmail_accounts
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY gmail_accounts_update_own ON gmail_accounts
    FOR UPDATE USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- Minimal role grants (anon cannot see any user data, authenticated gets full CRUD via RLS)
-- ─────────────────────────────────────────────────────────────────────────────
GRANT USAGE ON SCHEMA public TO anon, authenticated;

-- anon: no access to user tables
REVOKE ALL ON uploads, statements, monthly_summaries, gmail_accounts FROM anon;

-- authenticated role: table access controlled by RLS policies above
GRANT SELECT, INSERT, UPDATE, DELETE ON uploads TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON statements TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON monthly_summaries TO authenticated;
GRANT SELECT ON gmail_accounts TO authenticated;  -- server writes via service_role


-- ─────────────────────────────────────────────────────────────────────────────
-- Verify RLS is enabled (informational — run after migration)
-- ─────────────────────────────────────────────────────────────────────────────
-- SELECT tablename, rowsecurity FROM pg_tables
-- WHERE schemaname = 'public'
-- AND tablename IN ('uploads', 'statements', 'monthly_summaries', 'gmail_accounts');
