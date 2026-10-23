# Invoice Payment Automation

A rule-based invoice follow-up prototype using Python, Flask, PostgreSQL and n8n-compatible API steps. It tracks invoice state, safely claims reminder work, records delivery outcomes and suppresses queued reminders after payment. No LLM is required for the invoice logic.

## Business problem

Manual invoice follow-up has more risk than simply calculating a due date:

- two scheduled runs can select the same invoice;
- a payment can arrive after a reminder is queued;
- an email provider can fail and require a bounded retry;
- a team needs a record of what was queued, sent, failed or skipped.

This prototype separates **previewing reminder candidates** from **claiming delivery work**. PostgreSQL is the source of truth for invoice and reminder state.

```text
Invoice intake -> validation -> atomic PostgreSQL insert
Schedule -> dry-run preview -> claim once -> n8n/email provider
                                      |-> sent outcome
                                      |-> failed outcome -> bounded retry
Payment update -----------------------> suppress queued reminder
```

## Implemented lifecycle

| Situation | Result |
| --- | --- |
| Paid or cancelled invoice | Excluded from reminder selection |
| Unpaid, due in 0-3 days | One `due_soon` reminder can be claimed |
| Unpaid and overdue | One `overdue` reminder can be claimed |
| Same schedule runs twice | Database uniqueness prevents a second claim for that stage |
| Payment recorded while reminder is queued | Queued event is marked `skipped` |
| Provider reports failure | Event records a short failure code and can be requeued |
| Third failed attempt reached | Further retry is rejected |

Reminder claims use invoice row locks plus a unique `(invoice_id, reminder_kind)` database constraint. This protects concurrent runs without pretending an email was sent. The workflow must report `sent` or `failed` after the provider responds.

## Run locally

Create an untracked `.env`:

```dotenv
INVOICE_API_KEY=replace-with-a-unique-local-secret
POSTGRES_PASSWORD=replace-with-a-url-safe-local-password
```

Start a fresh API/database pair:

```sh
docker compose up --build -d
curl http://127.0.0.1:5080/health
curl http://127.0.0.1:5080/ready
```

`init.sql` is only applied when PostgreSQL creates a fresh volume. For an existing database created by the earlier project version, back it up and apply [`migrations/001_invoice_lifecycle.sql`](migrations/001_invoice_lifecycle.sql) once before using the new endpoints. Do not point the migration at a database you have not identified and backed up.

## API

All endpoints except `/health` and `/ready` require `X-API-Key` matching `INVOICE_API_KEY`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Process health |
| GET | `/ready` | Database connectivity |
| POST | `/invoice` | Validate and atomically save an invoice |
| PATCH | `/invoices/{invoice_id}/status` | Mark unpaid, paid or cancelled; suppress queued work for terminal states |
| GET | `/reminders` | Backward-compatible read-only preview |
| POST | `/reminder-runs` | Preview candidates or claim delivery work |
| PATCH | `/reminder-events/{reminder_id}` | Record a `sent` or `failed` delivery outcome |
| POST | `/reminder-events/{reminder_id}/retry` | Requeue a failed delivery below the attempt limit |
| GET | `/reminder-events/summary` | Count queued, sent, failed and skipped events |

### 1. Create a synthetic invoice

Use dates relative to the day you run the example:

```json
{
  "invoice_id": "demo-invoice-001",
  "customer_name": "Demo Customer",
  "customer_email": "demo@example.com",
  "invoice_number": "DEMO-001",
  "amount": 25000,
  "currency": "INR",
  "issue_date": "2026-10-18",
  "due_date": "2026-10-24",
  "status": "unpaid"
}
```

Successful creation returns HTTP `201`. Duplicate invoice IDs or invoice numbers return `409`; invalid amount/date/status input returns `400`.

### 2. Preview without writing

```http
POST /reminder-runs
X-API-Key: ...
Content-Type: application/json

{"dry_run": true}
```

The response lists candidates and always reports `queued_count: 0`. This is suitable for an operator preview or an n8n approval step.

### 3. Claim reminder work

Send `{"dry_run": false}` to the same endpoint. Newly claimed items include a `reminder_id` and `delivery_status: queued`. A repeated or concurrent run cannot claim the same invoice stage again.

### 4. Record the provider result

```json
{"status": "sent"}
```

or, without customer/message text:

```json
{"status": "failed", "failure_code": "EMAIL_PROVIDER_TIMEOUT"}
```

A failed event can be returned to `queued` through its retry endpoint until the three-attempt limit is reached.

### 5. Record payment

```json
{"status": "paid"}
```

The status endpoint marks the invoice paid and changes any still-queued event to `skipped` in the same transaction. Paid and cancelled invoices are terminal in this prototype and cannot be reopened.

## Tests

Fast tests:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt pytest
python -m pytest -q test_invoice_api.py
```

The isolated PostgreSQL runner creates its own synthetic-only local cluster with no TCP listener and never reads `DATABASE_URL`:

```sh
scripts/run_database_tests.sh
```

The current 12-test suite covers authentication, validation, atomic duplicate handling, dry-run behavior, concurrent schedule claims, repeated schedules, payment suppression, failed-send retry, terminal invoice states, summary reporting and the legacy-schema migration. GitHub Actions runs fast tests, PostgreSQL lifecycle tests and a Docker build. It does not send Gmail or collect a payment.

The sanitised workflow under [`workflows/`](workflows/) was clean-imported and re-exported with n8n 2.44.5. The imported copy remained inactive, contained eight nodes, zero credential-bearing nodes and no pinned data. Importability is not evidence of a live Gmail execution.

## Limits and safe use

This is a portfolio prototype, not an accounting, collections or payment-processing system.

- It does not reconcile bank transactions or verify that money arrived.
- It queues work; n8n/email-provider delivery remains a separate integration.
- If a worker disappears after claiming an event but before recording an outcome, the event can remain `queued`; a production system needs a lease/timeout and reconciliation job.
- Provider timeout may be ambiguous: retrying could duplicate a message if the provider accepted it but the acknowledgement was lost.
- One due-soon and one overdue reminder are allowed per invoice. A real cadence needs an approved contact policy and opt-out handling.
- Status authentication uses a shared API key rather than user roles.
- Date decisions use the server date.
- Use fictional invoices only. Keep credentials outside Git and store only bounded failure codes, not message bodies or personal data.

No recovery-rate improvement, money collected, user count or percentage time saving has been measured.

## Author

[Akshit Singh](https://www.linkedin.com/in/akshit-singh-outlook/) — AI automation portfolio project.
