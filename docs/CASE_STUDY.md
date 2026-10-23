# Case study: reliable invoice reminder lifecycle

## Problem

A due-date query alone does not make reminder automation reliable. Two schedules may run together, payment may arrive after work is selected, and a mail provider can fail between selection and delivery. Without a ledger, the team cannot distinguish queued, sent, failed and skipped reminders.

## Implemented approach

1. Validate and atomically store invoices in PostgreSQL.
2. Preview candidates without writing state.
3. Claim due-soon or overdue work using row locks and a unique database constraint.
4. Let n8n deliver through a separately configured provider.
5. Record a `sent` or `failed` outcome using the generated reminder ID.
6. Allow bounded requeue for definite failures.
7. When payment/cancellation is recorded, suppress still-queued reminders in the same transaction.

## Evidence

- Twelve tests pass against an isolated PostgreSQL 17 cluster.
- Two concurrent schedule runs create one reminder event for the same invoice stage.
- A repeated schedule cannot reclaim an existing stage.
- Payment changes queued work to `skipped`; the old worker cannot mark it sent.
- A definite provider failure can be requeued, then recorded sent with its attempt count retained.
- The legacy-schema migration is applied in a disposable schema during testing.

## Trade-offs and limits

The unique key allows one due-soon and one overdue reminder per invoice, intentionally preferring bounded contact over a configurable cadence. A real system needs an approved collections policy, leases for abandoned queued work, provider reconciliation for ambiguous outcomes, opt-outs, roles and bank/accounting reconciliation. The prototype does not collect money or claim measured recovery improvement.
