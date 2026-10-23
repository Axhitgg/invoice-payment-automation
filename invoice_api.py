from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import os
import re
import uuid

import psycopg
from flask import Flask, jsonify, request

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "dbname=invoice_db")
INVOICE_API_KEY = os.environ.get("INVOICE_API_KEY", "invoice-demo-key-2026")
MAX_REMINDER_ATTEMPTS = 3
ALLOWED_INVOICE_STATUSES = {"unpaid", "paid", "cancelled"}
ALLOWED_FAILURE_CODE = re.compile(r"^[A-Z0-9_]{1,64}$")


def is_authorized():
    return request.headers.get("X-API-Key") == INVOICE_API_KEY


def unauthorized_response():
    return jsonify({"received": False, "error": "Unauthorized"}), 401


def parse_boolean(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise ValueError("Expected a boolean")


def serialize_invoice(row, as_of=None):
    as_of = as_of or date.today()
    (
        invoice_id,
        customer_name,
        customer_email,
        invoice_number,
        amount,
        currency,
        issue_date,
        due_date,
        status,
    ) = row
    reminder_kind = "overdue" if due_date < as_of else "due_soon"
    return {
        "invoice_id": invoice_id,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "invoice_number": invoice_number,
        "amount": str(amount),
        "currency": currency,
        "issue_date": issue_date.isoformat(),
        "due_date": due_date.isoformat(),
        "status": status,
        "reminder_kind": reminder_kind,
        "recommended_action": (
            "Send overdue reminder and alert the finance team"
            if reminder_kind == "overdue"
            else "Send payment reminder"
        ),
    }


def due_invoice_rows(cursor, as_of, lock=False):
    lock_clause = " FOR UPDATE SKIP LOCKED" if lock else ""
    cursor.execute(
        f"""
        SELECT
            invoice_id,
            customer_name,
            customer_email,
            invoice_number,
            amount,
            currency,
            issue_date,
            due_date,
            status
        FROM invoices
        WHERE status = 'unpaid'
          AND due_date <= %s
        ORDER BY due_date, invoice_id
        {lock_clause}
        """,
        (as_of + timedelta(days=3),),
    )
    return cursor.fetchall()


def save_invoice(invoice):
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO invoices (
                    invoice_id,
                    customer_name,
                    customer_email,
                    invoice_number,
                    amount,
                    currency,
                    issue_date,
                    due_date,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                (
                    invoice["invoice_id"],
                    invoice["customer_name"],
                    invoice["customer_email"],
                    invoice["invoice_number"],
                    invoice["amount"],
                    invoice["currency"],
                    invoice["issue_date"],
                    invoice["due_date"],
                    invoice["status"],
                ),
            )
            row = cursor.fetchone()
            connection.commit()
            return row[0] if row else None


def get_invoice_action(status, due_date):
    if status != "unpaid":
        return "No action required"

    days_until_due = (due_date - date.today()).days
    if days_until_due < 0:
        return "Send overdue reminder and alert the finance team"
    if days_until_due <= 3:
        return "Send payment reminder"
    return "No reminder needed yet"


@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.get("/ready")
def ready():
    try:
        with psycopg.connect(DATABASE_URL) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
    except psycopg.Error:
        return jsonify({"status": "not_ready", "database": "unavailable"}), 503
    return jsonify({"status": "ready", "database": "ok"}), 200


@app.post("/invoice")
def create_invoice():
    if not is_authorized():
        return unauthorized_response()

    data = request.get_json(silent=True) or {}
    invoice_id = data.get("invoice_id") or str(uuid.uuid4())
    customer_name = data.get("customer_name", "").strip()
    customer_email = data.get("customer_email", "").strip().lower()
    invoice_number = data.get("invoice_number", "").strip()
    currency = data.get("currency", "INR").strip().upper()
    status = data.get("status", "unpaid").strip().lower()

    try:
        amount = Decimal(str(data.get("amount", "")))
        issue_date = datetime.strptime(data.get("issue_date", ""), "%Y-%m-%d").date()
        due_date = datetime.strptime(data.get("due_date", ""), "%Y-%m-%d").date()
    except (InvalidOperation, TypeError, ValueError):
        return jsonify({
            "received": False,
            "status": "invalid",
            "error": "Amount and dates must use valid formats",
        }), 400

    if not customer_name or not customer_email or not invoice_number:
        return jsonify({
            "received": False,
            "status": "invalid",
            "error": "Customer name, email, and invoice number are required",
        }), 400
    if amount <= 0:
        return jsonify({
            "received": False,
            "status": "invalid",
            "error": "Amount must be greater than zero",
        }), 400
    if due_date < issue_date:
        return jsonify({
            "received": False,
            "status": "invalid",
            "error": "Due date cannot be before issue date",
        }), 400
    if status not in ALLOWED_INVOICE_STATUSES:
        return jsonify({
            "received": False,
            "status": "invalid",
            "error": "Status must be unpaid, paid, or cancelled",
        }), 400

    invoice = {
        "invoice_id": invoice_id,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "invoice_number": invoice_number,
        "amount": str(amount),
        "currency": currency,
        "issue_date": issue_date.isoformat(),
        "due_date": due_date.isoformat(),
        "status": status,
        "recommended_action": get_invoice_action(status, due_date),
    }

    database_id = save_invoice(invoice)
    if database_id is None:
        return jsonify({
            "received": False,
            "duplicate": True,
            "invoice_id": invoice_id,
            "message": "This invoice ID or invoice number was already processed",
        }), 409

    return jsonify({
        "received": True,
        "saved": True,
        "database_id": database_id,
        "invoice": invoice,
    }), 201


@app.patch("/invoices/<invoice_id>/status")
def update_invoice_status(invoice_id):
    if not is_authorized():
        return unauthorized_response()

    data = request.get_json(silent=True) or {}
    new_status = str(data.get("status", "")).strip().lower()
    if new_status not in ALLOWED_INVOICE_STATUSES:
        return jsonify({"updated": False, "error": "Invalid invoice status"}), 400

    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT status FROM invoices WHERE invoice_id = %s FOR UPDATE",
                (invoice_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return jsonify({"updated": False, "error": "Invoice not found"}), 404

            old_status = row[0]
            if old_status in {"paid", "cancelled"} and new_status != old_status:
                return jsonify({
                    "updated": False,
                    "error": f"Cannot change a {old_status} invoice",
                }), 409

            cursor.execute(
                """
                UPDATE invoices
                SET status = %s,
                    paid_at = CASE WHEN %s = 'paid' THEN COALESCE(paid_at, NOW()) ELSE paid_at END,
                    updated_at = NOW()
                WHERE invoice_id = %s
                """,
                (new_status, new_status, invoice_id),
            )
            skipped = 0
            if new_status in {"paid", "cancelled"}:
                cursor.execute(
                    """
                    UPDATE reminder_events
                    SET status = 'skipped',
                        failure_code = %s,
                        updated_at = NOW()
                    WHERE invoice_id = %s
                      AND status = 'queued'
                    """,
                    (f"INVOICE_{new_status.upper()}", invoice_id),
                )
                skipped = cursor.rowcount
        connection.commit()

    return jsonify({
        "updated": True,
        "invoice_id": invoice_id,
        "previous_status": old_status,
        "status": new_status,
        "queued_reminders_suppressed": skipped,
    }), 200


@app.get("/reminders")
def check_reminders():
    if not is_authorized():
        return unauthorized_response()

    as_of = date.today()
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            rows = due_invoice_rows(cursor, as_of)
    reminders = [serialize_invoice(row, as_of) for row in rows]
    return jsonify({
        "received": True,
        "dry_run": True,
        "as_of": as_of.isoformat(),
        "reminder_count": len(reminders),
        "reminders": reminders,
    }), 200


@app.post("/reminder-runs")
def create_reminder_run():
    if not is_authorized():
        return unauthorized_response()

    data = request.get_json(silent=True) or {}
    try:
        dry_run = parse_boolean(data.get("dry_run"), default=True)
    except ValueError as error:
        return jsonify({"received": False, "error": str(error)}), 400

    as_of = date.today()
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            rows = due_invoice_rows(cursor, as_of, lock=not dry_run)
            reminders = [serialize_invoice(row, as_of) for row in rows]
            if dry_run:
                return jsonify({
                    "received": True,
                    "dry_run": True,
                    "as_of": as_of.isoformat(),
                    "candidate_count": len(reminders),
                    "queued_count": 0,
                    "reminders": reminders,
                }), 200

            queued = []
            already_recorded = 0
            for reminder in reminders:
                reminder_id = str(uuid.uuid4())
                cursor.execute(
                    """
                    INSERT INTO reminder_events (
                        reminder_id,
                        invoice_id,
                        reminder_kind,
                        status
                    )
                    VALUES (%s, %s, %s, 'queued')
                    ON CONFLICT (invoice_id, reminder_kind) DO NOTHING
                    RETURNING reminder_id
                    """,
                    (
                        reminder_id,
                        reminder["invoice_id"],
                        reminder["reminder_kind"],
                    ),
                )
                inserted = cursor.fetchone()
                if inserted is None:
                    already_recorded += 1
                    continue
                queued.append({**reminder, "reminder_id": inserted[0], "delivery_status": "queued"})
        connection.commit()

    return jsonify({
        "received": True,
        "dry_run": False,
        "as_of": as_of.isoformat(),
        "candidate_count": len(reminders),
        "queued_count": len(queued),
        "already_recorded_count": already_recorded,
        "reminders": queued,
    }), 200


@app.patch("/reminder-events/<reminder_id>")
def record_reminder_outcome(reminder_id):
    if not is_authorized():
        return unauthorized_response()

    data = request.get_json(silent=True) or {}
    outcome = str(data.get("status", "")).strip().lower()
    failure_code = str(data.get("failure_code", "")).strip().upper()
    if outcome not in {"sent", "failed"}:
        return jsonify({"updated": False, "error": "Status must be sent or failed"}), 400
    if outcome == "failed" and not ALLOWED_FAILURE_CODE.fullmatch(failure_code):
        return jsonify({
            "updated": False,
            "error": "A short uppercase failure_code is required",
        }), 400

    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE reminder_events AS events
                SET status = %s,
                    attempt_count = attempt_count + 1,
                    failure_code = CASE WHEN %s = 'failed' THEN %s ELSE NULL END,
                    sent_at = CASE WHEN %s = 'sent' THEN NOW() ELSE sent_at END,
                    updated_at = NOW()
                FROM invoices
                WHERE events.reminder_id = %s
                  AND events.invoice_id = invoices.invoice_id
                  AND events.status = 'queued'
                  AND invoices.status = 'unpaid'
                RETURNING events.invoice_id, events.status, events.attempt_count
                """,
                (outcome, outcome, failure_code or None, outcome, reminder_id),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    "SELECT status FROM reminder_events WHERE reminder_id = %s",
                    (reminder_id,),
                )
                existing = cursor.fetchone()
                if existing is None:
                    return jsonify({"updated": False, "error": "Reminder event not found"}), 404
                return jsonify({
                    "updated": False,
                    "error": f"Reminder is already {existing[0]} or its invoice is no longer unpaid",
                }), 409
        connection.commit()

    return jsonify({
        "updated": True,
        "reminder_id": reminder_id,
        "invoice_id": row[0],
        "status": row[1],
        "attempt_count": row[2],
    }), 200


@app.post("/reminder-events/<reminder_id>/retry")
def retry_reminder(reminder_id):
    if not is_authorized():
        return unauthorized_response()

    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE reminder_events AS events
                SET status = 'queued',
                    failure_code = NULL,
                    updated_at = NOW()
                FROM invoices
                WHERE events.reminder_id = %s
                  AND events.invoice_id = invoices.invoice_id
                  AND events.status = 'failed'
                  AND events.attempt_count < %s
                  AND invoices.status = 'unpaid'
                RETURNING events.invoice_id, events.attempt_count
                """,
                (reminder_id, MAX_REMINDER_ATTEMPTS),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    """
                    SELECT events.status, events.attempt_count, invoices.status
                    FROM reminder_events AS events
                    JOIN invoices ON invoices.invoice_id = events.invoice_id
                    WHERE events.reminder_id = %s
                    """,
                    (reminder_id,),
                )
                existing = cursor.fetchone()
                if existing is None:
                    return jsonify({"queued": False, "error": "Reminder event not found"}), 404
                return jsonify({
                    "queued": False,
                    "error": "Reminder is not retryable",
                    "reminder_status": existing[0],
                    "attempt_count": existing[1],
                    "invoice_status": existing[2],
                }), 409
        connection.commit()

    return jsonify({
        "queued": True,
        "reminder_id": reminder_id,
        "invoice_id": row[0],
        "attempt_count": row[1],
    }), 200


@app.get("/reminder-events/summary")
def reminder_summary():
    if not is_authorized():
        return unauthorized_response()

    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT status, COUNT(*)
                FROM reminder_events
                GROUP BY status
                ORDER BY status
                """
            )
            counts = {status: count for status, count in cursor.fetchall()}
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM reminder_events AS events
                JOIN invoices ON invoices.invoice_id = events.invoice_id
                WHERE events.status = 'failed'
                  AND events.attempt_count < %s
                  AND invoices.status = 'unpaid'
                """,
                (MAX_REMINDER_ATTEMPTS,),
            )
            retryable = cursor.fetchone()[0]

    return jsonify({
        "received": True,
        "counts": counts,
        "retryable_failed_count": retryable,
        "max_attempts": MAX_REMINDER_ATTEMPTS,
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5080, debug=True)
