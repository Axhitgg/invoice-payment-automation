-- Apply once to an existing database created by the original init.sql.
-- Back up the database first. Fresh databases receive the same structure from init.sql.
BEGIN;

ALTER TABLE invoices
    ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'invoices_status_check'
    ) THEN
        ALTER TABLE invoices
            ADD CONSTRAINT invoices_status_check
            CHECK (status IN ('unpaid', 'paid', 'cancelled'));
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS reminder_events (
    id BIGSERIAL PRIMARY KEY,
    reminder_id TEXT UNIQUE NOT NULL,
    invoice_id TEXT NOT NULL REFERENCES invoices(invoice_id),
    reminder_kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    failure_code TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT reminder_kind_check CHECK (reminder_kind IN ('due_soon', 'overdue')),
    CONSTRAINT reminder_status_check CHECK (status IN ('queued', 'sent', 'failed', 'skipped')),
    CONSTRAINT reminder_attempt_count_check CHECK (attempt_count >= 0),
    CONSTRAINT one_reminder_per_stage UNIQUE (invoice_id, reminder_kind)
);

CREATE INDEX IF NOT EXISTS reminder_events_status_idx
    ON reminder_events (status, updated_at);

COMMIT;
