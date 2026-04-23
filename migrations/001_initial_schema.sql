-- Migration 001: Initial schema for Money Clarity
-- Run once against your Supabase project:
--   psql $DATABASE_URL -f migrations/001_initial_schema.sql
-- Or apply via Supabase Dashboard > SQL Editor

-- ─────────────────────────────────────────────────────────────────────────────
-- uploads: tracks every file uploaded (manual or via Gmail)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS uploads (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,          -- Supabase auth.uid()
    filename        TEXT NOT NULL,
    storage_path    TEXT NOT NULL,          -- path in Supabase Storage "statements" bucket
    source          TEXT NOT NULL DEFAULT 'manual', -- 'manual' | 'gmail'
    gmail_message_id TEXT,                  -- Gmail message ID (for deduplication)
    dedup_hash      TEXT,                   -- SHA-256 of message_id+filename
    status          TEXT NOT NULL DEFAULT 'uploaded', -- uploaded | parsed | parse_failed
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS uploads_user_id_idx ON uploads(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS uploads_dedup_hash_idx ON uploads(dedup_hash) WHERE dedup_hash IS NOT NULL;


-- ─────────────────────────────────────────────────────────────────────────────
-- statements: individual parsed transactions
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS statements (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL,
    upload_id   UUID REFERENCES uploads(id) ON DELETE CASCADE,
    date        DATE NOT NULL,
    description TEXT NOT NULL,
    debit       NUMERIC(14,2) NOT NULL DEFAULT 0,
    credit      NUMERIC(14,2) NOT NULL DEFAULT 0,
    category    TEXT NOT NULL DEFAULT 'Other',
    type        TEXT NOT NULL DEFAULT 'expense',  -- 'income' | 'expense'
    month       TEXT NOT NULL,                    -- 'YYYY-MM' for fast aggregation
    source      TEXT,                             -- original filename
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS statements_user_month_idx ON statements(user_id, month);
CREATE INDEX IF NOT EXISTS statements_user_id_idx ON statements(user_id);
CREATE INDEX IF NOT EXISTS statements_upload_id_idx ON statements(upload_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- monthly_summaries: pre-aggregated per-user per-month totals
-- Updated by trigger on statements INSERT/UPDATE/DELETE
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS monthly_summaries (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL,
    month       TEXT NOT NULL,             -- 'YYYY-MM'
    income      NUMERIC(14,2) NOT NULL DEFAULT 0,
    expense     NUMERIC(14,2) NOT NULL DEFAULT 0,
    net         NUMERIC(14,2) NOT NULL DEFAULT 0,
    categories  JSONB NOT NULL DEFAULT '{}',  -- {"Food & Dining": 8500.00, ...}
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(user_id, month)
);

CREATE INDEX IF NOT EXISTS monthly_summaries_user_id_idx ON monthly_summaries(user_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- gmail_accounts: encrypted Gmail OAuth tokens per user
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS gmail_accounts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL UNIQUE,   -- one Gmail account per user
    gmail_user_id       TEXT NOT NULL,           -- Google account ID or email
    access_token_enc    TEXT NOT NULL,           -- AES-GCM encrypted, format: kid:nonce:ct
    refresh_token_enc   TEXT NOT NULL DEFAULT '',
    scope               TEXT NOT NULL DEFAULT '',
    token_expiry        TIMESTAMPTZ,
    last_synced_at      TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS gmail_accounts_user_id_idx ON gmail_accounts(user_id);
