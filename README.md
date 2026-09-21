# Invoice Processing and Payment Reminder Automation

An invoice workflow for validating invoices, tracking due dates, and sending payment reminders.

## Workflow

Invoice request → n8n Webhook → Python Flask API → PostgreSQL

Daily schedule → Reminder API → Split invoices → Due-date decision → Gmail reminder

## Features

- Invoice validation
- Email normalization
- API-key authentication
- Duplicate invoice protection
- Due-date tracking
- Paid-invoice safety rule
- Due-soon reminders
- Overdue finance escalation
- PostgreSQL persistence
- n8n Webhook intake
- n8n scheduled reminders
- Gmail notifications
- Docker Compose setup
- pytest tests

## Example invoice

```json
{
  "invoice_id": "inv-001",
  "customer_name": "Neha",
  "customer_email": "neha@example.com",
  "invoice_number": "INV-2026-001",
  "amount": 25000,
  "currency": "INR",
  "issue_date": "2026-09-18",
  "due_date": "2026-10-18",
  "status": "unpaid"
}

Reminder rules
- Paid invoice: no action
- Due within three days: send payment reminder
- Overdue invoice: send reminder and alert finance
- Duplicate invoice ID: reject safely
Technology
Python, Flask, PostgreSQL, n8n, Docker, Gunicorn, pytest, Gmail, Git, GitHub Actions.
Security
API keys and database passwords are stored in environment variables and must not be committed to GitHub.
