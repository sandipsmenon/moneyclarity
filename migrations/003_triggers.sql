-- Migration 003: DB function + trigger to auto-update monthly_summaries
-- Fires after any INSERT, UPDATE, DELETE on statements table.
-- This ensures /summary always reflects latest data without a manual job.

CREATE OR REPLACE FUNCTION refresh_monthly_summary()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER  -- run as owner, bypass RLS for this internal aggregation
AS $$
DECLARE
    _user_id UUID;
    _month   TEXT;
    _income  NUMERIC(14,2);
    _expense NUMERIC(14,2);
    _cats    JSONB;
BEGIN
    -- Determine which (user_id, month) pair was affected
    IF TG_OP = 'DELETE' THEN
        _user_id := OLD.user_id;
        _month   := OLD.month;
    ELSE
        _user_id := NEW.user_id;
        _month   := NEW.month;
    END IF;

    -- Aggregate from scratch for this user+month (simple and correct)
    SELECT
        COALESCE(SUM(CASE WHEN type = 'income' THEN credit ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN type = 'expense' THEN debit ELSE 0 END), 0),
        COALESCE(
            jsonb_object_agg(category, cat_total) FILTER (WHERE type = 'expense'),
            '{}'::jsonb
        )
    INTO _income, _expense, _cats
    FROM (
        SELECT type, credit, debit, category,
               SUM(debit) OVER (PARTITION BY category) AS cat_total
        FROM statements
        WHERE user_id = _user_id
          AND month   = _month
          AND type    = 'expense'
        UNION ALL
        SELECT type, credit, debit, NULL AS category, 0 AS cat_total
        FROM statements
        WHERE user_id = _user_id
          AND month   = _month
          AND type    = 'income'
    ) agg;

    -- Recompute categories separately (simpler)
    SELECT COALESCE(
        jsonb_object_agg(category, total_debit),
        '{}'::jsonb
    )
    INTO _cats
    FROM (
        SELECT category, SUM(debit) AS total_debit
        FROM statements
        WHERE user_id = _user_id
          AND month   = _month
          AND type    = 'expense'
        GROUP BY category
    ) cat_agg;

    SELECT
        COALESCE(SUM(CASE WHEN type = 'income' THEN credit ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN type = 'expense' THEN debit ELSE 0 END), 0)
    INTO _income, _expense
    FROM statements
    WHERE user_id = _user_id AND month = _month;

    -- Upsert monthly_summaries
    INSERT INTO monthly_summaries (user_id, month, income, expense, net, categories, updated_at)
    VALUES (_user_id, _month, _income, _expense, _income - _expense, _cats, now())
    ON CONFLICT (user_id, month)
    DO UPDATE SET
        income     = EXCLUDED.income,
        expense    = EXCLUDED.expense,
        net        = EXCLUDED.net,
        categories = EXCLUDED.categories,
        updated_at = now();

    RETURN NULL;  -- AFTER trigger, return value ignored
END;
$$;


-- Drop and recreate trigger (idempotent)
DROP TRIGGER IF EXISTS trg_refresh_monthly_summary ON statements;

CREATE TRIGGER trg_refresh_monthly_summary
    AFTER INSERT OR UPDATE OR DELETE ON statements
    FOR EACH ROW
    EXECUTE FUNCTION refresh_monthly_summary();


-- ─────────────────────────────────────────────────────────────────────────────
-- Backfill trigger: recompute summaries for all existing statements
-- Run once after applying this migration if you already have data.
-- ─────────────────────────────────────────────────────────────────────────────
-- DO $$
-- DECLARE r RECORD;
-- BEGIN
--   FOR r IN SELECT DISTINCT user_id, month FROM statements LOOP
--     -- Simulate a no-op update to fire trigger
--     UPDATE statements SET date = date
--     WHERE user_id = r.user_id AND month = r.month AND id = (
--       SELECT id FROM statements WHERE user_id = r.user_id AND month = r.month LIMIT 1
--     );
--   END LOOP;
-- END;
-- $$;


-- ─────────────────────────────────────────────────────────────────────────────
-- Enable Supabase Realtime on these tables (run in Supabase Dashboard or via SQL)
-- This lets the Streamlit frontend subscribe to live changes.
-- ─────────────────────────────────────────────────────────────────────────────
-- ALTER PUBLICATION supabase_realtime ADD TABLE statements;
-- ALTER PUBLICATION supabase_realtime ADD TABLE monthly_summaries;
