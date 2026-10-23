# Synthetic demo scenarios

Use fictional invoices and test recipients only.

## 1. Preview before sending

- Create one invoice due tomorrow and one due later than three days.
- Run `POST /reminder-runs` with `dry_run: true`.
- Expect one candidate, zero queued events and no ledger write.

## 2. Concurrent schedules

- Create one invoice due tomorrow.
- Start two non-dry reminder runs together.
- Expect only one queued reminder event for the `due_soon` stage.
- Run the schedule again and show that it cannot claim the same stage.

## 3. Payment arrives before delivery

- Claim a reminder but do not send it.
- Mark the invoice paid.
- Expect the queued event to become `skipped`.
- Attempt to record it as sent and show the `409` response.

## 4. Definite provider failure

- Claim an overdue reminder.
- Record `failed` with `EMAIL_PROVIDER_TIMEOUT` in a controlled test.
- Requeue it through the retry endpoint and then record `sent`.
- Show the retained attempt count and summary.

Do not describe a provider timeout as definitely unsent in a real system. The scenario demonstrates state handling, not proof against duplicate delivery.
