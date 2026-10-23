CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    invoice_id TEXT UNIQUE NOT NULL,
    customer_name TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    invoice_number TEXT UNIQUE NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'INR',
    issue_date DATE NOT NULL,
    due_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'unpaid',
    reminder_count INTEGER NOT NULL DEFAULT 0,
    last_reminder_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT invoices_status_check CHECK (status IN ('unpaid', 'paid', 'cancelled'))
);

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
