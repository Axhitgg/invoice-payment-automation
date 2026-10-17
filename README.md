# Invoice Payment Automation

A rule-based invoice and reminder prototype using Python, Flask, PostgreSQL, n8n and Gmail. No LLM is required for the invoice logic.

## Business problem

Teams tracking unpaid invoices manually can overlook due dates or send a reminder after payment has already been recorded. This project gives a scheduled workflow a structured list of unpaid invoices that need attention.

## Example

A small agency submits an unpaid invoice. The API validates the amount and dates and stores it. On a daily schedule, n8n calls the reminder endpoint, splits the results and sends a customer reminder. An overdue record can also trigger a finance-team alert. Invoices recorded as paid are excluded from the reminder query.

```text
Invoice / n8n webhook -> Flask validation -> Duplicate-ID check -> PostgreSQL
Scheduled n8n trigger -> GET /reminders -> Due-date routing -> Gmail
```

## Implemented rules

| Invoice state | Recommended action |
| --- | --- |
| Paid | No reminder |
| Unpaid, due in 0-3 days | Payment reminder |
| Unpaid and overdue | Overdue reminder and finance alert |
| Due later | No reminder yet |

The API validates positive amounts and ISO dates, rejects due dates earlier than issue dates, normalises customer email and currency, checks invoice IDs and persists records. n8n/Gmail delivery is a separate configured workflow; an importable n8n export is not included in this repository.

## Run locally

Create an untracked `.env` in the cloned repository:

```dotenv
INVOICE_API_KEY=replace-with-a-unique-local-secret
POSTGRES_PASSWORD=replace-with-a-url-safe-local-password
```

Then start the API and PostgreSQL with Docker Compose:

```sh
docker compose up --build -d
curl http://127.0.0.1:5080/health
```

Compose supplies DATABASE_URL. `init.sql` runs when creating a fresh database volume, not as a migration on every restart. Stop without removing data using `docker compose down`. Override demo defaults with your own secrets.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /health | Process health |
| POST | /invoice | Validate and save an invoice |
| GET | /reminders | Return unpaid invoices due within three days or already overdue |

The invoice and reminder endpoints require `X-API-Key` matching INVOICE_API_KEY. Synthetic invoice body:

```json
{
  "invoice_id": "demo-invoice-001",
  "customer_name": "Demo Customer",
  "customer_email": "demo@example.com",
  "invoice_number": "DEMO-001",
  "amount": 25000,
  "currency": "INR",
  "issue_date": "2026-10-18",
  "due_date": "2026-10-21",
  "status": "unpaid"
}
```

Adjust sample dates relative to the day you run the demo. Reminder decisions use the server date. `/reminders` returns `reminder_count` and `reminders`; it does not itself send email or mark a reminder as sent. Missing/invalid fields and duplicate IDs currently return HTTP 200 with `received: false`, so inspect the body. Supply a stable invoice_id for repeat-submission detection.

## Tests

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt pytest
INVOICE_API_KEY=invoice-demo-key-2026 python -m pytest -q test_invoice_api.py
```

The four tests cover missing API key, negative amount, duplicate ID and health. They are not tests of Gmail delivery or payment collection. [Inspect CI runs](https://github.com/Axhitgg/invoice-payment-automation/actions). No recovery-rate improvement, money collected or percentage time saving has been measured.

## Limits and safe use

This is a portfolio prototype, not an accounting or payment-processing system. It does not collect money, reconcile bank transactions or expose a payment-status update endpoint. Paid status must be maintained through a separate reviewed process. Repeated reminder queries can return the same invoices; add a delivery ledger, deduplication and retry policy before real email campaigns. Date logic uses the server timezone. Authentication uses a shared API key, and health does not check the database. Use fictional invoices and keep credentials outside Git.

## Author

[Akshit Singh](https://www.linkedin.com/in/akshit-singh-outlook/) - AI automation portfolio project.
