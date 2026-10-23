# n8n workflow export

`invoice-reminder-lifecycle.json` is a sanitised, inactive workflow with two entry paths:

- manual trigger → dry-run preview with no ledger write;
- daily schedule → claim reminder work → Gmail → record `sent` or bounded `failed` outcome.

## Import and configure safely

1. Import the JSON and keep it inactive.
2. Replace `https://YOUR-INVOICE-API.example.com` with the intended API base URL.
3. Replace every `REPLACE_AFTER_IMPORT` header by configuring an n8n Header Auth credential for `X-API-Key`; do not commit the real key.
4. Configure a separate Gmail OAuth credential on **Send Approved Reminder**.
5. Replace the fictional message only after the sender, test recipients, contact cadence, opt-out behavior and wording are approved.
6. Run **Manual Preview Trigger** first and inspect the candidate count.
7. Use only fictional invoices/test recipients while verifying the `sent` and `failed` outcome branches.
8. Confirm paid invoices are excluded and queued work becomes `skipped` before considering activation.

The backend, not the n8n canvas, owns invoice state, claim uniqueness, payment suppression and retry limits. A workflow error is recorded using a bounded code rather than customer/message text.

## Boundaries

The committed export has no credential object, OAuth token, API key, execution history or pinned invoice data. It is inactive and must not be activated against real contacts without a reviewed sending policy.

The failure branch records `EMAIL_PROVIDER_ERROR`. This shows a definite provider error, not proof that every timeout is safe to retry. If an acknowledgement is lost after the provider accepted a message, delivery can be ambiguous and a retry could duplicate email.

## Import verification

On 23 October 2026, the JSON was syntax-checked and clean-imported into an isolated n8n 2.44.5 user folder. A clean re-export confirmed one inactive workflow, eight nodes, zero credential-bearing nodes and no pinned data. No node was activated or executed, no Gmail message was sent and no API endpoint was contacted.
